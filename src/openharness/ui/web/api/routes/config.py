"""配置管理路由"""

import logging
from fastapi import APIRouter
from openharness.ui.web.protocol.models import *

log = logging.getLogger(__name__)

router = APIRouter(prefix="/config", tags=["config"])


@router.get("/")
async def get_config():
    """获取当前配置"""

    # TODO: 返回实际配置
    return {
        "success": True,
        "config": {
            "model": "claude-sonnet-4-6",
            "provider": "anthropic",
            "permission_mode": "default",
            "theme": "dark",
            "max_turns": 8,
            "max_tokens": 4096
        }
    }


@router.put("/")
async def update_config(update: ConfigUpdate):
    """更新配置"""

    log.info(f"Updating config: {update.dict(exclude_unset=True)}")

    # TODO: 实际更新配置
    updated_config = {}
    if update.model is not None:
        updated_config["model"] = update.model
    if update.permission_mode is not None:
        updated_config["permission_mode"] = update.permission_mode
    if update.theme is not None:
        updated_config["theme"] = update.theme
    if update.max_turns is not None:
        updated_config["max_turns"] = update.max_turns

    return {
        "success": True,
        "config": updated_config,
        "message": "Configuration updated"
    }


@router.get("/models")
async def list_models():
    """获取可用模型列表"""

    # TODO: 返回实际可用模型
    return {
        "success": True,
        "models": [
            {
                "id": "claude-sonnet-4-6",
                "name": "Claude Sonnet 4.6",
                "provider": "anthropic"
            },
            {
                "id": "claude-opus-4-6",
                "name": "Claude Opus 4.6",
                "provider": "anthropic"
            }
        ]
    }


@router.get("/providers")
async def list_providers():
    """获取提供商列表"""

    # TODO: 返回实际提供商
    return {
        "success": True,
        "providers": [
            {
                "id": "anthropic",
                "name": "Anthropic",
                "models": ["claude-sonnet-4-6", "claude-opus-4-6"],
                "configured": True
            }
        ]
    }