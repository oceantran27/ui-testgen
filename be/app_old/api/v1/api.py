from fastapi import APIRouter

from app.api.v1.endpoints import behavior_flow

api_router = APIRouter()
api_router.include_router(behavior_flow.router, prefix="/behavior-flows", tags=["behavior-flows"])
