"""WebSocket 连接处理器 - 集成真正的 Agent Loop

处理 WebSocket 连接，集成 ReactBackendHost 实现真正的 AI Agent 能力
"""

import asyncio
import logging
import uuid
from fastapi import WebSocket, WebSocketDisconnect
from openharness.ui.backend_host import ReactBackendHost, BackendHostConfig
from openharness.ui.runtime import build_runtime, start_runtime, close_runtime, handle_line

log = logging.getLogger(__name__)


class WebSocketAgentHost:
    """WebSocket Agent Host - 连接 WebSocket 和 ReactBackendHost"""

    def __init__(self, websocket: WebSocket, session_id: str, model: str = None):
        self.websocket = websocket
        self.session_id = session_id
        self.model = model
        self.backend_host: ReactBackendHost = None
        self.request_queue: asyncio.Queue = None
        self._running = False

    async def initialize(self):
        """初始化 Backend Host"""
        config = BackendHostConfig(
            model=self.model
        )

        self.backend_host = ReactBackendHost(config)
        self.request_queue = asyncio.Queue()

        # 初始化权限和问题请求字典
        if not hasattr(self.backend_host, '_permission_requests'):
            self.backend_host._permission_requests = {}
        if not hasattr(self.backend_host, '_question_requests'):
            self.backend_host._question_requests = {}

        # 启动 backend host 任务
        asyncio.create_task(self._run_backend_host())

        # 启动事件转发任务
        asyncio.create_task(self._forward_events_to_websocket())

    async def _run_backend_host(self):
        """运行 Backend Host（在后台任务中）"""
        try:
            # 重新实现 backend_host 的运行逻辑，但使用 WebSocket 而不是 stdin/stdout
            await self._backend_host_loop()
        except Exception as e:
            log.error(f"Backend host error: {e}", exc_info=True)

    async def _backend_host_loop(self):
        """简化的 Backend Host 循环"""
        from openharness.ui.runtime import build_runtime, start_runtime, close_runtime, handle_line

        # 构建运行时
        self.backend_host._bundle = await build_runtime(
            model=self.model,
            session_backend=None,
            permission_prompt=self._ask_permission,
            ask_user_prompt=self._ask_question,
            enforce_max_turns=True,
        )

        bundle = self.backend_host._bundle

        # 启动运行时
        await start_runtime(bundle)

        # 发送就绪事件
        await self._send_to_websocket({
            "type": "ready",
            "data": {
                "session_id": self.session_id,
                "message": "Agent session ready"
            }
        })

        self._running = True

        # 消息处理循环
        while self._running:
            try:
                # 从队列获取请求
                request = await asyncio.wait_for(self.request_queue.get(), timeout=1.0)

                if request.get("type") == "shutdown":
                    break

                if request.get("type") == "submit_line":
                    line = request.get("line", "").strip()
                    if line:
                        # 处理用户消息
                        await self._process_line(line)

            except asyncio.TimeoutError:
                continue
            except Exception as e:
                log.error(f"Error in backend loop: {e}", exc_info=True)

        # 关闭运行时
        if self.backend_host._bundle:
            await close_runtime(bundle)

    async def _process_line(self, line: str):
        """处理用户输入行"""
        bundle = self.backend_host._bundle

        # 发送用户消息事件
        await self._send_to_websocket({
            "type": "user_message",
            "data": {
                "role": "user",
                "content": line
            }
        })

        # 定义系统打印函数
        async def print_system(message: str):
            await self._send_to_websocket({
                "type": "system_message",
                "text": message
            })

        # 定义事件渲染函数
        async def render_event(event):
            """将后端事件转换为 WebSocket 事件"""
            from openharness.engine.stream_events import (
                AssistantTextDelta,
                AssistantTurnComplete,
                ToolExecutionStarted,
                ToolExecutionCompleted,
                ErrorEvent
            )

            if isinstance(event, AssistantTextDelta):
                await self._send_to_websocket({
                    "type": "assistant_delta",
                    "text": event.text
                })

            elif isinstance(event, AssistantTurnComplete):
                await self._send_to_websocket({
                    "type": "assistant_complete",
                    "message": {
                        "role": "assistant",
                        "content": event.message.text.strip()
                    }
                })

            elif isinstance(event, ToolExecutionStarted):
                await self._send_to_websocket({
                    "type": "tool_started",
                    "tool_name": event.tool_name,
                    "tool_input": event.tool_input
                })

            elif isinstance(event, ToolExecutionCompleted):
                await self._send_to_websocket({
                    "type": "tool_completed",
                    "tool_name": event.tool_name,
                    "output": event.output,
                    "is_error": event.is_error
                })

            elif isinstance(event, ErrorEvent):
                await self._send_to_websocket({
                    "type": "error",
                    "message": event.message
                })

        # 定义清除输出函数
        async def clear_output():
            # WebSocket 不支持清除输出
            pass

        # 处理消息
        await handle_line(
            bundle,
            line,
            print_system=print_system,
            render_event=render_event,
            clear_output=clear_output
        )

    async def _ask_permission(self, tool_name: str, tool_input: dict) -> bool:
        """请求权限"""
        request_id = str(uuid.uuid4())

        await self._send_to_websocket({
            "type": "permission_request",
            "request_id": request_id,
            "tool_name": tool_name,
            "tool_input": tool_input
        })

        # 等待响应（使用超时）
        response_future = asyncio.Future()
        self.backend_host._permission_requests[request_id] = response_future

        try:
            result = await asyncio.wait_for(response_future, timeout=300)
            return result
        except asyncio.TimeoutError:
            return False
        finally:
            self.backend_host._permission_requests.pop(request_id, None)

    async def _ask_question(self, question: str) -> str:
        """询问用户问题"""
        request_id = str(uuid.uuid4())

        await self._send_to_websocket({
            "type": "question_request",
            "request_id": request_id,
            "question": question
        })

        # 等待响应
        response_future = asyncio.Future()
        self.backend_host._question_requests[request_id] = response_future

        try:
            result = await asyncio.wait_for(response_future, timeout=600)
            return result
        except asyncio.TimeoutError:
            return ""
        finally:
            self.backend_host._question_requests.pop(request_id, None)

    async def _forward_events_to_websocket(self):
        """将 backend host 事件转发到 WebSocket"""
        # 这个方法由 backend_host 的 _emit 方法调用
        # 我们通过重写 _emit 来实现
        pass

    async def _send_to_websocket(self, data: dict):
        """发送数据到 WebSocket"""
        try:
            await self.websocket.send_json(data)
        except Exception as e:
            log.error(f"Error sending to websocket: {e}")

    async def process_user_message(self, content: str):
        """处理用户消息"""
        if self.request_queue:
            await self.request_queue.put({
                "type": "submit_line",
                "line": content
            })

    async def handle_permission_response(self, request_id: str, allowed: bool):
        """处理权限响应"""
        if request_id in self.backend_host._permission_requests:
            self.backend_host._permission_requests[request_id].set_result(allowed)

    async def handle_question_response(self, request_id: str, answer: str):
        """处理问题响应"""
        if request_id in self.backend_host._question_requests:
            self.backend_host._question_requests[request_id].set_result(answer)

    async def close(self):
        """关闭连接"""
        self._running = False
        if self.request_queue:
            await self.request_queue.put({"type": "shutdown"})


async def websocket_connection_handler(websocket: WebSocket):
    """
    WebSocket 连接处理器主函数 - 集成真正的 Agent Loop

    基于 testfastapi 的成功模式，集成 ReactBackendHost
    """

    # 记录连接请求信息
    client_addr = f"{websocket.client.host}:{websocket.client.port}"
    log.info(f"WebSocket connection request from {client_addr}")

    # 直接接受连接（简化模式，参考 testfastapi）
    await websocket.accept()
    log.info(f"WebSocket connection accepted for {client_addr}")

    # 获取会话参数
    session_id = websocket.query_params.get("session", str(uuid.uuid4()))
    model = websocket.query_params.get("model", None)

    agent_host = None
    try:
        # 创建 Agent Host
        agent_host = WebSocketAgentHost(websocket, session_id, model)
        await agent_host.initialize()

        # 消息处理循环
        async for message in websocket.iter_json():
            msg_type = message.get("type", "unknown")
            log.debug(f"Message from {session_id}: {msg_type}")

            if msg_type == "user_message":
                content = message.get("content", "")
                await agent_host.process_user_message(content)

            elif msg_type == "permission_response":
                request_id = message.get("request_id")
                allowed = message.get("allowed", False)
                await agent_host.handle_permission_response(request_id, allowed)

            elif msg_type == "question_response":
                request_id = message.get("request_id")
                answer = message.get("answer", "")
                await agent_host.handle_question_response(request_id, answer)

            elif msg_type == "ping":
                await websocket.send_json({"type": "pong"})

            else:
                log.warning(f"Unknown message type: {msg_type}")
                await websocket.send_json({
                    "type": "error",
                    "message": f"Unknown message type: {msg_type}"
                })

    except WebSocketDisconnect as e:
        log.info(f"WebSocket {session_id} disconnected: code={e.code}, reason={e.reason}")
    except Exception as e:
        log.error(f"Error in WebSocket connection {session_id}: {e}", exc_info=True)
        try:
            await websocket.send_json({
                "type": "error",
                "message": str(e)
            })
        except:
            pass
    finally:
        if agent_host:
            await agent_host.close()
        log.info(f"WebSocket session {session_id} closed")