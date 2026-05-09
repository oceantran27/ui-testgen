# Object Storage

We use an S3-compatible Object Storage for saving raw images, normalized images, thumbnails, and JSON artifacts.
For local development, we use **MinIO**.

## Storage Path Conventions

Files should be saved following this directory structure pattern:
- Raw images: `raw/{run_id}/{image_id}.{ext}`
- Normalized images: `normalized/{run_id}/{image_id}.png`
- Thumbnails: `thumbnail/{run_id}/{image_id}.webp`
- Artifacts: `artifacts/{run_id}/{node_name}/{artifact_name}.json`
- Final Exports: `export/{run_id}/scenarios.gherkin`

## Important Rule
**Do not save binary image files or massive JSON payloads into the PostgreSQL database.**
Always upload files using `StorageService` (`app/services/storage_service.py`), get the generated S3 URI, and save only the URI string to the database.
