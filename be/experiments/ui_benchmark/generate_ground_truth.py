import asyncio
import json
import argparse
from pathlib import Path
from typing import List, Dict, Any

from utils import load_images_from_dir, call_ui_extraction, trim_ui_elements, ensure_sys_path

ensure_sys_path()

# ── CONFIGURATION ──
INPUT_IMAGES_DIR = Path(r"C:\sqa-workspace\ui-testgen\be\data\images") # EDIT THIS
GT_OUTPUT_DIR = Path(__file__).resolve().parent / "ground_truth"
CONCURRENCY = 5
MODEL_NAME = "gemini-2.5-flash" # e.g., "gemini-1.5-flash", "gpt-4o"
MODEL_PROVIDER = "gemini"      # "gemini" or "openai"
ID_MIN = 1                     # Start index (1-based)
ID_MAX = 5                   # End index (inclusive)
# ───────────────────

async def process_image(image_path: Path, output_dir: Path, semaphore: asyncio.Semaphore, run_id: str):
    async with semaphore:
        print(f"Processing {image_path.name} using {MODEL_NAME}...")
        try:
            result, latency = await call_ui_extraction(image_path, run_id, model_name=MODEL_NAME, provider=MODEL_PROVIDER)
            trimmed_elements = trim_ui_elements(result)
            
            output_file = output_dir / f"{image_path.stem}.json"
            with open(output_file, "w", encoding="utf-8") as f:
                json.dump({"ui_elements": trimmed_elements}, f, indent=2, ensure_ascii=False)
            
            print(f"Saved ground truth for {image_path.name} to {output_file.name}")
        except Exception as e:
            print(f"Error processing {image_path.name}: {e}")

async def main():
    input_dir = INPUT_IMAGES_DIR
    output_dir = GT_OUTPUT_DIR
    output_dir.mkdir(parents=True, exist_ok=True)
    
    images = load_images_from_dir(input_dir)
    # Apply range filter
    images = images[ID_MIN-1 : ID_MAX]
    
    if not images:
        print(f"No images found in {input_dir} within range [{ID_MIN}, {ID_MAX}]")
        return

    print(f"Found {len(images)} images in range. Starting extraction with concurrency={CONCURRENCY}...")
    
    run_id = f"gen_gt_{input_dir.stem}"
    semaphore = asyncio.Semaphore(CONCURRENCY)
    
    tasks = []
    for img in images:
        # Create task and start it immediately
        tasks.append(asyncio.create_task(process_image(img, output_dir, semaphore, run_id)))
        # Wait 2 seconds before starting the next one
        await asyncio.sleep(2)
        
    await asyncio.gather(*tasks)
    
    print(f"\nGround truth generation completed. Saved to {output_dir}")

if __name__ == "__main__":
    asyncio.run(main())
