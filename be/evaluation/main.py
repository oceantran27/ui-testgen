import json
import re
import numpy as np
import logging
import sys
import os
from sentence_transformers import SentenceTransformer, util
import torch

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(os.path.dirname(__file__), 'log.txt'), mode='a', encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)

def preprocess_text(text: str) -> str:
    return re.sub(r'^[*\s-]+|[*\s-]+$', '', text.lower())

def perform_evaluation(data: dict, model: SentenceTransformer, context_info: str = "Unknown Context"):
    logging.info(f"--- EVALUATION: {context_info} ---")
    
    gt_raw = data.get("ground_truth", [])
    om_raw = data.get("user_intents", [])

    # Normalize inputs
    om_norm = [preprocess_text(i) for i in om_raw]
    gt_norm = []
    for item in gt_raw:
        if isinstance(item, list):
            gt_norm.append([preprocess_text(sub) for sub in item])
        else:
            gt_norm.append(preprocess_text(item))

    num_ground_truth = len(gt_norm)
    num_model_output = len(om_norm)

    if not gt_norm and not om_norm:
        return {
            "num_ground_truth": 0, "num_model_output": 0,
            "percent_match": 0.0, "percent_hallucination": 0.0,
            "ground_truth": [], "model_output": [], 
            "match": [], "miss": [], "hallucination": []
        }

    # Compute embeddings
    om_emb = model.encode(om_norm, convert_to_tensor=True) if om_norm else torch.tensor([])
    
    # Compute Similarity Matrix
    scores_matrix = []
    if om_norm and gt_norm:
        for gt_item in gt_norm:
            if isinstance(gt_item, list):
                gt_emb = model.encode(gt_item, convert_to_tensor=True)
                sim = util.cos_sim(gt_emb, om_emb)
                scores_matrix.append(torch.max(sim, dim=0)[0].cpu().numpy().tolist())
            else:
                gt_emb = model.encode(gt_item, convert_to_tensor=True)
                sim = util.cos_sim(gt_emb, om_emb)
                scores_matrix.append(sim.cpu().numpy().flatten().tolist())
    
    scores_matrix = np.array(scores_matrix) if scores_matrix else np.zeros((len(gt_norm), len(om_norm)))

    # --- Matching Logic ---
    THRESHOLD = 0.6
    matched_om_indices = set()
    matched_gt_indices = set()

    if scores_matrix.size > 0:
        rows, cols = np.where(scores_matrix >= THRESHOLD)
        matches = sorted([(scores_matrix[r, c], r, c) for r, c in zip(rows, cols)], key=lambda x: x[0], reverse=True)

        for _, gt_idx, om_idx in matches:
            if om_idx in matched_om_indices:
                continue 
            matched_om_indices.add(om_idx)
            matched_gt_indices.add(gt_idx)

    # --- New Metrics ---
    num_matched_ground_truth = len(matched_gt_indices)
    num_matched_model_output = len(matched_om_indices)
    
    num_not_match_model_output = num_model_output - num_matched_model_output

    # Recall = (# đúng được dự đoán) / (# ground truth)
    percent_match = num_matched_ground_truth / num_ground_truth if num_ground_truth > 0 else 0.0
    
    # Hallucination Rate = (# dự đoán sai) / (# dự đoán)
    percent_hallucination = num_not_match_model_output / num_model_output if num_model_output > 0 else 0.0

    match_intents = [gt_raw[i] for i in range(num_ground_truth) if i in matched_gt_indices]
    miss_intents = [gt_raw[i] for i in range(num_ground_truth) if i not in matched_gt_indices]
    hallucination_intents = [om_raw[i] for i in range(num_model_output) if i not in matched_om_indices]

    logging.info(f"Match GT: {num_matched_ground_truth}, Miss: {len(miss_intents)}, Hallucination: {len(hallucination_intents)}")

    return {
        "num_ground_truth": num_ground_truth,
        "num_model_output": num_model_output,
        "percent_match": round(percent_match, 4), # This is effectively Recall
        "percent_hallucination": round(percent_hallucination, 4),
        "ground_truth": gt_raw,
        "model_output": om_raw,
        "match": match_intents,
        "miss": miss_intents,
        "hallucination": hallucination_intents,
    }