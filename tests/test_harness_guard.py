"""Tests for the guard in dashboard/experiments/harness/runcase.py.

Each test writes a case file in a temp folder and runs runcase.py with a fake
`claude` first on PATH. The fake claude records its environment in a marker file,
so a refused case must leave no marker (claude never started) and no folder made
by runcase.py. Nothing here touches the real ~/.claude or the network.
"""
import json
import os
import shutil
import socket
import stat
import subprocess
import tempfile
import unittest

import helpers

RUNCASE = os.path.join(helpers.REPO, "dashboard", "experiments", "harness", "runcase.py")
PYTHON = "/usr/bin/python3"

FAKE_CLAUDE = """#!/usr/bin/python3
import json, os
with open(%r, "w") as fh:
    json.dump(dict(os.environ), fh)
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
        fake = os.path.join(self.bin, "claude")
        with open(fake, "w") as fh:
            fh.write(FAKE_CLAUDE % self.marker)
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
        self.assert_refused({"name": "t", "agents": {"probe": text}}, mention="hooks:")

    def test_agent_frontmatter_mcp_servers(self):
        text = "---\nname: probe\nmcpServers:\n  x: {}\n---\nbody\n"
        self.assert_refused({"name": "t", "agents": {"probe": text}}, mention="mcpServers")

    def test_caller_shell_base_url(self):
        self.assert_refused({"name": "t"}, {"ANTHROPIC_BASE_URL": "http://example.invalid"},
                            mention="ANTHROPIC_BASE_URL")

    def test_caller_shell_api_key(self):
        self.assert_refused({"name": "t"}, {"ANTHROPIC_API_KEY": "sk-real"},
                            mention="ANTHROPIC_API_KEY")

    def test_caller_shell_auth_token(self):
        self.assert_refused({"name": "t"}, {"ANTHROPIC_AUTH_TOKEN": "tok"},
                            mention="ANTHROPIC_AUTH_TOKEN")


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


if __name__ == "__main__":
    unittest.main()
