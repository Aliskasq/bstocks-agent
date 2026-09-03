"""Auth helper CLI.

    python3 -m app.cli_auth doc        # print the client metadata document to publish
    python3 -m app.cli_auth discover   # show Binance's OAuth endpoints
    python3 -m app.cli_auth login        # PKCE login, browser on this machine
    python3 -m app.cli_auth login-manual # headless VPS: paste the redirect URL
    python3 -m app.cli_auth status     # do we have a valid token?
    python3 -m app.cli_auth tools      # list MCP tools using the stored token
"""
from __future__ import annotations

import json
import sys

from .services import binance_oauth as oauth
from .tools.binance_mcp import BinanceMCP


def main() -> None:
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"

    if cmd == "doc":
        oauth.print_client_document()
        print("\nSet BINANCE_OAUTH_CLIENT_ID in .env to that URL once published.")

    elif cmd == "discover":
        print(json.dumps(oauth.discover(), indent=2))

    elif cmd == "login":
        scopes = sys.argv[2] if len(sys.argv) > 2 else ""
        oauth.login(scopes=scopes)

    elif cmd == "login-manual":
        scopes = sys.argv[2] if len(sys.argv) > 2 else ""
        oauth.login_manual(scopes=scopes)

    elif cmd == "status":
        tok = oauth.load_token()
        if not tok:
            print("No token stored. Run: python3 -m app.cli_auth login")
            return
        access = oauth.get_access_token()
        print(json.dumps({
            "has_token": bool(access),
            "scope": tok.get("scope"),
            "expires_at": tok.get("expires_at"),
            "has_refresh": bool(tok.get("refresh_token")),
        }, indent=2))

    elif cmd == "tools":
        mcp = BinanceMCP()
        if not mcp.token:
            print("No access token. Run login first.")
            return
        try:
            tools = mcp.list_tools()
        except Exception as exc:  # noqa: BLE001
            print(f"MCP error: {type(exc).__name__}: {exc}")
            return
        print(f"{len(tools)} tools exposed by Binance Agent OS:\n")
        for t in tools:
            desc = (t.get("description") or "")[:100]
            print(f"  {t.get('name'):<40} {desc}")

    else:
        print(__doc__)


if __name__ == "__main__":
    main()
