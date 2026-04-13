"""Web API 协议模型定义

参考现有 protocol.py 的模型设计，但扩展 Web 专用功能
"""

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field

# ============================================================================
# WebSocket 消息模型
# ============================================================================

class WebSocketMessage(BaseModel):
    """WebSocket 基础消息模型"""
    type: str
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())
    request_id: Optional[str] = None

# ============================================================================
# 客户端 → 服务器消息
# ============================================================================

class SubmitLine(WebSocketMessage):
    """确认用户消息响应"""
    type: Literal["submit_line"] = "submit_line"
    content: str

class PermissionResponse(WebSocketMessage):
    """权限确认响应"""
    type: Literal["permission_response"] = "permission_response"
    request_id: str
    allowed: bool

class QuestionResponse(WebSocketMessage):
    """问题响应"""
    type: Literal["question_response"] = "question_response"
    request_id: str
    answer: str

# ============================================================================
# 服务器 → 客户端事件
# ============================================================================

class ReadyEvent(WebSocketMessage):
    """后端就绪事件"""
    type: Literal["ready"] = "ready"
    data: Dict[str, Any]

class TranscriptItem(WebSocketMessage):
    """确认用户消息响应"""
    type: Literal["transcript_item"] = "transcript_item"
    content: str

class AssistantDeltaEvent(WebSocketMessage):
    """助手流式输出增量事件"""
    type: Literal["assistant_delta"] = "assistant_delta"
    text: str

class AssistantCompleteEvent(WebSocketMessage):
    """助手响应完成事件"""
    type: Literal["assistant_complete"] = "assistant_complete"
    message: Dict[str, Any]
    usage: Optional[Dict[str, int]] = None

class ToolStartedEvent(WebSocketMessage):
    """工具开始执行事件"""
    type: Literal["tool_started"] = "tool_started"
    tool_name: str
    tool_input: Dict[str, Any]

class ToolCompletedEvent(WebSocketMessage):
    """工具执行完成事件"""
    type: Literal["tool_completed"] = "tool_completed"
    tool_name: str
    output: str
    is_error: bool = False

class PermissionRequestEvent(WebSocketMessage):
    """权限请求事件"""
    type: Literal["permission_request"] = "permission_request"
    request_id: str
    tool_name: str
    reason: str

class QuestionRequestEvent(WebSocketMessage):
    """问题请求事件"""
    type: Literal["question_request"] = "question_request"
    request_id: str
    question: str

class StateSnapshotEvent(WebSocketMessage):
    """状态快照事件"""
    type: Literal["state_snapshot"] = "state_snapshot"
    state: Dict[str, Any]

class ErrorEvent(WebSocketMessage):
    """错误事件"""
    type: Literal["error"] = "error"
    message: str
    details: Optional[Dict[str, Any]] = None

# ============================================================================
# REST API 模型
# ============================================================================

class SessionConfig(BaseModel):
    """会话配置"""
    model: str = "claude-sonnet-4-6"
    system_prompt: Optional[str] = None
    max_turns: int = 8
    max_tokens: int = 4096

class CreateSessionRequest(BaseModel):
    """创建会话请求"""
    config: SessionConfig

class CreateSessionResponse(BaseModel):
    """创建会话响应"""
    success: bool
    session_id: str
    websocket_url: str
    created_at: str

class SessionDetail(BaseModel):
    """会话详情"""
    session_id: str
    created_at: str
    updated_at: str
    model: str
    status: str
    message_count: int

class ConfigUpdate(BaseModel):
    """配置更新"""
    model: Optional[str] = None
    permission_mode: Optional[str] = None
    theme: Optional[str] = None
    max_turns: Optional[int] = None

class TaskDetail(BaseModel):
    """任务详情"""
    id: str
    type: str
    status: str
    description: str
    created_at: str

# ============================================================================
# 通用响应模型
# ============================================================================

class ApiResponse(BaseModel):
    """统一 API 响应格式"""
    success: bool
    data: Optional[Any] = None
    error: Optional[str] = None
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())

class ErrorResponse(BaseModel):
    """错误响应"""
    success: bool = False
    error: str
    code: str
    details: Optional[Dict[str, Any]] = None
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())