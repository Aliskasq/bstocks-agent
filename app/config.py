"""Central config loaded from environment (.env)."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load_dotenv() -> None:
    env_path = ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


_load_dotenv()


def _num(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except ValueError:
        return default


OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL = os.environ.get("OPENROUTER_MODEL", "anthropic/claude-opus-5")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

BINANCE_MCP_URL = os.environ.get("BINANCE_MCP_URL", "https://agent.binance.com/mcp/agentic")
BINANCE_MCP_TOKEN = os.environ.get("BINANCE_MCP_TOKEN", "")

MAX_POSITION_USD = _num("MAX_POSITION_USD", 50)
MAX_DAILY_LOSS_USD = _num("MAX_DAILY_LOSS_USD", 10)
MAX_TRADES_PER_DAY = int(_num("MAX_TRADES_PER_DAY", 3))
MAX_LEVERAGE = _num("MAX_LEVERAGE", 2)

ALLOW_MOCK_MARKET = os.environ.get("ALLOW_MOCK_MARKET", "0") == "1"

TRACE_DIR = ROOT / "traces"
DB_PATH = ROOT / "agent.db"
