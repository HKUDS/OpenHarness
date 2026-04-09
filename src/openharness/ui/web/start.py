"""OpenHarness Web API 启动脚本

可以直接运行此脚本来启动 Web API 服务器
"""

if __name__ == "__main__":
    from openharness.ui.web.server import start_server
    from openharness.ui.web.config import WebServerConfig

    # 自定义配置
    config = WebServerConfig(
        host="0.0.0.0",
        port=8000,
        debug=True,
        cors_origins=["http://localhost:5173", "http://localhost:3000"]
    )

    print("Starting OpenHarness Web API...")
    print(f"Server: http://{config.host}:{config.port}")
    print(f"WebSocket: ws://{config.host}:{config.port}/ws")
    print(f"API Docs: http://{config.host}:{config.port}/docs")
    print()

    start_server(config)