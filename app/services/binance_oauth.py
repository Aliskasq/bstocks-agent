"""Binance Agent OS auth: OAuth 2.1 + PKCE with Client ID Metadata Documents.

Discovered from the live endpoint (see docs/AGENT_OS_AUTH.md):
  - no API key, no client secret, no dynamic registration
  - client_id IS an https URL pointing at our own metadata JSON
  - PKCE S256 mandatory, token_endpoint_auth_method = "none"

Flow:
  1. discover()            -> read .well-known documents
  2. build_authorize_url() -> human opens it, logs in, grants scopes
  3. local callback server -> captures ?code=
  4. exchange_code()       -> access_token (+ refresh_token)
  5. token cached on disk (0600) and auto-refreshed
"""
from __future__ import annotations

import base64
import hashlib
import http.server
import json
import os
import secrets
import threading
import time
import urllib.parse
from pathlib import Path

import httpx

from ..config import ROOT

RESOURCE = "https://agent.binance.com/mcp/agentic"
PROTECTED_RESOURCE_DOC = (
    "https://agent.binance.com/.well-known/oauth-protected-resource/gateway-mcp"
)
AUTH_SERVER_DOC = "https://agent.binance.com/.well-known/oauth-authorization-server"

TOKEN_PATH = ROOT / ".binance_token.json"

# Where our Client ID Metadata Document is published. Must be a public HTTPS URL
# that Binance can fetch. GitHub Pages or a Cloudflare Tunnel both work.
CLIENT_ID = os.environ.get("BINANCE_OAUTH_CLIENT_ID", "")
REDIRECT_URI = os.environ.get("BINANCE_OAUTH_REDIRECT_URI",
                              "http://127.0.0.1:8765/callback")
SCOPES = os.environ.get("BINANCE_OAUTH_SCOPES", "")


# ---- PKCE ---------------------------------------------------------------

def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def make_pkce() -> tuple[str, str]:
    """Return (verifier, challenge). Verifier never leaves this process
    until the final token exchange."""
    verifier = _b64url(secrets.token_bytes(48))
    challenge = _b64url(hashlib.sha256(verifier.encode()).digest())
    return verifier, challenge


# ---- discovery ----------------------------------------------------------

_META_CACHE: dict | None = None


def discover() -> dict:
    """Fetch the authorization-server metadata (cached per process)."""
    global _META_CACHE
    if _META_CACHE:
        return _META_CACHE
    with httpx.Client(timeout=20) as c:
        pr = c.get(PROTECTED_RESOURCE_DOC)
        pr.raise_for_status()
        servers = pr.json().get("authorization_servers") or []
        doc_url = AUTH_SERVER_DOC
        if servers:
            doc_url = servers[0].rstrip("/") + "/.well-known/oauth-authorization-server"
        meta = c.get(doc_url)
        meta.raise_for_status()
        _META_CACHE = meta.json()
    return _META_CACHE


def client_metadata_document(client_id: str = "", redirect_uri: str = "") -> dict:
    """The JSON we must publish at `client_id`. client_id MUST equal its own URL."""
    cid = client_id or CLIENT_ID
    return {
        "client_id": cid,
        "client_name": "bStocks AI Agent",
        "client_uri": cid.rsplit("/", 1)[0] if cid else "",
        "redirect_uris": [redirect_uri or REDIRECT_URI],
        "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"],
        "token_endpoint_auth_method": "none",
        "application_type": "native",
    }


# ---- authorize ----------------------------------------------------------

def build_authorize_url(challenge: str, state: str, *, scopes: str = "",
                        client_id: str = "", redirect_uri: str = "") -> str:
    meta = discover()
    params = {
        "response_type": "code",
        "client_id": client_id or CLIENT_ID,
        "redirect_uri": redirect_uri or REDIRECT_URI,
        "resource": RESOURCE,
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    scope = scopes or SCOPES
    if scope:
        params["scope"] = scope
    return meta["authorization_endpoint"] + "?" + urllib.parse.urlencode(params)


class _CallbackHandler(http.server.BaseHTTPRequestHandler):
    result: dict = {}

    def do_GET(self):  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        if not parsed.path.startswith("/callback"):
            self.send_response(404)
            self.end_headers()
            return
        qs = urllib.parse.parse_qs(parsed.query)
        _CallbackHandler.result = {k: v[0] for k, v in qs.items()}
        ok = "code" in _CallbackHandler.result
        body = (
            b"<h2>Authorization received.</h2><p>You can close this tab.</p>"
            if ok else
            b"<h2>Authorization failed.</h2><pre>"
            + json.dumps(_CallbackHandler.result).encode() + b"</pre>"
        )
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):  # silence
        return


def wait_for_code(redirect_uri: str = "", timeout_s: int = 300) -> dict:
    """Run a one-shot local server and block until Binance redirects back."""
    uri = urllib.parse.urlparse(redirect_uri or REDIRECT_URI)
    port = uri.port or 8765
    _CallbackHandler.result = {}
    server = http.server.HTTPServer(("127.0.0.1", port), _CallbackHandler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    deadline = time.time() + timeout_s
    try:
        while time.time() < deadline:
            if _CallbackHandler.result:
                return _CallbackHandler.result
            time.sleep(0.3)
    finally:
        server.shutdown()
    return {"error": "timeout waiting for authorization callback"}


# ---- token --------------------------------------------------------------

def _save_token(tok: dict) -> None:
    tok = dict(tok)
    if "expires_in" in tok:
        tok["expires_at"] = time.time() + float(tok["expires_in"]) - 60
    TOKEN_PATH.write_text(json.dumps(tok, indent=2))
    try:
        os.chmod(TOKEN_PATH, 0o600)
    except OSError:
        pass


def load_token() -> dict | None:
    if not TOKEN_PATH.exists():
        return None
    try:
        return json.loads(TOKEN_PATH.read_text())
    except (json.JSONDecodeError, OSError):
        return None


def _post_token(data: dict) -> dict:
    meta = discover()
    with httpx.Client(timeout=30) as c:
        r = c.post(meta["token_endpoint"], data=data,
                   headers={"Content-Type": "application/x-www-form-urlencoded"})
    if r.status_code >= 400:
        raise RuntimeError(f"token endpoint HTTP {r.status_code}: {r.text[:300]}")
    tok = r.json()
    _save_token(tok)
    return tok


def exchange_code(code: str, verifier: str, *, client_id: str = "",
                  redirect_uri: str = "") -> dict:
    return _post_token({
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri or REDIRECT_URI,
        "client_id": client_id or CLIENT_ID,
        "code_verifier": verifier,
        "resource": RESOURCE,
    })


def refresh(refresh_token: str, *, client_id: str = "") -> dict:
    return _post_token({
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": client_id or CLIENT_ID,
        "resource": RESOURCE,
    })


def get_access_token() -> str | None:
    """Cached token, refreshed if expired. None if we never authorized."""
    tok = load_token()
    if not tok:
        return None
    if tok.get("expires_at") and time.time() >= tok["expires_at"]:
        if tok.get("refresh_token"):
            try:
                tok = refresh(tok["refresh_token"])
            except Exception:
                return None
        else:
            return None
    return tok.get("access_token")


# ---- interactive login --------------------------------------------------

def login(*, scopes: str = "", client_id: str = "",
          redirect_uri: str = "") -> dict:
    """Print the URL for the human, wait for the callback, store the token."""
    cid = client_id or CLIENT_ID
    if not cid:
        raise RuntimeError(
            "BINANCE_OAUTH_CLIENT_ID is not set. Publish the client metadata "
            "document (see print_client_document()) at a public HTTPS URL and set "
            "BINANCE_OAUTH_CLIENT_ID to that exact URL."
        )
    verifier, challenge = make_pkce()
    state = secrets.token_urlsafe(16)
    url = build_authorize_url(challenge, state, scopes=scopes,
                              client_id=cid, redirect_uri=redirect_uri)

    print("\n1. Open this URL in a browser and approve the scopes:\n")
    print(url + "\n")
    print(f"2. Waiting for redirect on {redirect_uri or REDIRECT_URI} ...")

    res = wait_for_code(redirect_uri)
    if "error" in res:
        raise RuntimeError(f"authorization failed: {res}")
    if res.get("state") != state:
        raise RuntimeError("state mismatch — possible CSRF, aborting")

    tok = exchange_code(res["code"], verifier, client_id=cid,
                        redirect_uri=redirect_uri)
    print(f"\nAccess token stored in {TOKEN_PATH} (mode 0600).")
    print("Scopes granted:", tok.get("scope", "(not reported)"))
    return tok


def login_manual(*, scopes: str = "", client_id: str = "",
                 redirect_uri: str = "") -> dict:
    """Headless login for machines without a browser.

    We print the authorize URL, the human opens it on their laptop, and the
    browser lands on a dead localhost address. Nothing is lost: the code sits
    in that URL's query string, so they paste it back here. The PKCE verifier
    never left this process, so the exchange still proves we started the flow.
    """
    cid = client_id or CLIENT_ID
    if not cid:
        raise RuntimeError("BINANCE_OAUTH_CLIENT_ID is not set")
    redirect = redirect_uri or REDIRECT_URI

    verifier, challenge = make_pkce()
    state = secrets.token_urlsafe(16)
    url = build_authorize_url(challenge, state, scopes=scopes,
                              client_id=cid, redirect_uri=redirect)

    print("\n1. Open this URL in a browser on ANY device and approve:\n")
    print(url + "\n")
    print("2. Your browser will fail to load a 127.0.0.1 page. That is expected.")
    print("   Copy the FULL address bar contents and paste it below.\n")

    raw = input("Redirected URL (or bare code): ").strip()
    if not raw:
        raise RuntimeError("nothing pasted")

    if "?" in raw or raw.startswith("http"):
        qs = urllib.parse.parse_qs(urllib.parse.urlparse(raw).query)
        got = {k: v[0] for k, v in qs.items()}
    else:
        got = {"code": raw, "state": state}

    if got.get("error"):
        raise RuntimeError(f"authorization failed: {got}")
    if "code" not in got:
        raise RuntimeError(f"no ?code= found in what you pasted: {got}")
    if got.get("state") and got["state"] != state:
        raise RuntimeError("state mismatch — start over, do not reuse old URLs")

    tok = exchange_code(got["code"], verifier, client_id=cid,
                        redirect_uri=redirect)
    print(f"\nAccess token stored in {TOKEN_PATH} (mode 0600).")
    print("Scopes granted:", tok.get("scope", "(not reported)"))
    return tok


def print_client_document(client_id: str = "", redirect_uri: str = "") -> None:
    print("Publish this file at exactly the URL used as client_id:\n")
    print(json.dumps(client_metadata_document(client_id, redirect_uri), indent=2))
