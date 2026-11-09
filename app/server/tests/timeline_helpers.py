"""A made-up session world for the timeline and session-list tests.

A test file imports this module by name after putting this folder on ``sys.path``.
Rows are written the way Claude Code writes them, into a fake config folder, and
read by a real ingest pass into a migrated store. Times are given as seconds before
the world's clock (``ago``, negative for after it). All names and paths are made up.
"""

import hashlib
import json
import sqlite3
from collections.abc import Sequence
from datetime import datetime, timedelta
from pathlib import Path

import ingest_helpers as h

import model_catalog
import prices
import timeline
import usage_query
from models import ModelCheck, Timeline

PROJECT = "demo-app"
OTHER = "other-app"
OTHER_FOLDER = "-work-other-app"
OPUS, SONNET, MYSTERY = "claude-opus-5-5", "claude-sonnet-5-5", "mystery-model"
PLANTED_TEXT = "SECRET-MESSAGE-TEXT"
PLANTED_TOOL = "SECRET-TOOL-INPUT"
PLANTED_CWD = "/secret/cwd/path"
S1, S2, S3 = h.S1, h.S2, h.S3
PRICES = prices.load_prices()
CATALOG = model_catalog.load_catalog()
NOW = 5000.0  # seconds after h.T0, so a request can sit an hour back


def rid(agent_id: str) -> str:
    """Return the run id of an agent id, 12 hex of a sha256."""
    return hashlib.sha256(agent_id.encode("utf-8")).hexdigest()[:12]


def cost_of(
    model: str, input_tokens: int, output: int, cache_read: int, cache_write: int
) -> float | None:
    """USD for one standard-speed, global-region request, from the price table."""
    rate = PRICES["models"].get(model)
    if rate is None:
        return None
    return (
        input_tokens * rate["input"]
        + output * rate["output"]
        + cache_read * rate["cache_read"]
        + cache_write * rate["cache_write_5m"]
    ) / 1000000.0


def check_with(rows: int) -> timeline.ModelCheckFn:
    """Return a model check function that reports ``rows`` as its in-effect count."""

    def build(_project: str, _runs: Sequence[object]) -> ModelCheck:
        return ModelCheck(rows=[], in_effect_count=rows)

    return build


class World:
    """A config folder, a store over it and a clock, with builders for the rows."""

    def __init__(self, base: Path, now: float = NOW) -> None:
        """Create the folders and the store. ``now`` is seconds after ``h.T0``."""
        self.config = h.Config(base)
        self.store = h.Store(base, self.config)
        self.now = now
        self.projects = {h.FOLDER: PROJECT, OTHER_FOLDER: OTHER}
        self.pricer = usage_query.Pricer(PRICES)
        self.metas: set[Path] = set()

    # -------------------------------------------------------------- writing

    def _path(self, sid: str, run: str | None, agent: str | None, folder: str) -> Path:
        if run is None:
            path = self.config.main(sid, folder)
            path.parent.mkdir(parents=True, exist_ok=True)
            return path
        path = self.config.agent(run, sid, folder)
        path.parent.mkdir(parents=True, exist_ok=True)
        if agent is not None and path not in self.metas:
            self.config.meta(run, agent, sid, folder)
            self.metas.add(path)
        return path

    def _stamp(self, ago: float) -> str:
        return h.stamp(self.now - ago)

    def add(  # noqa: PLR0913, PLR0917 - a row has this many fields
        self,
        ago: float,
        mid: str,
        input_tokens: int = 0,
        output: int = 0,
        cache_read: int = 0,
        cache_write: int = 0,
        *,
        model: str = OPUS,
        effort: str | None = "high",
        run: str | None = None,
        agent: str | None = None,
        sid: str = S1,
        folder: str = h.FOLDER,
        branch: str = "main",
        stop: str | None = None,
        request_id: bool = True,
        message_id: bool = True,
    ) -> Path:
        """Append one assistant row ``ago`` seconds before the clock.

        ``stop`` is None for a row that calls a tool (the agent works on),
        ``end_turn`` for a row that ends its turn with no tool call, and
        ``handback`` for a row that calls SubagentHandback.
        """
        path = self._path(sid, run, agent, folder)
        content: list[dict[str, object]] = [
            {"type": "text", "text": PLANTED_TEXT},
            {"type": "tool_use", "name": "Bash", "input": {"command": PLANTED_TOOL}},
        ]
        message: dict[str, object] = {
            "id": "msg_" + mid,
            "model": model,
            "role": "assistant",
            "usage": {
                "input_tokens": input_tokens,
                "output_tokens": output,
                "cache_creation_input_tokens": cache_write,
                "cache_read_input_tokens": cache_read,
                "cache_creation": {
                    "ephemeral_5m_input_tokens": cache_write,
                    "ephemeral_1h_input_tokens": 0,
                },
                "service_tier": "standard",
                "speed": "standard",
                "inference_geo": "global",
            },
            "content": content,
        }
        if not message_id:
            del message["id"]
        if stop == "end_turn":
            message["content"] = [{"type": "text", "text": PLANTED_TEXT}]
            message["stop_reason"] = "end_turn"
        elif stop == "handback":
            content[1]["name"] = "SubagentHandback"
        row: dict[str, object] = {
            "type": "assistant",
            "timestamp": self._stamp(ago),
            "cwd": PLANTED_CWD,
            "sessionId": sid,
            "gitBranch": branch,
            "isSidechain": run is not None,
            "message": message,
        }
        if effort is not None:
            row["effort"] = effort
        if request_id:
            row["requestId"] = "req_" + mid
        self.config.append(path, [json.dumps(row).encode()])
        return path

    def _user(
        self, ago: float, run: str | None, row: dict[str, object], sid: str, folder: str
    ) -> Path:
        path = self._path(sid, run, None, folder)
        full = {
            "type": "user",
            "timestamp": self._stamp(ago),
            "sessionId": sid,
            "isSidechain": run is not None,
            **row,
        }
        self.config.append(path, [json.dumps(full).encode()])
        return path

    def link(
        self,
        ago: float,
        child: str,
        *,
        run: str | None = None,
        sid: str = S1,
        folder: str = h.FOLDER,
    ) -> Path:
        """Append the row that names the agent a transcript launched."""
        return self._user(
            ago,
            run,
            {
                "message": {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": "t1",
                            "content": PLANTED_TEXT,
                        }
                    ],
                },
                "toolUseResult": {
                    "status": "async_launched",
                    "agentId": child,
                    "prompt": PLANTED_TEXT,
                },
            },
            sid,
            folder,
        )

    def brief(  # noqa: PLR0913 - a row has this many fields
        self,
        ago: float,
        run: str,
        kind: str,
        sender: str | None = None,
        *,
        sid: str = S1,
        folder: str = h.FOLDER,
    ) -> Path:
        """Append a user row that briefs (resumes) an agent."""
        origin: dict[str, object] = {"kind": kind}
        if sender is not None:
            origin.update({"from": sender, "body": PLANTED_TEXT})
        return self._user(
            ago,
            run,
            {"message": {"role": "user", "content": PLANTED_TEXT}, "origin": origin},
            sid,
            folder,
        )

    def nudge(self, ago: float, run: str, *, sid: str = S1) -> Path:
        """Append a plain user row to an agent, which wakes it with no brief."""
        return self._user(
            ago,
            run,
            {"message": {"role": "user", "content": PLANTED_TEXT}},
            sid,
            h.FOLDER,
        )

    # -------------------------------------------------------------- reading

    def conn(self) -> sqlite3.Connection:
        """Run an ingest pass and return the store connection."""
        self.store.run()
        return self.store.conn

    def moment(self, ago: float = 0.0) -> datetime:
        """Return the clock time ``ago`` seconds before the world's clock."""
        return h.T0 + timedelta(seconds=self.now - ago)

    def timeline(
        self,
        sid: str = S1,
        *,
        ago: float = 0.0,
        project: str = PROJECT,
        check: timeline.ModelCheckFn = timeline.empty_model_check,
    ) -> Timeline | None:
        """Build the timeline at the clock (or ``ago`` seconds before it)."""
        return timeline.build_timeline(
            self.conn(),
            session_id=sid,
            project_key=project,
            folder_keys=self.projects,
            now=self.moment(ago),
            pricer=self.pricer,
            catalog=CATALOG,
            model_check_fn=check,
            prices=timeline.bundled_prices(self.moment().date()),
        )

    def live(
        self, sid: str = S1, *, ago: float = 0.0, project: str = PROJECT
    ) -> Timeline:
        """Build the timeline and fail when the session is unknown."""
        answer = self.timeline(sid, ago=ago, project=project)
        assert answer is not None
        return answer

    def close(self) -> None:
        """Close the store."""
        self.store.close()


RAW_IDS = (
    "lead1", "wkr_a", "wkr_b", "res1", "unn1", "mys1", "fg1", "fut1", "cyc_a", "cyc_b"
)  # fmt: skip
AGENT_RUNS = (
    "lead1", "wkr_a", "wkr_b", "res1", "unn1", "mys1", "fg1", "cyc_a", "cyc_b"
)  # fmt: skip


def build_dispatch(w: World) -> None:
    """A session with a lead, two workers, resumes, an unlinked run and a cycle.

    The comments give seconds before the clock.
    """
    for ago, mid in ((900, "m1"), (600, "m2"), (5, "m3")):
        w.add(ago, mid, 100, 10)
    w.link(880, "lead1")
    w.link(700, "res1")
    w.link(300, "unn1")
    w.link(296, "mys1")
    w.link(-20, "fut1")  # after the clock: ignored, and fut1 has no request yet either
    w.add(-30, "f0", 1, 1, run="fut1", agent="future")
    # lead1 launches two workers one second apart, and ends its turn at 100
    w.add(870, "l1", 50, 5, run="lead1", agent="lead")
    w.link(860, "wkr_a", run="lead1")
    w.link(859, "wkr_b", run="lead1")
    w.add(400, "l2", 50, 5, run="lead1", agent="lead")
    w.add(100, "l3", 50, 5, run="lead1", agent="lead", stop="end_turn")
    # wkr_a hands back at 650
    for ago, mid, stop in (
        (858, "a1", None),
        (700, "a2", None),
        (650, "a3", "handback"),
    ):
        w.add(
            ago,
            mid,
            20,
            2,
            run="wkr_a",
            agent="worker",
            model=SONNET,
            effort="medium",
            stop=stop,
        )
    # wkr_b hands back at 600, the lead briefs it at 500 (a peer), it hands back at 300
    for ago, mid, stop in (
        (857, "b1", None),
        (690, "b2", None),
        (600, "b3", "handback"),
    ):
        w.add(
            ago,
            mid,
            20,
            2,
            run="wkr_b",
            agent="worker",
            model=SONNET,
            effort="medium",
            stop=stop,
        )
    w.brief(500, "wkr_b", "peer", sender="lead1")
    for ago, mid, stop in ((490, "b4", None), (300, "b5", "handback")):
        w.add(
            ago,
            mid,
            20,
            2,
            run="wkr_b",
            agent="worker",
            model=SONNET,
            effort="medium",
            stop=stop,
        )
    # res1 ends its turn at 680, the coordinator resumes it at 120, it is still at work
    for ago, mid, stop in (
        (695, "r1", None),
        (690, "r2", None),
        (680, "r3", "end_turn"),
    ):
        w.add(ago, mid, 30, 3, run="res1", agent="reviewer", stop=stop)
    w.brief(120, "res1", "coordinator")
    w.add(110, "r4", 30, 3, run="res1", agent="reviewer")
    w.add(30, "r5", 30, 3, run="res1", agent="reviewer")
    # an unnamed run and an unpriced model, launched four seconds apart
    w.add(298, "u1", 10, 1, run="unn1")
    w.add(297, "u2", 10, 1, run="unn1")
    w.add(295, "y1", 10, 1, run="mys1", agent="scout", model=MYSTERY)
    w.add(294, "y2", 10, 1, run="mys1", agent="scout", model=MYSTERY)
    # a foreground run that nothing links yet
    w.add(250, "g1", 10, 1, run="fg1", agent="scout")
    w.add(240, "g2", 10, 1, run="fg1", agent="scout")
    # a cycle (cyc_a names cyc_b at 195, cyc_b names cyc_a at 185), and a run that
    # names itself at 196
    w.add(200, "c1", 10, 1, run="cyc_a", agent="loop")
    w.add(190, "c2", 10, 1, run="cyc_a", agent="loop")
    w.add(199, "c3", 10, 1, run="cyc_b", agent="loop")
    w.add(189, "c4", 10, 1, run="cyc_b", agent="loop")
    w.link(196, "cyc_a", run="cyc_a")
    w.link(195, "cyc_b", run="cyc_a")
    w.link(185, "cyc_a", run="cyc_b")


def one_kid(w: World, stop: str | None = None) -> World:
    """A main session that launched one scout at 90, with its first request at 80."""
    w.add(100, "m", 1, 1)
    w.link(90, "kid")
    w.add(80, "k1", 1, 1, run="kid", agent="scout", stop=stop)
    return w
