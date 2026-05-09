"""LLM-as-judge semantic intent coverage (offline experiments).

Artifacts: collect writes ``ground_truth.json`` under ``data/result/intent_coverage_judge/<UTC>/`` by default.
CLI ``--mode baseline|propose`` writes eval outputs under ``{gt-dir}/eval/<UTC>/``.

See ``run.default_intent_coverage_judge_run_dir`` for the default result root.
"""
