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
```bash
arq app.workers.main_worker.WorkerSettings
```
