"""Web API 配置管理"""

from dataclasses import dataclass
from typing import List

@dataclass
class WebServerConfig:
    """Web 服务器配置"""

    # 服务器配置
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = False

    # CORS 配置
    cors_origins: List[str] = None
    cors_allow_credentials: bool = True
    cors_allow_methods: List[str] = None
    cors_allow_headers: List[str] = None
    cors_allow_origins_regex: List[str] = None  # 支持正则表达式

    # WebSocket 配置
    ws_ping_interval: int = 20  # 心跳间隔（秒）
    ws_ping_timeout: int = 30   # 心跳超时（秒）
    ws_max_connections: int = 100  # 最大连接数

    # 会话配置
    session_timeout: int = 3600  # 会话超时（秒）
    max_sessions_per_user: int = 5  # 每用户最大会话数

    # 安全配置
    enable_auth: bool = False  # 是否启用认证
    jwt_secret: str = "your-secret-key"  # JWT 密钥
    jwt_expire_hours: int = 24  # JWT 过期时间

    def __post_init__(self):
        if self.cors_origins is None:
            # 必须包含 localhost 和 127.0.0.1
            self.cors_origins = [
                "http://localhost:5173",   # Vue 开发服务器
                "http://127.0.0.1:5173",  # Vue 开发服务器 (备用)
                "http://localhost:3000",   # React 开发服务器
                "http://127.0.0.1:3000",  # React 开发服务器 (备用)
                "http://localhost:8000",   # Web API 自身 (localhost)
                "http://127.0.0.1:8000",   # Web API 自身 (127.0.0.1)
                "ws://localhost:8000",     # WebSocket 连接 (localhost)
                "ws://127.0.0.1:8000",     # WebSocket 连接 (127.0.0.1)
                "null",                    # 允许同源请求
            ]
        if self.cors_allow_methods is None:
            self.cors_allow_methods = ["GET", "POST", "PUT", "DELETE", "OPTIONS"]
        if self.cors_allow_headers is None:
            self.cors_allow_headers = ["*"]
        if self.cors_allow_origins_regex is None:
            self.cors_allow_origins_regex = []

# 默认配置实例
default_config = WebServerConfig()