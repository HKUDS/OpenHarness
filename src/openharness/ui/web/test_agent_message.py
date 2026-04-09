"""完整的 Agent Loop 消息测试"""

import asyncio
import websockets
import json

async def test_agent_messaging():
    """测试 Agent 消息处理"""
    uri = "ws://localhost:8000/ws"

    try:
        print(f"连接到 {uri}...")
        async with websockets.connect(uri) as websocket:
            print("WebSocket 连接成功!")

            # 接收就绪消息
            try:
                message = await asyncio.wait_for(websocket.recv(), timeout=5)
                data = json.loads(message)
                print(f"收到就绪消息: {data.get('type')}")
                session_id = data.get('data', {}).get('session_id')
                print(f"会话ID: {session_id}")
            except asyncio.TimeoutError:
                print("等待就绪消息超时")
                return

            # 发送简单消息
            test_message = {
                "type": "user_message",
                "content": "你好"
            }
            print(f"发送消息: {test_message['content']}")
            await websocket.send(json.dumps(test_message))

            # 接收响应
            response_count = 0
            max_responses = 20  # 防止无限循环

            try:
                while response_count < max_responses:
                    message = await asyncio.wait_for(websocket.recv(), timeout=10)
                    data = json.loads(message)
                    msg_type = data.get("type")

                    print(f"收到消息类型: {msg_type}")

                    if msg_type == "user_message":
                        print(f"用户消息回显: {data.get('data', {}).get('content', '')}")

                    elif msg_type == "assistant_delta":
                        text = data.get('text', '')
                        print(f"AI响应: {text}", end='', flush=True)
                        response_count += 1

                    elif msg_type == "assistant_complete":
                        content = data.get('message', {}).get('content', '')
                        print(f"\nAI响应完成: {content}")
                        print("成功完成 Agent 消息测试!")
                        break

                    elif msg_type == "tool_started":
                        tool_name = data.get('tool_name', '')
                        print(f"\n工具开始: {tool_name}")

                    elif msg_type == "tool_completed":
                        tool_name = data.get('tool_name', '')
                        print(f"工具完成: {tool_name}")

                    elif msg_type == "permission_request":
                        tool_name = data.get('tool_name', '')
                        print(f"权限请求: {tool_name}")
                        # 自动拒绝权限请求
                        permission_response = {
                            "type": "permission_response",
                            "request_id": data.get("request_id"),
                            "allowed": False
                        }
                        await websocket.send(json.dumps(permission_response))

                    elif msg_type == "error":
                        error_msg = data.get('message', 'Unknown error')
                        print(f"错误: {error_msg}")
                        break

                    elif msg_type == "pong":
                        print("收到 pong")

                    else:
                        print(f"未知消息类型: {msg_type}")

            except asyncio.TimeoutError:
                print(f"\n等待响应超时 (收到 {response_count} 条响应)")
                if response_count > 0:
                    print("部分测试通过")

    except Exception as e:
        print(f"测试失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_agent_messaging())
