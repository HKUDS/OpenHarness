"""Observable application state store."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace

from openharness.state.app_state import AppState


Listener = Callable[[AppState], None]


class AppStateStore:
    """Very small observable state store."""    # 状态管理器 (管理应用的可变状态，实现观察者模式)

    def __init__(self, initial_state: AppState) -> None:
        self._state = initial_state         # 实际状态数据
        self._listeners: list[Listener] = []

    def get(self) -> AppState:
        """Return the current state snapshot."""   #获取当前状态快照
        return self._state

    def set(self, **updates) -> AppState:
        """Update the state and notify listeners."""    #更新状态并通知所有监听者
        self._state = replace(self._state, **updates)
        for listener in list(self._listeners):
            listener(self._state)
        return self._state

    def subscribe(self, listener: Listener) -> Callable[[], None]:
        """Register a listener and return an unsubscribe callback."""   #注册监听者，返回取消订阅函数
        self._listeners.append(listener)

        def _unsubscribe() -> None:
            if listener in self._listeners:
                self._listeners.remove(listener)

        return _unsubscribe
