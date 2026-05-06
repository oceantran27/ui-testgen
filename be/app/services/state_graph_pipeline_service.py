"""Orchestrate dedupe → UI extraction → user intents → state graph flows."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from typing import Any

from app.core.config import settings
from app.core.exceptions import AIProcessingError
from app.schemas.state_graph import StateGraphInputScreen, StateGraphOrganizeResponse
from app.services.image_dedup_service import dedupe_image_paths
from app.services.state_graph_flow_service import normalize_and_complete_flows, run_state_graph_flow_sync
from app.services.state_graph_screen_metadata import build_state_graph_screen_dict
from app.services.test_scenario_generator_service import generate_all_test_scenarios_async
from app.services.ui_extraction_payload import (
    filter_scoped_ui_extraction,
    user_intent_input_to_minified_json,
)
from app.services.ui_extraction_service import extract_ui_extraction_gemini_sync
from app.services.user_intent_service import generate_user_intents_openai_sync

logger = logging.getLogger(__name__)


def _write_json(path: str, data: Any) -> None:
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except OSError as exc:
        logger.warning("Could not write artifact %s: %s", path, exc)


class StateGraphPipelineService:
    async def run(
        self,
        *,
        input_id: str,
        saved_paths: list[str],
        out_dir: str,
    ) -> StateGraphOrganizeResponse:
        """
        `saved_paths`: on-disk paths for every uploaded file (pre-dedupe order preserved for logging).
        Writes intermediate JSON under `out_dir` when possible.
        """

        t0 = time.perf_counter()
        dedup = await asyncio.to_thread(dedupe_image_paths, saved_paths)
        _write_json(
            os.path.join(out_dir, "dedup.json"),
            {
                "canonical_paths": dedup.canonical_paths,
                "canonical_image_ids": dedup.canonical_image_ids,
                "input_path_to_image_id": dedup.input_path_to_image_id,
                "dropped_paths": dedup.dropped_paths,
                "elapsed_setup_seconds": time.perf_counter() - t0,
            },
        )

        if not dedup.canonical_paths:
            raise AIProcessingError("No images remain after deduplication")

        extract_model = settings.STATE_GRAPH_UI_EXTRACTION_MODEL
        intent_model = settings.STATE_GRAPH_USER_INTENT_MODEL
        flow_model = settings.STATE_GRAPH_FLOW_MODEL
        e2e_model = settings.STATE_GRAPH_E2E_SCENARIO_MODEL

        async def _process_screen(
            path: str,
        ) -> tuple[dict[str, Any], str, dict[str, Any], list[dict[str, Any]]]:
            image_id = dedup.input_path_to_image_id[path]

            def _sync_extract_and_intent():
                ui_ext, _h_sec = extract_ui_extraction_gemini_sync(path, extract_model)
                scoped = filter_scoped_ui_extraction(ui_ext)
                minified = user_intent_input_to_minified_json(scoped)
                intents = generate_user_intents_openai_sync(image_id, minified, intent_model)
                return ui_ext, intents

            ui_extraction, intents = await asyncio.to_thread(_sync_extract_and_intent)

            user_intents_list = intents.model_dump(mode="json")["user_intents"]
            ui_dump = ui_extraction.model_dump(mode="json", exclude_none=True)
            screen_doc = StateGraphInputScreen.model_validate(
                build_state_graph_screen_dict(
                    image_id=image_id,
                    extraction=ui_extraction,
                    user_intents=user_intents_list,
                )
            ).model_dump(mode="json")

            _write_json(
                os.path.join(out_dir, f"screen_{image_id[:16]}.json"),
                {
                    "image_id": image_id,
                    "ui_extraction": ui_dump,
                    "user_intents": user_intents_list,
                    "interactive_element_count": len(ui_extraction.controls),
                    "state_graph_screen": screen_doc,
                },
            )
            return screen_doc, image_id, ui_dump, user_intents_list

        try:
            # Process all screens concurrently
            tasks = [_process_screen(path) for path in dedup.canonical_paths]
            screen_rows = await asyncio.gather(*tasks)

            screens = [row[0] for row in screen_rows]
            ui_extractions: dict[str, dict[str, Any]] = {}
            user_intents_by_image: dict[str, list[dict[str, Any]]] = {}
            for screen_doc, image_id, ui_dump, intents_list in screen_rows:
                ui_extractions[image_id] = ui_dump
                user_intents_by_image[image_id] = intents_list

            bundle = {"screens": list(screens)}
            _write_json(os.path.join(out_dir, "screens_bundle.json"), bundle)

            known_ids = set(dedup.canonical_image_ids)
            flows_raw = await asyncio.to_thread(
                run_state_graph_flow_sync,
                bundle,
                flow_model,
                known_ids,
            )
            _write_json(
                os.path.join(out_dir, "flows_raw.json"),
                [f.model_dump(mode="json") for f in flows_raw],
            )

            flows_final = normalize_and_complete_flows(known_ids, flows_raw)

            state_graph_payload = {
                "flows": [f.model_dump(mode="json") for f in flows_final],
            }
            final_test_output = await generate_all_test_scenarios_async(
                ui_extractions,
                user_intents_by_image,
                state_graph_payload,
                e2e_model,
            )

            result = StateGraphOrganizeResponse(
                model=flow_model,
                input_id=input_id,
                flows=flows_final,
                final_test_output=final_test_output,
            )
            _write_json(
                os.path.join(out_dir, "final_test_output.json"),
                final_test_output.model_dump(mode="json"),
            )
            _write_json(os.path.join(out_dir, "result.json"), result.model_dump(mode="json"))
            return result
        except AIProcessingError:
            raise
        except Exception as exc:
            logger.error("State graph pipeline failed: %s", exc)
            raise AIProcessingError(f"State graph pipeline failed: {exc}") from exc




state_graph_pipeline_service = StateGraphPipelineService()
