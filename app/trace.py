"""Decision trace: the artifact that proves agentic behaviour to judges.

Every cycle records: goal, each tool call with args + result, LLM reasoning,
final decision, and risk verdict. Written as JSON and streamed to the dashboard.
"""
import json
import time
import uuid
from typing import Any, Callable

from .config import TRACE_DIR


class Trace:
    def __init__(self, goal: str, on_event: Callable[[dict], None] | None = None):
        self.id = uuid.uuid4().hex[:12]
        self.goal = goal
        self.started_at = time.time()
        self.events: list[dict] = []
        self._on_event = on_event

    def add(self, kind: str, **data: Any) -> dict:
        event = {"t": round(time.time() - self.started_at, 3), "kind": kind, **data}
        self.events.append(event)
        if self._on_event:
            try:
                self._on_event({"trace_id": self.id, **event})
            except Exception:
                pass
        return event

    def tool_call(self, name: str, args: dict) -> None:
        self.add("tool_call", tool=name, args=args)

    def tool_result(self, name: str, result: Any, ms: int | None = None) -> None:
        self.add("tool_result", tool=name, result=result, ms=ms)

    def llm(self, role: str, content: Any) -> None:
        self.add("llm", role=role, content=content)

    def decision(self, decision: dict) -> None:
        self.add("decision", **decision)

    def risk(self, verdict: dict) -> None:
        self.add("risk", **verdict)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "goal": self.goal,
            "started_at": self.started_at,
            "duration_s": round(time.time() - self.started_at, 3),
            "events": self.events,
        }

    def save(self) -> str:
        TRACE_DIR.mkdir(parents=True, exist_ok=True)
        path = TRACE_DIR / f"{int(self.started_at)}-{self.id}.json"
        path.write_text(json.dumps(self.to_dict(), indent=2, default=str))
        return str(path)

    def pretty(self) -> str:
        lines = [f"TRACE {self.id}  goal={self.goal!r}"]
        for e in self.events:
            k = e["kind"]
            if k == "tool_call":
                lines.append(f"  [{e['t']:>6.2f}s] -> {e['tool']}({json.dumps(e['args'])})")
            elif k == "tool_result":
                res = json.dumps(e["result"], default=str)
                if len(res) > 300:
                    res = res[:300] + "..."
                lines.append(f"  [{e['t']:>6.2f}s] <- {e['tool']} {res}")
            elif k == "llm":
                content = str(e.get("content"))
                if len(content) > 400:
                    content = content[:400] + "..."
                lines.append(f"  [{e['t']:>6.2f}s] LLM/{e['role']}: {content}")
            elif k == "decision":
                d = {kk: vv for kk, vv in e.items() if kk not in ("t", "kind")}
                lines.append(f"  [{e['t']:>6.2f}s] DECISION {json.dumps(d, default=str)}")
            elif k == "risk":
                d = {kk: vv for kk, vv in e.items() if kk not in ("t", "kind")}
                lines.append(f"  [{e['t']:>6.2f}s] RISK {json.dumps(d, default=str)}")
            else:
                lines.append(f"  [{e['t']:>6.2f}s] {k} {json.dumps({kk: vv for kk, vv in e.items() if kk not in ('t','kind')}, default=str)}")
        return "\n".join(lines)
