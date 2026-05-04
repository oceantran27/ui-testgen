"""
BDD scenario title evaluation for the two-stage pipeline (UI hierarchy Agent 1, BDD Agent 2).

Run from the ``be/`` directory::

    cd be
    python -m experiments.bdd_two_stage_title_eval --help

Default ``--pipeline hybrid`` aligns with ``POST /happy-path-bridged`` (Gemini UI extraction + GPT BDD).
Set ``PYTHONPATH=`` to ``be`` if package imports fail. Outputs CSV + titles JSON + Agent 1 hierarchy JSON
under ``data/result/<utc_timestamp>/``.
"""
