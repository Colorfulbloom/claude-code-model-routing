"""Tests for the pin check (dashboard/pincheck.py).

Entries are small hand-built dicts in the resolver's shape. The demo class at
the end runs the real reader, resolver and usage views on the made-up demo set.
Nothing here reads the real ~/.claude.
"""
import datetime
import itertools
import json
import os
import sys
import tempfile
import unittest
import zoneinfo

import helpers

sys.path.insert(0, os.path.join(helpers.REPO, "dashboard"))
sys.path.insert(0, os.path.join(helpers.FIXTURES, "demo"))
import build_demo  # noqa: E402
import pincheck  # noqa: E402
import prices as prices_mod  # noqa: E402
import resolve  # noqa: E402
import transcripts  # noqa: E402
import usage  # noqa: E402

CATALOG = resolve.load_rules()["models"]
PRICES = prices_mod.load_prices()
UTC = datetime.timezone.utc

OPUS = "claude-opus-5-5"
SONNET = "claude-sonnet-5-5"
HAIKU = "claude-haiku-4-5"
FABLE = "claude-fable-5-1"


def entry(key, value, status="in_effect", layer="agent", agent="a", scope="agent",
          file="agents/a.md", line=4, **kw):
    out = {"key": key, "value": value, "status": status, "layer": layer, "scope": scope,
           "file": file, "line": line}
    if scope == "agent":
        out["agent"] = agent
    out.update(kw)
    return out


def agent_file(agent="a"):
    return entry("agentFile", None, agent=agent, line=2)


def run(model=OPUS, effort="high", run_id="r"):
    return {"run_id": run_id, "model": model, "effort": effort, "requests": 1}


def runs_of(models=(), efforts=()):
    """Runs from two parallel lists. A shorter list repeats its last value."""
    n = max(len(models), len(efforts), 1)
    pick = lambda items, i, default: items[min(i, len(items) - 1)] if items else default
    return [run(pick(models, i, OPUS), pick(efforts, i, "high"), "r%d" % i) for i in range(n)]


def check(entries, runs, key="a"):
    return pincheck.check_agent(entries, key, [], runs, CATALOG)


# One setting in each state: (entries for that key, values two runs show).
# X is the pin, Y what a lowered pin becomes, W the winner that beats a lost pin
# and Z a value nobody set.
VALUES = {"model": dict(X=OPUS, Y=SONNET, W=HAIKU, Z=FABLE),
          "effort": dict(X="high", Y="medium", W="xhigh", Z="low")}


def setting_case(kind, state):
    v = VALUES[kind]
    if state == pincheck.MATCHES:
        return [entry(kind, v["X"])], [v["X"], v["X"]]
    if state == pincheck.MATCHES_LOWERED:
        return [entry(kind, v["X"], "lowered", becomes=v["Y"])], [v["Y"], v["Y"]]
    if state == pincheck.OVERRIDDEN:
        return ([entry(kind, v["X"], "overridden"),
                 entry(kind, v["W"], "in_effect", layer="env", file="s.json")],
                [v["W"], v["W"]])
    if state == pincheck.CANNOT_CHECK:
        return [entry(kind, v["X"], "unknown")], [v["X"], v["X"]]
    if state == pincheck.DIFFERS:
        return [entry(kind, v["X"])], [v["Z"], v["Z"]]
    if state == pincheck.MIXED:
        return [entry(kind, v["X"])], [v["X"], v["Z"]]
    raise AssertionError(state)


def pair_case(model_state, effort_state):
    m_entries, m_values = setting_case("model", model_state)
    e_entries, e_values = setting_case("effort", effort_state)
    return [agent_file()] + m_entries + e_entries, runs_of(m_values, e_values)


class TestStatesOneSetting(unittest.TestCase):
    """Each of the six states, on each setting alone."""

    def test_each_state_on_each_setting(self):
        for kind in ("model", "effort"):
            for state in pincheck.STATES:
                with self.subTest(kind=kind, state=state):
                    rows, values = setting_case(kind, state)
                    runs = runs_of(values if kind == "model" else (), values if kind == "effort" else ())
                    got = check([agent_file()] + rows, runs)
                    self.assertEqual(state, got["state"])
                    self.assertEqual(state, got[kind]["state"])
                    self.assertIsNone(got["effort" if kind == "model" else "model"])
                    self.assertEqual("model_only" if kind == "model" else "effort_only", got["pinned"])
                    self.assertEqual("agent_file", got["source"])

    def test_the_six_states_in_order(self):
        self.assertEqual(("differs", "mixed", "overridden", "cannot_check", "matches_lowered", "matches"),
                         pincheck.STATES)

    def test_a_pin_that_won_and_runs_that_agree_on_something_else_differs(self):
        rows = [agent_file(), entry("effort", "high", "default")]
        self.assertEqual("differs", check(rows, runs_of(efforts=["low", "low"]))["state"])

    def test_a_lost_pin_with_runs_that_equal_the_pin_is_overridden(self):
        rows = [agent_file(), entry("effort", "high", "ignored"),
                entry("effort", "xhigh", layer="env", file="s.json")]
        got = check(rows, runs_of(efforts=["high"]))
        self.assertEqual("overridden", got["state"])
        self.assertTrue(got["effort"]["runs_match_pin"])

    def test_a_won_and_lowered_pin_with_every_run_at_the_pin_matches(self):
        rows = [agent_file(), entry("effort", "xhigh", "lowered", becomes="high")]
        got = check(rows, runs_of(efforts=["xhigh", "xhigh"]))
        self.assertEqual("matches", got["state"])
        self.assertTrue(got["effort"]["runs_match_pin"])

    def test_a_won_and_lowered_pin_with_runs_at_what_it_becomes_stays_matches_lowered(self):
        rows = [agent_file(), entry("effort", "xhigh", "lowered", becomes="high")]
        got = check(rows, runs_of(efforts=["high", "high"]))
        self.assertEqual("matches_lowered", got["state"])
        self.assertFalse(got["effort"]["runs_match_pin"])

    def test_runs_match_pin_is_false_in_every_other_case(self):
        for kind in ("model", "effort"):
            for state in (pincheck.MATCHES, pincheck.MATCHES_LOWERED, pincheck.CANNOT_CHECK,
                          pincheck.DIFFERS, pincheck.MIXED):
                rows, values = setting_case(kind, state)
                runs = runs_of(values if kind == "model" else (), values if kind == "effort" else ())
                got = check([agent_file()] + rows, runs)
                self.assertFalse(got[kind]["runs_match_pin"], (kind, state))
        rows, values = setting_case("effort", pincheck.OVERRIDDEN)
        self.assertFalse(check([agent_file()] + rows, runs_of(efforts=values))["effort"]["runs_match_pin"])

    def test_pinned_id_is_the_catalog_id_of_an_alias(self):
        got = check([agent_file(), entry("model", "opus"), entry("effort", "high")], runs_of())
        self.assertEqual(OPUS, got["model"]["pinned"]["id"])
        self.assertEqual("high", got["effort"]["pinned"]["id"])

    def test_lost_pin_statuses_all_give_overridden(self):
        for status in ("overridden", "ignored", "invalid"):
            rows = [agent_file(), entry("effort", "high", status),
                    entry("effort", "xhigh", layer="env", file="s.json")]
            self.assertEqual("overridden", check(rows, runs_of(efforts=["xhigh"]))["state"], status)

    def test_default_counts_as_won(self):
        rows = [agent_file(), entry("effort", "high", "default")]
        self.assertEqual("matches", check(rows, runs_of(efforts=["high"]))["state"])

    def test_model_names_compare_through_the_catalog(self):
        # A dated pin and a catalog id are the same model.
        rows = [agent_file(), entry("model", HAIKU + "-20251001")]
        self.assertEqual("matches", check(rows, runs_of(models=[HAIKU]))["state"])
        # An alias too, and inherit with the resolved value in value.
        rows = [agent_file(), entry("model", "sonnet", raw="sonnet")]
        self.assertEqual("matches", check(rows, runs_of(models=[SONNET]))["state"])
        rows = [agent_file(), entry("model", SONNET, raw="inherit")]
        self.assertEqual("matches", check(rows, runs_of(models=[SONNET]))["state"])

    def test_an_unknown_model_name_compares_as_written(self):
        rows = [agent_file(), entry("model", "my-model")]
        self.assertEqual("matches", check(rows, runs_of(models=["my-model"]))["state"])
        self.assertEqual("differs", check(rows, runs_of(models=["other"]))["state"])

    def test_no_value_is_cannot_check(self):
        rows = [agent_file(), entry("effort", None)]
        self.assertEqual("cannot_check", check(rows, runs_of(efforts=["high"]))["state"])

    def test_a_lowered_winner_without_becomes_is_cannot_check(self):
        rows = [agent_file(), entry("effort", "xhigh", "lowered")]
        self.assertEqual("cannot_check", check(rows, runs_of(efforts=["high"]))["state"])


class TestWhoGetsAPin(unittest.TestCase):
    def test_a_built_in_agent_has_no_pin(self):
        rows = [agent_file("other"), entry("effort", "high", agent="other")]
        self.assertIsNone(check(rows, [run()], key="general-purpose"))
        self.assertIsNone(check([], [run()], key="Explore"))

    def test_unnamed_has_no_pin(self):
        self.assertIsNone(check([agent_file()], [run()], key="@unnamed"))

    def test_an_agent_with_no_file_row_but_agent_layer_entries_is_checked(self):
        got = check([entry("effort", "high")], runs_of(efforts=["high"]))
        self.assertEqual("matches", got["state"])

    def test_other_agents_entries_are_not_used(self):
        rows = [agent_file(), entry("effort", "high"),
                entry("effort", "low", agent="b"), entry("model", HAIKU, agent="b")]
        got = check(rows, runs_of(efforts=["high"]))
        self.assertEqual("effort_only", got["pinned"])
        self.assertEqual("matches", got["state"])

    def test_a_model_only_file(self):
        # The effort row has a winner from elsewhere, but the file pins none.
        rows = [agent_file(), entry("model", OPUS),
                entry("effort", "xhigh", layer="env", file="s.json")]
        got = check(rows, runs_of(models=[OPUS], efforts=["low"]))
        self.assertEqual("model_only", got["pinned"])
        self.assertEqual("matches", got["state"])
        self.assertIsNone(got["effort"])
        self.assertEqual(0, got["mismatched_runs"])

    def test_an_effort_only_file_never_gives_cannot_check_for_the_model(self):
        rows = [agent_file(), entry("effort", "high")]
        got = check(rows, runs_of(models=["whatever-model"], efforts=["high"]))
        self.assertEqual("effort_only", got["pinned"])
        self.assertEqual("matches", got["state"])
        self.assertIsNone(got["model"])

    def test_a_file_that_pins_neither(self):
        rows = [agent_file(), entry("effort", "xhigh", layer="env", file="s.json")]
        got = check(rows, [run()])
        self.assertIsNotNone(got)
        self.assertEqual("none", got["pinned"])
        self.assertIsNone(got["state"])
        self.assertIsNone(got["model"])
        self.assertIsNone(got["effort"])
        self.assertEqual((0, 1), (got["mismatched_runs"], got["total_runs"]))

    def test_no_runs_gives_no_state(self):
        got = check([agent_file(), entry("effort", "high")], [])
        self.assertIsNone(got["state"])
        self.assertEqual((0, 0), (got["mismatched_runs"], got["total_runs"]))
        self.assertEqual([], got["effort"]["ran"])


class TestMain(unittest.TestCase):
    def rows(self, model_status="in_effect", effort_status="lowered"):
        return [
            entry("model", OPUS, model_status, layer="user", scope="main", file="config/settings.json", line=2),
            entry("model", "sonnet", "overridden", layer="project", scope="main", file="p.json"),
            entry("effortLevel", "xhigh", effort_status, layer="env", scope="main",
                  file="p/local.json", line=3, model=OPUS, becomes="high", via="CLAUDE_CODE_EFFORT_LEVEL"),
            entry("effortLevel", "medium", "overridden", layer="project", scope="main", file="p.json"),
        ]

    def test_main_matches_lowered(self):
        got = check(self.rows(), [run(OPUS, "high")], key="@main")
        self.assertEqual("matches_lowered", got["state"])
        self.assertEqual("settings", got["source"])
        self.assertEqual("both", got["pinned"])
        self.assertEqual(("xhigh", "p/local.json", 3), tuple(got["effort"]["pinned"][k] for k in ("value", "file", "line")))
        self.assertEqual("matches", got["model"]["state"])
        self.assertEqual("config/settings.json", got["model"]["pinned"]["file"])

    def test_main_matches(self):
        rows = self.rows(effort_status="in_effect")
        self.assertEqual("matches", check(rows, [run(OPUS, "xhigh")], key="@main")["state"])

    def test_main_differs_mixed_and_cannot_check(self):
        self.assertEqual("differs", check(self.rows(), [run(OPUS, "low")], key="@main")["state"])
        self.assertEqual("mixed", check(self.rows(), [run(OPUS, "high"), run(OPUS, "low")], key="@main")["state"])
        self.assertEqual("cannot_check", check(self.rows("unknown"), [run(OPUS, "high")], key="@main")["state"])

    def test_main_with_no_winner_in_a_row_leaves_it_out(self):
        rows = [r for r in self.rows() if r["key"] == "model"]
        got = check(rows, [run(OPUS, "low")], key="@main")
        self.assertEqual("model_only", got["pinned"])
        self.assertEqual("matches", got["state"])

    def test_main_never_gives_overridden(self):
        for effort in ("xhigh", "high", "medium", "low"):
            for model in (OPUS, SONNET):
                got = check(self.rows(), [run(model, effort)], key="@main")
                self.assertNotEqual("overridden", got["state"])


class TestWorstOf(unittest.TestCase):
    def test_every_pair_gives_the_worse_state(self):
        for model_state, effort_state in itertools.product(pincheck.STATES, repeat=2):
            with self.subTest(model=model_state, effort=effort_state):
                rows, runs = pair_case(model_state, effort_state)
                got = check(rows, runs)
                want = min(model_state, effort_state, key=pincheck.STATES.index)
                self.assertEqual(want, got["state"])
                self.assertEqual(model_state, got["model"]["state"])
                self.assertEqual(effort_state, got["effort"]["state"])
                self.assertEqual("both", got["pinned"])

    def test_cannot_check_is_worse_than_matches(self):
        for other in ("matches", "matches_lowered"):
            rows, runs = pair_case("cannot_check", other)
            self.assertEqual("cannot_check", check(rows, runs)["state"])
            rows, runs = pair_case(other, "cannot_check")
            self.assertEqual("cannot_check", check(rows, runs)["state"])

    def test_cannot_check_is_better_than_overridden(self):
        rows, runs = pair_case("cannot_check", "overridden")
        self.assertEqual("overridden", check(rows, runs)["state"])
        rows, runs = pair_case("overridden", "cannot_check")
        self.assertEqual("overridden", check(rows, runs)["state"])

    def test_worst_helper(self):
        self.assertIsNone(pincheck.worst([None, None]))
        self.assertEqual("mixed", pincheck.worst([None, "matches", "mixed", "overridden"]))


class TestMismatchedRuns(unittest.TestCase):
    ROWS = [agent_file(), entry("model", OPUS), entry("effort", "high")]

    def test_a_run_off_on_both_settings_counts_once(self):
        runs = [run(OPUS, "high", "r1"), run(SONNET, "low", "r2"), run(SONNET, "high", "r3"),
                run(OPUS, "low", "r4")]
        got = check(self.ROWS, runs)
        self.assertEqual("mixed", got["state"])
        self.assertEqual((3, 4), (got["mismatched_runs"], got["total_runs"]))

    def test_a_run_with_no_effort_is_left_out_of_the_effort_check(self):
        runs = [run(OPUS, "high", "r1"), run(OPUS, None, "r2"), run(OPUS, "high", "r3")]
        got = check(self.ROWS, runs)
        self.assertEqual("matches", got["state"])
        self.assertEqual((0, 3), (got["mismatched_runs"], got["total_runs"]))
        self.assertEqual(["high"], got["effort"]["ran"])

    def test_a_run_with_no_effort_still_counts_through_its_model(self):
        runs = [run(OPUS, "high", "r1"), run(SONNET, None, "r2")]
        got = check(self.ROWS, runs)
        self.assertEqual("mixed", got["state"])
        self.assertEqual((1, 2), (got["mismatched_runs"], got["total_runs"]))

    def test_no_run_has_an_effort(self):
        runs = [run(OPUS, None, "r1"), run(OPUS, None, "r2")]
        got = check(self.ROWS, runs)
        self.assertIsNone(got["effort"]["state"])
        self.assertEqual("matches", got["model"]["state"])
        self.assertEqual("matches", got["state"])
        self.assertEqual((0, 2), (got["mismatched_runs"], got["total_runs"]))

    def test_a_known_expected_value_with_no_recorded_run_value_adds_nothing(self):
        rows = [agent_file(), entry("model", OPUS), entry("effort", "high")]
        runs = [run(OPUS, None, "r1"), run(OPUS, None, "r2")]
        got = check(rows, runs)
        self.assertEqual("matches", got["state"])
        self.assertIsNone(got["effort"]["state"])
        # an Unknown expected value is still cannot_check, even with no run value
        rows = [agent_file(), entry("model", OPUS), entry("effort", "high", "unknown")]
        got = check(rows, runs)
        self.assertEqual("cannot_check", got["effort"]["state"])
        self.assertEqual("cannot_check", got["state"])

    def test_a_cannot_check_setting_adds_nothing_to_n(self):
        rows = [agent_file(), entry("model", OPUS), entry("effort", "high", "unknown")]
        runs = [run(OPUS, "low", "r1"), run(SONNET, "low", "r2")]
        got = check(rows, runs)
        self.assertEqual("mixed", got["state"])
        self.assertEqual((1, 2), (got["mismatched_runs"], got["total_runs"]))

    def test_runs_at_a_lost_pin_do_not_count_against_it(self):
        rows = [agent_file(), entry("effort", "high", "overridden"),
                entry("effort", "xhigh", layer="env", file="s.json")]
        runs = [run(OPUS, "high", "r%d" % i) for i in range(3)] + [run(OPUS, "xhigh", "w1"), run(OPUS, "xhigh", "w2")]
        got = check(rows, runs)
        self.assertEqual("mixed", got["state"])
        self.assertEqual((2, 5), (got["mismatched_runs"], got["total_runs"]))

    def test_n_and_m_are_filled_for_every_state(self):
        for state in pincheck.STATES:
            rows, runs = pair_case(state, state)
            got = check(rows, runs)
            self.assertEqual(len(runs), got["total_runs"], state)
            self.assertIsInstance(got["mismatched_runs"], int)
        rows, runs = pair_case("differs", "differs")
        self.assertEqual(2, check(rows, runs)["mismatched_runs"])
        rows, runs = pair_case("matches", "matches")
        self.assertEqual(0, check(rows, runs)["mismatched_runs"])

    def test_overridden_runs_are_not_mismatched(self):
        rows, runs = pair_case("overridden", "overridden")
        self.assertEqual(0, check(rows, runs)["mismatched_runs"])


class TestSettingData(unittest.TestCase):
    def test_ran_lists_distinct_values_most_common_first(self):
        runs = runs_of(efforts=["low", "high", "high", "low", "medium", "high"])
        got = check([agent_file(), entry("effort", "high")], runs)
        self.assertEqual(["high", "low", "medium"], got["effort"]["ran"])

    def test_pinned_and_expected_carry_value_file_line_and_source(self):
        rows = [agent_file(),
                entry("effort", "high", "overridden", file="agents/a.md", line=5),
                entry("effort", "xhigh", "in_effect", layer="env", file="s.json", line=3,
                      via="CLAUDE_CODE_EFFORT_LEVEL", reason="why", rule_id="r-1")]
        got = check(rows, runs_of(efforts=["xhigh"]))["effort"]
        self.assertEqual({"value": "high", "file": "agents/a.md", "line": 5, "status": "overridden", "id": "high"}, got["pinned"])
        self.assertEqual({"value": "xhigh", "status": "in_effect", "becomes": None, "key": "effort",
                          "file": "s.json", "line": 3, "layer": "env", "via": "CLAUDE_CODE_EFFORT_LEVEL",
                          "reason": "why", "rule_id": "r-1"}, got["expected"])
        self.assertIsNone(got["cap"])

    def test_cap_comes_from_the_winning_max_effort_entry(self):
        cap = entry("maxEffortLevel", "medium", layer="project", scope="main", file="p.json", line=9, model=FABLE)
        other = entry("maxEffortLevel", "low", layer="project", scope="main", file="q.json", line=1, model=OPUS)
        lost = entry("maxEffortLevel", "high", "overridden", layer="user", scope="main", file="u.json", line=2, model=FABLE)
        rows = [agent_file(), entry("effort", "xhigh", "overridden"),
                entry("effort", "xhigh", "lowered", layer="env", file="s.json", line=3, becomes="medium", model=FABLE)]
        got = check(rows + [other, lost, cap], runs_of(efforts=["medium"]))["effort"]
        self.assertEqual({"key": "maxEffortLevel", "value": "medium", "model": FABLE, "file": "p.json", "line": 9},
                         got["cap"])

    def test_cap_has_no_file_when_no_row_won_for_that_model(self):
        rows = [agent_file(), entry("effort", "xhigh", "overridden"),
                entry("effort", "xhigh", "lowered", layer="env", file="s.json", line=3, becomes="medium", model=FABLE)]
        got = check(rows, runs_of(efforts=["medium"]))["effort"]
        self.assertEqual({"key": "maxEffortLevel", "value": "medium", "model": FABLE, "file": None, "line": None},
                         got["cap"])

    def test_the_builder_sentence_has_its_data(self):
        rows = [agent_file("builder"),
                entry("model", FABLE, agent="builder"),
                entry("effort", "xhigh", "overridden", agent="builder", file="agents/builder.md", line=5),
                entry("effort", "xhigh", "lowered", layer="env", agent="builder", file="local.json", line=3,
                      becomes="medium", model=FABLE, via="CLAUDE_CODE_EFFORT_LEVEL"),
                entry("maxEffortLevel", "medium", layer="project", scope="main", file="p.json", line=4, model=FABLE)]
        got = check(rows, runs_of(models=[FABLE], efforts=["medium"] * 3), key="builder")
        self.assertEqual("overridden", got["state"])
        eff = got["effort"]
        self.assertEqual("xhigh", eff["pinned"]["value"])
        self.assertEqual("agents/builder.md", eff["pinned"]["file"])
        self.assertEqual("medium", eff["expected"]["becomes"])
        self.assertEqual("CLAUDE_CODE_EFFORT_LEVEL", eff["expected"]["via"])
        self.assertEqual(("local.json", 3), (eff["expected"]["file"], eff["expected"]["line"]))
        self.assertEqual(("medium", "p.json", 4), (eff["cap"]["value"], eff["cap"]["file"], eff["cap"]["line"]))

    def test_checker_gives_a_pin_fn_with_the_usage_signature(self):
        rows = [agent_file(), entry("effort", "high")]
        fn = pincheck.checker(rows, CATALOG)
        got = fn("a", [{"model": OPUS, "effort": "high", "requests": 1, "runs": 1}], runs_of(efforts=["high"]))
        self.assertEqual("matches", got["state"])
        self.assertIsNone(fn("@unnamed", [], [run()]))
        self.assertIsNone(fn("Explore", [], [run()]))

    def test_the_input_is_not_changed(self):
        rows, runs = pair_case("overridden", "differs")
        before = json.dumps([rows, runs], sort_keys=True)
        check(rows, runs)
        self.assertEqual(before, json.dumps([rows, runs], sort_keys=True))


class TestDemoSet(unittest.TestCase):
    """The real reader, resolver and usage views on the made-up demo set."""

    PROJECT = "Tidewater reporting"

    @classmethod
    def setUpClass(cls):
        cls.tmp = os.path.realpath(tempfile.mkdtemp(prefix="d-", dir=helpers._tmp_base()))
        out = os.path.join(cls.tmp, "set")
        truth = build_demo.build(out)
        now = datetime.datetime.strptime(truth["window"]["end"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
        tz = zoneinfo.ZoneInfo(truth["window"]["tz"])
        result = transcripts.Reader(os.path.join(out, "config")).read(now)
        with open(os.path.join(out, "config", "routing-dashboard.json"), encoding="utf-8") as fh:
            listed = json.load(fh)["projects"]
        projects = [{"key": p["name"], "name": p["name"], "path": p["path"]} for p in listed]
        folders = transcripts.project_folders(projects, result.records)
        cls.shown = [{"key": p["key"], "name": p["name"], "folder": folders[p["key"]]} for p in projects]
        rules = resolve.load_rules()
        inputs = build_demo.inputs_for(out, cls.PROJECT, rules)
        cls.entries = resolve.resolve(inputs, rules, resolve.load_agent_fields())

        def build(scope):
            return usage.build_views(result.records, scope, now, tz, PRICES, CATALOG, result.oldest_by_folder,
                                     projects=cls.shown, pin_fn=pincheck.checker(cls.entries, CATALOG))
        cls.single = build(cls.PROJECT)["30d"]
        cls.everything = build("all")["30d"]

    @classmethod
    def tearDownClass(cls):
        helpers.rmtree_force(cls.tmp)

    def agent(self, key):
        return [r for r in self.single["by_agent"] if r["route_key"] == key][0]

    def test_builder_and_reviewer_are_overridden(self):
        self.assertEqual("overridden", self.agent("builder")["pin"]["state"])
        self.assertEqual("overridden", self.agent("reviewer")["pin"]["state"])

    def test_scribe_differs(self):
        pin = self.agent("scribe")["pin"]
        self.assertEqual("differs", pin["state"])
        self.assertEqual("differs", pin["model"]["state"])
        self.assertEqual("overridden", pin["effort"]["state"])

    def test_main_matches_with_the_lowered_note(self):
        pin = self.agent("@main")["pin"]
        self.assertEqual("matches_lowered", pin["state"])
        self.assertEqual("settings", pin["source"])
        self.assertEqual("matches", pin["model"]["state"])
        self.assertEqual("xhigh", pin["effort"]["expected"]["value"])
        self.assertEqual("high", pin["effort"]["expected"]["becomes"])

    def test_the_data_for_the_builder_sentence(self):
        pin = self.agent("builder")["pin"]
        eff = pin["effort"]
        self.assertEqual("both", pin["pinned"])
        self.assertEqual("agent_file", pin["source"])
        self.assertEqual("xhigh", eff["pinned"]["value"])
        self.assertEqual("config/agents/builder.md", eff["pinned"]["file"])
        self.assertEqual(5, eff["pinned"]["line"])
        self.assertEqual("lowered", eff["expected"]["status"])
        self.assertEqual("xhigh", eff["expected"]["value"])
        self.assertEqual("medium", eff["expected"]["becomes"])
        self.assertEqual("effort", eff["expected"]["key"])
        self.assertEqual("env", eff["expected"]["layer"])
        self.assertEqual("CLAUDE_CODE_EFFORT_LEVEL", eff["expected"]["via"])
        self.assertEqual("projects/tidewater-reporting/.claude/settings.local.json", eff["expected"]["file"])
        self.assertEqual(3, eff["expected"]["line"])
        self.assertEqual("maxEffortLevel", eff["cap"]["key"])
        self.assertEqual("medium", eff["cap"]["value"])
        self.assertEqual("claude-fable-5-1", eff["cap"]["model"])
        self.assertEqual(["medium"], eff["ran"])
        self.assertEqual(pin["total_runs"], self.agent("builder")["runs"])
        self.assertEqual(0, pin["mismatched_runs"])

    def test_a_single_project_view_fills_pin(self):
        for key in ("builder", "reviewer", "scribe", "@main"):
            self.assertIsNotNone(self.agent(key)["pin"], key)

    def test_all_projects_leaves_pin_empty(self):
        self.assertTrue(self.everything["by_agent"])
        for row in self.everything["by_agent"]:
            self.assertIsNone(row["pin"], row["route_key"])


if __name__ == "__main__":
    unittest.main()
