import os
import sys
import csv
import time
import json
from datetime import datetime
import re

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '')))

from app.services.openai_service import OpenAIService
from app.services.gemini_service import GeminiService
from evaluation.main import perform_evaluation
from sentence_transformers import SentenceTransformer

def extract_intents_from_response(response_text):
    """Extracts user goals from model JSON output following the new schema."""
    try:
        # Some models may wrap JSON in ```json ... ``` fences
        json_match = re.search(r'```json\s*([\s\S]*?)\s*```', response_text)
        json_str = json_match.group(1) if json_match else response_text

        data = json.loads(json_str)

        # Preferred: new schema with "scenarios" and "user_goal"
        if isinstance(data, dict) and "scenarios" in data:
            scenarios = data.get("scenarios", [])
            user_goals = []
            for scenario in scenarios:
                if isinstance(scenario, dict):
                    goal = scenario.get("user_goal")
                    if isinstance(goal, str) and goal.strip():
                        user_goals.append(goal.strip())
            if user_goals:
                return user_goals

        # Backward compatibility: older schema with "user_intents" and "intent_name"
        user_intents = data.get("user_intents", []) if isinstance(data, dict) else []
        extracted = []
        for intent in user_intents:
            if isinstance(intent, dict) and "intent_name" in intent:
                name = intent.get("intent_name")
                if isinstance(name, str) and name.strip():
                    extracted.append(name.strip())
            elif isinstance(intent, str) and intent.strip():
                extracted.append(intent.strip())
        return extracted

    except (json.JSONDecodeError, TypeError) as e:
        print(f"JSON Error: {e}")
        return []

def run_experiment():
    """Runs experiment: processes images, evaluates output, saves metrics to CSV."""
    # Switch between providers/models here or override by env vars:
    # EXP_PROVIDER in {openai, gemini}, EXP_MODEL e.g. gemini-2.5-pro
    provider = os.getenv("EXP_PROVIDER", "gemini").strip().lower()
    model_type = os.getenv("EXP_MODEL", "gemini-2.5-flash").strip()
    
    results_dir = "experiment_results"
    os.makedirs(results_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_filename = os.path.join(results_dir, f"evaluation_{model_type}_{timestamp}.csv")

    # Load Ground Truth
    gt_path = os.path.abspath(os.path.join(os.path.dirname(__file__), 'data', 'ground_truth.json'))
    try:
        with open(gt_path, 'r', encoding='utf-8') as f:
            gt_data = {}
            for item in json.load(f):
                try:
                    gt_data[int(item['id'])] = item['ground_truth']
                except (ValueError, KeyError):
                    continue
    except FileNotFoundError:
        print(f"Missing GT file: {gt_path}")
        return

    # Load Images
    img_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), 'data', 'images'))
    if not os.path.exists(img_dir):
        print(f"Missing Image dir: {img_dir}")
        return
    
    img_files = sorted([f for f in os.listdir(img_dir) if f.endswith(".png")])
    if not img_files:
        print(f"No PNGs in {img_dir}")
        return

    # Initialize AI Service (OpenAI/Gemini)
    print(f"Initializing AI service: provider={provider}, model={model_type}")
    try:
        if provider == "openai":
            ai_service = OpenAIService(model_name=model_type)
        elif provider == "gemini":
            ai_service = GeminiService(model_name=model_type)
        else:
            print(f"Unsupported provider: {provider}")
            return
    except Exception as e:
        print(f"Failed to initialize AI service: {e}")
        return
    
    # Load the evaluation model once to avoid reloading in the loop
    try:
        eval_model_name = 'BAAI/bge-large-en-v1.5'
        print(f"Loading evaluation model: {eval_model_name}...")
        eval_model = SentenceTransformer(eval_model_name)
    except Exception as e:
        print(f"Fatal: Could not load evaluation model. Error: {e}")
        return

    with open(csv_filename, "w", newline="", encoding="utf-8") as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow([
            "image_name",
            "num_ground_truth",
            "num_model_output",
            "precision",
            "recall",
            "hallucination_rate",
            "ground_truth",
            "model_output",
            "match",
            "miss",
            "hallucinations"
        ])

        for img_name in img_files:
            try:
                img_id = int(os.path.splitext(img_name)[0])

                # Loop only from image 5 to 35
                # if (img_id <= 57) :
                #     continue
                
                print(f"Processing: {img_name}")
                
                gt = gt_data.get(img_id)
                
                if gt is None:
                    print(f"Skipping {img_name}: No GT found.")
                    continue

                raw_output = ai_service.analyze_image(os.path.join(img_dir, img_name))
                user_goals = extract_intents_from_response(raw_output)

                if not user_goals:
                    print(f"Warning: No intents for {img_name}")
                    writer.writerow([
                        img_name,
                        len(gt),
                        0,
                        0.0, # precision
                        0.0, # recall
                        0.0, # hallucination_rate
                        json.dumps(gt, ensure_ascii=False),
                        "[]",
                        "[]",
                        json.dumps(gt, ensure_ascii=False),
                        "[]"
                    ])
                    continue

                # Pass extracted user goals to the evaluator using the new key
                res = perform_evaluation({"ground_truth": gt, "user_goals": user_goals}, model=eval_model, context_info=img_name)

                # Calculate Precision and Recall
                # Precision = 1 - percent_hallucination (since percent_hallucination is rate of unmatched OM)
                precision = 1.0 - res["percent_hallucination"]
                # Recall = percent_match (since percent_match is rate of matched GT)
                recall = res["percent_match"]
                hallucination_metric = res["percent_hallucination"]

                writer.writerow([
                    img_name,
                    res["num_ground_truth"],
                    res["num_model_output"],
                    f"{precision:.4f}",
                    f"{recall:.4f}",
                    f"{hallucination_metric:.4f}",
                    json.dumps(res["ground_truth"], ensure_ascii=False),
                    json.dumps(res["model_output"], ensure_ascii=False),
                    json.dumps(res["match"], ensure_ascii=False),
                    json.dumps(res["miss"], ensure_ascii=False),
                    json.dumps(res["hallucination"], ensure_ascii=False)
                ])
                print(f"Evaluated: {img_name} | Precision: {precision:.2%} | Recall: {recall:.2%}")

            except Exception as e:
                print(f"Error {img_name}: {e}")
                writer.writerow([img_name, "Error", "Error", "", "", "", "", "", "", "", ""])

            time.sleep(1)

    print(f"Done. Results: {csv_filename}")

if __name__ == "__main__":
    run_experiment()