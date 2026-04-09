"""任务管理路由"""

import logging
from fastapi import APIRouter, HTTPException
from openharness.ui.web.protocol.models import *

log = logging.getLogger(__name__)

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.get("/")
async def list_tasks():
    """获取任务列表"""

    # TODO: 返回实际任务列表
    return {
        "success": True,
        "tasks": [],
        "count": 0
    }


@router.get("/{task_id}")
async def get_task(task_id: str):
    """获取任务详情"""

    # TODO: 返回实际任务详情
    return TaskDetail(
        id=task_id,
        type="agent",
        status="running",
        description="Example task",
        created_at="2024-01-01T00:00:00"
    )


@router.post("/{task_id}/stop")
async def stop_task(task_id: str):
    """停止任务"""

    log.info(f"Stopping task: {task_id}")

    # TODO: 实际停止任务
    return {
        "success": True,
        "message": f"Task {task_id} stopped"
    }


@router.get("/{task_id}/output")
async def get_task_output(task_id: str):
    """获取任务输出"""

    # TODO: 返回实际任务输出
    return {
        "success": True,
        "task_id": task_id,
        "output": "Task output placeholder"
    }