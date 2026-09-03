# Deploy to VPS (no domain required)

Two things need a public HTTPS URL:
1. the **Client ID Metadata Document** (Binance must fetch it), and
2. optionally a **live dashboard** for judges to click.

Both are solvable without buying a domain.

---

## Option A — Cloudflare Tunnel (recommended, no domain, no account juggling)

```bash
# install
curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 \
  -o /usr/local/bin/cloudflared && chmod +x /usr/local/bin/cloudflared

# run the app
cd /opt/bstocks-agent
uvicorn app.main:app --host 127.0.0.1 --port 8000 &

# expose it — prints a https://<random>.trycloudflare.com URL
cloudflared tunnel --url http://127.0.0.1:8000
```

Then serve the client metadata document from the same app. Add to `app/main.py`:

```python
@app.get("/oauth-client.json")
def oauth_client():
    from .services.binance_oauth import client_metadata_document
    import os
    cid = os.environ["BINANCE_OAUTH_CLIENT_ID"]
    return client_metadata_document(cid)
```

Set in `.env`:
```
BINANCE_OAUTH_CLIENT_ID=https://<random>.trycloudflare.com/oauth-client.json
BINANCE_OAUTH_REDIRECT_URI=https://<random>.trycloudflare.com/oauth/callback
```

Caveat: the free tunnel URL changes on restart, so re-run `cli_auth login` if it
rotates. Keep the tunnel process alive during the judging window (use `tmux` or a
systemd unit).

---

## Option B — GitHub Pages for the metadata doc only

Cheapest if you only need auth to work, not a public dashboard.

1. Create a public repo, enable Pages on `main` / root.
2. Commit `oauth-client.json` produced by `python3 -m app.cli_auth doc`, with
   `client_id` set to `https://<user>.github.io/<repo>/oauth-client.json`.
3. Keep `BINANCE_OAUTH_REDIRECT_URI=http://127.0.0.1:8765/callback` and run
   `cli_auth login` on the machine where you have a browser.

The file contains **no secrets** — a public `client_id` is by design in OAuth 2.1.

---

## Running as a service

`/etc/systemd/system/bstocks.service`:

```ini
[Unit]
Description=bStocks AI Agent
After=network.target

[Service]
WorkingDirectory=/opt/bstocks-agent
EnvironmentFile=/opt/bstocks-agent/.env
ExecStart=/usr/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
Restart=always
User=bstocks

[Install]
WantedBy=multi-user.target
```

```bash
systemctl daemon-reload && systemctl enable --now bstocks
```

---

## Hardening before you expose it

- The dashboard has **no auth**. Anyone with the URL can start the agent and press
  Confirm. Before sharing publicly either:
  - put HTTP basic auth in front (Nginx `auth_basic`), or
  - keep `MAX_POSITION_USD` tiny and fund the sub-account with the bare minimum, or
  - remove the `/api/confirm` button for the public build.
- Never commit `.env` or `.binance_token.json` (both are git-ignored).
- Keep the Agentic sub-account funded with only what you can afford to lose.
- Request the narrowest OAuth scopes that still let the demo work.
