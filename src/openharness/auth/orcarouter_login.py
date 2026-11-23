"""OAuth 2.0 + PKCE login for OrcaRouter.

The flow follows RFC 7636.  ``S256`` is sent on *both* flows, including the
loopback one: the consent screen lets the user choose "show me a code", so a
client that can be handed a code by a human must always bind the code to this
process with a real challenge.

Two transports are offered:

* **Flow A — loopback redirect** (default).  The CLI binds ``127.0.0.1`` on an
  ephemeral port before opening the browser, so the code comes back
  automatically.  OrcaRouter does not require a pre-registered redirect URI, so
  there is nothing to configure per deployment.
* **Flow B — out-of-band code.**  For sandboxes, containers and locked-down
  machines where a callback cannot be reached; the user reads the code off the
  consent screen and pastes it back.

Neither flow needs a client secret, and neither one reveals the verifier: it
stays in this process until the exchange.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlsplit

from openharness.api.orcarouter import (
    DEFAULT_LOGIN_TIMEOUT,
    DEFAULT_SCOPE,
    OrcaRouterAuthError,
    OrcaRouterCredential,
    build_authorize_url,
    code_challenge_for,
    exchange_code,
    generate_code_verifier,
    generate_state,
    states_match,
)

log = logging.getLogger(__name__)

FLOW_LOOPBACK = "loopback"
FLOW_OOB = "oob"
VALID_FLOWS = (FLOW_LOOPBACK, FLOW_OOB)

CALLBACK_PATH = "/cb"

_CALLBACK_PAGE = (
    "<!doctype html><html><head><meta charset='utf-8'>"
    "<title>OpenHarness</title></head><body "
    "style='font-family:system-ui;margin:4rem auto;max-width:32rem;text-align:center'>"
    "<h1>{heading}</h1><p>{body}</p></body></html>"
)


def _callback_page(heading: str, body: str) -> bytes:
    return _CALLBACK_PAGE.format(heading=heading, body=body).encode("utf-8")


def _try_open_browser(url: str) -> bool:
    """Open *url* in the default browser.  Returns False when it cannot be done.

    Only http(s) URLs are handed to the platform opener: ``xdg-open``/``open``
    resolve unrecognised tokens against PATH, which is an unintended-action
    footgun.
    """
    if urlsplit(url).scheme not in {"http", "https"}:
        return False
    try:
        from openharness.auth.flows import DeviceCodeFlow

        return DeviceCodeFlow._try_open_browser(url)
    except (ImportError, OSError):  # pragma: no cover - opener is best-effort
        return False


class _CallbackServer:
    """A single-shot loopback listener for Flow A."""

    def __init__(self) -> None:
        self._server: HTTPServer | None = None
        self._thread: threading.Thread | None = None
        self._done = threading.Event()
        self.query: dict[str, list[str]] = {}
        self.port = 0

    def start(self) -> None:
        outer = self

        class _Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def do_GET(self) -> None:
                parsed = urlsplit(self.path)
                if parsed.path != CALLBACK_PATH:
                    self.send_response(404)
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return

                outer.query = parse_qs(parsed.query, keep_blank_values=True)
                denied = outer.query.get("error")
                if denied:
                    html = _callback_page(
                        "Authorization declined",
                        "You can close this tab and return to OpenHarness.",
                    )
                else:
                    html = _callback_page(
                        "Connected",
                        "You can close this tab and return to OpenHarness.",
                    )
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(html)))
                self.end_headers()
                self.wfile.write(html)
                outer._done.set()

            def log_message(self, *args: object) -> None:
                return

        self._server = HTTPServer(("127.0.0.1", 0), _Handler)
        self.port = int(self._server.server_address[1])
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    def wait(self, timeout: float) -> bool:
        return self._done.wait(timeout)

    def cancel(self) -> None:
        """Close the listener.  Safe to call from any terminal path."""
        self._done.set()
        if self._server is not None:
            try:
                self._server.shutdown()
            except OSError:  # pragma: no cover - best effort shutdown
                log.debug("OrcaRouter callback listener shutdown raised", exc_info=True)
            try:
                self._server.server_close()
            except OSError:  # pragma: no cover - best effort shutdown
                log.debug("OrcaRouter callback listener close raised", exc_info=True)
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=2)
        self._thread = None
        self._server = None


def _require_state(query: dict[str, list[str]], expected_state: str) -> None:
    """Compare the state echo before touching the code.

    This is the only thing standing between the listener and a code someone
    else's page dropped on it.
    """
    received = (query.get("state") or [None])[0]
    if not states_match(expected_state, received):
        raise OrcaRouterAuthError(
            "The OrcaRouter redirect did not echo the expected state value. "
            "The authorization was discarded; run the login again.",
            kind="state_mismatch",
        )


def run_pkce_login(
    *,
    app_name: str = "OpenHarness",
    flow: str = FLOW_LOOPBACK,
    auth_base: str | None = None,
    timeout: float = DEFAULT_LOGIN_TIMEOUT,
    scope: str = DEFAULT_SCOPE,
    opener: Callable[[str], None] | None = None,
    prompt_for_code: Callable[[], str] | None = None,
    on_authorize_url: Callable[[str], None] | None = None,
    announce: Callable[[str], None] | None = None,
    exchange: Callable[..., OrcaRouterCredential] | None = None,
) -> OrcaRouterCredential:
    """Run the PKCE flow and return the issued credential.

    Nothing here writes to disk: persistence is the credential provider's job,
    so a failed exchange cannot leave a partial credential behind.
    """
    if flow not in VALID_FLOWS:
        raise ValueError(f"unknown OrcaRouter login flow: {flow}")

    say = announce or (lambda message: print(message, flush=True))
    open_browser = opener or _try_open_browser
    do_exchange = exchange or exchange_code

    # Fresh secrets per attempt, from a cryptographic RNG.
    verifier = generate_code_verifier()
    challenge = code_challenge_for(verifier)
    state = generate_state()

    server: _CallbackServer | None = None
    try:
        if flow == FLOW_LOOPBACK:
            server = _CallbackServer()
            server.start()
            callback_url = f"http://127.0.0.1:{server.port}{CALLBACK_PATH}"
        else:
            callback_url = "oob"

        url = build_authorize_url(
            auth_base or "",
            callback_url=callback_url,
            code_challenge=challenge,
            state=state,
            app_name=app_name,
            scope=scope,
        )

        if on_authorize_url is not None:
            on_authorize_url(url)

        say("Opening your browser to authorize OpenHarness with OrcaRouter…")
        say(url)
        if not open_browser(url):
            say("Could not open a browser automatically — open the URL above to continue.")

        if flow == FLOW_LOOPBACK:
            assert server is not None
            if not server.wait(timeout):
                raise OrcaRouterAuthError(
                    f"Timed out after {int(timeout)}s waiting for the OrcaRouter redirect. "
                    "Start the login again when you are ready to approve it.",
                    kind="timeout",
                )
            _require_state(server.query, state)
            error = (server.query.get("error") or [None])[0]
            if error:
                raise OrcaRouterAuthError(
                    f"OrcaRouter authorization was declined ({error}).",
                    kind="access_denied",
                )
            code = (server.query.get("code") or [None])[0]
            if not code:
                raise OrcaRouterAuthError(
                    "The OrcaRouter redirect carried no authorization code.",
                    kind="missing_code",
                )
        else:
            say("Approve the request in your browser, then paste the code it shows.")
            if prompt_for_code is None:
                code = input("Code: ").strip()
            else:
                code = str(prompt_for_code()).strip()
            if not code:
                raise OrcaRouterAuthError(
                    "No authorization code was entered.", kind="missing_code"
                )

        say("Exchanging the authorization code…")
        return do_exchange(code, verifier, auth_base=auth_base)
    except KeyboardInterrupt:
        raise OrcaRouterAuthError(
            "OrcaRouter login cancelled.", kind="cancelled"
        ) from None
    finally:
        # Every terminal path releases the listener and the verifier.
        if server is not None:
            server.cancel()
        del verifier
        del challenge


def login_time_remaining(started_at: float, timeout: float) -> float:
    """Remaining budget for a login attempt, floored at zero."""
    return max(0.0, timeout - (time.monotonic() - started_at))


__all__ = [
    "FLOW_LOOPBACK",
    "FLOW_OOB",
    "VALID_FLOWS",
    "login_time_remaining",
    "run_pkce_login",
]
