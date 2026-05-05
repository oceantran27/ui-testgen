import asyncio
import argparse
import sys
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

from app.services.two_stage_test_scenario_service import two_stage_test_scenario_service


async def main():
    parser = argparse.ArgumentParser(
        description="Smoke-test the two-stage test scenario pipeline (UI hierarchy + scenario suite)"
    )
    parser.add_argument("image_path", type=str, help="Path to the test UI screenshot")
    parser.add_argument("--stage1", type=str, default="gemini-2.5-flash", help="Model for stage 1 (vision)")
    parser.add_argument("--stage2", type=str, default="gemini-2.5-flash", help="Model for stage 2 (text)")

    args = parser.parse_args()

    if not Path(args.image_path).exists():
        print(f"Error: Image {args.image_path} does not exist.")
        sys.exit(1)

    print("Testing two-stage test scenario pipeline...")
    print(f"Image: {args.image_path}")
    print(f"Stage 1 (vision): {args.stage1}")
    print(f"Stage 2 (text): {args.stage2}")
    print("-" * 50)

    try:
        result = await two_stage_test_scenario_service.generate(
            args.image_path,
            stage1_model=args.stage1,
            stage2_model=args.stage2,
        )

        print("\n--- Test scenario suite JSON ---")
        print(result.model_dump_json(indent=2))
        print("-----------------------")

    except Exception as e:
        print(f"\nPipeline execution failed: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
