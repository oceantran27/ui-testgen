# UI State Extraction Evaluation Report

## 1. Dataset summary

| Item | Count |
|---|---:|
| Raw outputs | 55 |
| Ground truth files | 55 |
| Evaluated pairs | 55 |
| Skipped | 0 |

## 2. Screen classification results

| Metric | Micro (dataset) | Macro (mean / image) |
|---|---:|---:|
| Screen type accuracy | 0.9455 | 0.9455 |
| Presentation scope accuracy | 1.0000 | 1.0000 |
| Outcome state type accuracy | 1.0000 | 1.0000 |
| Screen enum accuracy (mean of three) | 0.9818 | 0.9818 |

## 3. Element extraction results

| Metric | Micro (dataset) | Macro (mean / image) |
|---|---:|---:|
| Precision | 0.9444 | 0.9623 |
| Recall | 0.9471 | 0.9668 |
| F1 | 0.9457 | 0.9595 |
| Correct count | 645 |  |
| Pred count | 683 |  |
| GT count | 681 |  |

## 4. Action extraction results

| Metric | Micro (dataset) | Macro (mean / image) |
|---|---:|---:|
| Precision | 0.9755 | 0.9795 |
| Recall | 0.9636 | 0.9702 |
| F1 | 0.9695 | 0.9712 |
| Correct count | 318 |  |
| Pred count | 326 |  |
| GT count | 330 |  |

## 5. Feedback extraction results

| Metric | Micro (dataset) | Macro (mean / image) |
|---|---:|---:|
| Precision | 0.9286 | 0.9231 |
| Recall | 0.9512 | 0.9259 |
| F1 | 0.9398 | 0.9359 |
| Correct count | 39 |  |
| Pred count | 42 |  |
| GT count | 41 |  |

## 6. Intent inference results

| Metric | Micro (dataset) | Macro (mean / image) |
|---|---:|---:|
| Precision | 0.7707 | 0.8206 |
| Recall | 0.7562 | 0.8167 |
| F1 | 0.7634 | 0.8000 |
| Correct count | 121 |  |
| Pred count | 157 |  |
| GT count | 160 |  |

## 7. Diagnostics: skipped/missing keys

Counts aggregate multiset evaluation-key skips (pred-side empty keys; intent column includes pred + GT misses).

| Diagnostic | Dataset total |
|---|---:|
| Skipped empty-key elements (pred) | 22 |
| Skipped empty-key actions (pred) | 1 |
| Skipped empty-key feedback (pred) | 0 |
| Intent key missing (pred + GT) | 14 |

### Images with non-zero key skips (top 10)

| image_id | Sum of skip counts |
|---|---:|
| exp_adm_s01 | 2 |
| exp_adm_s07 | 2 |
| exp_bank_s01 | 2 |
| exp_bank_s05 | 2 |
| exp_book_s03 | 2 |
| exp_book_s06 | 2 |
| exp_event_s02 | 2 |
| exp_event_s03 | 2 |
| exp_adm_s05 | 1 |
| exp_adm_s08 | 1 |

## 8. Notes and limitations

- **Summary v4 (micro):** Pooled precision/recall/F1 use summed matched / pred / GT counts across images. Screen accuracies are mean per-image over three taxonomy fields (**domain** excluded).
- **Element counts** follow **text-grounded** denominators (evaluable label keys); see `evaluation_per_image.json` for full per-image blocks.
- **Auxiliary metrics** (interaction groups, ID grounding, intent sub-multisets, reference consistency) are not listed here; see `evaluation_summary.json` → `diagnostic_metrics` and optional pipeline JSONL debug logs.
