"""OpenHarness Web API - WebSocket + REST API 混合方案

Web API 子模块，位于 ui/web/ 目录下，与现有 UI 架构保持一致。
采用 WebSocket + REST API 混合架构：
- WebSocket：实时通信（流式响应、权限确认、状态更新）
- REST API：资源管理（会话、配置、文件、任务）
"""

__version__ = "1.0.0"

from openharness.ui.web.server import create_app, start_server

__all__ = ["create_app", "start_server"]