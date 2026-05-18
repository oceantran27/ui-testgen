# Schema audit — unused columns/tables

Method: for each SQLAlchemy `Mapped` attribute under `be/app/db/models/`, search `be/app` (excluding `db/migrations`) for reads/writes and check API/FE payloads.

## Implemented drops (migration + ORM aligned)

| Table | Columns | Evidence |
|-------|---------|----------|
| `runs` | `input_level`, `input_level_confidence`, `input_level_reason` | No `.input_level*` assignments on `Run` in application code; API exposes `input_level` on **flows** (`Flow.input_level`), not on runs; FE references `input_level_mode` only in run config typing. Columns were added in Phase 7 migration but never wired. |
| `behaviour_scenarios` | `path_id` | No reads/writes of `BehaviourScenario.path_id` in `be/app`; `_persist_scenario_row` never sets it. |

## Not dropped (still referenced or risky)

- All other `runs` columns: used by `be/app/services/graph_service.py`, `be/app/api/routes/runs.py`, finalizer, etc.
- Full table drops: none identified; checkpoint/duplicate tables already removed by `617efa320277_pipeline_v2_refactor.py`.
- Deeper sweep: repeat this grep-per-column pass for large JSON blobs (`*_json`) if product owners confirm export/API contracts.
