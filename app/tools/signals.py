"""Signal Score 0-100 with an explainable component breakdown.

Cheap deterministic scoring runs BEFORE the LLM: it keeps token cost low and
gives judges a transparent, auditable pre-filter.
"""
from __future__ import annotations

from .indicators import calculate_indicators
from .volume import momentum, volatility, volume_anomaly


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def score_candidate(symbol: str, candles: list[dict]) -> dict:
    ind = calculate_indicators(candles)
    vol = volume_anomaly(candles)
    vlt = volatility(candles)
    mom = momentum(candles)

    # Momentum: 0-25
    ch = mom.get("change_pct") or 0.0
    momentum_pts = _clamp(12.5 + ch * 2.5, 0, 25)

    # Volume: 0-25
    ratio = vol.get("ratio") or 1.0
    volume_pts = _clamp((ratio - 0.7) * 12, 0, 25)

    # Trend: 0-20
    trend_pts = 0.0
    if ind.get("ema_cross") == "bullish":
        trend_pts += 12
    if (ind.get("macd_hist") or 0) > 0:
        trend_pts += 8
    trend_pts = _clamp(trend_pts, 0, 20)

    # Breakout: 0-20 — position within recent range
    closes = [float(c["close"]) for c in candles[-40:]]
    if len(closes) >= 5:
        lo, hi = min(closes), max(closes)
        pos = (closes[-1] - lo) / (hi - lo) if hi > lo else 0.5
        breakout_pts = _clamp(pos * 20, 0, 20)
    else:
        pos, breakout_pts = 0.5, 10.0

    # Risk penalty: 0 to -10 (overheated RSI or extreme volatility)
    penalty = 0.0
    rsi = ind.get("rsi")
    if rsi is not None and rsi > 75:
        penalty -= (rsi - 75) / 2.5
    if (vlt.get("stdev_pct") or 0) > 4:
        penalty -= 3
    penalty = _clamp(penalty, -10, 0)

    total = _clamp(momentum_pts + volume_pts + trend_pts + breakout_pts + penalty, 0, 100)

    label = (
        "STRONG" if total >= 85 else
        "WATCH" if total >= 65 else
        "WEAK" if total >= 45 else
        "AVOID"
    )

    return {
        "symbol": symbol,
        "signal_score": round(total, 1),
        "label": label,
        "components": {
            "momentum": round(momentum_pts, 1),
            "volume": round(volume_pts, 1),
            "trend": round(trend_pts, 1),
            "breakout": round(breakout_pts, 1),
            "risk_penalty": round(penalty, 1),
        },
        "range_position_pct": round(pos * 100, 1),
        "indicators": ind,
        "volume_anomaly": vol,
        "volatility": vlt,
        "momentum": mom,
    }
