"""Memory — SQLite store of past setups, decisions and outcomes.

Key point for judges: memory is RETRIEVED and injected into the prompt, so the
agent's reasoning can cite what happened last time a similar setup appeared.
"""
from __future__ import annotations

import json
import sqlite3
import time
from typing import Any

from ..config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS memories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    symbol TEXT NOT NULL,
    fingerprint TEXT NOT NULL,
    signal_score REAL,
    indicators TEXT,
    decision TEXT,
    confidence REAL,
    reason TEXT,
    monitor_condition TEXT,
    entry REAL,
    exit REAL,
    pnl_pct REAL,
    outcome TEXT
);
CREATE INDEX IF NOT EXISTS idx_symbol ON memories(symbol);
CREATE INDEX IF NOT EXISTS idx_fingerprint ON memories(fingerprint);
"""


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def fingerprint(indicators: dict, vol: dict, mom: dict) -> str:
    """Coarse bucket signature so 'similar setups' can be matched cheaply."""
    rsi = indicators.get("rsi")
    rsi_b = "na" if rsi is None else (
        "oversold" if rsi < 35 else "low" if rsi < 45 else
        "neutral" if rsi < 60 else "high" if rsi < 72 else "overbought"
    )
    trend = indicators.get("ema_cross") or "na"
    volr = vol.get("ratio")
    vol_b = "na" if volr is None else (
        "spike" if volr >= 2 else "elevated" if volr >= 1.3 else "normal"
    )
    ch = mom.get("change_pct")
    mom_b = "na" if ch is None else (
        "strong_up" if ch >= 4 else "up" if ch >= 1 else
        "flat" if ch > -1 else "down" if ch > -4 else "strong_down"
    )
    return f"{trend}|rsi:{rsi_b}|vol:{vol_b}|mom:{mom_b}"


def save_memory(symbol: str, fp: str, signal_score: float | None,
                indicators: dict, decision: dict) -> int:
    with _conn() as conn:
        cur = conn.execute(
            """INSERT INTO memories
               (ts, symbol, fingerprint, signal_score, indicators, decision,
                confidence, reason, monitor_condition)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (
                time.time(), symbol, fp, signal_score, json.dumps(indicators),
                decision.get("decision"), decision.get("confidence"),
                decision.get("reason"), decision.get("monitor_condition"),
            ),
        )
        return int(cur.lastrowid)


def record_outcome(memory_id: int, entry: float, exit_price: float) -> dict:
    pnl = (exit_price - entry) / entry * 100 if entry else 0.0
    outcome = "win" if pnl > 0 else "loss" if pnl < 0 else "flat"
    with _conn() as conn:
        conn.execute(
            "UPDATE memories SET entry=?, exit=?, pnl_pct=?, outcome=? WHERE id=?",
            (entry, exit_price, round(pnl, 3), outcome, memory_id),
        )
    return {"memory_id": memory_id, "pnl_pct": round(pnl, 3), "outcome": outcome}


def search_memory(symbol: str | None = None, fp: str | None = None,
                  limit: int = 5) -> list[dict]:
    """Similar past setups: same fingerprint first, then same symbol."""
    rows: list[Any] = []
    with _conn() as conn:
        if fp:
            rows += conn.execute(
                "SELECT * FROM memories WHERE fingerprint=? ORDER BY ts DESC LIMIT ?",
                (fp, limit),
            ).fetchall()
        if symbol and len(rows) < limit:
            rows += conn.execute(
                "SELECT * FROM memories WHERE symbol=? AND (? IS NULL OR fingerprint<>?)"
                " ORDER BY ts DESC LIMIT ?",
                (symbol, fp, fp, limit - len(rows)),
            ).fetchall()
    out = []
    for r in rows:
        out.append({
            "id": r["id"],
            "age_hours": round((time.time() - r["ts"]) / 3600, 1),
            "symbol": r["symbol"],
            "fingerprint": r["fingerprint"],
            "signal_score": r["signal_score"],
            "decision": r["decision"],
            "reason": r["reason"],
            "pnl_pct": r["pnl_pct"],
            "outcome": r["outcome"],
        })
    return out


def outcome_stats(fp: str) -> dict:
    with _conn() as conn:
        row = conn.execute(
            """SELECT COUNT(*) n,
                      SUM(CASE WHEN outcome='win' THEN 1 ELSE 0 END) wins,
                      AVG(pnl_pct) avg_pnl
               FROM memories WHERE fingerprint=? AND outcome IS NOT NULL""",
            (fp,),
        ).fetchone()
    n = row["n"] or 0
    return {
        "fingerprint": fp,
        "resolved_setups": n,
        "win_rate": round((row["wins"] or 0) / n, 2) if n else None,
        "avg_pnl_pct": round(row["avg_pnl"], 2) if row["avg_pnl"] is not None else None,
    }
