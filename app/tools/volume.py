"""Volume anomaly + volatility descriptors."""
from __future__ import annotations
import statistics


def volume_anomaly(candles: list[dict], lookback: int = 20) -> dict:
    vols = [float(c["volume"]) for c in candles]
    if len(vols) < 5:
        return {"ratio": None, "verdict": "insufficient_data"}
    recent = vols[-1]
    base = vols[-(lookback + 1):-1] or vols[:-1]
    mean = statistics.fmean(base)
    if mean == 0:
        return {"ratio": None, "verdict": "no_baseline"}
    ratio = recent / mean
    verdict = (
        "extreme" if ratio >= 4 else
        "high" if ratio >= 2 else
        "elevated" if ratio >= 1.3 else
        "normal" if ratio >= 0.7 else
        "dry"
    )
    return {"ratio": round(ratio, 2), "baseline_avg": round(mean, 2), "verdict": verdict}


def volatility(candles: list[dict], lookback: int = 20) -> dict:
    closes = [float(c["close"]) for c in candles]
    if len(closes) < 3:
        return {"stdev_pct": None, "verdict": "insufficient_data"}
    window = closes[-lookback:]
    rets = [
        (window[i] - window[i - 1]) / window[i - 1] * 100
        for i in range(1, len(window))
        if window[i - 1]
    ]
    if not rets:
        return {"stdev_pct": None, "verdict": "insufficient_data"}
    sd = statistics.pstdev(rets)
    verdict = "high" if sd >= 3 else "moderate" if sd >= 1.2 else "low"
    return {"stdev_pct": round(sd, 2), "verdict": verdict}


def momentum(candles: list[dict], bars: int = 10) -> dict:
    closes = [float(c["close"]) for c in candles]
    if len(closes) <= bars:
        return {"change_pct": None}
    change = (closes[-1] - closes[-1 - bars]) / closes[-1 - bars] * 100
    return {"change_pct": round(change, 2), "bars": bars}
