# bStocks AI Agent — Hackathon Plan (Binance Agent OS, Track A)

Deadline: 2026-09-08 23:59 UTC. Today: 2026-09-03.
Prize target: Track A ($20k USDC).

## Winning thesis (one sentence for judges)
"Give it a goal and risk limits, not a ticker: the agent scans bStocks, picks its own
tools, recalls past setups, refuses trades that violate risk, waits for conditions,
and only then acts through Binance Agent OS — every step traced."

## Non-negotiables (what actually wins)
1. Visible decision TRACE (tool calls + inputs + outputs + LLM reasoning) per cycle.
2. A REFUSAL moment on camera (agent says WAIT / Risk Manager rejects).
3. Memory that is USED, not just stored (past similar setups injected into prompt).
4. Real Binance Agent OS / MCP call in the loop (not mocked in the final demo).
5. 90-second demo video that lands the "not a bot" contrast in first 15 seconds.

## Scope discipline
IN:  scanner, indicators, signal score, memory (SQLite), risk manager, agent loop,
     MCP integration, single-page dashboard, trace viewer, README, video.
OUT: PostgreSQL, Docker, charts, auth, multiple strategies, ML, mobile, 50 indicators.

## Stack (frozen)
Ubuntu VPS · Python 3.12 · FastAPI · SQLite · OpenRouter (Claude Opus 5)
· Binance MCP (https://agent.binance.com/mcp/agentic) · single-page React or plain
HTML+HTMX/vanilla WS · Nginx + certbot.

## Schedule

### Day 1 (Sep 3, today) — VERTICAL SLICE
Goal: end-to-end thin path works.
- [ ] VPS ready: python, venv, nginx, domain + TLS (or skip TLS until Day 4)
- [ ] repo skeleton + .env.example (NEVER commit .env)
- [ ] services/openrouter.py: chat with tool-calling loop
- [ ] tools/market.py: get_market_data(symbol) via Binance MCP
- [ ] tools/indicators.py: RSI, EMA20/50, MACD, ATR
- [ ] one manual run: goal -> LLM -> tool call -> MCP data -> indicators -> answer
- [ ] persist trace to traces/ as JSON
EXIT CRITERION: `python -m app.demo "NVDA"` prints a full trace with real MCP data.

### Day 2 (Sep 4) — INTELLIGENCE
- [ ] tools/volume.py, volatility.py
- [ ] scanner: bStocks universe -> cheap Python prefilter -> top 5-10
- [ ] signals.py: Signal Score 0-100 with component breakdown (must be explainable)
- [ ] memory.py + SQLite schema (setups, decisions, outcomes)
- [ ] search_memory(symbol, setup_fingerprint) -> k similar past setups
- [ ] risk.py: MAX_POSITION, MAX_DAILY_LOSS, MAX_TRADES, MAX_LEVERAGE, verdict + reason
- [ ] structured LLM output enforced: {decision, confidence, reason, monitor_condition}
EXIT CRITERION: scan produces ranked candidates; LLM returns valid JSON decision
that cites at least one memory item.

### Day 3 (Sep 5) — AUTONOMY + TRADING PATH
- [ ] agent/loop.py: SCAN -> FILTER -> CALC -> MEMORY -> LLM -> DECIDE
- [ ] monitor_condition watcher (e.g. pullback_2_percent) + re-analysis on trigger
- [ ] trade path: decision -> risk check -> USER CONFIRM -> MCP order -> verify -> remember
- [ ] Agentic sub-account wired, scopes minimal (market data + trade only if needed)
- [ ] outcome recording (entry/exit/PnL) closing the memory loop
EXIT CRITERION: loop runs unattended 30+ min, produces a WAIT then a triggered
re-analysis, and one confirmed order path executed at least once (small size).

### Day 4 (Sep 6) — DASHBOARD + TRACE UI
- [ ] FastAPI REST + WebSocket broadcast
- [ ] single page: goal/risk input, agent status, top opportunities, current decision,
      activity log, TRACE panel (expandable per cycle)
- [ ] visual "REJECTED BY RISK MANAGER" state — make it loud
EXIT CRITERION: open page on phone, watch agent think live.

### Day 5 (Sep 7) — PACKAGE + SUBMIT
- [ ] README: thesis, architecture diagram, cycle diagram, "why not a bot" table,
      setup instructions, safety notes, scope of MCP permissions
- [ ] 90s demo video: 0-15s contrast, 15-45s scan+WAIT, 45-70s trigger+risk+order,
      70-90s memory/outcome + trace
- [ ] screenshots, GitHub public, license
- [ ] SUBMIT (do not wait for Sep 8)
BUFFER: Sep 8 is buffer only. Never plan work into it.

## Daily rule
Every day ends with something demoable. If a feature threatens the exit criterion,
cut the feature.

## Security
- OpenRouter key: rotate after hackathon (was shared in chat).
- Binance: Agentic sub-account only, minimal scopes, tiny position sizes.
- No keys in frontend, no keys in repo.

## Reminders (cron)
- Daily 08:00 UTC standup ping with today's exit criterion
- Sep 7 12:00 UTC: submission prep
- Sep 8 20:00 UTC: hard deadline alarm (3h before)
