# Agent Test Codebases

This folder contains four independent stage-focused evaluators for the multi-agent pipeline:

- `vp-agent-tests`
- `ba-agent-tests`
- `qa-agent-tests`
- `verifier-agent-tests`

Each evaluator runs a single target stage and emits a JSON report with KPIs:

- schema validity rate
- stage latency (`p50`, `p95`)
- traceability coverage
- semantic precision/recall (when applicable)
- token and cost estimates

## Baseline Image

Default image for all evaluators:

- `be/data/images/02.png`

## Setup

From repository root:

```powershell
Set-Location c:/sqa-workspace/ui-testgen
c:/sqa-workspace/ui-testgen/.venv/Scripts/python.exe -m pip install -r agent-test-codebases/requirements.txt
```

## Run

Run each evaluator from repository root.

### Visual Parser

```powershell
c:/sqa-workspace/ui-testgen/.venv/Scripts/python.exe agent-test-codebases/vp-agent-tests/run_eval.py
```

### Business Analyst

```powershell
c:/sqa-workspace/ui-testgen/.venv/Scripts/python.exe agent-test-codebases/ba-agent-tests/run_eval.py
```

### QA Generator

```powershell
c:/sqa-workspace/ui-testgen/.venv/Scripts/python.exe agent-test-codebases/qa-agent-tests/run_eval.py
```

### Verifier

```powershell
c:/sqa-workspace/ui-testgen/.venv/Scripts/python.exe agent-test-codebases/verifier-agent-tests/run_eval.py
```

## Notes

- Live LLM mode is the default execution mode.
- Each evaluator supports `--upstream-mode fixture` for deterministic runs.
- Reports are stored under each evaluator's `reports/` directory.
