from fastapi import APIRouter
from app.api.v1.endpoints import behavior_flow, platform, test_scenarios

api_router = APIRouter()
api_router.include_router(platform.router, tags=["platform"])
api_router.include_router(test_scenarios.router, prefix="/test-scenarios", tags=["test-scenarios"])
api_router.include_router(behavior_flow.router, prefix="/behavior-flows", tags=["behavior-flows"])
