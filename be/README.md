# UI TestGen Backend

Backend API for automating UI testing via LangGraph and VLM agents.

## Architecture
- **Framework:** FastAPI
- **Database:** PostgreSQL (with SQLAlchemy async + Alembic)
- **Object Storage:** MinIO/S3
- **Job Queue:** ARQ (Redis)

## Local Setup

1. Copy `.env.example` to `.env`:
   ```bash
   cp .env.example .env
   ```
2. Start infrastructure via Docker Compose:
   ```bash
   cd docker && docker-compose up -d
   ```
3. Setup Python virtual environment and install dependencies:
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```
4. Run Database Migrations:
   ```bash
   alembic upgrade head
   ```

## Running the Application

**Start the API server:**
```bash
uvicorn main:app --reload
```

**Start the background worker:**
```bash
arq app.workers.main_worker.WorkerSettings
```

## System Verification
Check that the system is ready by hitting the health APIs:
- `GET http://localhost:8000/health`
- `GET http://localhost:8000/ready`
