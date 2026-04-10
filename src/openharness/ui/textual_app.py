"""Default Textual terminal UI for OpenHarness."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass

from rich.panel import Panel
from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Footer, Header, Input, RichLog, Static

from openharness.api.client import SupportsStreamingMessages
from openharness.config.settings import load_settings, save_settings
from openharness.engine.stream_events import (
    AssistantTextDelta,
    AssistantTurnComplete,
    CompactProgressEvent,
    ErrorEvent,
    StatusEvent,
    StreamEvent,
    ToolExecutionCompleted,
    ToolExecutionStarted,
)
from openharness.tasks import get_task_manager
from openharness.ui.runtime import build_runtime, close_runtime, handle_line, start_runtime


@dataclass(frozen=True)
class AppConfig:
    """Configuration for a terminal app session."""

    prompt: str | None = None
    model: str | None = None
    base_url: str | None = None
    system_prompt: str | None = None
    api_key: str | None = None
    api_client: SupportsStreamingMessages | None = None


class PermissionScreen(ModalScreen[bool]):
    """Simple approval modal for mutating tools."""

    BINDINGS = [
        Binding("escape", "deny", "Deny"),
        Binding("y", "allow", "Allow"),
        Binding("n", "deny", "Deny"),
    ]

    def __init__(self, tool_name: str, reason: str) -> None:
        super().__init__()
        self._tool_name = tool_name
        self._reason = reason

    def compose(self) -> ComposeResult:
        yield Container(
            Static(
                Panel.fit(
                    f"Allow tool [bold]{self._tool_name}[/bold]?\n\n{self._reason}",
                    title="Permission Required",
                )
            ),
            Horizontal(
                Button("Allow", id="allow", variant="success"),
                Button("Deny", id="deny", variant="error"),
                classes="permission-actions",
            ),
            id="permission-dialog",
        )

    @on(Button.Pressed)
    def handle_button_press(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "allow")

    def action_allow(self) -> None:
        self.dismiss(True)

    def action_deny(self) -> None:
        self.dismiss(False)


class QuestionScreen(ModalScreen[str]):
    """Prompt the user for a short answer during tool execution."""

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("enter", "submit", "Submit"),
    ]

    def __init__(self, question: str) -> None:
        super().__init__()
        self._question = question

    def compose(self) -> ComposeResult:
        yield Container(
            Static(
                Panel.fit(
                    self._question,
                    title="Question",
                )
            ),
            Input(placeholder="Type your answer", id="question-input"),
            Horizontal(
                Button("Submit", id="submit", variant="primary"),
                Button("Cancel", id="cancel", variant="default"),
                classes="permission-actions",
            ),
            id="permission-dialog",
        )

    def on_mount(self) -> None:
        self.query_one("#question-input", Input).focus()

    @on(Button.Pressed)
    def handle_button_press(self, event: Button.Pressed) -> None:
        if event.button.id == "submit":
            self.dismiss(self.query_one("#question-input", Input).value.strip())
            return
        self.dismiss("")

    @on(Input.Submitted, "#question-input")
    def handle_submit(self, event: Input.Submitted) -> None:
        self.dismiss(event.value.strip())

    def action_submit(self) -> None:
        self.dismiss(self.query_one("#question-input", Input).value.strip())

    def action_cancel(self) -> None:
        self.dismiss("")


class OpenHarnessTerminalApp(App[None]):
    """Terminal-first Textual UI."""

    CSS = """
    Screen {
        layout: vertical;
    }

    #main-row {
        height: 1fr;
    }

    #transcript-column {
        width: 3fr;
        min-width: 60;
    }

    #side-column {
        width: 1fr;
        min-width: 28;
    }

    #transcript {
        height: 1fr;
        border: solid $accent;
    }

    #current-response {
        min-height: 3;
        max-height: 8;
        border: round $primary;
        padding: 0 1;
    }

    #composer {
        dock: bottom;
        height: 3;
        border: solid $accent;
    }

    #status-bar, #tasks-panel, #mcp-panel {
        border: round $surface;
        padding: 0 1;
        margin-bottom: 1;
    }

    #permission-dialog {
        width: 60;
        height: auto;
        padding: 1 2;
        background: $panel;
        border: round $accent;
    }

    .permission-actions {
        align: center middle;
        height: auto;
        margin-top: 1;
    }
    """

    BINDINGS = [
        Binding("ctrl+l", "clear_conversation", "Clear"),
        Binding("ctrl+r", "refresh_sidebars", "Refresh"),
        Binding("ctrl+k", "toggle_vim", "Vim"),
        Binding("ctrl+v", "toggle_voice", "Voice"),
        Binding("ctrl+d", "quit_session", "Exit"),
    ]

    def __init__(
        self,
        *,
        prompt: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
        system_prompt: str | None = None,
        api_key: str | None = None,
        api_client: SupportsStreamingMessages | None = None,
    ) -> None:
        super().__init__()
        self._config = AppConfig(
            prompt=prompt,
            model=model,
            base_url=base_url,
            system_prompt=system_prompt,
            api_key=api_key,
            api_client=api_client,
        )
        self._bundle = None
        self._assistant_buffer = ""
        self._busy = False
        self.transcript_lines: list[str] = []

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(id="main-row"):
            with Vertical(id="transcript-column"):
                yield RichLog(id="transcript", wrap=True, highlight=True, markup=True)
                yield Static("Ready.", id="current-response")
                yield Input(placeholder="Ask OpenHarness or enter a /command", id="composer")
            with Vertical(id="side-column"):
                yield Static("Starting...", id="status-bar")
                yield Static("No tasks yet.", id="tasks-panel")
                yield Static("No MCP servers configured.", id="mcp-panel")
        yield Footer()

    async def on_mount(self) -> None:
        self._bundle = await build_runtime(
            prompt=self._config.prompt,
            cwd=str(self.app.cwd) if getattr(self.app, 'cwd', None) else None,
            model=self._config.model,
            base_url=self._config.base_url,
            system_prompt=self._config.system_prompt,
            api_key=self._config.api_key,
            api_client=self._config.api_client,
            permission_prompt=self._ask_permission,
            ask_user_prompt=self._ask_question,
        )
        await start_runtime(self._bundle)
        self.query_one("#composer", Input).focus()
        self._refresh_sidebars()
        self.set_interval(1.0, self._refresh_sidebars)
        if self._config.prompt:
            self.call_later(lambda: asyncio.create_task(self._process_line(self._config.prompt or "")))

    async def on_unmount(self) -> None:
        if self._bundle is not None:
            await close_runtime(self._bundle)

    async def _ask_permission(self, tool_name: str, reason: str) -> bool:
        return bool(await self._open_modal(PermissionScreen(tool_name, reason)))

    async def _ask_question(self, question: str) -> str:
        return str(await self._open_modal(QuestionScreen(question)) or "")

    async def _open_modal(self, screen: ModalScreen) -> object:
        loop = asyncio.get_running_loop()
        future: asyncio.Future[object] = loop.create_future()

        def _done(result: object) -> None:
            if not future.done():
                future.set_result(result)

        self.push_screen(screen, callback=_done)
        return await future

    @on(Input.Submitted, "#composer")
    async def handle_submit(self, event: Input.Submitted) -> None:
        event.input.value = ""
        await self._process_line(event.value)

    async def _process_line(self, line: str) -> None:
        if not line.strip() or self._bundle is None or self._busy:
            return
        self._busy = True
        composer = self.query_one("#composer", Input)
        composer.disabled = True
        self._append_line(f"user> {line}")
        self._set_current_response("[dim]Working...[/dim]")
        try:
            should_continue = await handle_line(
                self._bundle,
                line,
                print_system=self._print_system,
                render_event=self._render_event,
                clear_output=self._clear_transcript,
            )
            self._refresh_sidebars()
            if not should_continue:
                self.exit()
        finally:
            self._busy = False
            composer.disabled = False
            composer.focus()

    async def _print_system(self, message: str) -> None:
        self._append_line(f"system> {message}")
        self._set_current_response("Ready.")

    async def _render_event(self, event: StreamEvent) -> None:
        if isinstance(event, AssistantTextDelta):
            self._assistant_buffer += event.text
            self._set_current_response(f"[bold]assistant>[/bold] {self._assistant_buffer}")
            return

        if isinstance(event, CompactProgressEvent):
            if event.phase == "hooks_start":
                if event.trigger == "reactive":
                    self._set_current_response("[dim]Preparing retry compaction...[/dim]")
                else:
                    self._set_current_response("[dim]Preparing conversation compaction...[/dim]")
            elif event.phase == "compact_start":
                if event.trigger == "reactive":
                    self._set_current_response("[dim]Context too large. Compacting and retrying...[/dim]")
                else:
                    self._set_current_response("[dim]Compacting conversation memory...[/dim]")
            elif event.phase == "compact_retry":
                attempt = f" (attempt {event.attempt})" if event.attempt is not None else ""
                self._set_current_response(f"[dim]Retrying compaction{attempt}...[/dim]")
            elif event.phase == "compact_failed":
                self._append_line(f"system> Compaction failed: {event.message or 'unknown error'}")
                self._set_current_response("Ready.")
            elif event.phase == "compact_end":
                self._set_current_response("[dim]Compaction complete.[/dim]")
            elif event.phase == "session_memory_start":
                self._set_current_response("[dim]Condensing earlier conversation...[/dim]")
            elif event.phase == "session_memory_end":
                self._set_current_response("[dim]Condensed earlier conversation.[/dim]")
            elif event.phase == "context_collapse_start":
                self._set_current_response("[dim]Collapsing oversized context...[/dim]")
            elif event.phase == "context_collapse_end":
                self._set_current_response("[dim]Context collapse complete.[/dim]")
            return

        if isinstance(event, AssistantTurnComplete):
            text = self._assistant_buffer or event.message.text or "(empty response)"
            self._append_line(f"assistant> {text}")
            self._assistant_buffer = ""
            self._set_current_response("Ready.")
            return

        if isinstance(event, ToolExecutionStarted):
            payload = json.dumps(event.tool_input, ensure_ascii=False)
            self._append_line(f"tool> {event.tool_name} {payload}")
            return

        if isinstance(event, ToolExecutionCompleted):
            prefix = "tool-error>" if event.is_error else "tool-result>"
            self._append_line(f"{prefix} {event.tool_name}: {event.output}")
            return

        if isinstance(event, ErrorEvent):
            self._append_line(f"error> {event.message}")
            self._assistant_buffer = ""
            self._set_current_response("Ready.")
            return
        if isinstance(event, StatusEvent):
            self._append_line(f"system> {event.message}")

    def action_clear_conversation(self) -> None:
        if self._bundle is None:
            return
        self._bundle.engine.clear()
        self.query_one("#transcript", RichLog).clear()
        self.transcript_lines.clear()
        self._set_current_response("Conversation cleared.")
        self._refresh_sidebars()

    def action_refresh_sidebars(self) -> None:
        self._refresh_sidebars()

    def action_toggle_vim(self) -> None:
        if self._bundle is None:
            return
        current = self._bundle.app_state.get().vim_enabled
        settings = load_settings()
        settings.vim_mode = not current
        save_settings(settings)
        self._bundle.app_state.set(vim_enabled=not current)
        self._refresh_sidebars()

    def action_toggle_voice(self) -> None:
        if self._bundle is None:
            return
        current = self._bundle.app_state.get().voice_enabled
        settings = load_settings()
        settings.voice_mode = not current
        save_settings(settings)
        self._bundle.app_state.set(voice_enabled=not current)
        self._refresh_sidebars()

    def action_quit_session(self) -> None:
        self.exit()

    def _append_line(self, message: str) -> None:
        self.transcript_lines.append(message)
        self.query_one("#transcript", RichLog).write(message)

    async def _clear_transcript(self) -> None:
        self.query_one("#transcript", RichLog).clear()
        self.transcript_lines.clear()

    def _set_current_response(self, message: str) -> None:
        self.query_one("#current-response", Static).update(message)

    def _refresh_sidebars(self) -> None:
        if self._bundle is None:
            return
        state = self._bundle.app_state.get()
        usage = self._bundle.engine.total_usage
        status_lines = [
            "[b]Status[/b]",
            f"model: {state.model}",
            f"permissions: {state.permission_mode}",
            f"fast: {'on' if state.fast_mode else 'off'}",
            f"style: {state.output_style}",
            f"vim: {'on' if state.vim_enabled else 'off'}",
            f"voice: {'on' if state.voice_enabled else 'off'}",
            f"tokens: {usage.total_tokens}",
            f"messages: {len(self._bundle.engine.messages)}",
        ]
        self.query_one("#status-bar", Static).update("\n".join(status_lines))

        tasks = get_task_manager().list_tasks()
        if tasks:
            task_lines = ["[b]Tasks[/b]"]
            for task in tasks[:10]:
                suffix: list[str] = []
                if task.metadata.get("progress"):
                    suffix.append(f"{task.metadata['progress']}%")
                if task.metadata.get("status_note"):
                    suffix.append(task.metadata["status_note"])
                detail = f" ({' | '.join(suffix)})" if suffix else ""
                task_lines.append(f"{task.id} {task.status} {task.description}{detail}")
        else:
            task_lines = ["[b]Tasks[/b]", "No background tasks."]
        self.query_one("#tasks-panel", Static).update("\n".join(task_lines))
        self.query_one("#mcp-panel", Static).update(self._bundle.mcp_summary())
