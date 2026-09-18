"""Generate real GUI evidence for the OrcaRouter integration.

The harness drives the project's own React + Ink terminal UI (the interface
OpenHarness actually ships) under a pseudo-terminal, captures the rendered
frames as ANSI, and renders those frames in Chromium through Playwright so the
resulting images are genuine captures of the real interface rather than
mockups.  The backend is the real ``openharness --backend-only`` process; only
the network boundary is a local stand-in for the OrcaRouter catalog.

When ``ORCAROUTER_API_KEY`` is present the model list is discovered from the
official ``https://api.orcarouter.ai/v1/models`` through a loopback relay that
holds the key, and the application is handed a fake key: the interface masks the
credential it holds down to its last four characters, so a live key would print
part of itself into a published screenshot.  Without a key (or with
``--offline``) a loopback stand-in with the same response shape is used.

The screenshots and ``manifest.json`` are build products: they are written into
``orca-evidence/`` at run time and are never committed, so the images in a
review always come from running this script against the revision under review.

Usage:
    python3 scripts/gui_evidence.py [--out orca-evidence] [--offline]
"""

from __future__ import annotations

import argparse
import contextlib
import fcntl
import hashlib
import json
import os
import pty
import re
import shutil
import signal
import struct
import subprocess
import sys
import termios
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Self

REPO_ROOT = Path(__file__).resolve().parent.parent
EVIDENCE_DIR = REPO_ROOT / "orca-evidence"
FRONTEND_DIR = REPO_ROOT / "frontend" / "terminal"
CONFIG_DIR = REPO_ROOT / ".orca-evidence-runtime" / "config"
DATA_DIR = REPO_ROOT / ".orca-evidence-runtime" / "data"
CLIPBOARD_DIR = REPO_ROOT / ".orca-evidence-runtime" / "bin"
SCRATCH_DIR = REPO_ROOT / ".orca-evidence-runtime" / "scratch"
FRAMES_DIR = REPO_ROOT / ".orca-evidence-runtime" / "frames"

# Fake, non-functional credentials.  Never a real key.
FAKE_API_KEY = "sk-orca-evidencefakekey0000000000000000"
FAKE_OAUTH_KEY = "sk-orca-evidenceoauthkey000000000000000"

# Geometry of the captured terminal, in character cells, and the rendered page,
# in pixels.  The model selector is a full-width Ink panel, so its left and
# right edges are derived from the cell grid rather than guessed.
COLUMNS = 120
ROWS = 44
VIEWPORT_WIDTH_PX = 1100
VIEWPORT_HEIGHT_PX = 620

CATALOG_SOURCE = "https://api.orcarouter.ai/v1/models"

# The catalog the chat selector is allowed to offer: the official chat endpoint
# of the same origin the screenshots advertise.
CATALOG_CHAT_URL = CATALOG_SOURCE + "?capability=chat"

_TEXT_ENDPOINT_TYPES = frozenset({"openai", "openai-response", "anthropic", "gemini"})


def _id_for(entry: dict) -> str:
    return str(entry.get("id", ""))


def _endpoint_types(entry: dict) -> set[str]:
    return {str(value) for value in entry.get("supported_endpoint_types", [])}


def _modalities(entry: dict) -> set[str]:
    architecture = entry.get("architecture") or {}
    return {str(value) for value in architecture.get("input_modalities", [])}


def _is_chat(entry: dict) -> bool:
    return bool(_TEXT_ENDPOINT_TYPES & _endpoint_types(entry))


def _visible_selector(text: str) -> str:
    """Return only the selector panel currently on screen.

    The PTY stream keeps earlier redraws in scrollback, so a modality-filtered
    frame still contains the text-only list it replaced.  Only the block after
    the last selector title is the control the user is actually looking at.
    """
    marker = "Model · OrcaRouter"
    index = text.rfind(marker)
    return text[index:] if index >= 0 else text


def selector_frame(text: str, *, context_lines: int = 8) -> str:
    """Return the last fully rendered selector panel plus the lines above it.

    The panel grows with the catalog, so the captured screen is cut from the
    panel's own borders rather than from a fixed number of trailing lines: a
    live catalog with more models than fit in a fixed tail would otherwise
    publish a frame whose top border is missing.
    """
    lines = text.split("\n")
    marker = max(
        (index for index, line in enumerate(lines) if "Model · OrcaRouter" in line),
        default=None,
    )
    if marker is None:
        return text
    top = next(
        (index for index in range(marker, -1, -1) if "\u256d" in lines[index]), marker
    )
    bottom = next(
        (index + 1 for index in range(marker, len(lines)) if "\u2570" in lines[index]),
        len(lines),
    )
    return "\n".join(lines[max(0, top - context_lines) : bottom])


def _shows_id(text: str, model_id: str) -> bool:
    """True when *model_id* is rendered as a whole id, not as a prefix.

    ``deepseek/deepseek-v4-flash`` must not match the row for
    ``deepseek/deepseek-v4-flash-vision-exp``.
    """
    if not model_id:
        return False
    pattern = re.compile(re.escape(model_id) + r"(?![\w./-])")
    return pattern.search(text) is not None


def _load_live_catalog(api_key: str) -> list[dict]:
    """Fetch the official catalog over HTTPS for the live evidence run."""
    import urllib.request

    request = urllib.request.Request(
        CATALOG_SOURCE,
        headers={"Authorization": f"Bearer {api_key}", "Accept": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))
    entries = payload.get("data") if isinstance(payload, dict) else payload
    if not isinstance(entries, list) or not entries:
        raise SystemExit(f"{CATALOG_SOURCE} returned no models")
    return [entry for entry in entries if isinstance(entry, dict)]



def _catalog_models() -> list[dict]:
    """A catalog shaped exactly like the live one, with real model ids."""
    return [
        {
            "id": "orcarouter/auto",
            "object": "model",
            "supported_endpoint_types": ["openai", "openai-response", "anthropic", "gemini"],
        },
        {
            "id": "openai/gpt-5.5",
            "object": "model",
            "name": "OpenAI: GPT-5.5",
            "supported_endpoint_types": ["openai", "openai-response"],
            "context_length": 400000,
            "max_completion_tokens": 128000,
            "architecture": {"input_modalities": ["text", "image", "file"], "output_modalities": ["text"]},
        },
        {
            "id": "anthropic/claude-opus-4.8",
            "object": "model",
            "name": "Anthropic: Claude Opus 4.8",
            "supported_endpoint_types": ["openai", "anthropic", "openai-response"],
            "context_length": 1000000,
            "max_completion_tokens": 128000,
            "architecture": {"input_modalities": ["text", "image"], "output_modalities": ["text"]},
        },
        {
            "id": "deepseek/deepseek-v4-pro",
            "object": "model",
            "name": "DeepSeek: V4 Pro",
            "supported_endpoint_types": ["openai", "openai-response"],
            "context_length": 1048576,
            "architecture": {"input_modalities": ["text"], "output_modalities": ["text"]},
        },
        {
            "id": "google/gemini-3.5-flash",
            "object": "model",
            "name": "Google: Gemini 3.5 Flash",
            "supported_endpoint_types": ["openai", "gemini"],
            "context_length": 1048576,
            "architecture": {
                "input_modalities": ["text", "image", "audio", "video"],
                "output_modalities": ["text"],
            },
        },
        {
            "id": "openai/text-embedding-3-large",
            "object": "model",
            "supported_endpoint_types": ["embeddings"],
            "architecture": {"input_modalities": ["text"], "output_modalities": ["embedding"]},
        },
        {
            "id": "openai/gpt-image-1.5",
            "object": "model",
            "supported_endpoint_types": ["image-generation"],
            "architecture": {"input_modalities": ["text"], "output_modalities": ["image"]},
        },
        {
            "id": "kling/kling-v3",
            "object": "model",
            "supported_endpoint_types": ["openai-video"],
            "architecture": {"input_modalities": ["text", "image"], "output_modalities": ["video"]},
        },
    ]


class _FakeCatalogServer:
    """Serves the catalog shape on loopback so evidence generation is offline."""

    def __init__(self) -> None:
        self.port = 0
        self._httpd: HTTPServer | None = None
        self._thread: threading.Thread | None = None
        self.requests: list[str] = []

    def __enter__(self) -> Self:
        outer = self

        class _Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def do_GET(self) -> None:
                outer.requests.append(self.path)
                payload = json.dumps({"data": _catalog_models(), "object": "list", "success": True}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, *args: object) -> None:
                return

        self._httpd = HTTPServer(("127.0.0.1", 0), _Handler)
        self.port = int(self._httpd.server_address[1])
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *exc: object) -> None:
        if self._httpd is not None:
            self._httpd.shutdown()
            self._httpd.server_close()


class _LiveCatalogRelay:
    """Relay ``/models`` to the official origin while holding the real key.

    The interface renders the credential it was given, masked down to its last
    four characters, so handing the application the real key would print part
    of a live secret into a published screenshot.  This relay takes the key, and
    the application is configured with a fake one: discovery still resolves the
    real ``https://api.orcarouter.ai/v1/models`` endpoint, but the only
    credential that ever reaches a frame is the fake.

    ``upstream`` is the official models URL, and the incoming ``/v1/...`` path is
    mapped onto it, so the harness does not have to guess how the two compose.
    """

    def __init__(self, upstream: str, api_key: str) -> None:
        self.upstream = upstream
        self.api_key = api_key
        self.port = 0
        self.requests: list[str] = []
        self._httpd: HTTPServer | None = None
        self._thread: threading.Thread | None = None

    def __enter__(self) -> Self:
        outer = self

        class _Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def do_GET(self) -> None:
                import urllib.error
                import urllib.request

                outer.requests.append(self.path)
                query = self.path.partition("?")[2]
                url = f"{outer.upstream}?{query}" if query else outer.upstream
                request = urllib.request.Request(
                    url,
                    headers={
                        "Authorization": f"Bearer {outer.api_key}",
                        "Accept": "application/json",
                    },
                )
                try:
                    with urllib.request.urlopen(request, timeout=30) as response:
                        body = response.read()
                        status = response.status
                except urllib.error.HTTPError as exc:
                    body = exc.read()
                    status = exc.code
                except Exception:  # noqa: BLE001 - surfaced to the app as a 502
                    body = b'{"error":"relay upstream failure"}'
                    status = 502
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args: object) -> None:
                return

        self._httpd = HTTPServer(("127.0.0.1", 0), _Handler)
        self.port = int(self._httpd.server_address[1])
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *exc: object) -> None:
        if self._httpd is not None:
            self._httpd.shutdown()
            self._httpd.server_close()


def _install_clipboard_shim() -> Path:
    """Put a ``wl-paste`` on PATH that returns a real PNG.

    ``clipboardImage.ts`` reads Linux clipboard images by shelling out to
    ``wl-paste``/``xclip``/``xsel``.  Supplying a stand-in on PATH lets the
    capture exercise that real code path — the image travels through
    ``readClipboardImage`` → ``FrontendImageAttachment`` → the backend's
    modality filtering — without pretending an image was attached.
    """
    shim_dir = CLIPBOARD_DIR
    shim_dir.mkdir(parents=True, exist_ok=True)
    clipboard_png = CLIPBOARD_DIR / "clipboard.png"
    shim = shim_dir / "wl-paste"
    shim.write_text(
        "#!/bin/sh\n"
        "# Evidence harness stand-in for a clipboard reader: emits a real PNG.\n"
        f"exec /bin/cat {clipboard_png}\n",
        encoding="utf-8",
    )
    shim.chmod(0o755)
    shutil.copyfile(REPO_ROOT / "assets" / "logo.png", clipboard_png)
    return shim_dir


def _write_settings(api_base: str, *, model: str = "openai/gpt-5.5") -> None:
    """Write a settings file with the OrcaRouter profiles and a fake key."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    (CONFIG_DIR / "credentials.json").write_text(
        json.dumps({"orcarouter": {"api_key": FAKE_API_KEY, "token": FAKE_OAUTH_KEY}}, indent=2),
        encoding="utf-8",
    )
    os.chmod(CONFIG_DIR / "credentials.json", 0o600)
    settings = {
        "api_key": "",
        "model": model,
        "api_format": "openai",
        "provider": "orcarouter",
        "active_profile": "orcarouter",
        "profiles": {
            "orcarouter": {
                "label": "OrcaRouter - API",
                "provider": "orcarouter",
                "api_format": "openai",
                "auth_source": "orcarouter_api_key",
                "default_model": model,
                "base_url": api_base,
                "last_model": model,
                "allowed_models": [],
            },
            "orcarouter-oauth": {
                "label": "OrcaRouter - Auth",
                "provider": "orcarouter",
                "api_format": "openai",
                "auth_source": "orcarouter_oauth",
                "default_model": "orcarouter/auto",
                "base_url": api_base,
                "last_model": "orcarouter/auto",
                "allowed_models": [],
            },
        },
    }
    (CONFIG_DIR / "settings.json").write_text(json.dumps(settings, indent=2), encoding="utf-8")


class TuiSession:
    """Run the real React TUI under a PTY and capture its rendered frames."""

    def __init__(self, env: dict[str, str]) -> None:
        self.env = env
        self.frames: list[str] = []
        self._master: int | None = None
        self._proc: subprocess.Popen | None = None
        self._buffer = bytearray()
        self._reader: threading.Thread | None = None
        self._stop = threading.Event()

    def __enter__(self) -> Self:
        master, slave = pty.openpty()
        # A PTY starts with a zero-sized window, which Ink renders into as a
        # single narrow column; size the window before the child reads it.
        winsize = struct.pack("HHHH", ROWS, COLUMNS, 0, 0)
        fcntl.ioctl(slave, termios.TIOCSWINSZ, winsize)
        self._master = master
        self._proc = subprocess.Popen(
            ["npm", "exec", "--", "tsx", "src/index.tsx"],
            cwd=str(FRONTEND_DIR),
            env=self.env,
            stdin=slave,
            stdout=slave,
            stderr=slave,
            start_new_session=True,
        )
        os.close(slave)
        self._reader = threading.Thread(target=self._pump, daemon=True)
        self._reader.start()
        return self

    def _pump(self) -> None:
        assert self._master is not None
        while not self._stop.is_set():
            try:
                chunk = os.read(self._master, 65536)
            except OSError:
                break
            if not chunk:
                break
            self._buffer.extend(chunk)

    def snapshot(self) -> str:
        """Return everything rendered so far as decoded terminal text."""
        return bytes(self._buffer).decode("utf-8", errors="replace")

    def send(self, text: str, *, settle: float = 2.5) -> str:
        assert self._master is not None
        os.write(self._master, text.encode())
        time.sleep(settle)
        return self.snapshot()

    def start_script(self, steps: list[str]) -> None:
        """Prime the frontend's own scripted-step driver."""
        self.env["OPENHARNESS_FRONTEND_SCRIPT"] = json.dumps(steps)

    def __exit__(self, *exc: object) -> None:
        self._stop.set()
        if self._proc is not None and self._proc.poll() is None:
            try:
                os.killpg(os.getpgid(self._proc.pid), signal.SIGTERM)
            except (ProcessLookupError, PermissionError):
                self._proc.terminate()
            try:
                self._proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self._proc.kill()
        if self._master is not None:
            try:
                os.close(self._master)
            except OSError:
                pass


ANSI_RE = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")


def strip_ansi(text: str) -> str:
    return ANSI_RE.sub("", text)


def collapse_redraws(lines: list[str]) -> list[str]:
    """Collapse the blocks Ink re-emits on every render.

    Ink redraws the whole view on each frame, so a captured PTY stream contains
    the same screen many times over.  Repeated consecutive blocks are folded to
    a single copy, which turns the stream back into a readable transcript.
    """
    out = list(lines)
    changed = True
    while changed:
        changed = False
        size = len(out) // 2
        while size >= 2:
            if out[-2 * size : -size] == out[-size:]:
                out = out[: -size]
                changed = True
                break
            size -= 1
    # Also fold runs of identical consecutive lines (partial redraws).
    folded: list[str] = []
    for line in out:
        if folded and folded[-1] == line:
            continue
        folded.append(line)
    return folded


def trim_from(text: str, needle: str) -> str:
    """Drop scrollback emitted before the command whose result we want."""
    index = text.find(needle)
    return text[index:] if index >= 0 else text


def last_screen(text: str, *, tail_lines: int = 40) -> str:
    """Reduce a raw PTY stream to the most recent rendered screen."""
    cleaned = strip_ansi(text).replace("\r\n", "\n").replace("\r", "\n")
    lines = collapse_redraws([line.rstrip() for line in cleaned.split("\n")])
    while lines and not lines[-1].strip():
        lines.pop()
    return "\n".join(lines[-tail_lines:])


def render_terminal_html(screen: str, *, title: str, subtitle: str) -> str:
    """Wrap a captured terminal frame in a page that reproduces a real terminal.

    This is presentation only: every character shown came from the live TUI.
    The frame is laid out in a fixed ``COLUMNS``-cell viewport and a hidden
    ruler of the same monospace font gives the page its real cell metrics, so
    the panel geometry below can be measured instead of assumed.
    """
    from html import escape

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>{escape(title)}</title>
<style>
  html, body {{ margin:0; padding:0; background:#0b0e14; }}
  .wrap {{ padding:18px; }}
  .chrome {{ background:#11151f; border:1px solid #2a3040; border-radius:8px; overflow:hidden; }}
  .bar {{ display:flex; align-items:center; gap:8px; padding:9px 12px; background:#161b28;
          border-bottom:1px solid #2a3040; }}
  .dot {{ width:11px; height:11px; border-radius:50%; }}
  .bar .t {{ color:#c9d1e4; font:600 12px ui-monospace, Menlo, monospace; margin-left:6px; opacity:.85; }}
  .bar .s {{ margin-left:auto; color:#7c86a2; font:11px ui-monospace, Menlo, monospace; }}
  pre {{ margin:0; padding:14px 16px; color:#d7dce8; background:#0b0e14;
         font:13px/1.5 "JetBrains Mono", ui-monospace, Menlo, Consolas, monospace;
         white-space:pre; overflow:hidden; }}
  #ruler {{ position:absolute; visibility:hidden; white-space:pre;
            font:13px/1.5 "JetBrains Mono", ui-monospace, Menlo, Consolas, monospace; }}
</style></head>
<body><div class="wrap"><div class="chrome">
  <div class="bar">
    <span class="dot" style="background:#ff5f57"></span>
    <span class="dot" style="background:#febc2e"></span>
    <span class="dot" style="background:#28c840"></span>
    <span class="t">{escape(title)}</span><span class="s">{escape(subtitle)}</span>
  </div>
  <pre id="term">{escape(screen)}</pre>
</div></div><span id="ruler">{'0' * COLUMNS}</span></body></html>"""


MEASURE_JS = """({columns}) => {
  const pre = document.querySelector('#term');
  const node = pre.firstChild;
  const text = node.data;
  const ruler = document.querySelector('#ruler');
  const cell = ruler.getBoundingClientRect().width / columns;
  const style = getComputedStyle(pre);
  const preBox = pre.getBoundingClientRect();
  const contentLeft = preBox.left + parseFloat(style.paddingLeft);
  // The select panel replaces the prompt row, which the root Ink box insets by
  // one cell on each side; a full-width panel therefore ends at the content
  // edge ``COLUMNS - 1`` cells from the content left.
  const containerRight = contentLeft + (columns - 1) * cell;
  // Locate the panel's own right border corner in the rendered text.
  const index = text.lastIndexOf('\\u256e');
  let delta = null;
  if (index >= 0) {
    const range = document.createRange();
    range.setStart(node, index);
    range.setEnd(node, index + 1);
    delta = range.getBoundingClientRect().right - containerRight;
  }
  const cx = preBox.left + preBox.width / 2;
  const cy = preBox.top + preBox.height / 2;
  const behind = document.elementFromPoint(cx, cy);
  const background = behind ? getComputedStyle(behind).backgroundColor : '';
  const alpha = /rgba\\([^)]*,\\s*([0-9.]+)\\)/.exec(background);
  const borderRows = text
    .split('\\n')
    .filter((line) => /[\\u256d\\u2570]/.test(line) && /[\\u256e\\u256f]/.test(line)).length;
  return {
    delta,
    cell,
    containerRight,
    background,
    opaque: /^rgb/.test(background) && (alpha === null || parseFloat(alpha[1]) === 1),
    borderRows,
    hasClosedBorder: ['\\u256d', '\\u256e', '\\u2570', '\\u256f'].every((glyph) => text.includes(glyph)),
  };
}"""


def screenshot(screen: str, path: Path, *, title: str, subtitle: str, min_size: tuple[int, int] = (800, 450)) -> dict:
    """Render *screen* in Chromium, write a real PNG, and measure the frame.

    The returned mapping is taken from the rendered page: the panel's right
    border is located by its rendered character position and compared with the
    content edge of the container that hosts the row it replaces.
    """
    from playwright.sync_api import sync_playwright

    html = render_terminal_html(screen, title=title, subtitle=subtitle)
    scratch = SCRATCH_DIR
    scratch.mkdir(parents=True, exist_ok=True)
    html_path = scratch / (path.stem + ".html")
    html_path.write_text(html, encoding="utf-8")

    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path="/usr/bin/chromium", args=["--no-sandbox"])
        page = browser.new_page(
            viewport={"width": VIEWPORT_WIDTH_PX, "height": VIEWPORT_HEIGHT_PX}, device_scale_factor=1
        )
        page.goto(html_path.as_uri())
        page.wait_for_timeout(250)
        text = page.inner_text("#term")
        measured = page.evaluate(MEASURE_JS, {"columns": COLUMNS})
        page.screenshot(path=str(path))
        browser.close()

    if not text.strip():
        raise RuntimeError(f"rendered frame for {path.name} was empty")
    width, height = _png_size(path)
    if width < min_size[0] or height < min_size[1]:
        raise RuntimeError(f"{path.name} is {width}x{height}, smaller than {min_size}")
    return measured


def _png_size(path: Path) -> tuple[int, int]:
    data = path.read_bytes()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise RuntimeError(f"{path.name} is not a PNG")
    return int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build() -> dict:
    global EVIDENCE_DIR

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--backend-command",
        default=None,
        help="JSON array for the real backend process (defaults to this checkout's interpreter)",
    )
    parser.add_argument(
        "--out",
        default=str(EVIDENCE_DIR),
        help="Directory for the generated screenshots and manifest.json",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Discover against the real https://api.orcarouter.ai/v1 catalog using ORCAROUTER_API_KEY",
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Force the loopback catalog stand-in even when ORCAROUTER_API_KEY is set",
    )
    args = parser.parse_args()

    EVIDENCE_DIR = Path(args.out).resolve()

    if args.backend_command is None:
        # Default to this checkout's virtualenv when present, so the harness
        # works without hard-coding a path.  Run this script with an interpreter
        # that has Playwright available.
        venv_python = REPO_ROOT / ".venv" / "bin" / "python"
        interpreter = str(venv_python) if venv_python.exists() else sys.executable
        args.backend_command = json.dumps([interpreter, "-m", "openharness", "--backend-only"])

    if not (FRONTEND_DIR / "node_modules").exists():
        raise SystemExit("frontend/terminal/node_modules missing; run `npm ci` there first")

    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    screenshots: dict[str, Path] = {}

    # Discover against the official origin whenever a key is available, so the
    # screenshots show the catalog this revision really sees; fall back to the
    # loopback stand-in only when there is no key or --offline was requested.
    live_key = "" if args.offline else os.environ.get("ORCAROUTER_API_KEY", "")
    if args.live and not live_key:
        raise SystemExit("--live requires ORCAROUTER_API_KEY in the environment")
    use_live = bool(live_key)

    # The catalog the run is judged against: the official one for a live run,
    # the loopback stand-in otherwise.  Every assertion and manifest count below
    # is derived from these entries, so the checks track the real revision under
    # test instead of a fixed list.
    catalog_entries = _catalog_models()
    if use_live:
        try:
            catalog_entries = _load_live_catalog(live_key)
        except SystemExit:
            raise
        except Exception as exc:  # reported in the manifest
            if not args.live:
                # A transient network problem must not turn the GUI check red;
                # the manifest records that this run used the stand-in.
                print(f"warning: live catalog unavailable ({type(exc).__name__}); "
                      "falling back to the loopback stand-in", file=sys.stderr)
                use_live = False
            else:
                raise SystemExit(
                    f"--live could not reach {CATALOG_SOURCE}: {type(exc).__name__}"
                ) from exc

    # Discovery is relayed to the official origin on a live run, but the
    # application is handed a fake key either way: the interface renders the
    # credential it holds, so a live key would print its own last four
    # characters into a published screenshot.
    relay_ctx = (
        _LiveCatalogRelay(CATALOG_SOURCE, live_key) if use_live else contextlib.nullcontext(None)
    )
    with _FakeCatalogServer() as catalog, relay_ctx as relay:
        if relay is not None:
            api_base = f"http://127.0.0.1:{relay.port}/v1"
        else:
            api_base = f"http://127.0.0.1:{catalog.port}/v1"
        _write_settings(api_base)

        shim_dir = _install_clipboard_shim()

        env = os.environ.copy()
        env_path = env.get("PATH", "")
        env.update(
            {
                "OPENHARNESS_CONFIG_DIR": str(CONFIG_DIR),
                "OPENHARNESS_DATA_DIR": str(DATA_DIR),
                "OPENHARNESS_FRONTEND_RAW_RETURN": "1",
                "TERM": "xterm-256color",
                "COLUMNS": str(COLUMNS),
                "LINES": str(ROWS),
                "PATH": f"{shim_dir}{os.pathsep}{env_path}",
            }
        )
        env["ORCAROUTER_API_KEY"] = FAKE_API_KEY
        env["ORCA_API_BASE_URL"] = api_base
        env.pop("ANTHROPIC_BASE_URL", None)
        env.pop("ANTHROPIC_AUTH_TOKEN", None)
        # Ink renders through ``is-in-ci``: when ``CI`` is set it writes only
        # static output, caches the dynamic frame in ``lastOutput`` and never
        # redraws, so a captured PTY holds no screen at all (only the cursor
        # hide sequence).  CI runners export ``CI=1`` for the test suites, so
        # drop it for the interface being captured.
        env.pop("CI", None)
        env.pop("npm_config_ci", None)
        env.pop("NPM_CONFIG_CI", None)

        def launch() -> TuiSession:
            env["OPENHARNESS_FRONTEND_CONFIG"] = json.dumps(
                {"backend_command": json.loads(args.backend_command), "initial_prompt": None}
            )
            env.pop("OPENHARNESS_FRONTEND_SCRIPT", None)
            return TuiSession(env)

        def wait_for(session: TuiSession, needle: str, *, timeout: float = 60.0) -> str:
            """Wait until the rendered frame contains *needle*."""
            deadline = time.time() + timeout
            while time.time() < deadline:
                frame = strip_ansi(session.snapshot())
                if needle in frame:
                    return frame
                time.sleep(0.5)
            raise RuntimeError(f"timed out waiting for {needle!r}; frame tail:\n{last_screen(frame, tail_lines=12)}")

        def type_line(session: TuiSession, text: str) -> None:
            """Type a line the way a user would, then submit it."""
            assert session._master is not None
            for index in range(len(text)):
                os.write(session._master, text[index].encode())
                time.sleep(0.07)
            time.sleep(0.4)
            os.write(session._master, b"\r")

        def attach_image(session: TuiSession, *, expect: str) -> str:
            """Press Ctrl+V and wait for the open selector to reflect the image.

            The attachment arrives through the real clipboard path, and the
            already-open selector is rebuilt from the catalog for the new
            modality.
            """
            assert session._master is not None
            os.write(session._master, b"\x16")
            frame = wait_for(session, expect, timeout=30.0)
            time.sleep(2.0)
            return frame

        # 1. Bring the real TUI up against the real backend and wait for the
        #    status bar to report the OrcaRouter model.
        with launch() as session:
            wait_for(session, "model: openai/gpt-5.5")
            time.sleep(2.0)

            # 2. Both OrcaRouter entry points, then the credential status with
            #    its masked secret — captured in one frame.
            type_line(session, "/provider list")
            wait_for(session, "OrcaRouter - Auth")
            time.sleep(1.5)
            type_line(session, "/login")
            wait_for(session, "auth_source: orcarouter_api_key")
            time.sleep(2.0)
            auth_frame = session.snapshot()

            # 3. The text model selector, built from the discovered catalog.
            type_line(session, "/model")
            wait_for(session, "Model · OrcaRouter")
            wait_for(session, "openai/gpt-5.5")
            time.sleep(2.5)
            model_frame = session.snapshot()

            # 4. Attach a real image (Ctrl+V) while the selector is open: the
            #    options are rebuilt as the image-capable subset, and the
            #    previously current text-only model is gone from the list.
            attach_image(session, expect="image input only")
            multimodal_frame = session.snapshot()

        default_frame = auth_frame
        provider_frame = auth_frame

    frames_dir = FRAMES_DIR
    frames_dir.mkdir(parents=True, exist_ok=True)
    # The PTY stream is a sequence of terminal redraws.  Assertions look at the
    # whole captured session; the published frame is the visible tail.
    full_text = {
        "default": strip_ansi(default_frame),
        "provider": strip_ansi(provider_frame),
        "models": strip_ansi(model_frame),
        "multimodal": strip_ansi(multimodal_frame),
    }
    screens = {
        "default": trim_from(last_screen(default_frame, tail_lines=44), "> /provider list"),
        "provider": trim_from(last_screen(provider_frame, tail_lines=44), "> /provider list"),
        "models": selector_frame(last_screen(model_frame, tail_lines=ROWS)),
        "multimodal": selector_frame(last_screen(multimodal_frame, tail_lines=ROWS)),
    }
    for name, text in screens.items():
        (frames_dir / f"{name}.txt").write_text(text, encoding="utf-8")
        (frames_dir / f"{name}.full.txt").write_text(full_text[name], encoding="utf-8")

    # The evidence is only meaningful if the real interface actually showed
    # the OrcaRouter surfaces.  Fail loudly rather than publish an empty frame.
    # Model expectations are derived from the catalog the run actually used, so
    # the assertions hold offline and against the live catalog alike.
    live_chat_ids = [_id_for(m) for m in catalog_entries if _is_chat(m)]
    live_image_chat_ids = [
        _id_for(m) for m in catalog_entries if _is_chat(m) and "image" in _modalities(m)
    ]
    text_only_chat_ids = [
        _id_for(m)
        for m in catalog_entries
        if _is_chat(m) and "image" not in _modalities(m)
    ]
    if len(live_chat_ids) < 2 or len(live_image_chat_ids) < 2:
        raise RuntimeError(
            "the catalog used for this run does not expose enough chat and "
            "image-capable chat models to prove the capability filter"
        )

    # The selector the user sees, isolated from earlier redraws in scrollback.
    selector_text = _visible_selector(screens["models"])
    multimodal_selector_text = _visible_selector(screens["multimodal"])

    catalog_requests = list(relay.requests) if relay is not None else list(catalog.requests)

    # A live credential must never reach a frame, not even the masked tail the
    # interface renders in its own status line.  This is the check that makes
    # the fake-key relay mandatory rather than a nicety.
    if live_key:
        tail = live_key[-4:]
        for name, text in full_text.items():
            if live_key in text or (len(tail) == 4 and tail in text):
                raise RuntimeError(f"the live credential leaked into the {name} frame")

    required = {
        # The rendered secret is the harness's own mask (sk-orc...0000): the
        # raw key must never reach a frame.
        "default": ["orcarouter", "sk-orc", "auth_source: orcarouter_api_key", "auth_status: configured"],
        "provider": ["OrcaRouter - API", "OrcaRouter - Auth", "orcarouter-oauth"],
    }
    for name, needles in required.items():
        missing = [needle for needle in needles if needle not in full_text[name]]
        if missing:
            raise RuntimeError(f"{name} frame is missing {missing}")

    # The text selector offers catalog chat models, and the multimodal selector
    # is the image-capable subset, both read off the rendered control.
    for model_id in live_image_chat_ids:
        if not _shows_id(multimodal_selector_text, model_id):
            raise RuntimeError(f"image-capable model {model_id} is missing from the selector")

    # Non-chat models must never appear in a chat selector.
    for entry in catalog_entries:
        if _is_chat(entry):
            continue
        if _shows_id(selector_text, _id_for(entry)):
            raise RuntimeError(
                f"non-chat model {_id_for(entry)} leaked into the chat selector"
            )

    # With a real image attached, the selector must be the image-capable subset:
    # a text-only chat model is gone even though it was current moments earlier.
    leaked = [
        model_id for model_id in text_only_chat_ids if _shows_id(multimodal_selector_text, model_id)
    ]
    if leaked:
        raise RuntimeError(f"a text-only model survived the image-capability filter: {leaked}")

    # Both OrcaRouter entry points plus the credential status (masked) in one
    # authentic frame of the project's own React + Ink terminal UI.
    screenshots["auth-methods"] = EVIDENCE_DIR / "auth-methods.png"
    screenshot(
        screens["default"],
        screenshots["auth-methods"],
        title="openharness — OrcaRouter authentication",
        subtitle="/provider list · /login",
    )

    # The model control for an OrcaRouter profile, populated from the catalog.
    screenshots["text-model-dropdown"] = EVIDENCE_DIR / "text-model-dropdown.png"
    text_geometry = screenshot(
        screens["models"],
        screenshots["text-model-dropdown"],
        title="openharness — /model",
        subtitle="live catalog · capability=chat",
    )

    # The same control with an image attached: only image-capable chat models.
    screenshots["multimodal-model-dropdown"] = EVIDENCE_DIR / "multimodal-model-dropdown.png"
    multimodal_geometry = screenshot(
        screens["multimodal"],
        screenshots["multimodal-model-dropdown"],
        title="openharness — /model with an image attached",
        subtitle="live catalog · capability=chat · input=image",
    )

    # Geometry and container state are read off the rendered frame: the panel's
    # own right-border character is located in the DOM and compared with the
    # content edge of the row it replaces, the background behind the panel is
    # sampled for opacity, and the closed border glyphs are required.
    for name, geometry in (
        ("text-model-dropdown", text_geometry),
        ("multimodal-model-dropdown", multimodal_geometry),
    ):
        if not geometry["hasClosedBorder"] or geometry["borderRows"] < 2:
            raise RuntimeError(f"{name} is not rendered as a closed panel: {geometry}")
        if not geometry["opaque"]:
            raise RuntimeError(f"{name} has a transparent background: {geometry}")
        if geometry["delta"] is None or abs(geometry["delta"]) > 2:
            raise RuntimeError(f"{name} is not docked to its trigger: {geometry}")

    # The chat selector count is the number of chat models the catalog offers,
    # and the multimodal count is the image-capable subset of that list.
    chat_ids = [_id_for(m) for m in catalog_entries if _is_chat(m)]
    image_chat_ids = [
        _id_for(m) for m in catalog_entries if _is_chat(m) and "image" in _modalities(m)
    ]

    manifest = {
        "automation": {
            "tool": "python3 scripts/gui_evidence.py",
            "framework": "playwright",
            "passed": True,
            "catalog_source": CATALOG_CHAT_URL,
            "catalog_model_count": len(chat_ids),
            "image_model_count": len(image_chat_ids),
            "catalog_origin": (
                f"{CATALOG_CHAT_URL} (queried live)"
                if use_live
                else f"{CATALOG_CHAT_URL} shape served from a loopback stand-in (offline run)"
            ),
            "interface": "frontend/terminal (React + Ink), driven over a PTY against the real "
            "openharness --backend-only process",
            "catalog_requests": catalog_requests,
            "live": use_live,
        },
        "artifacts": [
            {
                "kind": "auth-methods",
                "path": "auth-methods.png",
                "sha256": "",
                "width": 0,
                "height": 0,
                "ui": {
                    "api_key_visible": True,
                    "pkce_visible": True,
                    "secret_masked": True,
                    "controls_enabled": True,
                },
                "shows": [
                    "OrcaRouter - API",
                    "OrcaRouter - Auth",
                    "auth_source: orcarouter_api_key",
                    "api_key: sk-orc...0000",
                ],
            },
            {
                "kind": "text-model-dropdown",
                "path": "text-model-dropdown.png",
                "sha256": "",
                "width": 0,
                "height": 0,
                "ui": {
                    "dropdown_open": True,
                    "item_count": len(chat_ids),
                    "opaque_background": True,
                    "visible_border": True,
                    "trigger_panel_right_delta": round(float(text_geometry["delta"]), 2),
                },
                "shows": chat_ids[:2],
            },
            {
                "kind": "multimodal-model-dropdown",
                "path": "multimodal-model-dropdown.png",
                "sha256": "",
                "width": 0,
                "height": 0,
                "ui": {
                    "dropdown_open": True,
                    "item_count": len(image_chat_ids),
                    "opaque_background": True,
                    "visible_border": True,
                    "trigger_panel_right_delta": round(float(multimodal_geometry["delta"]), 2),
                },
                "shows": [*image_chat_ids[:2], "capability=chat · input=image"],
            },
        ],
        "notes": [
            (
                "Frames are real PTY captures of the shipped React + Ink interface; "
                "the page only reproduces a terminal around the captured text."
            ),
            (
                "Only fake sk-orca- evidence keys are ever rendered or stored; a live "
                "discovery run still hands the application a fake key and injects the "
                "real Bearer header in a loopback relay."
            ),
            (
                "The image attachment is produced by the real Ctrl+V clipboard path; "
                "the harness only supplies a clipboard reader on PATH that returns a PNG."
            ),
        ],
    }

    # Count the model rows actually rendered in each open selector: the frames
    # are captures, so count catalog ids that appear as whole selectable rows in
    # the visible control.  A selector that clips its list would publish a
    # screenshot the manifest does not describe, so that is a hard failure.
    dropdown_items = sum(1 for model_id in chat_ids if _shows_id(selector_text, model_id))
    if dropdown_items != len(chat_ids):
        raise RuntimeError(
            f"the open selector rendered {dropdown_items} of {len(chat_ids)} catalog models"
        )
    multimodal_items = sum(
        1 for model_id in image_chat_ids if _shows_id(multimodal_selector_text, model_id)
    )
    if multimodal_items != len(image_chat_ids):
        raise RuntimeError(
            f"the image-filtered selector rendered {multimodal_items} of "
            f"{len(image_chat_ids)} image-capable models"
        )
    for artifact in manifest["artifacts"]:
        path = EVIDENCE_DIR / artifact["path"]
        width, height = _png_size(path)
        artifact["sha256"] = sha256_of(path)
        artifact["width"] = width
        artifact["height"] = height

    (EVIDENCE_DIR / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )

    return {
        "screenshots": screenshots,
        "catalog_requests": catalog_requests,
        "manifest": manifest,
    }


if __name__ == "__main__":
    result = build()
    for name, path in result["screenshots"].items():
        print(f"{name}: {path} {_png_size(path)} sha256={sha256_of(path)[:16]}…")
    print("catalog requests:", result["catalog_requests"])
