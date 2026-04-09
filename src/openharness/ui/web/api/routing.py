"""API 路由注册

集中注册所有 REST API 路由
"""

from fastapi import APIRouter
from .routes import sessions, config, tasks

# 创建主路由器
api_router = APIRouter(prefix="/api/v1")

# 注册子路由
api_router.include_router(sessions.router, tags=["sessions"])
api_router.include_router(config.router, tags=["config"])
api_router.include_router(tasks.router, tags=["tasks"])

__all__ = ["api_router"]