from fastapi import APIRouter
from app.api.v1.endpoints import analyze, bdd, behavior_flow

api_router = APIRouter()
api_router.include_router(analyze.router, tags=["analysis"])
api_router.include_router(bdd.router, prefix="/bdd", tags=["bdd"])
api_router.include_router(behavior_flow.router, prefix="/behavior-flows", tags=["behavior-flows"])
