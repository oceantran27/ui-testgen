import asyncio
import json
import csv
import time
from pathlib import Path
from typing import List, Dict, Any, Set

from utils import load_images_from_dir, call_ui_extraction, trim_ui_elements, match_elements, ensure_sys_path

ensure_sys_path()

# ── CONFIGURATION ──
INPUT_IMAGES_DIR = Path(r"C:\sqa-workspace\ui-testgen\be\data\images") # EDIT THIS
GT_DIR = Path(__file__).resolve().parent / "ground_truth"
RESULTS_DIR = Path(__file__).resolve().parent / "result"
MODEL_NAME = "gpt-5.4-mini" # e.g., "gemini-1.5-flash", "gpt-4o"
MODEL_PROVIDER = "openai"      # "gemini" or "openai"
CONCURRENCY = 5
ID_MIN = 1                     # Start index (1-based)
ID_MAX = 10                   # End index (inclusive)
# ───────────────────

def evaluate_image(gt_elements: List[Dict[str, Any]], model_elements: List[Dict[str, Any]]) -> Dict[str, Any]:
    matched_gt_indices: Set[int] = set()
    matched_model_indices: Set[int] = set()
    
    # Greedy matching
    for i, gt_el in enumerate(gt_elements):
        for j, model_el in enumerate(model_elements):
            if j in matched_model_indices:
                continue
            if match_elements(gt_el, model_el):
                matched_gt_indices.add(i)
                matched_model_indices.add(j)
                break
    
    tp = len(matched_gt_indices)
    fp = len(model_elements) - len(matched_model_indices)
    fn = len(gt_elements) - len(matched_gt_indices)
    
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0
    
    missing = [gt_elements[i] for i in range(len(gt_elements)) if i not in matched_gt_indices]
    exceed = [model_elements[j] for j in range(len(model_elements)) if j not in matched_model_indices]
    
    return {
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "missing": missing,
        "exceed": exceed
    }

def format_element_list(elements: List[Dict[str, Any]]) -> str:
    """Formats elements for CSV output."""
    lines = []
    for el in elements:
        label_or_text = el.get('label') or el.get('text') or "N/A"
        lines.append(f"[{el['type']}] {label_or_text}")
    return " | ".join(lines)

async def process_eval(image_path: Path, gt_dir: Path, results_list: List[Dict], semaphore: asyncio.Semaphore, run_id: str):
    async with semaphore:
        gt_file = gt_dir / f"{image_path.stem}.json"
        if not gt_file.exists():
            print(f"Skipping {image_path.name}: Ground truth file {gt_file.name} not found.")
            return

        print(f"Evaluating {image_path.name} using {MODEL_NAME}...")
        try:
            with open(gt_file, "r", encoding="utf-8") as f:
                gt_data = json.load(f)
            gt_elements = gt_data.get("ui_elements", [])
            
            # Fresh extraction
            extraction_result, latency = await call_ui_extraction(image_path, run_id, model_name=MODEL_NAME, provider=MODEL_PROVIDER)
            model_elements = trim_ui_elements(extraction_result)
            
            eval_metrics = evaluate_image(gt_elements, model_elements)
            eval_metrics["image_name"] = image_path.name
            eval_metrics["latency_ms"] = latency
            results_list.append(eval_metrics)
            
            print(f"  Done {image_path.name}: Recall: {eval_metrics['recall']:.2f}, Latency: {latency}ms")
        except Exception as e:
            print(f"Error evaluating {image_path.name}: {e}")

async def main():
    input_dir = INPUT_IMAGES_DIR
    gt_dir = GT_DIR
    results_dir = RESULTS_DIR
    results_dir.mkdir(parents=True, exist_ok=True)
    
    images = load_images_from_dir(input_dir)
    # Apply range filter
    images = images[ID_MIN-1 : ID_MAX]
    
    if not images:
        print(f"No images found in {input_dir} within range [{ID_MIN}, {ID_MAX}]")
        return

    results = []
    print(f"Found {len(images)} images in range. Starting evaluation with concurrency={CONCURRENCY}...")
    run_id = f"eval_{input_dir.stem}"
    semaphore = asyncio.Semaphore(CONCURRENCY)
    
    tasks = []
    for img in images:
        tasks.append(asyncio.create_task(process_eval(img, gt_dir, results, semaphore, run_id)))
        await asyncio.sleep(2) # Staggered start
        
    await asyncio.gather(*tasks)

    if not results:
        print("No evaluation results to save.")
        return

    # Sort results by image name to keep CSV tidy
    results.sort(key=lambda x: x["image_name"])

    # Timestamped CSV in results folder
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    csv_path = results_dir / f"{timestamp}_evaluation_results.csv"
    
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["image_name", "recall", "precision", "f1_score", "latency_ms", "missing", "exceed"])
        writer.writeheader()
        for r in results:
            writer.writerow({
                "image_name": r["image_name"],
                "recall": round(r["recall"], 4),
                "precision": round(r["precision"], 4),
                "f1_score": round(r["f1"], 4),
                "latency_ms": r["latency_ms"],
                "missing": format_element_list(r["missing"]),
                "exceed": format_element_list(r["exceed"])
            })
            
    print(f"\nEvaluation completed. Results saved to {csv_path}")

if __name__ == "__main__":
    asyncio.run(main())
