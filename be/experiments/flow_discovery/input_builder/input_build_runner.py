"""Orchestrate joint raw directory → experiment packages + compressed catalog."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from experiments.flow_discovery import config
from experiments.flow_discovery.input_builder.build_report_builder import build_final_report
from experiments.flow_discovery.input_builder.compressed_catalog_builder import ExperimentCompressedCatalogBuilder
from experiments.flow_discovery.input_builder.experiment_id_factory import ExperimentIdFactory, new_experiment_run_id
from experiments.flow_discovery.input_builder.joint_raw_loader import JointRawLoader, iter_joint_input_json_paths
from experiments.flow_discovery.input_builder.joint_raw_normalizer import JointRawNormalizer
from experiments.flow_discovery.input_builder.screen_intent_package_builder import ExperimentScreenIntentPackageBuilder
from experiments.flow_discovery.input_builder.state_catalog_builder import ExperimentStateCatalogBuilder
from experiments.flow_discovery.io_utils import write_json_document
from experiments.flow_discovery.schemas.input_builder_schema import InputBuilderResult


class FlowDiscoveryInputBuildRunner:
    def run(
        self,
        app_id: str,
        raw_joint_dir: str,
        out_dir: str,
        image_map_path: str | None = None,
        *,
        strict: bool = False,
        experiment_run_id: str | None = None,
    ) -> InputBuilderResult:
        rid = experiment_run_id or new_experiment_run_id(app_id)
        out = Path(out_dir).resolve()
        out.mkdir(parents=True, exist_ok=True)

        loader = JointRawLoader()
        records, loader_warnings = loader.load_dir(raw_joint_dir, image_map_path, strict=strict)
        eligible_paths = iter_joint_input_json_paths(raw_joint_dir)
        raw_seen = len(eligible_paths)
        invalid_raw = len([w for w in loader_warnings if w.startswith("RAW_JSON_")])

        normalizer = JointRawNormalizer()
        normalized: list[Any] = []
        norm_warnings: list[str] = []
        for rec in records:
            n = normalizer.normalize(rec, strict=strict)
            norm_warnings.extend(n.warnings)
            normalized.append(n)

        id_factory = ExperimentIdFactory(app_id)
        state_builder = ExperimentStateCatalogBuilder(app_id)
        state_catalog, state_report = state_builder.build_state_catalog(normalized, id_factory)

        ui_pkg_id = f"ui_pkg_exp_{app_id}_{uuid.uuid4().hex[:10]}"
        ui_state_package: dict[str, Any] = {
            "schema_version": "1.0",
            "agent_name": config.INPUT_BUILDER_AGENT_NAME,
            "extraction_mode": "offline_from_raw_joint_outputs",
            "ui_state_package_id": ui_pkg_id,
            "extracted_states": state_catalog,
            "state_catalog": state_catalog,
            "interaction_group_catalog": [
                {**g, "source_state_id": s["state_id"]}
                for s in state_catalog
                for g in (s.get("interaction_groups") or [])
                if isinstance(g, dict)
            ],
            "report": {
                "app_id": app_id,
                "experiment_run_id": rid,
                **state_report,
            },
        }

        sip_builder = ExperimentScreenIntentPackageBuilder(app_id)
        sip_pkg, sip_side_report = sip_builder.build_screen_intent_package(state_catalog, normalized, id_factory)

        comp_builder = ExperimentCompressedCatalogBuilder()
        val_warn: list[str] = list(loader_warnings) + norm_warnings
        val_warn.extend(state_report.get("warnings") or [])
        val_warn.extend(sip_side_report.get("warnings") or [])
        compressed, comp_val_warn = comp_builder.build(
            rid,
            state_catalog,
            sip_pkg,
            ui_state_package,
            validation_warnings=val_warn,
        )

        unresolved_n = len(sip_pkg.get("unresolved_screen_groups") or [])
        intent_n = len(sip_pkg.get("screen_intent_catalog") or [])

        report = build_final_report(
            app_id=app_id,
            experiment_run_id=rid,
            raw_file_count=raw_seen,
            normalized_output_count=len(normalized),
            state_count=len(state_catalog),
            screen_intent_count=intent_n,
            unresolved_screen_group_count=unresolved_n,
            invalid_raw_file_count=invalid_raw,
            state_build_warning_count=len(state_report.get("warnings") or []),
            screen_intent_warning_count=int(sip_side_report.get("screen_intent_warning_count") or 0),
            warnings=list(compressed.get("warnings") or comp_val_warn),
            compressed_catalog_package=compressed,
        )

        write_json_document(out / "ui_state_package.experiment.json", ui_state_package)
        write_json_document(out / "screen_intent_package.experiment.json", sip_pkg)
        write_json_document(out / "compressed_catalog_package.json", compressed)
        write_json_document(out / "build_report.json", report)

        return InputBuilderResult(
            app_id=app_id,
            experiment_run_id=rid,
            ui_state_package=ui_state_package,
            screen_intent_package=sip_pkg,
            compressed_catalog_package=compressed,
            build_report=report,
        )


__all__ = ["FlowDiscoveryInputBuildRunner"]
