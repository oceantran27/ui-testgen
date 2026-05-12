# Environment Configuration

## Variables List

The following variables can be configured in the `.env` file or exported to the system environment.

### App Config

- `ENVIRONMENT`: Current environment, e.g. `local`, `dev`, `staging`, `prod`
- `PROJECT_NAME`: Title of the project
- `API_V1_STR`: API prefix path (e.g. `/api/v1`)

### Database Config

- `DATABASE_URL`: The Async PostgreSQL database URL (format: `postgresql+asyncpg://user:pass@host:port/dbname`)

### Storage Config (MinIO / S3)

- `STORAGE_ENDPOINT`: S3/MinIO endpoint URL (e.g. `http://localhost:9000`)
- `STORAGE_ACCESS_KEY`: Access key ID
- `STORAGE_SECRET_KEY`: Secret access key
- `STORAGE_BUCKET_NAME`: The target bucket name
- `STORAGE_SECURE`: Boolean indicating whether to use SSL (true for AWS S3, usually false for local MinIO)

### Queue Config

- `REDIS_URL`: Redis connection URL for the ARQ job queue
- **`ARQ_JOB_TIMEOUT_SECONDS`**: When `> 0` and `ARQ_JOB_NO_TIMEOUT` is `false`, maximum seconds for one `process_run` ARQ job (entire LangGraph pipeline). Default `14400` (4 hours). Avoid setting **`300`** unless deliberate: it mirrors ARQ’s built-in default and is a common source of “nothing changed” timeouts. **`0` or a negative value** means **no finite ARQ deadline** (`timedelta.max`), same semantics as **`ARQ_JOB_NO_TIMEOUT=true`** — use only when you intentionally allow very long runs; a stuck API call blocks a worker slot.
- **`ARQ_JOB_NO_TIMEOUT`**: When `true`, maps ARQ **`job_timeout` to effectively unlimited (`timedelta.max`) so you are never cut off at ARQ’s built-in **300 s** default.
- **`ARQ_INTERPRET_300S_AS_LONG_JOB`**: Default `true`. When **`ARQ_JOB_TIMEOUT_SECONDS`** is exactly **`300`**, the worker rewrites **`process_run`** timeouts to **`ARQ_JOB_LONG_PIPELINE_FALLBACK_SECONDS`** (default `14400`) with a **`worker_arq_timeout_300_interpreted_as_long_job`** WARN log unless you disable this reinterpretation via `false` in `.env`.
- **`DISABLE_MODEL_CALL_ASYNCIO_TIMEOUT`**: When `true`, skips `asyncio.wait_for` around each model invoke in `retry_handler.py` (no asyncio-level per-call cutoff). Sending **`ModelRequest.timeout_seconds <= 0`** has the same effect for that single request regardless of this flag.

- `ENABLE_GRAPH_CHECKPOINT`: When `true` (default), LangGraph uses PostgreSQL checkpointing; the first `setup()` each run adds latency. For local dev without resume needs, set `false` in `.env`.

### Model Provider HTTP timeouts

- **`DISABLE_MODEL_HTTP_TIMEOUT`**: When `true`, expands HTTP client timeouts inside the OpenAI / Gemini SDK layers as far as the SDK allows (`httpx.Timeout(None)` / very large Gemini `HttpOptions.timeout` in ms). This does **not** remove network or vendor-side drops.

- Start **both** the API and the ARQ worker (`arq app.workers.main_worker.WorkerSettings`). Submitted runs are not processed by the Uvicorn process alone.

- Start the worker from the **`be/`** directory so `.env` (with the variables above) is picked up reliably by `pydantic-settings`; otherwise misconfiguration can silently fall back on ARQ’s **300 second** job default.

- `VIEWPORT_SHORT_EDGE_MIN` / `VIEWPORT_SHORT_EDGE_MAX`: Integer bounds for `min(width, height)` (default 900–1400)
- `VIEWPORT_LONG_EDGE_MIN` / `VIEWPORT_LONG_EDGE_MAX`: Integer bounds for `max(width, height)` (default 1400–2500)
- `VIEWPORT_ASPECT_RATIO_MIN` / `VIEWPORT_ASPECT_RATIO_MAX`: Float bounds for `long_side / short_side` (default 1.5–2.0)
- `ALLOWED_IMAGE_FORMATS`: List of formats, default: `png, jpg, jpeg, webp`
- `MAX_UPLOAD_SIZE_MB`: Max file upload size in megabytes
- `MAX_IMAGES_PER_RUN`: Limit of images per analysis run
- `DUPLICATE_ALLOWED`: Boolean flag
- `UNORDERED_IMAGES_ALLOWED`: Boolean flag
- `INPUT_LEVEL_DETECTION`: Algorithm mode (`auto`, `level1`, etc)
- `JOB_EXECUTION_MODE`: `async` or `sync`
- `WORKER_CONCURRENCY`: Number of concurrent worker processes

### Phase 6 — UI state extraction

- **`UI_STATE_EXTRACTION_MAX_CONCURRENCY`**: Maximum concurrent vision-model calls during UI state extraction for one run (default **5**, allowed range **1–50** in `config.py`). Lower this if Gemini/OpenAI returns rate-limit (429) errors.

## Config Loading

Configurations are loaded using `pydantic-settings` in `app/core/config.py`.
It will read from the `.env` file automatically if it's present in the current working directory.