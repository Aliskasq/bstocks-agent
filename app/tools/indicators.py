"""Pure-Python technical indicators. No numpy dependency on purpose (fast install)."""
from __future__ import annotations


def _ema(values: list[float], period: int) -> float | None:
    if len(values) < period:
        return None
    k = 2 / (period + 1)
    ema = sum(values[:period]) / period
    for v in values[period:]:
        ema = v * k + ema * (1 - k)
    return ema


def _ema_series(values: list[float], period: int) -> list[float]:
    if len(values) < period:
        return []
    k = 2 / (period + 1)
    ema = sum(values[:period]) / period
    out = [ema]
    for v in values[period:]:
        ema = v * k + ema * (1 - k)
        out.append(ema)
    return out


def rsi(closes: list[float], period: int = 14) -> float | None:
    if len(closes) < period + 1:
        return None
    gains, losses = [], []
    for i in range(1, period + 1):
        d = closes[i] - closes[i - 1]
        gains.append(max(d, 0.0))
        losses.append(max(-d, 0.0))
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    for i in range(period + 1, len(closes)):
        d = closes[i] - closes[i - 1]
        avg_gain = (avg_gain * (period - 1) + max(d, 0.0)) / period
        avg_loss = (avg_loss * (period - 1) + max(-d, 0.0)) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def macd(closes: list[float], fast: int = 12, slow: int = 26, signal: int = 9) -> dict:
    fast_s = _ema_series(closes, fast)
    slow_s = _ema_series(closes, slow)
    if not fast_s or not slow_s:
        return {"macd": None, "signal": None, "hist": None}
    n = min(len(fast_s), len(slow_s))
    line = [fast_s[-n + i] - slow_s[-n + i] for i in range(n)]
    sig_s = _ema_series(line, signal)
    sig = sig_s[-1] if sig_s else None
    return {
        "macd": round(line[-1], 4),
        "signal": round(sig, 4) if sig is not None else None,
        "hist": round(line[-1] - sig, 4) if sig is not None else None,
    }


def atr(highs: list[float], lows: list[float], closes: list[float], period: int = 14) -> float | None:
    n = min(len(highs), len(lows), len(closes))
    if n < period + 1:
        return None
    trs = []
    for i in range(1, n):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )
        trs.append(tr)
    val = sum(trs[:period]) / period
    for tr in trs[period:]:
        val = (val * (period - 1) + tr) / period
    return val


def calculate_indicators(candles: list[dict]) -> dict:
    """candles: [{open,high,low,close,volume}, ...] oldest -> newest."""
    closes = [float(c["close"]) for c in candles]
    highs = [float(c["high"]) for c in candles]
    lows = [float(c["low"]) for c in candles]
    e20, e50 = _ema(closes, 20), _ema(closes, 50)
    a = atr(highs, lows, closes)
    price = closes[-1] if closes else None
    m = macd(closes)
    return {
        "price": round(price, 4) if price is not None else None,
        "rsi": round(rsi(closes), 2) if rsi(closes) is not None else None,
        "ema20": round(e20, 4) if e20 is not None else None,
        "ema50": round(e50, 4) if e50 is not None else None,
        "ema_cross": (
            "bullish" if e20 and e50 and e20 > e50 else "bearish" if e20 and e50 else None
        ),
        "macd": m["macd"],
        "macd_hist": m["hist"],
        "atr": round(a, 4) if a is not None else None,
        "atr_pct": round(a / price * 100, 2) if a and price else None,
        "candles_used": len(candles),
    }
