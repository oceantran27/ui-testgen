import asyncio
import json
import csv
import time
from pathlib import Path
from typing import List, Dict, Any, Set, Optional

from utils import load_images_from_dir, call_ui_extraction, trim_ui_elements, match_elements, ensure_sys_path

ensure_sys_path()

# ── CONFIGURATION ──
INPUT_IMAGES_DIR = Path(r"C:\sqa-workspace\ui-testgen\be\data\images") # EDIT THIS
GT_DIR = Path(__file__).resolve().parent / "ground_truth"
RESULTS_BASE_DIR = Path(__file__).resolve().parent / "result"

# If MO_DIR is set to a path, evaluation will use existing JSONs from that folder.
# If set to None, it will run the model and generate new JSONs.
MO_DIR: Optional[Path] = Path(r"C:\sqa-workspace\ui-testgen\be\experiments\ui_benchmark\result\20260513_051743_output\result\20240513_044500_output") # Example: Path(r"C:\...C:\sqa-workspace\ui-testgen\be\experiments\ui_benchmark\result\20260513_051743_output\result\20240513_044500_output")

MODEL_NAME = "gemini-2.5-flash" # e.g., "gemini-1.5-flash", "gpt-4o"
MODEL_PROVIDER = "gemini"      # "gemini" or "openai"
CONCURRENCY = 5
ID_MIN = 1                     # Start index (1-based)
ID_MAX = 5               # End index (inclusive)
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

async def run_extraction_task(image_path: Path, output_dir: Path, semaphore: asyncio.Semaphore, run_id: str) -> Dict[str, Any]:
    async with semaphore:
        print(f"Extracting {image_path.name} using {MODEL_NAME}...")
        try:
            extraction_result, latency = await call_ui_extraction(image_path, run_id, model_name=MODEL_NAME, provider=MODEL_PROVIDER)
            model_elements = trim_ui_elements(extraction_result)
            
            output_data = {
                "image_name": image_path.name,
                "latency_ms": latency,
                "ui_elements": model_elements
            }
            
            # Save raw model output JSON
            json_path = output_dir / f"{image_path.stem}.json"
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(output_data, f, indent=2, ensure_ascii=False)
            
            return output_data
        except Exception as e:
            print(f"Error extracting {image_path.name}: {e}")
            return None

async def main():
    input_dir = INPUT_IMAGES_DIR
    gt_dir = GT_DIR
    
    images = load_images_from_dir(input_dir)
    images = images[ID_MIN-1 : ID_MAX]
    
    if not images:
        print(f"No images found in {input_dir} within range [{ID_MIN}, {ID_MAX}]")
        return

    # Phase 1: Get Model Outputs
    model_outputs: List[Dict[str, Any]] = []
    
    if MO_DIR and MO_DIR.exists():
        print(f"Loading existing model outputs from {MO_DIR}...")
        for image_path in images:
            mo_file = MO_DIR / f"{image_path.stem}.json"
            if mo_file.exists():
                with open(mo_file, "r", encoding="utf-8") as f:
                    model_outputs.append(json.load(f))
            else:
                print(f"Warning: Model output for {image_path.name} not found in {MO_DIR}")
        current_results_dir = MO_DIR
    else:
        print(f"Generating new model outputs for {len(images)} images...")
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        current_results_dir = RESULTS_BASE_DIR / f"{timestamp}_output"
        current_results_dir.mkdir(parents=True, exist_ok=True)
        
        run_id = f"eval_{input_dir.stem}"
        semaphore = asyncio.Semaphore(CONCURRENCY)
        tasks = []
        for img in images:
            tasks.append(asyncio.create_task(run_extraction_task(img, current_results_dir, semaphore, run_id)))
            await asyncio.sleep(2)
        
        raw_outputs = await asyncio.gather(*tasks)
        model_outputs = [o for o in raw_outputs if o is not None]

    # Phase 2: Evaluation
    if not model_outputs:
        print("No model outputs available for evaluation.")
        return

    print(f"\nStarting evaluation against Ground Truth ({len(model_outputs)} samples)...")
    eval_results = []
    for mo in model_outputs:
        img_name = mo["image_name"]
        stem = Path(img_name).stem
        gt_file = gt_dir / f"{stem}.json"
        
        if not gt_file.exists():
            print(f"Skipping {img_name}: Ground truth file {gt_file.name} not found.")
            continue
            
        with open(gt_file, "r", encoding="utf-8") as f:
            gt_data = json.load(f)
        gt_elements = gt_data.get("ui_elements", [])
        
        metrics = evaluate_image(gt_elements, mo["ui_elements"])
        metrics["image_name"] = img_name
        metrics["latency_ms"] = mo.get("latency_ms", 0)
        eval_results.append(metrics)

    if not eval_results:
        print("No evaluation metrics could be calculated.")
        return

    # Phase 3: Save CSV Report
    eval_results.sort(key=lambda x: x["image_name"])
    csv_timestamp = time.strftime("%Y%m%d_%H%M%S")
    csv_path = current_results_dir / f"evaluation_results_{csv_timestamp}.csv"
    
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["image_name", "recall", "precision", "f1_score", "latency_ms", "missing", "exceed"])
        writer.writeheader()
        for r in eval_results:
            writer.writerow({
                "image_name": r["image_name"],
                "recall": round(r["recall"], 4),
                "precision": round(r["precision"], 4),
                "f1_score": round(r["f1"], 4),
                "latency_ms": r["latency_ms"],
                "missing": format_element_list(r["missing"]),
                "exceed": format_element_list(r["exceed"])
            })
            
    print(f"\nEvaluation completed. Result directory: {current_results_dir}")
    print(f"CSV Report: {csv_path.name}")

if __name__ == "__main__":
    asyncio.run(main())
