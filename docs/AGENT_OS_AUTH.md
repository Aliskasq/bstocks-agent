# How to connect to Binance Agent OS (MCP) — findings

Discovered 2026-09-03 by probing the live endpoint. This is authoritative because it
comes from the server's own OAuth discovery documents, not from a blog post.

## The key fact

**There is no API key for the Agentic MCP endpoint.** Our earlier assumption
(`BINANCE_MCP_TOKEN` = a static key) was wrong. It uses **OAuth 2.1 with PKCE** and
**Client ID Metadata Documents** (CIMD) — no client secret, no pre-registration.

That is why we were getting a bare `HTTP 401`.

## Discovery chain (reproducible)

```bash
# 1. Unauthenticated call reveals the auth mechanism
curl -i -X POST https://agent.binance.com/mcp/agentic \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}'
# -> HTTP/2 401
# -> www-authenticate: Bearer resource_metadata="https://agent.binance.com/.well-known/oauth-protected-resource/gateway-mcp"
```

```bash
# 2. Protected-resource metadata
curl -s https://agent.binance.com/.well-known/oauth-protected-resource/gateway-mcp
```
```json
{
  "resource": "https://agent.binance.com/mcp/agentic",
  "authorization_servers": ["https://agent.binance.com"]
}
```

```bash
# 3. Authorization-server metadata
curl -s https://agent.binance.com/.well-known/oauth-authorization-server
```
```json
{
  "issuer": "https://agent.binance.com",
  "authorization_endpoint": "https://accounts.binance.com/agentic-oauth/authorize",
  "token_endpoint": "https://accounts.binance.com/oauth-agentic/token",
  "token_endpoint_auth_methods_supported": ["none"],
  "response_types_supported": ["code"],
  "grant_types_supported": ["authorization_code"],
  "code_challenge_methods_supported": ["S256"],
  "client_id_metadata_document_supported": true
}
```

Notes from further probing:
- `POST /register` → 404, so **Dynamic Client Registration is NOT supported**.
- `/.well-known/openid-configuration` → 404 (plain OAuth 2.1, not OIDC).
- `token_endpoint_auth_methods_supported: ["none"]` → public client, PKCE mandatory.
- `client_id_metadata_document_supported: true` → the `client_id` is an **HTTPS URL**
  pointing at a JSON document describing our client. This replaces registration.

## What this means for us

We must implement a standard OAuth 2.1 + PKCE authorization-code flow:

1. **Host a Client ID Metadata Document** at a public HTTPS URL, e.g.
   `https://<our-domain>/oauth-client.json`:
   ```json
   {
     "client_id": "https://<our-domain>/oauth-client.json",
     "client_name": "bStocks AI Agent",
     "redirect_uris": ["https://<our-domain>/oauth/callback"],
     "grant_types": ["authorization_code"],
     "response_types": ["code"],
     "token_endpoint_auth_method": "none"
   }
   ```
   `client_id` MUST equal the document's own URL.

2. **Build the authorize URL** and open it in a browser (the human logs into Binance
   and grants scopes):
   ```
   https://accounts.binance.com/agentic-oauth/authorize
     ?response_type=code
     &client_id=https%3A%2F%2F<our-domain>%2Foauth-client.json
     &redirect_uri=https%3A%2F%2F<our-domain>%2Foauth%2Fcallback
     &resource=https%3A%2F%2Fagent.binance.com%2Fmcp%2Fagentic
     &scope=<requested scopes>
     &state=<random>
     &code_challenge=<BASE64URL(SHA256(verifier))>
     &code_challenge_method=S256
   ```

3. **Exchange the code** at the token endpoint (no client secret):
   ```
   POST https://accounts.binance.com/oauth-agentic/token
   Content-Type: application/x-www-form-urlencoded

   grant_type=authorization_code
   &code=<code>
   &redirect_uri=<same as above>
   &client_id=https://<our-domain>/oauth-client.json
   &code_verifier=<verifier>
   &resource=https://agent.binance.com/mcp/agentic
   ```

4. **Call MCP** with `Authorization: Bearer <access_token>`, then `initialize` →
   `tools/list` → `tools/call`. Refresh the token when it expires.

## Practical requirements

- A **public HTTPS domain** is mandatory (for the metadata doc and the redirect URI).
  A VPS with Nginx + certbot covers this; `localhost` will not work for the metadata
  document since Binance must fetch it.
- Trading actions execute in a separate **Agentic sub-account**, and the scopes granted
  during the consent screen decide what we may do. Request the minimum: market data
  first, trading only if the demo needs it.
- The human must complete the consent screen once, interactively. This cannot be
  automated away — which is fine, and is actually a good thing to show judges as a
  security property.

## Status in our codebase

`app/tools/binance_mcp.py` already sends `Authorization: Bearer <token>` and handles
JSON-RPC + SSE correctly. It only needs a token provider instead of a static env var,
i.e. `app/services/binance_oauth.py` implementing steps 1-4 above.

## Логин на VPS без браузера

На сервере нет браузера, но он и не нужен: браузер должен открыться **на твоей машине**,
а не на VPS. Секрет (PKCE verifier) при этом всё время лежит в процессе на VPS,
поэтому перехватить поток нельзя.

```bash
cd ~/bstocks-agent
echo 'BINANCE_OAUTH_CLIENT_ID=https://aliskasq.github.io/bstocks-agent/oauth-client.json' >> .env
python3 -m app.cli_auth login-manual
```

Что произойдёт:

1. Скрипт напечатает длинный URL на `accounts.binance.com`.
2. Открываешь его на своём ноутбуке/телефоне, логинишься, подтверждаешь права.
3. Браузер попробует уйти на `http://127.0.0.1:8765/callback?code=...` и покажет
   **ошибку «сайт недоступен». Это нормально** — на твоём ноутбуке ничего не слушает.
4. Копируешь **всю строку из адресной строки** и вставляешь в терминал VPS.
5. Скрипт сверит `state`, обменяет код на токен и положит его в
   `.binance_token.json` с правами 0600.

Проверка:

```bash
python3 -m app.cli_auth status   # has_token: true
python3 -m app.cli_auth tools    # список инструментов Agent OS
```

Важно: код в URL одноразовый и живёт недолго (обычно ~60с). Если замешкалась —
просто запусти `login-manual` снова, старый URL не переиспользовать.

Совет на первый раз: запроси только market data, без права торговать:

```bash
python3 -m app.cli_auth login-manual "market:read"
```

Альтернатива, если хочется «как на десктопе»: SSH-туннель, тогда localhost-редирект
долетит до VPS и `login` сработает автоматически.

```bash
# на своей машине
ssh -L 8765:127.0.0.1:8765 user@vps
# в этой же сессии, на VPS:
python3 -m app.cli_auth login
```

## Выбор модели в дашборде

`GET /api/models?free_only=true&tools_only=true` — каталог моделей, доступных нашему
ключу. По умолчанию только бесплатные и только с tool-calling (агенту без инструментов
делать нечего). `POST /api/model {"model": "..."}` переключает модель на ходу.

Бесплатные модели живут в общем пуле и регулярно отдают HTTP 429. `_post_chat()`
делает экспоненциальный backoff и после второй неудачи автоматически переключается
на другую бесплатную модель, чтобы цикл не падал. Все переключения видны в trace.
