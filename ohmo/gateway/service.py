"""Gateway service lifecycle for ohmo."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import os.path
import signal
import subprocess
import sys
import time
from pathlib import Path

if sys.platform == "win32":
    import ctypes

from openharness.channels.bus.events import OutboundMessage
from openharness.channels.bus.queue import MessageBus
from openharness.channels.impl.manager import ChannelManager
from openharness.utils.fs import atomic_write_text

from ohmo.gateway.bridge import OhmoGatewayBridge
from ohmo.gateway.config import build_channel_manager_config, load_gateway_config
from ohmo.gateway.models import GatewayState
from ohmo.gateway.runtime import OhmoSessionRuntimePool
from ohmo.workspace import (
    get_gateway_restart_notice_path,
    get_logs_dir,
    get_state_path,
    get_workspace_root,
    initialize_workspace,
)

logger = logging.getLogger(__name__)
_REPO_ROOT = Path(__file__).resolve().parents[2]
_STARTUP_TIMEOUT_SECONDS = 15.0
_STARTUP_GRACE_SECONDS = 0.2
_GATEWAY_PID_ENV = "OHMO_GATEWAY_PID"


class OhmoGatewayService:
    """Foreground/background service wrapper for the personal gateway."""

    def __init__(self, cwd: str | Path | None = None, workspace: str | Path | None = None) -> None:
        self._cwd = str(Path(cwd or Path.cwd()).resolve())
        self._workspace = workspace
        os.chdir(self._cwd)
        root = initialize_workspace(self._workspace)
        os.environ["OHMO_WORKSPACE"] = str(root)
        self._config = load_gateway_config(self._workspace)
        if self._config.allow_remote_admin_commands and self._config.allowed_remote_admin_commands:
            logger.warning(
                "ohmo gateway remote administrative commands enabled commands=%s",
                ",".join(self._config.allowed_remote_admin_commands),
            )
        self._bus = MessageBus()
        self._manager = ChannelManager(build_channel_manager_config(self._config), self._bus)
        self._runtime_pool = OhmoSessionRuntimePool(
            cwd=self._cwd,
            workspace=self._workspace,
            provider_profile=self._config.provider_profile,
            create_feishu_group=self.create_group_for_user,
            publish_group_welcome=self.publish_group_welcome,
        )
        self._stop_event: asyncio.Event | None = None
        self._restart_requested = False
        self._bridge = OhmoGatewayBridge(
            bus=self._bus,
            runtime_pool=self._runtime_pool,
            restart_gateway=self.request_restart,
            workspace=root,
            feishu_group_policy=str(
                self._config.channel_configs.get("feishu", {}).get("group_policy", "managed_or_mention")
            ),
            send_tool_hints=self._config.send_tool_hints,
        )

    @property
    def pid_file(self) -> Path:
        return get_workspace_root(self._workspace) / "gateway.pid"

    @property
    def log_file(self) -> Path:
        return get_logs_dir(self._workspace) / "gateway.log"

    @property
    def state_file(self) -> Path:
        return get_state_path(self._workspace)

    def _channel_last_error(self) -> str | None:
        for name, channel in self._manager.channels.items():
            error = getattr(channel, "last_error", None)
            if error:
                return f"{name}: {error}"
        return None

    def write_state(self, *, running: bool, last_error: str | None = None) -> None:
        state = GatewayState(
            running=running,
            pid=os.getpid() if running else None,
            active_sessions=self._runtime_pool.active_sessions,
            provider_profile=self._config.provider_profile,
            enabled_channels=self._config.enabled_channels,
            last_error=last_error or self._channel_last_error(),
        )
        atomic_write_text(self.state_file, state.model_dump_json(indent=2) + "\n")

    async def request_restart(self, message, session_key: str) -> None:
        """Ask the foreground gateway loop to restart itself."""
        restart_notice = {
            "channel": message.channel,
            "chat_id": message.chat_id,
            "session_key": session_key,
            "content": "✅ gateway 已经重新连上，可以继续了。\nGateway is back online. We can continue.",
        }
        get_gateway_restart_notice_path(self._workspace).write_text(
            json.dumps(restart_notice, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        self._restart_requested = True
        # Let the outbound dispatcher flush the restart notice to the IM channel
        # before we tear down the bridge and channel connections.
        await asyncio.sleep(0.75)
        if self._stop_event is not None:
            self._stop_event.set()

    async def create_group(self, message, name: str) -> str:
        """Create a managed group through the active channel implementation."""
        if message.channel != "feishu":
            raise RuntimeError(f"{message.channel} does not support managed group creation.")
        return await self.create_group_for_user(str(message.sender_id), name)

    async def create_group_for_user(self, user_open_id: str, name: str) -> str:
        """Create a managed Feishu group for a user open_id."""
        channel = self._manager.get_channel("feishu")
        if channel is None:
            raise RuntimeError("Feishu channel is not enabled.")
        creator = getattr(channel, "create_managed_group", None)
        if creator is None:
            raise RuntimeError("Feishu channel does not support managed group creation.")
        result = creator(user_open_id=str(user_open_id), name=name)
        return str(await result if asyncio.iscoroutine(result) else result)

    async def publish_group_welcome(self, chat_id: str, content: str, owner_open_id: str) -> None:
        """Send a welcome message to a newly created managed group."""
        await self._bus.publish_outbound(
            OutboundMessage(
                channel="feishu",
                chat_id=chat_id,
                content=content,
                metadata={"chat_type": "group", "_session_key": f"feishu:{chat_id}:{owner_open_id}"},
            )
        )

    def _exec_restart(self) -> None:
        root = str(get_workspace_root(self._workspace))
        argv = [
            sys.executable,
            "-m",
            "ohmo",
            "gateway",
            "run",
            "--cwd",
            self._cwd,
            "--workspace",
            root,
        ]
        logger.info("ohmo gateway restarting in-place argv=%s", argv)
        os.execv(sys.executable, argv)

    async def _publish_pending_restart_notice(self) -> None:
        path = get_gateway_restart_notice_path(self._workspace)
        if not path.exists():
            return
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            channel = payload.get("channel")
            chat_id = payload.get("chat_id")
            content = payload.get("content")
            session_key = payload.get("session_key")
            if not isinstance(channel, str) or not isinstance(chat_id, str) or not isinstance(content, str):
                return
            await asyncio.sleep(2.0)
            await self._bus.publish_outbound(
                OutboundMessage(
                    channel=channel,
                    chat_id=chat_id,
                    content=content,
                    metadata={"_session_key": session_key} if isinstance(session_key, str) else {},
                )
            )
            logger.info(
                "ohmo gateway published restart confirmation channel=%s chat_id=%s session_key=%s",
                channel,
                chat_id,
                session_key,
            )
        finally:
            path.unlink(missing_ok=True)

    async def run_foreground(self) -> int:
        pid = str(os.getpid())
        restart_request = _restart_request_path(get_workspace_root(self._workspace), pid)
        restart_request.unlink(missing_ok=True)
        self.pid_file.write_text(pid, encoding="utf-8")
        previous_pid = os.environ.get(_GATEWAY_PID_ENV)
        os.environ[_GATEWAY_PID_ENV] = pid
        stop_event = asyncio.Event()
        self._stop_event = stop_event
        self._restart_requested = False

        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            with contextlib.suppress(NotImplementedError):
                loop.add_signal_handler(sig, stop_event.set)

        async def _state_heartbeat() -> None:
            while not stop_event.is_set():
                self.write_state(running=True)
                for _ in range(20):
                    if stop_event.is_set():
                        return
                    if restart_request.exists():
                        restart_request.unlink(missing_ok=True)
                        self._restart_requested = True
                        stop_event.set()
                        return
                    await asyncio.sleep(0.25)

        bridge_task = asyncio.create_task(self._bridge.run(), name="ohmo-gateway-bridge")
        manager_task = asyncio.create_task(self._manager.start_all(), name="ohmo-gateway-channels")
        restart_notice_task = asyncio.create_task(
            self._publish_pending_restart_notice(),
            name="ohmo-gateway-restart-notice",
        )
        stop_task = asyncio.create_task(stop_event.wait(), name="ohmo-gateway-stop")
        tasks = [bridge_task, manager_task, restart_notice_task, stop_task]
        workers = {bridge_task}
        if self._config.enabled_channels:
            workers.add(manager_task)
        last_error = None
        try:
            await asyncio.sleep(0)
            for worker in workers:
                if worker.done():
                    worker.result()
                    raise RuntimeError(f"{worker.get_name()} stopped during startup")
            self.write_state(running=True)
            state_task = asyncio.create_task(_state_heartbeat(), name="ohmo-gateway-state")
            tasks.append(state_task)
            finished, _ = await asyncio.wait(
                {stop_task, state_task, *workers}, return_when=asyncio.FIRST_COMPLETED,
            )
            if not stop_event.is_set():
                for worker in finished:
                    worker.result()
                names = ", ".join(task.get_name() for task in finished)
                raise RuntimeError(f"Gateway worker stopped unexpectedly: {names}")
        except Exception as exc:
            last_error = str(exc)
            raise
        finally:
            self._bridge.stop()
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            await self._manager.stop_all()
            with contextlib.suppress(FileNotFoundError):
                if self.pid_file.read_text(encoding="utf-8").strip() == pid:
                    self.write_state(running=False, last_error=last_error)
                    self.pid_file.unlink(missing_ok=True)
            self._stop_event = None
            if previous_pid is None:
                os.environ.pop(_GATEWAY_PID_ENV, None)
            else:
                os.environ[_GATEWAY_PID_ENV] = previous_pid
        if self._restart_requested:
            self._exec_restart()
        return 0


def _restart_request_path(root: Path, pid: str) -> Path:
    return root / f"gateway-restart-{pid}.request"


def request_restart_from_gateway_child(workspace: str | Path | None = None) -> bool:
    """Queue a restart when the command is running inside the gateway's own session."""
    pid = os.environ.get(_GATEWAY_PID_ENV, "")
    inherited_workspace = os.environ.get("OHMO_WORKSPACE")
    root = get_workspace_root(workspace)
    if not pid.isascii() or not pid.isdecimal() or not inherited_workspace:
        return False
    if root != Path(inherited_workspace).resolve():
        return False
    with contextlib.suppress(FileNotFoundError):
        if (root / "gateway.pid").read_text(encoding="utf-8").strip() == pid:
            atomic_write_text(_restart_request_path(root, pid), "restart\n")
            return True
    return False


def _read_gateway_state(path: Path) -> GatewayState | None:
    try:
        return GatewayState.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def start_gateway_process(cwd: str | Path | None = None, workspace: str | Path | None = None) -> int:
    """Start the gateway as a detached subprocess."""
    service = OhmoGatewayService(cwd, workspace)
    service.log_file.parent.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    pythonpath_entries = [str(_REPO_ROOT)]
    existing_pythonpath = env.get("PYTHONPATH")
    if existing_pythonpath:
        pythonpath_entries.append(existing_pythonpath)
    env["PYTHONPATH"] = os.pathsep.join(pythonpath_entries)

    popen_kwargs: dict = {
        "cwd": service._cwd,
        "stdout": None,
        "stderr": None,
        "env": env,
    }
    if sys.platform == "win32":
        popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS  # type: ignore[attr-defined]
        popen_kwargs["stdin"] = subprocess.DEVNULL
    else:
        popen_kwargs["start_new_session"] = True

    with service.log_file.open("a", encoding="utf-8") as log_file:
        popen_kwargs["stdout"] = log_file
        popen_kwargs["stderr"] = log_file
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "ohmo",
                "gateway",
                "run",
                "--cwd",
                service._cwd,
                "--workspace",
                str(get_workspace_root(workspace)),
                "--no-console-log",
            ],
            **popen_kwargs,
        )

    deadline = time.monotonic() + _STARTUP_TIMEOUT_SECONDS
    ready_since: float | None = None
    while True:
        exit_code = process.poll()
        if exit_code is not None:
            raise RuntimeError(
                f"Gateway process (pid={process.pid}) exited with status {exit_code}. "
                f"Check {service.log_file} for details."
            )
        now = time.monotonic()
        state = _read_gateway_state(service.state_file)
        if state and state.running and state.pid == process.pid:
            if ready_since is None:
                ready_since = now
            if now - ready_since >= _STARTUP_GRACE_SECONDS:
                return process.pid
        else:
            ready_since = None
        if now >= deadline:
            break
        time.sleep(0.1)

    with contextlib.suppress(ProcessLookupError):
        process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
    raise RuntimeError(
        f"Gateway process (pid={process.pid}) did not report readiness. "
        f"Check {service.log_file} for details."
    )


def _pid_is_running(pid: int) -> bool:
    if sys.platform == "win32":
        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            return False
        try:
            exit_code = ctypes.c_ulong()
            if kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
                return exit_code.value == 259  # STILL_ACTIVE
            return False
        finally:
            kernel32.CloseHandle(handle)
    else:
        try:
            os.kill(pid, 0)
        except OSError:
            return False
        return True


def _iter_workspace_gateway_pids(workspace: str | Path | None = None) -> list[int]:
    root = str(get_workspace_root(workspace))
    if sys.platform == "win32":
        try:
            result = subprocess.run(
                ["wmic", "process", "where",
                 f"commandline like '%-m ohmo gateway run%' and commandline like '%--workspace {root}%'",
                 "get", "processid"],
                capture_output=True, text=True, check=True,
            )
        except Exception:
            return []
        current_pid = os.getpid()
        pids: list[int] = []
        for line in result.stdout.splitlines():
            line = line.strip()
            if not line or line.lower() == "processid":
                continue
            try:
                pid = int(line)
            except ValueError:
                continue
            if pid == current_pid:
                continue
            if _pid_is_running(pid):
                pids.append(pid)
        return pids
    else:
        try:
            result = subprocess.run(
                ["ps", "-eo", "pid=,args="],
                capture_output=True,
                text=True,
                check=True,
            )
        except Exception:
            return []

        current_pid = os.getpid()
        pids = []
        for line in result.stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                pid_text, args = line.split(None, 1)
                pid = int(pid_text)
            except ValueError:
                continue
            if pid == current_pid:
                continue
            if "-m ohmo gateway run" not in args:
                continue
            if f"--workspace {root}" not in args:
                continue
            if _pid_is_running(pid):
                pids.append(pid)
        return pids


def stop_gateway_process(cwd: str | Path | None = None, workspace: str | Path | None = None) -> bool:
    """Stop the background gateway process if present."""
    service = OhmoGatewayService(cwd, workspace)
    pids: list[int] = []
    if service.pid_file.exists():
        try:
            pids.append(int(service.pid_file.read_text(encoding="utf-8").strip()))
        except ValueError:
            pass
    pids.extend(_iter_workspace_gateway_pids(workspace))
    unique_pids = []
    for pid in pids:
        if pid not in unique_pids and _pid_is_running(pid):
            unique_pids.append(pid)
    if not unique_pids:
        service.pid_file.unlink(missing_ok=True)
        return False
    if sys.platform == "win32":
        for pid in unique_pids:
            with contextlib.suppress(Exception):
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(pid)],
                    capture_output=True,
                    check=False,
                )
    else:
        for pid in unique_pids:
            with contextlib.suppress(ProcessLookupError):
                os.kill(pid, signal.SIGTERM)
    service.pid_file.unlink(missing_ok=True)
    service.write_state(running=False)
    return True


def gateway_status(cwd: str | Path | None = None, workspace: str | Path | None = None) -> GatewayState:
    """Load the last known gateway state."""
    service = OhmoGatewayService(cwd, workspace)
    live_pid: int | None = None
    if service.pid_file.exists():
        try:
            pid = int(service.pid_file.read_text(encoding="utf-8").strip())
        except ValueError:
            pid = None
        if pid is not None and _pid_is_running(pid):
            live_pid = pid
    if live_pid is None:
        live_pids = _iter_workspace_gateway_pids(workspace)
        if live_pids:
            live_pid = live_pids[0]
            service.pid_file.write_text(str(live_pid), encoding="utf-8")
        else:
            service.pid_file.unlink(missing_ok=True)

    state = _read_gateway_state(service.state_file)

    return GatewayState(
        running=live_pid is not None,
        pid=live_pid,
        active_sessions=state.active_sessions if state else 0,
        provider_profile=service._config.provider_profile,
        enabled_channels=service._config.enabled_channels,
        last_error=state.last_error if state else None,
    )
