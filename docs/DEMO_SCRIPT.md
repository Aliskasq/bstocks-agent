# Demo video script — 90 seconds

Target: judge understands "this is not a bot" within 15 seconds.
Record at 1280x720+. No music. Narrate or use captions.

---

## 0:00–0:15 — The contrast

**Show:** the dashboard, goal field visible.

**Say / caption:**
> "Most trading demos ask: should I buy NVDA? This one never gets told a ticker.
> It gets a goal and risk limits — and decides for itself."

**Do:** type the goal, click **Start agent**.

---

## 0:15–0:45 — It researches, then refuses

**Show:** activity log filling in, opportunities table populating, decision panel.

**Say:**
> "It scans the bStocks universe, ranks candidates in Python, then picks its own
> tools — price data through Binance Agent OS, indicators, volume, and its own memory
> of past setups."

**Do:** let the decision land on `WAIT`. Zoom the reasoning text.

**Say:**
> "Highest score of the scan — and it refuses to buy. RSI 88, at the top of its range,
> volume 3.6x. It calls that chase-and-exhaustion, not a base. It sets a condition:
> come back on a 3% pullback."

**Point at:** the monitoring panel — condition, reference price, check counter rising.

> "Waiting is real state here, not a sentence. Python checks it every tick, so the
> agent can watch for hours at zero token cost."

---

## 0:45–1:10 — The trigger, and the second refusal

**Show:** `TRIGGERED` line in the log, then the re-analysis decision.

**Say:**
> "The pullback fires. A bot would buy — the condition it was waiting for is satisfied.
> Watch what the agent does instead."

**Do:** let `AVOID` render. Zoom the reasoning.

**Say:**
> "It re-verifies from scratch and refuses again. The pullback broke straight through
> the EMA20, MACD flipped, RSI collapsed from 89 to 22, score fell from 84 to 17.
> A satisfied condition is not a valid setup — and it knows the difference."

---

## 1:10–1:25 — Risk cannot be argued with

**Show:** risk panel; if a BUY is available, click **Confirm** to show the gate.
Otherwise show the six PASS/FAIL checks.

**Say:**
> "When it does want to trade, it can only propose. Position size, leverage, daily loss
> floor — enforced in Python, outside the model. It can be vetoed, and it needs my
> confirmation before anything reaches the Agentic sub-account."

---

## 1:25–1:40 — Proof

**Show:** trace viewer, expand one trace JSON. Scroll through tool calls.

**Say:**
> "And none of this is a claim. Every cycle records every tool call, argument, result
> and decision. These traces ship in the repo."

**End card:**
```
bStocks AI Agent
Goal-driven · Tool-using · Remembers · Refuses
Built on Binance Agent OS (MCP)
github.com/<user>/bstocks-agent
```

---

## Recording checklist

- [ ] `MOCK DATA` badge is **not** showing — use live MCP data
- [ ] `Agent OS authorized` badge is green
- [ ] Browser zoom ~110% so text is readable when compressed
- [ ] Close unrelated tabs; hide bookmarks bar
- [ ] Pre-seed memory with a few resolved outcomes so retrieval is non-empty
- [ ] Have a WAIT→trigger→AVOID sequence ready (use `demo_day2` timing to rehearse)
- [ ] Keep it under 2:00 — judges watch dozens

## Fastest path if time runs short

Record `python3 -m app.demo_day2` in a terminal instead of the dashboard. The full
WAIT → trigger → re-analysis story prints in ~40 seconds with the trace inline.
Less pretty, equally convincing.
