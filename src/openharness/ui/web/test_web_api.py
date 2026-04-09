"""OpenHarness Web API 测试脚本"""

import requests
import json
import asyncio
import websockets


BASE_URL = "http://localhost:8000"
WS_URL = "ws://localhost:8000/ws"

def print_section(title):
    """打印分节标题"""
    print(f"\n{'='*50}")
    print(f"  {title}")
    print(f"{'='*50}")

def test_health():
    """测试健康检查"""
    print_section("1. 健康检查测试")

    response = requests.get(f"{BASE_URL}/health")
    print(f"状态码: {response.status_code}")
    print(f"响应: {json.dumps(response.json(), indent=2, ensure_ascii=False)}")

    return response.status_code == 200

def test_root():
    """测试根路径"""
    print_section("2. 根路径测试")

    response = requests.get(f"{BASE_URL}/")
    print(f"状态码: {response.status_code}")
    print(f"响应: {json.dumps(response.json(), indent=2, ensure_ascii=False)}")

    return response.status_code == 200

def test_create_session():
    """测试创建会话"""
    print_section("3. 创建会话测试")

    payload = {
        "config": {
            "model": "claude-sonnet-4-6",
            "max_turns": 8
        }
    }

    response = requests.post(
        f"{BASE_URL}/api/v1/sessions/",
        json=payload,
        headers={"Content-Type": "application/json"}
    )

    print(f"状态码: {response.status_code}")
    print(f"响应: {json.dumps(response.json(), indent=2, ensure_ascii=False)}")

    if response.status_code == 200:
        data = response.json()
        return data.get("session_id")
    return None

def test_get_config():
    """测试获取配置"""
    print_section("4. 获取配置测试")

    response = requests.get(f"{BASE_URL}/api/v1/config/")
    print(f"状态码: {response.status_code}")
    print(f"响应: {json.dumps(response.json(), indent=2, ensure_ascii=False)}")

    return response.status_code == 200

def test_get_models():
    """测试获取模型列表"""
    print_section("5. 获取模型列表测试")

    response = requests.get(f"{BASE_URL}/api/v1/config/models")
    print(f"状态码: {response.status_code}")
    print(f"响应: {json.dumps(response.json(), indent=2, ensure_ascii=False)}")

    return response.status_code == 200

async def test_websocket_connection():
    """测试 WebSocket 连接（使用 websockets 包）"""
    print_section("6. WebSocket 连接测试")

    try:
        # 建立 WebSocket 连接
        async with websockets.connect(WS_URL) as ws:
            print("通过 WebSocket 连接成功")

            # 等待 ready 事件
            first_message = await asyncio.wait_for(ws.recv(), timeout=5.0)
            data = json.loads(first_message)
            print(f"收到消息: {json.dumps(data, indent=2, ensure_ascii=False)}")

            # 发送测试消息
            test_message = {
                "type": "user_message",
                "content": "你好，这是一个测试消息"
            }
            await ws.send(json.dumps(test_message))
            print(f"发送消息: {test_message['content']}")

            # 接收响应（设置超时）
            try:
                while True:
                    message = await asyncio.wait_for(ws.recv(), timeout=5.0)
                    data = json.loads(message)
                    print(f"收到响应: {data.get('type', 'unknown')}")

                    if data.get('type') == 'assistant_complete':
                        print("通过 收到完整响应")
                        break

            except asyncio.TimeoutError:
                print("⏰ 接收超时（正常，测试结束）")

        print("通过 WebSocket 连接已关闭")
        return True

    except Exception as e:
        print(f"失败 WebSocket 连接失败: {e}")
        import traceback
        traceback.print_exc()  # 打印详细错误信息
        return False

def main():
    """主测试函数"""
    print("OpenHarness Web API 测试开始")
    print(f"服务器地址: {BASE_URL}")

    results = {}

    # 测试 HTTP API
    results["健康检查"] = test_health()
    results["根路径"] = test_root()
    results["获取配置"] = test_get_config()
    results["模型列表"] = test_get_models()

    # 测试会话创建
    session_id = test_create_session()
    if session_id:
        print(f"通过 会话创建成功，ID: {session_id}")
        results["创建会话"] = True
    else:
        print("失败 会话创建失败")
        results["创建会话"] = False

    # 测试 WebSocket（异步） 
    results["WebSocket"] = asyncio.run(test_websocket_connection())

    # 测试结果汇总
    print_section("测试结果汇总")
    for test_name, passed in results.items():
        status = "通过 通过" if passed else "失败 失败"
        print(f"{test_name}: {status}")

    # 总体结果
    total_tests = len(results)
    passed_tests = sum(results.values())
    print(f"\n总计: {passed_tests}/{total_tests} 测试通过")

    if passed_tests == total_tests:
        print("所有测试通过！Web API 运行正常")
    else:
        print("部分测试失败，请检查服务器日志")

if __name__ == "__main__":
    main()