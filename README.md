# bStocks AI Agent

**Autonomous market research & trading agent built on Binance Agent OS.**

You don't tell it what to buy. You give it a **goal** and **risk limits** — it decides
what to research, which tools to call, when to wait, and when to refuse.

---

## Why this is an agent, not a bot

A trading bot is a rule evaluated on a tick:

```
price crosses EMA  →  BUY
```

This agent runs a loop with judgement in it:

```
GOAL
 ↓
SCAN universe            (deterministic Python pre-filter, no LLM cost)
 ↓
CHOOSE what to inspect   (the model picks its own tools)
 ↓
CALCULATE indicators     (Python does the math, the model never invents numbers)
 ↓
RECALL memory            (past similar setups + how they resolved)
 ↓
REASON  →  BUY / WAIT / AVOID
 ↓
RISK GATE                (deterministic code, can veto the model)
 ↓
USER CONFIRMATION
 ↓
EXECUTE via Agent OS  →  VERIFY  →  REMEMBER OUTCOME
 ↓
MONITOR condition        (patience as observable state)
 ↓
on trigger: RE-ANALYZE from scratch
```

The interesting behaviour is **refusal**. In a real run the agent scored TSLA at 84.8,
then declined to buy:

> "RSI 88.07, price 145.07 sits 4.9% above EMA20, range_position 100.0%, 12 consecutive
> higher closes for +6.3% in 10 bars, on 3.59x baseline volume — that is
> chase-and-exhaustion territory, not a base. Memory returns zero resolved setups for
> this fingerprint, so there is no validated historical edge to justify paying the top
> tick."
>
> → `WAIT`, monitoring for `pullback_3_percent`

It then waited, the pullback fired at −5.59% — and it **still refused**, because the
setup had degraded rather than improved:

> "The pullback I waited for did not stop at the EMA20 — it broke straight through it.
> MACD flipped negative, RSI collapsed from 88.93 to 22.08, signal score fell from 84.4
> to 16.6. Buying a knife with zero validated edge is exactly the marginal trade I
> should refuse."
>
> → `AVOID`

A bot would have bought: the condition it was told to wait for was satisfied.
The agent understood that a satisfied condition is not the same as a valid setup.

Full machine-readable evidence for both runs lives in [`traces/`](traces/).

---

## Architecture

```
                    ┌──────────────────────────┐
   Browser  ◄──WS───┤  FastAPI  (app/main.py)  │
   dashboard        └────────────┬─────────────┘
                                 │
                    ┌────────────▼─────────────┐
                    │   AgentLoop (loop.py)    │
                    │  scan · monitor · react  │
                    └────────────┬─────────────┘
                                 │
              ┌──────────────────┼──────────────────┐
              ▼                  ▼                  ▼
       Scanner/Signals       Memory            Risk Manager
       (signals.py)       (SQLite)             (risk.py)
              │                  │                  │
              └──────────────────┼──────────────────┘
                                 ▼
                    ┌──────────────────────────┐
                    │  OpenRouter (Claude Opus)│  ← tool-calling only
                    └────────────┬─────────────┘
                                 │ requests tools
              ┌──────────────────┴──────────────────┐
              ▼                                     ▼
     Local Python tools                    Binance Agent OS (MCP)
   indicators · volume · memory          agent.binance.com/mcp/agentic
   signal score · risk limits                       │
                                                    ▼
                                          Agentic sub-account
```

**Design rule: the model reasons, Python decides what is permitted.** The LLM can
request a trade; it cannot set position size, bypass the daily loss limit, or execute.

---

## Agent OS integration

Everything reaches Binance through the MCP endpoint
`https://agent.binance.com/mcp/agentic` — JSON-RPC 2.0 over streamable HTTP
(`initialize` → `tools/list` → `tools/call`), with SSE responses handled.

Auth is **OAuth 2.1 + PKCE with Client ID Metadata Documents** — there is no API key
for this endpoint. We discovered the full flow from the server's own metadata; it is
documented reproducibly in [`docs/AGENT_OS_AUTH.md`](docs/AGENT_OS_AUTH.md).

Step-by-step VPS setup (Russian): [`docs/INSTALL-ru.md`](docs/INSTALL-ru.md).

Security properties worth noting:
- No client secret, no static key. `client_id` is a public URL to a metadata document.
- The human grants scopes interactively once; this cannot be automated away.
- Trading is confined to a separate **Agentic sub-account**.
- Request the minimum scope set — market data first, trading only if needed.

---

## The five things that make it agentic

| Capability | Where | Why it matters |
|---|---|---|
| Goal-driven, not ticker-driven | `agent/prompts.py` | user never names a symbol |
| Own tool selection | `services/openrouter.py` | model picks from 6 registered tools |
| Memory that is *used* | `tools/memory.py` | past setups injected, cited in reasoning |
| Patience as state | `agent/monitor.py` | WAIT becomes a checkable condition |
| Refusal | `tools/risk.py` | deterministic veto outside the model |

### Memory

Setups get a coarse **fingerprint** (`bullish|rsi:overbought|vol:spike|mom:strong_up`)
so similar past situations can be retrieved cheaply, along with their realized
outcomes and win rate. The agent references retrieved rows by id in its reasoning.

### Monitor conditions

The model may only emit machine-checkable conditions:

`pullback_<N>_percent` · `breakout_above_<price>` · `rsi_below_<N>` · `volume_normalizes`

These are parsed and evaluated in pure Python every tick — so the agent can watch
patiently for hours at **zero token cost**. The LLM is invoked only at decision points.

### Risk manager

Six deterministic checks, each with a human-readable reason surfaced in the UI:
max position, max leverage, trades per day, daily loss floor, no pyramiding,
positive size. Re-checked **again at execution time**, not just at decision time.

---

## Dashboard

Single page, live over WebSocket:

- goal input, agent status, data source, auth state
- ranked opportunities from the deterministic pre-filter
- current decision with confidence, reasoning and recalled memory
- risk panel with per-check PASS/FAIL and a loud `REJECTED BY RISK MANAGER` state
- monitoring panel showing what the agent is waiting for and how long
- activity log
- **decision trace viewer** — every tool call, argument and result per cycle

---

## Setup

```bash
git clone <repo> && cd bstocks-agent
pip install -r requirements.txt
cp .env.example .env          # add your OpenRouter key
```

### Connect to Binance Agent OS

```bash
# 1. Print the client metadata document
python3 -m app.cli_auth doc

# 2. Publish it at a public HTTPS URL (GitHub Pages or Cloudflare Tunnel),
#    then set BINANCE_OAUTH_CLIENT_ID in .env to that exact URL.

# 3. Interactive login — opens the Binance consent screen
python3 -m app.cli_auth login

# 4. Verify
python3 -m app.cli_auth status
python3 -m app.cli_auth tools     # lists the tools Agent OS exposes
```

### Run

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
# dashboard at http://localhost:8000
```

CLI demos:

```bash
python3 -m app.demo             # one decision cycle, prints full trace
python3 -m app.demo_day2        # WAIT → monitor → trigger → re-analysis
```

---

## Configuration

| Variable | Meaning |
|---|---|
| `OPENROUTER_API_KEY` | OpenRouter key |
| `OPENROUTER_MODEL` | default `anthropic/claude-opus-5` |
| `BINANCE_OAUTH_CLIENT_ID` | public HTTPS URL of your client metadata document |
| `BINANCE_OAUTH_REDIRECT_URI` | default `http://127.0.0.1:8765/callback` |
| `MAX_POSITION_USD` | hard position cap (default 50) |
| `MAX_DAILY_LOSS_USD` | daily realized loss floor (default 10) |
| `MAX_TRADES_PER_DAY` | trade count cap (default 3) |
| `MAX_LEVERAGE` | leverage cap (default 2) |
| `ALLOW_MOCK_MARKET` | `1` = synthetic candles for offline dev **only** |

`ALLOW_MOCK_MARKET=1` exists so the logic can be developed and tested without
credentials. The dashboard displays a loud `MOCK DATA` badge whenever it is active,
so a demo can never silently pass off synthetic data as live.

---

## Layout

```
app/
├── agent/       loop.py · agent.py · monitor.py · prompts.py
├── tools/       binance_mcp.py · indicators.py · volume.py
│               signals.py · memory.py · risk.py
├── services/    openrouter.py · binance_oauth.py
├── main.py      FastAPI + WebSocket
├── trace.py     decision trace recorder
└── cli_auth.py  OAuth helper CLI
frontend/        single-page dashboard
docs/            AGENT_OS_AUTH.md · DEPLOY.md · INSTALL-ru.md
                 DEMO_SCRIPT.md
traces/          recorded decision traces
```

No numpy, no PostgreSQL, no Docker — four dependencies total, installs in seconds.

---

## Install as a Claude Code Custom Agent

**Quick install (one command):**

```bash
# From any directory, install the agent into your ~/.claude/agents/
git clone https://github.com/Aliskasq/bstocks-agent.git ~/.claude/agents/bstocks-source
ln -sf ~/.claude/agents/bstocks-source/.claude/agents/bstocks.md ~/.claude/agents/bstocks.md
```

Or manually:

```bash
git clone https://github.com/Aliskasq/bstocks-agent.git
cp bstocks-agent/.claude/agents/bstocks.md ~/.claude/agents/
```

**Then in any project, just ask Claude Code:**

> "Use the bstocks agent to scan for bStocks opportunities"

Claude Code will invoke the `bstocks` CLI via the `bash` tool. The agent definition (`.claude/agents/bstocks.md`) tells it how to use the CLI.

### Prerequisites (run once in the cloned repo)

```bash
cd ~/.claude/agents/bstocks-source
pip install -r requirements.txt
cp .env.example .env
# Add OPENROUTER_API_KEY to .env
# Run OAuth flow once:
python3 -m app.cli_auth login-manual
```

### Available commands (via the agent)

| Command | What it does |
|---------|--------------|
| `bstocks scan` | Rank universe by signal score |
| `bstocks cycle` | Full decision: scan → LLM → risk gate |
| `bstocks watch` | Check active wait conditions |
| `bstocks risk` | Show limits + today's usage |
| `bstocks memory SYMBOL` | Recall similar past setups |
| `bstocks state` | Show watches, last decision, pending trade |
| `bstocks confirm` | Execute pending trade (after risk re-check) |

### Free models on OpenRouter

Set `OPENROUTER_MODEL` in `.env` to any free model:

```
minimax/minimax-01
nvidia/nemotron-3-ultra-550b-a55b:free
nvidia/nemotron-3.5-lightning:free
nvidia/nemotron-3-super-120b-a12b:free
```

---

## Safety

- Risk limits are enforced in Python, never by the model.
- Trades require explicit user confirmation before execution.
- Risk is re-validated at execution time.
- Trading is scoped to an Agentic sub-account with minimal OAuth scopes.
- Secrets never enter the repo (`.env`, `.binance_token.json` are git-ignored;
  the token file is written `0600`).

This is a hackathon prototype. Not financial advice.

## License

MIT
