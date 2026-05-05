"""
Scenario title evaluation for the two-stage pipeline (UI hierarchy stage 1, scenario suite stage 2).

Run from the ``be/`` directory::

    cd be
    python -m experiments.two_stage_test_scenario_title_eval --help

Default ``--pipeline hybrid`` aligns with ``POST /api/v1/test-scenarios/from-image-bridged``
(Gemini UI extraction + GPT scenario generation).
Set ``PYTHONPATH`` to ``be`` if package imports fail. Outputs CSV + titles JSON + stage-1 hierarchy JSON
under ``data/result/<utc_timestamp>/``.
"""
