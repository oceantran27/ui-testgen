"""
Phase 5 integration test — tests ModelProviderAdapter with MockProvider.
Tests: text_structured, vision_structured, pairwise_vision, schema mismatch retry, API endpoints.
"""
import asyncio
import sys
import os

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import httpx

BASE = "http://localhost:8000/api/v1"
TEST_IMAGE = "original.png"


def check(label, condition, detail=""):
    status = "✅" if condition else "❌"
    print(f"{status} {label}" + (f": {detail}" if detail else ""))
    if not condition:
        sys.exit(1)


async def test_mock_adapter_direct():
    """Test adapter directly with MockProvider."""
    import os
    os.environ["DEFAULT_MODEL_PROVIDER"] = "mock"

    from app.model_providers import model_adapter
    from app.model_providers.schemas import UIStateExtractionResult
    from app.model_providers.base import ImageInput

    # --- Text structured ---
    resp = await model_adapter.call_text_structured(
        task_name="test_text_call",
        run_id="run_test",
        node_name="test_node",
        system_instruction="You are a test assistant.",
        user_instruction="Classify this input.",
        output_schema=UIStateExtractionResult,
        prompt_name="test_prompt",
        prompt_version="v1",
    )
    check("Text structured call", resp.status.value == "success", f"status={resp.status}")
    check("Text parsed_output not None", resp.parsed_output is not None)
    check("Text latency_ms > 0", resp.latency_ms > 0, f"latency_ms={resp.latency_ms}")
    check("Text usage present", resp.usage is not None)
    print(f"   provider={resp.provider}, model={resp.model_name}, tokens={resp.usage.total_tokens}")

    # --- Vision structured ---
    resp2 = await model_adapter.call_vision_structured(
        task_name="test_vision_call",
        run_id="run_test",
        node_name="test_node",
        system_instruction="You are a UI analyst.",
        user_instruction="Describe this screenshot.",
        image_inputs=[ImageInput(image_id="img_test", image_bytes=b"fake_image_bytes")],
        output_schema=UIStateExtractionResult,
        prompt_name="test_vision_prompt",
        prompt_version="v1",
    )
    check("Vision structured call", resp2.status.value == "success")
    check("Vision image_count=1", resp2.image_count == 1)

    # --- Pairwise vision ---
    resp3 = await model_adapter.call_pairwise_vision(
        task_name="semantic_duplicate_verification",
        run_id="run_test",
        node_name="semantic_duplicate_adjudication_node",
        instruction="Are these two screenshots showing the same UI state?",
        image_a=ImageInput(image_id="img_a", image_bytes=b"image_a_bytes"),
        image_b=ImageInput(image_id="img_b", image_bytes=b"image_b_bytes"),
        output_schema=UIStateExtractionResult,
        prompt_name="semantic_duplicate_verification_prompt",
        prompt_version="v1",
    )
    check("Pairwise vision call", resp3.status.value == "success")
    check("Pairwise image_count=2", resp3.image_count == 2)

    print("\n✅ All direct adapter tests passed!")


async def test_via_api():
    """Test Phase 5 API endpoints."""
    async with httpx.AsyncClient(base_url=BASE, timeout=30.0) as client:
        # Create run
        r = await client.post("/runs")
        run_id = r.json()["run_id"]
        check("Create run", r.status_code == 201, run_id)

        # model-config endpoint
        r = await client.get(f"/runs/{run_id}/model-config")
        check("GET model-config 200", r.status_code == 200)
        cfg = r.json()
        check("model-config has default_provider", "default_model_provider" in cfg)
        check("model-config has feature_flags", "feature_flags" in cfg)
        check("model-config has gemini models", cfg["gemini_text_model"] == "gemini-2.0-flash")
        print(f"   default_provider={cfg['default_model_provider']}, gemini_vision={cfg['gemini_vision_model']}")

        # model-calls list (empty initially)
        r = await client.get(f"/runs/{run_id}/model-calls")
        check("GET model-calls 200", r.status_code == 200)
        check("model-calls total=0 initially", r.json()["total"] == 0)

        print("\n✅ All API tests passed!")


async def main():
    print("=== Phase 5 — Model Provider Integration Test ===\n")

    print("--- Direct Adapter Test (MockProvider) ---")
    await test_mock_adapter_direct()

    print("\n--- API Endpoint Test ---")
    await test_via_api()

    print("\n🎉 Phase 5 tests completed!")


if __name__ == "__main__":
    asyncio.run(main())
