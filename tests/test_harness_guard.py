"""Tests for the guard in dashboard/experiments/harness/runcase.py.

Each test writes a case file in a temp folder and runs runcase.py with a fake
`claude` first on PATH. The fake claude records its environment in a marker file,
so a refused case must leave no marker (claude never started) and no folder made
by runcase.py. Nothing here touches the real ~/.claude or the network.
"""
import glob
import importlib.util
import json
import os
import shutil
import socket
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

import helpers

RUNCASE = os.path.join(helpers.REPO, "dashboard", "experiments", "harness", "runcase.py")
PYTHON = "/usr/bin/python3"
HARNESS = os.path.dirname(RUNCASE)


def load_runcase():
    spec = importlib.util.spec_from_file_location("runcase_under_test", RUNCASE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

FAKE_CLAUDE = """#!/usr/bin/python3
import json, os, sys
with open(%r, "w") as fh:
    json.dump(dict(os.environ), fh)
with open(%r, "w") as fh:
    json.dump(sys.argv, fh)
"""

# What the child may hold: three caller variables and the fixed values.
EXPECTED_CHILD_ENV = {
    "PATH", "TMPDIR", "LANG", "HOME", "CLAUDE_CONFIG_DIR", "ANTHROPIC_API_KEY",
    "ANTHROPIC_BASE_URL", "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC",
    "CLAUDE_CODE_DISABLE_OFFICIAL_MARKETPLACE_AUTOINSTALL", "DISABLE_AUTOUPDATER",
}
# Added by macOS and by the /usr/bin/python3 shim that runs the fake claude, not by runcase.py.
SYSTEM_ADDED = {"__CF_USER_TEXT_ENCODING", "CPATH", "LIBRARY_PATH", "SDKROOT", "MANPATH"}


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class GuardTestBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="harness-guard-", dir=helpers._tmp_base())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.bin = os.path.join(self.tmp, "bin")
        self.scratch = os.path.join(self.tmp, "scratch")
        os.makedirs(self.bin)
        os.makedirs(self.scratch)
        self.marker = os.path.join(self.tmp, "claude-started.json")
        self.argv_marker = os.path.join(self.tmp, "claude-argv.json")
        fake = os.path.join(self.bin, "claude")
        with open(fake, "w") as fh:
            fh.write(FAKE_CLAUDE % (self.marker, self.argv_marker))
        os.chmod(fake, os.stat(fake).st_mode | stat.S_IXUSR)

    def run_case(self, case, caller_extra=None):
        path = os.path.join(self.tmp, "case.json")
        with open(path, "w") as fh:
            json.dump(case, fh)
        # No ANTHROPIC_* variables, unless a test adds one on purpose.
        env = {"PATH": self.bin + ":/usr/bin:/bin", "TMPDIR": self.scratch, "LANG": "en_US.UTF-8"}
        env.update(caller_extra or {})
        return subprocess.run([PYTHON, RUNCASE, path, str(free_port())], env=env,
                              capture_output=True, text=True, timeout=60,
                              stdin=subprocess.DEVNULL)

    def assert_refused(self, case, caller_extra=None, mention=None):
        r = self.run_case(case, caller_extra)
        self.assertEqual(r.returncode, 2, "stdout=%r stderr=%r" % (r.stdout, r.stderr))
        self.assertIn("runcase refused", r.stderr)
        if mention:
            self.assertIn(mention, r.stderr)
        self.assertFalse(os.path.exists(self.marker), "claude started")
        self.assertEqual(os.listdir(self.scratch), [], "runcase.py made a folder before refusing")


class RefusedCases(GuardTestBase):
    def test_env_use_mantle(self):
        self.assert_refused({"name": "t", "env": {"CLAUDE_CODE_USE_MANTLE": "1"}},
                            mention="CLAUDE_CODE_USE_MANTLE")

    def test_env_use_anthropic_aws(self):
        self.assert_refused({"name": "t", "env": {"CLAUDE_CODE_USE_ANTHROPIC_AWS": "1"}},
                            mention="CLAUDE_CODE_USE_ANTHROPIC_AWS")

    def test_env_aws_bearer_token(self):
        self.assert_refused({"name": "t", "env": {"AWS_BEARER_TOKEN_BEDROCK": "x"}},
                            mention="AWS_BEARER_TOKEN_BEDROCK")

    def test_env_otel_endpoint(self):
        self.assert_refused(
            {"name": "t", "env": {"OTEL_EXPORTER_OTLP_ENDPOINT": "http://example.invalid"}},
            mention="OTEL_EXPORTER_OTLP_ENDPOINT")

    def test_env_beta_tracing_endpoint(self):
        self.assert_refused(
            {"name": "t", "env": {"BETA_TRACING_ENDPOINT": "http://example.invalid"}},
            mention="BETA_TRACING_ENDPOINT")

    def test_project_settings_hooks(self):
        hooks = {"SessionStart": [{"hooks": [{"type": "command",
                                              "command": "curl http://example.invalid"}]}]}
        self.assert_refused({"name": "t", "project": {"hooks": hooks}}, mention="hooks")

    def test_user_settings_env_disable_nonessential_traffic(self):
        self.assert_refused(
            {"name": "t", "user": {"env": {"CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": ""}}},
            mention="CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC")

    def test_user_settings_env_disable_marketplace_autoinstall(self):
        self.assert_refused(
            {"name": "t",
             "user": {"env": {"CLAUDE_CODE_DISABLE_OFFICIAL_MARKETPLACE_AUTOINSTALL": "0"}}},
            mention="CLAUDE_CODE_DISABLE_OFFICIAL_MARKETPLACE_AUTOINSTALL")

    def test_case_env_disable_autoupdater(self):
        self.assert_refused({"name": "t", "env": {"DISABLE_AUTOUPDATER": "0"}},
                            mention="DISABLE_AUTOUPDATER")

    def test_project_settings_status_line(self):
        self.assert_refused(
            {"name": "t", "project": {"statusLine": {"type": "command", "command": "echo"}}},
            mention="statusLine")

    def test_local_settings_mcp_servers(self):
        self.assert_refused({"name": "t", "local": {"mcpServers": {}}}, mention="mcpServers")

    def test_cli_settings_enable_all_project_mcp_servers(self):
        self.assert_refused({"name": "t", "cli_settings": {"enableAllProjectMcpServers": True}},
                            mention="enableAllProjectMcpServers")

    def test_user_settings_api_key_helper(self):
        self.assert_refused({"name": "t", "user": {"apiKeyHelper": "echo x"}},
                            mention="apiKeyHelper")

    def test_user_settings_otel_headers_helper(self):
        self.assert_refused({"name": "t", "user": {"otelHeadersHelper": "echo x"}},
                            mention="otelHeadersHelper")

    def test_args_mcp_config(self):
        self.assert_refused({"name": "t", "args": ["--mcp-config", "x.json"]}, mention="mcp")

    def test_args_strict_mcp_config(self):
        self.assert_refused({"name": "t", "args": ["--strict-mcp-config"]}, mention="mcp")

    def test_args_plugin_dir(self):
        self.assert_refused({"name": "t", "args": ["--plugin-dir", "x"]}, mention="--plugin-dir")

    def test_args_setting_sources(self):
        self.assert_refused({"name": "t", "args": ["--setting-sources", "user"]},
                            mention="--setting-sources")

    def test_args_settings_flag(self):
        self.assert_refused({"name": "t", "args": ["--settings", "x.json"]}, mention="--settings")

    def test_args_agents_and_add_dir(self):
        self.assert_refused({"name": "t", "args": ["--agents", "{}"]}, mention="--agents")
        self.assert_refused({"name": "t", "args": ["--add-dir", "/"]}, mention="--add-dir")

    def test_args_flag_without_value(self):
        self.assert_refused({"name": "t", "args": ["--model"]})

    def test_args_url(self):
        self.assert_refused({"name": "t", "args": ["--model", "http://example.invalid"]})

    def test_agent_frontmatter_hooks(self):
        text = "---\nname: probe\nhooks:\n  Stop: []\n---\nbody\n"
        self.assert_refused({"name": "t", "agents": {"probe": text}}, mention="hooks")

    def test_agent_frontmatter_hooks_in_any_form(self):
        forms = (
            '---\nname: probe\n"hooks": {}\n---\nbody\n',
            "---\nname: probe\nhooks : {}\n---\nbody\n",
            "---\nname: probe\n'hooks':\n  Stop: []\n---\nbody\n",
            "---\nname: probe\nHooks:\n  Stop: []\n---\nbody\n",
            "---\nname: probe\n  hooks: {}\n---\nbody\n",
            "---\n{name: probe, hooks: {}}\n---\nbody\n",
            "\ufeff---\nname: probe\nhooks: {}\n---\nbody\n",
        )
        for text in forms:
            with self.subTest(text=text):
                self.assert_refused({"name": "t", "agents": {"probe": text}},
                                    mention="frontmatter sets")

    def test_agent_frontmatter_mcp_servers_in_any_form(self):
        for text in ('---\nname: probe\n"mcpServers" : {}\n---\nbody\n',
                     "---\nname: probe\nmcpservers: {}\n---\nbody\n"):
            with self.subTest(text=text):
                self.assert_refused({"name": "t", "agents": {"probe": text}},
                                    mention="frontmatter sets")

    def test_agent_frontmatter_initial_prompt(self):
        for text in ("---\nname: probe\ninitialPrompt: /login\n---\nbody\n",
                     '---\nname: probe\n"initialPrompt" : x\n---\nbody\n'):
            with self.subTest(text=text):
                self.assert_refused({"name": "t", "agents": {"probe": text}},
                                    mention="initialPrompt")

    def test_agent_text_that_is_not_a_string(self):
        for bad in (5, None, ["---"], {"a": 1}):
            with self.subTest(text=bad):
                self.assert_refused({"name": "t", "agents": {"probe": bad}}, mention="not a string")

    def test_settings_keys_that_start_a_helper_or_load_a_plugin(self):
        keys = {"fileSuggestion": {"type": "command", "command": "echo"},
                "subagentStatusLine": {"type": "command", "command": "echo"},
                "gcpAuthRefresh": "echo x",
                "extraKnownMarketplaces": {},
                "enabledPlugins": {},
                "agent": "probe"}
        for layer in ("user", "project", "local", "cli_settings"):
            for key, value in keys.items():
                with self.subTest(layer=layer, key=key):
                    self.assert_refused({"name": "t", layer: {key: value}}, mention=key)

    def test_agent_input_keys_off_the_allowlist(self):
        for key in ("isolation", "run_in_background", "name", "mode"):
            with self.subTest(key=key):
                self.assert_refused({"name": "t", "agent_input": {"prompt": "go", key: "x"}},
                                    mention=key)

    def test_agent_input_values_that_are_not_strings(self):
        for bad in (5, None, True, ["go"], {"a": "b"}):
            with self.subTest(value=bad):
                self.assert_refused({"name": "t", "agent_input": {"prompt": bad}},
                                    mention="not a string")

    def test_agent_input_that_is_not_an_object(self):
        for bad in ("go", ["prompt"], 5):
            with self.subTest(agent_input=bad):
                self.assert_refused({"name": "t", "agent_input": bad}, mention="agent_input")

    def test_agent_frontmatter_mcp_servers(self):
        text = "---\nname: probe\nmcpServers:\n  x: {}\n---\nbody\n"
        self.assert_refused({"name": "t", "agents": {"probe": text}}, mention="mcpServers")

    def test_prompt_not_on_the_allowlist(self):
        self.assert_refused({"name": "t", "prompt": "/login"}, mention="prompt allowlist")
        self.assert_refused({"name": "t", "prompt": "say hi\n/effort"}, mention="prompt allowlist")

    def test_prompt_that_is_not_a_string(self):
        for bad in (5, None, ["say hi"], {"say": "hi"}):
            with self.subTest(prompt=bad):
                self.assert_refused({"name": "t", "prompt": bad}, mention="prompt allowlist")

    def test_text_reply_that_is_not_a_bool(self):
        for bad in ("yes", 1, "true", None):
            with self.subTest(text_reply=bad):
                self.assert_refused({"name": "t", "text_reply": bad}, mention="text_reply")

    def test_caller_shell_base_url(self):
        self.assert_refused({"name": "t"}, {"ANTHROPIC_BASE_URL": "http://example.invalid"},
                            mention="ANTHROPIC_BASE_URL")

    def test_caller_shell_api_key(self):
        self.assert_refused({"name": "t"}, {"ANTHROPIC_API_KEY": "sk-real"},
                            mention="ANTHROPIC_API_KEY")

    def test_caller_shell_auth_token(self):
        self.assert_refused({"name": "t"}, {"ANTHROPIC_AUTH_TOKEN": "tok"},
                            mention="ANTHROPIC_AUTH_TOKEN")


class InProcessChecks(GuardTestBase):
    def test_every_case_file_passes_check_case(self):
        runcase = load_runcase()
        files = sorted(glob.glob(os.path.join(HARNESS, "cases-*.json")))
        self.assertTrue(files)
        count = 0
        for path in files:
            with open(path) as fh:
                cases = json.load(fh)
            for case in cases if isinstance(cases, list) else [cases]:
                with self.subTest(file=os.path.basename(path), case=case.get("name")):
                    runcase.check_case(case)
                    count += 1
        self.assertGreater(count, 0)

    def test_read_transcript_drops_efforts_that_are_not_levels(self):
        runcase = load_runcase()
        cfg = os.path.join(self.tmp, "cfg")
        proj = os.path.join(cfg, "projects", "p")
        os.makedirs(proj)
        rows = [
            {"type": "assistant", "effort": "high", "perTurnEffort": "xhigh"},
            {"type": "assistant", "effort": "ultra", "perTurnEffort": 5},
            {"type": "assistant", "effort": {"a": 1}, "perTurnEffort": ["low"]},
            {"type": "assistant", "effort": "max"},
            {"type": "assistant", "effort": "HIGH", "perTurnEffort": "low\n"},
            {"type": "api-request", "params": {"output_config": {"effort": "medium"}}},
            {"type": "api-request", "params": {"output_config": {"effort": "<script>"}}},
            {"type": "api-request", "params": {"output_config": {"effort": 3}}},
        ]
        with open(os.path.join(proj, "s.jsonl"), "w") as fh:
            fh.write("\n".join(json.dumps(r) for r in rows))
        self.assertEqual(runcase.read_transcript(cfg), [
            ["main", "assistant", "high", "xhigh"],
            ["main", "assistant", None, None],
            ["main", "assistant", "max", None],
            ["main", "api-request", "medium", None],
            ["main", "api-request", None, None],
        ])

    def test_timeout_removes_the_throwaway_root(self):
        runcase = load_runcase()
        runcase.CLAUDE_TIMEOUT = 1
        slow = os.path.join(self.bin, "claude")
        with open(slow, "w") as fh:
            fh.write("#!/usr/bin/python3\nimport time\ntime.sleep(30)\n")
        path = os.path.join(self.tmp, "case.json")
        with open(path, "w") as fh:
            json.dump({"name": "slow"}, fh)
        env = {"PATH": self.bin + ":/usr/bin:/bin", "TMPDIR": self.scratch, "LANG": "en_US.UTF-8"}
        with mock.patch.dict(os.environ, env, clear=True), \
                mock.patch.object(sys, "argv", ["runcase.py", path, str(free_port())]):
            with self.assertRaises(subprocess.TimeoutExpired):
                runcase.main()
        self.assertEqual(os.listdir(self.scratch), [], "throwaway root left behind")


class AllowedCase(GuardTestBase):
    def test_allowed_case_starts_claude_with_a_closed_environment(self):
        leak = {"AWS_PROFILE": "leak", "HTTPS_PROXY": "http://leak", "OTEL_X": "leak",
                "CLAUDE_CODE_USE_BEDROCK": "1"}
        r = self.run_case({"name": "ok", "user": {"model": "claude-sonnet-5-5"},
                           "env": {"ANTHROPIC_MODEL": "claude-haiku-5-5"}}, leak)
        self.assertEqual(r.returncode, 0, "stdout=%r stderr=%r" % (r.stdout, r.stderr))
        self.assertNotIn("Traceback", r.stderr)
        # The fake claude exits at once: no init line, no api log.
        out = json.loads(r.stdout)
        self.assertEqual(out["case"], "ok")
        self.assertIsNone(out["init_model"])
        self.assertEqual(out["sent"], [])
        with open(self.marker) as fh:
            env = json.load(fh)
        extra = set(env) - EXPECTED_CHILD_ENV - SYSTEM_ADDED
        self.assertEqual(extra, {"ANTHROPIC_MODEL"})
        self.assertEqual(env["ANTHROPIC_MODEL"], "claude-haiku-5-5")
        for name in leak:
            self.assertNotIn(name, env)
        self.assertEqual(env["TMPDIR"], self.scratch)
        self.assertEqual(env["LANG"], "en_US.UTF-8")
        self.assertEqual(env["CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC"], "1")
        self.assertEqual(env["CLAUDE_CODE_DISABLE_OFFICIAL_MARKETPLACE_AUTOINSTALL"], "1")
        self.assertEqual(env["DISABLE_AUTOUPDATER"], "1")
        self.assertTrue(env["ANTHROPIC_BASE_URL"].startswith("http://127.0.0.1:"),
                        env["ANTHROPIC_BASE_URL"])
        self.assertEqual(env["ANTHROPIC_API_KEY"], "sk-ant-fake-000")
        self.assertTrue(env["HOME"].startswith(self.scratch))
        self.assertTrue(env["CLAUDE_CONFIG_DIR"].startswith(self.scratch))

    def test_effort_status_prompt_with_text_reply(self):
        r = self.run_case({"name": "ok", "prompt": "/effort status", "text_reply": True})
        self.assertEqual(r.returncode, 0, "stdout=%r stderr=%r" % (r.stdout, r.stderr))
        self.assertNotIn("Traceback", r.stderr)
        with open(self.argv_marker) as fh:
            argv = json.load(fh)
        self.assertEqual(argv[argv.index("-p") + 1], "/effort status")
        with open(self.marker) as fh:
            env = json.load(fh)
        # TEXT_REPLY is for the fake API only.
        self.assertNotIn("TEXT_REPLY", env)
        self.assertEqual(set(env) - EXPECTED_CHILD_ENV - SYSTEM_ADDED, set())
        out = json.loads(r.stdout)
        self.assertEqual(out["case"], "ok")
        self.assertEqual(out["transcript"], [])
        self.assertEqual(out["result"], [])

    def test_default_prompt_is_say_hi(self):
        r = self.run_case({"name": "ok"})
        self.assertEqual(r.returncode, 0, "stdout=%r stderr=%r" % (r.stdout, r.stderr))
        with open(self.argv_marker) as fh:
            argv = json.load(fh)
        self.assertEqual(argv[argv.index("-p") + 1], "say hi")


if __name__ == "__main__":
    unittest.main()
