# Database Architecture

This project uses **PostgreSQL** with **SQLAlchemy** (Async engine) and **Alembic** for migrations.

## Tables
Currently, the Phase 0 defines the following base tables:

### `runs`
Represents an analysis lifecycle.
- `id`: Run ID (string)
- `status`: Lifecycle state (`created`, `queued`, `processing`, `completed`, `failed`, `cancelled`)
- `total_images`, `valid_images`, `invalid_images`: Counts for image stats
- `input_level`: The determined flow level (e.g., Level 1, 2, or 3)

### `images`
Stores metadata for uploaded screenshots.
- `id`: Image ID (string)
- `run_id`: Foreign key to `runs`
- `storage_uri`, `thumbnail_uri`, `normalized_uri`: S3 paths
- `sha256_hash`: For exact duplicate detection

### `jobs`
Manages async background processing tasks.
- `id`: Job ID
- `run_id`: Foreign key to `runs`
- `job_type`: Task name (e.g. `process_run`)
- `status`: Execution state

### `artifacts`
Used for persisting intermediate JSON state and final LangGraph results.
- `id`: Artifact ID
- `run_id`: Foreign key to `runs`
- `artifact_type`: Type descriptor (e.g. `state_catalog`, `flow_graph`)
- `storage_uri`: Pointer to external JSON storage if large

## Migrations
To manage schema updates:
```bash
# Generate a new migration
alembic revision --autogenerate -m "Add new table"

# Apply migration
alembic upgrade head
```
