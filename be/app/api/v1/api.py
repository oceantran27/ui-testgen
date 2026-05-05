from fastapi import APIRouter
from app.api.v1.endpoints import bdd, behavior_flow, platform

api_router = APIRouter()
api_router.include_router(platform.router, tags=["platform"])
api_router.include_router(bdd.router, prefix="/bdd", tags=["bdd"])
api_router.include_router(behavior_flow.router, prefix="/behavior-flows", tags=["behavior-flows"])
