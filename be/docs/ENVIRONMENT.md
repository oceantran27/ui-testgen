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

### Business Logic Config
- `REQUIRED_VIEWPORT_WIDTH`: Integer, e.g. 1440
- `REQUIRED_VIEWPORT_HEIGHT`: Integer, e.g. 900
- `ALLOWED_IMAGE_FORMATS`: List of formats, default: `png, jpg, jpeg, webp`
- `MAX_UPLOAD_SIZE_MB`: Max file upload size in megabytes
- `MAX_IMAGES_PER_RUN`: Limit of images per analysis run
- `DUPLICATE_ALLOWED`: Boolean flag
- `UNORDERED_IMAGES_ALLOWED`: Boolean flag
- `INPUT_LEVEL_DETECTION`: Algorithm mode (`auto`, `level1`, etc)
- `JOB_EXECUTION_MODE`: `async` or `sync`
- `WORKER_CONCURRENCY`: Number of concurrent worker processes

## Config Loading
Configurations are loaded using `pydantic-settings` in `app/core/config.py`.
It will read from the `.env` file automatically if it's present in the current working directory.
