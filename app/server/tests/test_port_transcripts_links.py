"""Tests for the dispatch links the transcript reader keeps (transcripts.Links).

The rounds fixtures (tests/fixtures/rounds, see its README) are copied into
throwaway folders and read with Reader.read_folder. Nothing here reads the real
~/.claude. All names and paths are made up.
"""

# ruff: noqa: PT009, PTH103, PTH105, PTH118, PTH120, PTH123
# ruff: noqa: PTH208, UP031, RUF005, E741

# old tests so the two suites stay easy to compare.
import datetime
import json
import os
import sys
import tempfile
import unittest
from collections.abc import Sequence
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/ is not on sys.path
import port_helpers as helpers

import transcripts

ROUNDS = os.path.join(helpers.FIXTURES, "rounds")
UTC = datetime.UTC
NOW = datetime.datetime(2026, 11, 4, 12, 0, 0, tzinfo=UTC)
S1 = "11111111-1111-4111-8111-111111111111"
FOLDER = "-work-demo-app"
RUN = "lead-1"
BODY = "PLANTED-BODY-9c1e"


def at(text: str) -> datetime.datetime | None:
    # The tests read times through the same parser the reader uses.
    return transcripts._parse_ts(text)  # pyright: ignore[reportPrivateUsage]


def links_of(
    result: transcripts.FolderResult,
) -> dict[tuple[str, str | None], transcripts.Links]:
    assert result.links is not None
    return result.links


def fixture_lines(name: str) -> list[bytes]:
    with open(os.path.join(ROUNDS, name), "rb") as fh:
        return [line for line in fh.read().split(b"\n") if line]


class LinksCase(unittest.TestCase):
    def config(self) -> str:
        cfg = os.path.realpath(
            tempfile.mkdtemp(prefix="transcripts-links-", dir=helpers.tmp_base())
        )
        self.addCleanup(helpers.rmtree_force, cfg)
        os.makedirs(os.path.join(cfg, "projects", FOLDER))
        return cfg

    def agent_path(self, cfg: str, run: str = RUN, sid: str = S1) -> str:
        return os.path.join(
            cfg, "projects", FOLDER, sid, "subagents", "agent-%s.jsonl" % run
        )

    def main_path(self, cfg: str, sid: str = S1) -> str:
        return os.path.join(cfg, "projects", FOLDER, sid + ".jsonl")

    def write(
        self,
        path: str,
        lines: list[bytes],
        end: bytes = b"\n",
        mode: str = "wb",
        old: bool = False,
    ) -> None:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, mode) as fh:
            fh.write(b"\n".join(lines) + end)
        stamp = (NOW - datetime.timedelta(days=100 if old else 0)).timestamp()
        os.utime(path, (stamp, stamp))

    # The result is a Links, or None when the key is missing, and the tests read both.
    def links(
        self,
        cfg: str,
        reader: transcripts.Reader | None = None,
        key: tuple[str, str | None] = (S1, RUN),
    ) -> Any:
        result = (reader or transcripts.Reader(cfg)).read_folder(FOLDER, NOW)
        return links_of(result).get(key)

    def fixture(self, name: str) -> str:
        cfg = self.config()
        self.write(self.agent_path(cfg), fixture_lines(name))
        return cfg


class RoundsFixtures(LinksCase):
    def rounds_count(self, name: str) -> int:
        return 1 + len(self.links(self.fixture(name)).rounds)

    def test_round_counts_match_the_readme(self):
        expected = {
            "coordinator-resume-same-prompt.jsonl": 2,
            "peer-resume-same-prompt-after-nudge.jsonl": 2,
            "nudge-new-prompt.jsonl": 1,
            "task-notification-after-handback.jsonl": 1,
            "worker-handback-wakes-lead.jsonl": 1,
        }
        for name, count in expected.items():
            with self.subTest(fixture=name):
                self.assertEqual(count, self.rounds_count(name))

    def test_a_coordinator_resume_is_a_round_by_kind(self):
        links = self.links(self.fixture("coordinator-resume-same-prompt.jsonl"))
        self.assertEqual(
            ((at("2026-08-21T18:45:50.795Z"), "coordinator", None),), links.rounds
        )
        self.assertEqual((), links.launched)

    def test_a_peer_that_is_not_a_launched_worker_is_a_round_with_its_id(self):
        links = self.links(self.fixture("peer-resume-same-prompt-after-nudge.jsonl"))
        self.assertEqual(
            ((at("2026-10-15T21:26:48.594Z"), "peer", "worker-1"),), links.rounds
        )

    def test_a_launched_workers_handback_is_not_a_round(self):
        links = self.links(self.fixture("worker-handback-wakes-lead.jsonl"))
        self.assertEqual((), links.rounds)
        self.assertEqual(
            (
                ("worker-1", at("2026-10-13T00:47:35.167Z")),
                ("worker-2", at("2026-10-13T00:47:35.168Z")),
            ),
            links.launched,
        )

    def test_stops_of_the_nudge_fixture_read_done_working_done(self):
        links = self.links(self.fixture("nudge-new-prompt.jsonl"))
        self.assertEqual(
            (
                (at("2026-10-11T03:16:00.991Z"), True),
                (at("2026-10-11T03:16:01.012Z"), False),
                (at("2026-10-11T03:16:07.208Z"), True),
            ),
            links.stops,
        )

    def test_the_handbacks_own_tool_result_does_not_wake_the_agent(self):
        links = self.links(self.fixture("task-notification-after-handback.jsonl"))
        self.assertEqual(
            (
                (at("2026-10-13T18:23:10.158Z"), True),
                (at("2026-10-13T21:26:41.027Z"), False),
                (at("2026-10-13T21:26:44.323Z"), True),
                (at("2026-10-13T21:26:44.336Z"), False),
                (at("2026-10-13T21:26:51.069Z"), True),
            ),
            links.stops,
        )

    def test_a_resume_wakes_a_finished_agent_and_it_finishes_again(self):
        links = self.links(self.fixture("coordinator-resume-same-prompt.jsonl"))
        self.assertEqual(
            (
                (at("2026-08-21T18:29:44.292Z"), True),
                (at("2026-08-21T18:45:50.795Z"), False),
                (at("2026-08-21T18:48:30.773Z"), True),
            ),
            links.stops,
        )

    def test_compact_and_spaced_json_give_the_same_links(self):
        for name in sorted(os.listdir(ROUNDS)):
            if not name.endswith(".jsonl"):
                continue
            rows = [json.loads(line) for line in fixture_lines(name)]
            results: list[Any] = []
            for separators in ((",", ":"), (", ", ": ")):
                cfg = self.config()
                self.write(
                    self.agent_path(cfg),
                    [
                        json.dumps(r, separators=separators).encode("utf-8")
                        for r in rows
                    ],
                )
                results.append(self.links(cfg))
            with self.subTest(fixture=name):
                self.assertEqual(results[0], results[1])
                self.assertEqual(self.links(self.fixture(name)), results[0])

    def test_rounds_are_kept_for_agent_files_only(self):
        cfg = self.config()
        self.write(
            self.main_path(cfg), fixture_lines("coordinator-resume-same-prompt.jsonl")
        )
        links = self.links(cfg, key=(S1, None))
        self.assertEqual((), links.rounds)
        self.assertEqual(3, len(links.stops))


class Growth(LinksCase):
    def test_a_file_that_grows_gives_the_result_of_one_read(self):
        for name in sorted(os.listdir(ROUNDS)):
            if not name.endswith(".jsonl"):
                continue
            lines = fixture_lines(name)
            whole = self.links(self.fixture(name))
            for cut in range(1, len(lines)):
                with self.subTest(fixture=name, cut=cut):
                    cfg = self.config()
                    path = self.agent_path(cfg)
                    self.write(path, lines[:cut])
                    reader = transcripts.Reader(cfg)
                    self.links(cfg, reader)
                    self.write(path, lines[cut:], mode="ab")
                    self.assertEqual(whole, self.links(cfg, reader))

    def test_a_line_cut_in_the_middle_waits_for_its_end(self):
        lines = fixture_lines("coordinator-resume-same-prompt.jsonl")
        whole = self.links(self.fixture("coordinator-resume-same-prompt.jsonl"))
        cfg = self.config()
        path = self.agent_path(cfg)
        brief = lines[9]
        self.write(path, lines[:9] + [brief[:40]], end=b"")
        reader = transcripts.Reader(cfg)
        self.assertEqual((), self.links(cfg, reader).rounds)
        self.write(path, [brief[40:]] + lines[10:], mode="ab", end=b"\n")
        self.assertEqual(whole, self.links(cfg, reader))

    def test_a_file_that_shrinks_starts_over(self):
        lines = fixture_lines("coordinator-resume-same-prompt.jsonl")
        cfg = self.config()
        path = self.agent_path(cfg)
        self.write(path, lines)
        reader = transcripts.Reader(cfg)
        self.assertEqual(1, len(self.links(cfg, reader).rounds))
        self.write(path, lines[:3])
        self.assertEqual(transcripts.Links((), (), ()), self.links(cfg, reader))

    def test_a_replaced_file_starts_over(self):
        cfg = self.config()
        path = self.agent_path(cfg)
        self.write(path, fixture_lines("worker-handback-wakes-lead.jsonl"))
        reader = transcripts.Reader(cfg)
        self.assertEqual(2, len(self.links(cfg, reader).launched))
        other = path + ".new"
        self.write(other, fixture_lines("nudge-new-prompt.jsonl") * 2)
        os.replace(other, path)  # a new inode, so the stored offset must not be reused
        self.assertEqual((), self.links(cfg, reader).launched)

    def test_an_unchanged_file_keeps_its_links_without_parsing_again(self):
        cfg = self.fixture("coordinator-resume-same-prompt.jsonl")
        reader = transcripts.Reader(cfg)
        first = self.links(cfg, reader)
        self.assertIs(first, self.links(cfg, reader))


class Folder(LinksCase):
    def test_keys_are_session_and_run_with_none_for_the_main_session(self):
        cfg = self.config()
        self.write(self.agent_path(cfg), fixture_lines("nudge-new-prompt.jsonl"))
        self.write(
            self.main_path(cfg), fixture_lines("worker-handback-wakes-lead.jsonl")
        )
        result = transcripts.Reader(cfg).read_folder(FOLDER, NOW)
        self.assertEqual({(S1, RUN), (S1, None)}, set(links_of(result)))

    def test_orphaned_and_superseded_main_files_merge_into_the_main_key_in_file_order(
        self,
    ):
        cfg = self.config()
        lines = fixture_lines("worker-handback-wakes-lead.jsonl")
        first = [
            l.replace(b"worker-1", b"child-a").replace(b"worker-2", b"child-b")
            for l in lines
        ]
        second = [
            l.replace(b"worker-1", b"child-c").replace(b"worker-2", b"child-d")
            for l in lines
        ]
        base = os.path.join(cfg, "projects", FOLDER)
        self.write(self.main_path(cfg), first)
        self.write(
            os.path.join(base, S1 + ".orphaned-20261103T1200-ab12.jsonl"), second
        )
        self.write(
            os.path.join(base, S1 + ".jsonl.superseded-20261103T1300"), second[:5]
        )
        result = transcripts.Reader(cfg).read_folder(FOLDER, NOW)
        links = links_of(result)[(S1, None)]
        # Path order: the main file, then the superseded copy, then the orphaned one.
        self.assertEqual(
            ["child-a", "child-b", "child-c", "child-d", "child-c", "child-d"],
            [c for c, _ts in links.launched],
        )
        self.assertEqual({(S1, None)}, set(links_of(result)))

    def test_a_file_skipped_as_old_gives_no_links(self):
        cfg = self.config()
        self.write(
            self.agent_path(cfg),
            fixture_lines("worker-handback-wakes-lead.jsonl"),
            old=True,
        )
        result = transcripts.Reader(cfg).read_folder(FOLDER, NOW)
        self.assertEqual({}, result.links)

    def test_a_folder_result_built_by_hand_has_no_links(self):
        self.assertIsNone(transcripts.FolderResult([], hash(()), False).links)


class WhatIsKept(LinksCase):
    def row(self, kind: str, **extra: Any) -> bytes:
        row = {
            "type": "user",
            "timestamp": "2026-11-04T10:00:00.000Z",
            "isSidechain": True,
            "agentId": RUN,
            "message": {"role": "user", "content": BODY},
        }
        row.update(extra)
        row["type"] = kind
        return json.dumps(row, separators=(",", ":")).encode("utf-8")

    def assistant(
        self,
        stop_reason: str | None = None,
        tools: Sequence[str] = (),
        ts: str = "2026-11-04T09:59:00.000Z",
    ) -> bytes:
        content = [{"type": "text", "text": BODY}] + [
            {"type": "tool_use", "name": n, "input": {"x": BODY}} for n in tools
        ]
        return json.dumps(
            {
                "type": "assistant",
                "timestamp": ts,
                "isSidechain": True,
                "agentId": RUN,
                "message": {
                    "role": "assistant",
                    "stop_reason": stop_reason,
                    "content": content,
                    "usage": {"input_tokens": 1, "output_tokens": 1},
                },
            },
            separators=(",", ":"),
        ).encode("utf-8")

    def test_ids_that_fail_the_pattern_are_dropped(self):
        cfg = self.config()
        bad = ["has space", "x" * 65, "semi;colon", "", "a/b", "café"]
        rows = [self.assistant(stop_reason="end_turn")]
        for n, child in enumerate(bad + ["good_id-1"]):
            rows.append(
                self.row(
                    "user",
                    toolUseResult={"agentId": child, "status": "async_launched"},
                    message={
                        "role": "user",
                        "content": [{"type": "tool_result", "content": BODY}],
                    },
                    timestamp="2026-11-04T10:00:%02d.000Z" % n,
                )
            )
        rows.append(
            self.row("user", origin={"kind": "peer", "from": "bad id", "body": BODY})
        )
        rows.append(
            self.row(
                "user",
                origin={"kind": "peer", "from": "good_peer", "body": BODY},
                timestamp="2026-11-04T10:01:00.000Z",
            )
        )
        self.write(self.agent_path(cfg), rows)
        links = self.links(cfg)
        self.assertEqual(["good_id-1"], [c for c, _ts in links.launched])
        # The first brief wakes the agent (sender dropped), so the second arrives
        # while it works.
        self.assertEqual([("peer", None)], [(k, by) for _ts, k, by in links.rounds])

    def test_the_first_link_per_child_wins(self):
        cfg = self.config()
        rows = [
            self.row(
                "user",
                toolUseResult={"agentId": "kid"},
                timestamp="2026-11-04T10:00:00.000Z",
                message={
                    "role": "user",
                    "content": [{"type": "tool_result", "content": "x"}],
                },
            ),
            self.row(
                "user",
                toolUseResult={"agentId": "kid"},
                timestamp="2026-11-04T10:05:00.000Z",
                message={
                    "role": "user",
                    "content": [{"type": "tool_result", "content": "x"}],
                },
            ),
        ]
        self.write(self.agent_path(cfg), rows)
        self.assertEqual(
            (("kid", at("2026-11-04T10:00:00.000Z")),), self.links(cfg).launched
        )

    def test_a_brief_counts_only_after_a_stop(self):
        cfg = self.config()
        rows = [
            self.assistant(tools=["Bash"]),
            self.row(
                "user",
                origin={"kind": "coordinator"},
                timestamp="2026-11-04T10:00:00.000Z",
            ),
            self.assistant(stop_reason="end_turn", ts="2026-11-04T10:01:00.000Z"),
            self.row(
                "user", origin={"kind": "human"}, timestamp="2026-11-04T10:02:00.000Z"
            ),
            self.row(
                "user", origin={"kind": "human"}, timestamp="2026-11-04T10:03:00.000Z"
            ),
        ]
        self.write(self.agent_path(cfg), rows)
        self.assertEqual(
            [(at("2026-11-04T10:02:00.000Z"), "human", None)],
            list(self.links(cfg).rounds),
        )

    def test_a_tool_result_only_row_is_never_a_brief(self):
        cfg = self.config()
        rows = [
            self.assistant(stop_reason="end_turn"),
            self.row(
                "user",
                origin={"kind": "coordinator"},
                message={
                    "role": "user",
                    "content": [{"type": "tool_result", "content": "x"}],
                },
            ),
            self.row(
                "user",
                origin={"kind": "coordinator"},
                message={"role": "user", "content": []},
            ),
        ]
        self.write(self.agent_path(cfg), rows)
        self.assertEqual((), self.links(cfg).rounds)

    def test_a_handback_prefix_is_not_a_brief(self):
        cfg = self.config()
        rows = [
            self.assistant(stop_reason="end_turn"),
            self.row(
                "user",
                origin={
                    "kind": "peer",
                    "from": "someone",
                    "body": "[Subagent hand-back] " + BODY,
                },
            ),
        ]
        self.write(self.agent_path(cfg), rows)
        self.assertEqual((), self.links(cfg).rounds)

    def test_no_text_is_kept(self):
        cfg = self.config()
        rows = [
            self.assistant(stop_reason="end_turn", tools=["SubagentHandback"]),
            self.row(
                "user",
                origin={
                    "kind": "peer",
                    "from": "boss",
                    "body": BODY,
                    "senderTaskId": "t1",
                },
            ),
            self.row(
                "user",
                toolUseResult={"agentId": "kid", "prompt": BODY, "stdout": BODY},
                message={
                    "role": "user",
                    "content": [{"type": "tool_result", "content": BODY}],
                },
            ),
            self.row("user", origin={"kind": "human"}),
        ]
        self.write(self.agent_path(cfg), rows)
        reader = transcripts.Reader(cfg)
        links = self.links(cfg, reader)
        self.assertEqual(1, len(links.rounds))
        self.assertEqual(1, len(links.launched))
        cache = reader._cache  # pyright: ignore[reportPrivateUsage]
        self.assertNotIn(BODY, repr(cache))
        self.assertNotIn("PLANTED", repr(cache))
        self.assertNotIn("PLANTED", repr(links))

    def test_a_malformed_user_line_is_not_counted(self):
        cfg = self.config()
        self.write(
            self.agent_path(cfg),
            [b'{"origin": broken', b'{"toolUseResult": {"agentId": broken'],
        )
        result = transcripts.Reader(cfg).read(NOW)
        self.assertEqual(0, result.notes["malformed_lines"])

    def test_a_row_with_a_bad_timestamp_is_ignored(self):
        cfg = self.config()
        rows = [
            self.row(
                "user",
                toolUseResult={"agentId": "kid"},
                timestamp="not a time",
                message={
                    "role": "user",
                    "content": [{"type": "tool_result", "content": "x"}],
                },
            )
        ]
        self.write(self.agent_path(cfg), rows)
        self.assertEqual((), self.links(cfg).launched)

    def test_a_tool_input_that_holds_the_word_keeps_its_usage_record(self):
        for field in ("pattern", "query"):
            for separators in ((",", ":"), (", ", ": ")):
                with self.subTest(field=field, separators=separators):
                    cfg = self.config()
                    grep = {
                        "type": "assistant",
                        "timestamp": "2026-11-04T09:59:00.000Z",
                        "isSidechain": True,
                        "agentId": RUN,
                        "message": {
                            "role": "assistant",
                            "model": "claude-test",
                            "stop_reason": None,
                            "content": [
                                {
                                    "type": "tool_use",
                                    "name": "Grep",
                                    "input": {field: "toolUseResult"},
                                }
                            ],
                            "usage": {"input_tokens": 3, "output_tokens": 4},
                        },
                    }
                    launch = {
                        "type": "user",
                        "timestamp": "2026-11-04T10:00:00.000Z",
                        "isSidechain": True,
                        "agentId": RUN,
                        "toolUseResult": {"agentId": "kid", "prompt": BODY},
                        "message": {
                            "role": "user",
                            "content": [{"type": "tool_result", "content": BODY}],
                        },
                    }
                    self.write(
                        self.agent_path(cfg),
                        [
                            json.dumps(r, separators=separators).encode("utf-8")
                            for r in (grep, launch)
                        ],
                    )
                    result = transcripts.Reader(cfg).read_folder(FOLDER, NOW)
                    self.assertEqual(1, len(result.records))
                    self.assertEqual(
                        ["kid"],
                        [pair[0] for pair in links_of(result)[(S1, RUN)].launched],
                    )


if __name__ == "__main__":
    unittest.main()
