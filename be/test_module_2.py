import asyncio
import argparse
import sys
import json
from pathlib import Path
from dotenv import load_dotenv

# Load env variables (like API keys)
load_dotenv()

from app.services.module_2_pipeline import module_2_pipeline_service

async def main():
    parser = argparse.ArgumentParser(description="Test Module 2 Pipeline (Agent 1 + Agent 2)")
    parser.add_argument("image_path", type=str, help="Path to the test UI screenshot")
    parser.add_argument("--stage1", type=str, default="gemini-2.5-flash", help="Model for Stage 1 (Vision)")
    parser.add_argument("--stage2", type=str, default="gemini-2.5-flash", help="Model for Stage 2 (Text)")
    
    args = parser.parse_args()
    
    if not Path(args.image_path).exists():
        print(f"Error: Image {args.image_path} does not exist.")
        sys.exit(1)
        
    print(f"Testing Module 2 Pipeline...")
    print(f"Image: {args.image_path}")
    print(f"Stage 1 (Vision): {args.stage1}")
    print(f"Stage 2 (Text): {args.stage2}")
    print("-" * 50)
    
    try:
        result = await module_2_pipeline_service.generate_bdd(
            image_path=args.image_path,
            stage1_model=args.stage1,
            stage2_model=args.stage2
        )
        
        print("\n--- BDD JSON Output ---")
        print(result.model_dump_json(indent=2))
        print("-----------------------")
        
    except Exception as e:
        print(f"\nPipeline execution failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
