"""会话管理路由"""

import logging
import uuid
from datetime import datetime
from fastapi import APIRouter, HTTPException
from openharness.ui.web.protocol.models import *
from openharness.ui.web.websocket.session_manager import WebSocketSessionManager

log = logging.getLogger(__name__)

router = APIRouter(prefix="/sessions", tags=["sessions"])

# 全局会话管理器（应该通过依赖注入）
session_manager = WebSocketSessionManager()


@router.post("/", response_model=CreateSessionResponse)
async def create_session(request: CreateSessionRequest):
    """创建新会话"""

    session_id = str(uuid.uuid4())
    created_at = datetime.now().isoformat()

    log.info(f"Creating session: {session_id} with model {request.config.model}")

    # TODO: 这里应该实际创建会话和初始化运行时
    # 目前返回模拟响应
    return CreateSessionResponse(
        success=True,
        session_id=session_id,
        websocket_url=f"ws://localhost:8000/ws?session={session_id}",
        created_at=created_at
    )


@router.get("/{session_id}", response_model=SessionDetail)
async def get_session(session_id: str):
    """获取会话详情"""

    session = session_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")

    # TODO: 返回实际会话详情
    return SessionDetail(
        session_id=session_id,
        created_at=datetime.now().isoformat(),
        updated_at=datetime.now().isoformat(),
        model="claude-sonnet-4-6",
        status="active",
        message_count=0
    )


@router.delete("/{session_id}")
async def delete_session(session_id: str):
    """删除会话"""

    session_manager.remove_session(session_id)
    log.info(f"Deleted session: {session_id}")

    return {"success": True, "message": f"Session {session_id} deleted"}


@router.post("/{session_id}/clear")
async def clear_session(session_id: str):
    """清空会话消息"""

    session = session_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")

    # TODO: 实现清空逻辑
    log.info(f"Cleared session messages: {session_id}")

    return {"success": True, "message": f"Session {session_id} messages cleared"}


@router.get("/")
async def list_sessions():
    """列出所有会话"""

    # TODO: 返回实际会话列表
    return {
        "success": True,
        "sessions": [],
        "count": 0
    }