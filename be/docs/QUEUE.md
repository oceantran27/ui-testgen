# Job Queue

We use **ARQ** (Async Redis Queue) for processing background tasks asynchronously.

## Job Types
Currently supported jobs:
- `process_run`: Coordinates LangGraph workflow execution for a given `run_id`.

## Worker Execution
The worker is started via `main_worker.py`. It establishes connections to Redis and the Database.
When a new job is added using `queue_service.enqueue_job()`, the worker picks it up and processes it.

## Lifecycle Status
Database syncs the following state updates:
1. API creates a run -> `queued`
2. Worker picks up job -> `processing`
3. Worker finishes -> `completed`
4. Worker fails -> `failed` (or `retrying` handled internally by ARQ)

## Starting the Worker

From the `be` directory (same virtualenv as the API):

```bash
arq app.workers.main_worker.WorkerSettings
```

The API (`uvicorn main:app`) **only** enqueues jobs to Redis. **All LangGraph pipeline nodes run inside this worker.** If you only start the API, runs stay `processing` or `queued` and the UI can look “stuck” on an early step.

## Troubleshooting

- **Run never leaves `queued`**: worker not running or cannot reach Redis / DB.
- **Early pipeline steps feel slow**: perceived delay is often (1) waiting for the worker to pick the job, (2) LangGraph **Postgres checkpoint** `setup()` on first connection (`ENABLE_GRAPH_CHECKPOINT=true` in `app/core/config.py` — set `ENABLE_GRAPH_CHECKPOINT=false` in `.env` for faster local runs if you do not need resume), or (3) vision-heavy nodes (e.g. joint screen understanding).

Watch **worker** logs (not only Uvicorn) for `pipeline_execution_started` and timing lines `graph_checkpoint_ready_ms` / `graph_ainvoke_ms` from `GraphExecutionService`.

When `PIPELINE_RUN_LOG_ENABLED=true` (default in `app/core/config.py`), each worker run also prints plain **BEGIN/END** step lines to the console and writes a session folder under `be/var/pipeline_run_logs/<UTC_timestamp>_<run_id>/` with `steps/*.json` (one file per graph node) plus `raw/` for model payloads. HTTP **4xx/5xx** from the API process are logged under `be/var/api_error_logs/`.

## Timeouts

- **ARQ `job_timeout`** (`app/workers/main_worker.py`): wraps each ARQ job in `asyncio.wait_for`. Without this wiring, ARQ’s **library default is 300 seconds** (the common cause of “random” timeouts mid-pipeline).

  - **`ARQ_JOB_TIMEOUT_SECONDS`** (`app/core/config.py`): finite wall-clock limit when `> 0` and `ARQ_JOB_NO_TIMEOUT` is `false` (default four hours unless overridden by `.env`).
  - **`ARQ_JOB_NO_TIMEOUT`** or **`ARQ_JOB_TIMEOUT_SECONDS <= 0`**: resolves to **`timedelta.max`** — effectively no Python-side job deadline.

  On worker startup you should see a log line reporting `ARQ_JOB_NO_TIMEOUT`, `ARQ_JOB_TIMEOUT_SECONDS`, and the resolved timeout (`unlimited timedelta.max` or `Ns`).

  **Operational risk**: unlimited jobs can wedge the worker indefinitely (blocking `max_jobs` slots); use only where you intentionally accept that.

- **`DISABLE_MODEL_CALL_ASYNCIO_TIMEOUT`**: skips `asyncio.wait_for` around `provider.generate()` in `retry_handler.py`. A per-request **`ModelRequest.timeout_seconds <= 0`** also disables asyncio wrapping.

- **`DISABLE_MODEL_HTTP_TIMEOUT`**: relaxes SDK HTTP timeouts where supported (`AsyncOpenAI` / Gemini `HttpOptions`). TCP, proxies, and vendor limits still apply.

- The **Run workspace “Log” tab** reads the latest `pipeline.log` for the run via `GET /api/v1/runs/{run_id}/pipeline-log` (same directory layout as above). The UI polls this endpoint while the tab is open and uses the `from_byte` / `next_byte` query for incremental tailing so logs update live without re-downloading the whole file each time (requires API and worker to share the same filesystem or volume).
