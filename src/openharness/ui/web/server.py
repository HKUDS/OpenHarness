"""FastAPI 服务器主入口

创建和配置 FastAPI 应用，集成 WebSocket 和 REST API
"""

import logging
import uvicorn
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket
from .config import WebServerConfig, default_config

log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时
    log.info("Starting OpenHarness Web API server...")

    yield

    # 关闭时
    log.info("Shutting down OpenHarness Web API server...")


def create_app(config: WebServerConfig = None) -> FastAPI:
    """创建 FastAPI 应用"""

    if config is None:
        config = default_config

    app = FastAPI(
        title="OpenHarness Web API",
        version="1.0.0",
        description="OpenHarness 的 Web API 接口 - WebSocket + REST API 混合架构",
        lifespan=lifespan
    )

    # 注册路由
    _register_routes(app)

    # 集成 Agent Loop 的 WebSocket 端点
    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket):
        """集成 Agent Loop 的 WebSocket 连接端点"""
        from .websocket.handler import websocket_connection_handler
        await websocket_connection_handler(websocket)

    return app


def _register_routes(app: FastAPI):
    """注册 API 路由"""

    try:
        # 导入路由
        from .api.routing import api_router
        # 注册 REST API 路由
        app.include_router(api_router)
    except ImportError:
        log.warning("REST API routing not available, running in WebSocket-only mode")

    # 基础路由
    @app.get("/")
    async def root():
        """根路径"""
        return {
            "message": "OpenHarness Web API",
            "version": "1.0.0",
            "docs": "/docs",
            "websocket": "ws://localhost:8000/ws"
        }

    @app.get("/health")
    async def health():
        """健康检查"""
        return {
            "status": "healthy",
            "websocket": "enabled"
        }


def start_server(config: WebServerConfig = None):
    """启动服务器"""

    if config is None:
        config = default_config

    app = create_app(config)

    uvicorn.run(
        app,
        host=config.host,
        port=config.port,
        log_level="info" if not config.debug else "debug"
    )


if __name__ == "__main__":
    start_server()