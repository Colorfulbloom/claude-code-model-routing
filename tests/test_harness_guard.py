"""Tests for the guard in dashboard/experiments/harness/runcase.py.

Each test writes a case file in a temp folder and runs runcase.py with a fake
`claude` first on PATH. The fake claude records its environment in a marker file,
so a refused case must leave no marker (claude never started) and no folder made
by runcase.py. Nothing here touches the real ~/.claude or the network.
"""
import contextlib
import glob
import importlib.util
import io
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
    "GIT_CONFIG_NOSYSTEM", "GIT_CONFIG_GLOBAL",
}
# Added by macOS and by the /usr/bin/python3 shim that runs the fake claude, not by runcase.py.
SYSTEM_ADDED = {"__CF_USER_TEXT_ENCODING", "CPATH", "LIBRARY_PATH", "SDKROOT", "MANPATH"}


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def agent_file(where, path, text="---\nname: probe\n---\nbody\n"):
    return {"where": where, "path": path, "text": text}


# Records where it ran and every file under the throwaway root, then prints one init row.
TREE_CLAUDE = """#!/usr/bin/python3
import json, os
root = os.path.realpath(os.path.dirname(os.environ["CLAUDE_CONFIG_DIR"]))
tree = {}
for dirpath, _d, files in os.walk(root):
    for f in files:
        p = os.path.join(dirpath, f)
        with open(p, errors="replace") as fh:
            tree[os.path.relpath(p, root)] = fh.read()
with open(%r, "w") as fh:
    json.dump({"cwd": os.path.relpath(os.getcwd(), root), "tree": tree}, fh)
print(json.dumps({"type": "system", "subtype": "init", "model": "m",
                  "agents": ["general-purpose", 5, None, "x" * 150, ["a"]]}))
"""

# Records its argv, env and folder, then exits with the given code.
FAKE_GIT = """#!/usr/bin/python3
import json, os, sys
with open(%r, "w") as fh:
    json.dump({"argv": sys.argv[1:], "env": dict(os.environ), "cwd": os.getcwd()}, fh)
sys.exit(%d)
"""


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

    def test_autocompact_prompt_takes_no_argument(self):
        for bad in ("/autocompact 200k", "/autocompact auto", "/autocompact ", " /autocompact",
                    "/autocompact\n", "/AUTOCOMPACT"):
            with self.subTest(prompt=bad):
                self.assert_refused({"name": "t", "prompt": bad}, mention="prompt allowlist")

    def test_cwd_other_than_project_or_nested(self):
        for bad in ("sub", "..", "/", "Project", "", None, 5, ["nested"], True):
            with self.subTest(cwd=bad):
                self.assert_refused({"name": "t", "cwd": bad}, mention="cwd")

    def test_git_init_that_is_not_a_bool(self):
        for bad in ("yes", 1, 0, "true", None, [True]):
            with self.subTest(git_init=bad):
                self.assert_refused({"name": "t", "git_init": bad}, mention="git_init")

    def test_agent_files_that_is_not_a_list(self):
        for bad in ({"where": "user"}, "a.md", None, 5, True):
            with self.subTest(agent_files=bad):
                self.assert_refused({"name": "t", "agent_files": bad}, mention="agent_files")

    def test_agent_files_with_too_many_items(self):
        items = [agent_file("user", "a%d.md" % i) for i in range(9)]
        self.assert_refused({"name": "t", "agent_files": items}, mention="more than 8")

    def test_agent_files_item_that_is_not_an_object(self):
        for bad in ("a.md", None, ["user", "a.md", "x"], 5):
            with self.subTest(item=bad):
                self.assert_refused({"name": "t", "agent_files": [bad]}, mention="not an object")

    def test_agent_files_item_with_wrong_keys(self):
        good = agent_file("user", "a.md")
        missing = {k: v for k, v in good.items() if k != "text"}
        extra = dict(good, mode="0777")
        renamed = {"where": "user", "file": "a.md", "text": "x"}
        for bad in (missing, extra, renamed, {}):
            with self.subTest(item=bad):
                self.assert_refused({"name": "t", "agent_files": [bad]}, mention="exactly the keys")

    def test_agent_files_where_off_the_list(self):
        for bad in ("home", "User", "", "managed", "../x", None, 5, ["user"]):
            with self.subTest(where=bad):
                self.assert_refused({"name": "t", "agent_files": [agent_file(bad, "a.md")]},
                                    mention="where")

    def test_agent_files_paths_that_are_not_allowed(self):
        bad_paths = (
            "", "/a.md", "/etc/a.md", "a.md/", "a//b.md", "/", "./a.md", "../a.md", "a/../b.md",
            "a/./b.md", "..", ".", "a/b/c.md", "a\\b.md", "..\\a.md", ".hidden.md", "a/.md",
            "-a.md", "a b.md", "a.txt", "a.md.bak.txt", "a.md.bak2", "a.bak", "a", "dir/a",
            "a.MD", "a.md\n", "a\x00.md", "caf\u00e9.md", "a/b.md/", "x" * 65 + ".md",
            None, 5, ["a.md"], True,
        )
        for bad in bad_paths:
            with self.subTest(path=bad):
                self.assert_refused({"name": "t", "agent_files": [agent_file("user", bad)]},
                                    mention="agent_files path")

    def test_agent_files_text_that_is_not_a_string(self):
        for bad in (5, None, ["---"], {"a": 1}, True):
            with self.subTest(text=bad):
                self.assert_refused({"name": "t", "agent_files": [agent_file("project", "a.md", bad)]},
                                    mention="not a string")

    def test_agent_files_frontmatter_forbidden_keys(self):
        forms = (
            "---\nname: probe\nhooks:\n  Stop: []\n---\nbody\n",
            '---\nname: probe\n"hooks": {}\n---\nbody\n',
            "---\n{name: probe, hooks: {}}\n---\nbody\n",
            "\ufeff---\nname: probe\nmcpServers: {}\n---\nbody\n",
            "---\nname: probe\n'mcpservers' : {}\n---\nbody\n",
            "---\nname: probe\ninitialPrompt: /login\n---\nbody\n",
        )
        for where in ("user", "project", "nested"):
            for text in forms:
                with self.subTest(where=where, text=text):
                    self.assert_refused(
                        {"name": "t", "agent_files": [agent_file(where, "p.md", text)]},
                        mention="frontmatter sets")

    def test_agent_files_two_items_for_the_same_file(self):
        same = [agent_file("user", "a.md"), agent_file("user", "a.md", "other")]
        self.assert_refused({"name": "t", "agent_files": same}, mention="same file")
        deep = [agent_file("nested", "d/a.md"), agent_file("nested", "d/a.md", "other")]
        self.assert_refused({"name": "t", "agent_files": deep}, mention="same file")
        # Case-insensitive disks make these one file.
        cased = [agent_file("project", "a.md"), agent_file("project", "A.md")]
        self.assert_refused({"name": "t", "agent_files": cased}, mention="same file")

    def test_agent_files_file_that_is_also_a_folder(self):
        clash = [agent_file("user", "d.md"), agent_file("user", "d.md/a.md")]
        self.assert_refused({"name": "t", "agent_files": clash}, mention="same file")
        self.assert_refused({"name": "t", "agent_files": list(reversed(clash))}, mention="same file")

    def test_agent_files_file_that_collides_with_the_agents_map(self):
        self.assert_refused({"name": "t", "agents": {"probe": "x"},
                             "agent_files": [agent_file("user", "probe.md")]}, mention="same file")


class FrontmatterGuard(GuardTestBase):
    """The frontmatter allowlist: forms that hid hooks or mcpServers from the old key scan."""

    def refused_both_ways(self, text, mention=None):
        runcase = load_runcase()
        cases = (
            {"name": "t", "agents": {"probe": text}},
            {"name": "t", "agent_files": [agent_file("user", "p.md", text)]},
        )
        for case in cases:
            with self.subTest(channel=sorted(set(case) - {"name"})[0], text=text):
                err = io.StringIO()
                with contextlib.redirect_stderr(err), self.assertRaises(SystemExit) as ctx:
                    runcase.check_case(case)
                self.assertEqual(ctx.exception.code, 2)
                self.assertIn("runcase refused", err.getvalue())
                if mention:
                    self.assertIn(mention, err.getvalue())

    def test_complex_key_question_mark(self):
        self.refused_both_ways("---\nname: probe\n? hooks\n: {}\n---\nbody\n")

    def test_escaped_double_quoted_hooks_key(self):
        self.refused_both_ways('---\nname: probe\n"ho\\x6fks": {}\n---\nbody\n')

    def test_escaped_double_quoted_mcp_servers_key(self):
        self.refused_both_ways('---\nname: probe\n"mcp\\x53ervers": {}\n---\nbody\n')

    def test_tagged_key(self):
        self.refused_both_ways("---\nname: probe\n!!str hooks: {}\n---\nbody\n")

    def test_anchored_key(self):
        self.refused_both_ways("---\nname: probe\n&a hooks: {}\n---\nbody\n")

    def test_double_quoted_key_split_over_two_lines(self):
        self.refused_both_ways('---\nname: probe\n"hoo\nks": {}\n---\nbody\n')

    def test_flow_map_broken_across_lines(self):
        self.refused_both_ways('---\nname: probe\nx: {"a": 1\n, "hooks"\n: {}}\n---\nbody\n')

    def test_indented_flow_map_broken_across_lines(self):
        self.refused_both_ways('---\nname: probe\nx:\n  {"a": 1\n  , "hooks"\n  : {}}\n---\nbody\n')

    def test_flow_map_with_escaped_key_on_one_line(self):
        self.refused_both_ways('---\nname: probe\nx: {"ho\\x6fks": {}}\n---\nbody\n')

    def test_key_line_inside_an_unclosed_flow_list(self):
        self.refused_both_ways("---\nname: probe\ntools: [Read\nmodel: haiku\n---\nbody\n",
                               mention="unclosed flow list")

    def test_indented_line_before_the_first_key(self):
        self.refused_both_ways("---\n  hooks_x: 1\n  name: probe\n---\nbody\n",
                               mention="before the first key")

    def test_indented_complex_key(self):
        self.refused_both_ways("---\nname: probe\nx:\n  ? hooks\n  : {}\n---\nbody\n")

    def test_top_level_line_starts_with_a_quote_or_bracket_or_star(self):
        for first in ("'hooks': {}", "[hooks]", "*a", ", hooks", ": x", "- hooks", "key : v",
                      "kéy: v", " hooks: {}", "hooks"):
            self.refused_both_ways("---\nname: probe\n%s\n---\nbody\n" % first)

    def test_fake_early_fence_with_u2028(self):
        self.refused_both_ways("---\nname: probe\n ---\nhooks: {}\n---\nbody\n", mention="U+2028")

    def test_fake_early_fence_with_u0085(self):
        self.refused_both_ways("---\nname: probe\n\x85---\nhooks: {}\n---\nbody\n", mention="U+0085")

    def test_other_line_breaks_and_controls_in_frontmatter_or_body(self):
        for bad in ("\r", " ", "\v", "\f", "\x00", "\x1c", "\x7f"):
            for text in ("---\nname: probe%s\n---\nbody\n" % bad, "---\nname: probe\n---\nbo%sdy\n" % bad):
                self.refused_both_ways(text, mention="U+%04X" % ord(bad))

    def test_crlf_text(self):
        self.refused_both_ways("---\r\nname: probe\r\nhooks: {}\r\n---\r\nbody\r\n", mention="U+000D")

    def test_fence_that_is_not_exactly_three_dashes(self):
        self.refused_both_ways("\n---\nname: probe\n---\nbody\n", mention="fence")
        self.refused_both_ways("--- \nname: probe\n---\nbody\n", mention="fence")
        self.refused_both_ways("---\nname: probe\n--- \nhooks: x\n---\nbody\n")
        self.refused_both_ways("---\nname: probe\nmodel: x\n----\nbody\n")

    def test_unclosed_file_still_refuses_forbidden_keys_and_fake_fences(self):
        self.refused_both_ways("---\nname: probe\nhooks: {}\nbody\n", mention="frontmatter sets")
        self.refused_both_ways("---\nname: probe\n--- \nbody\n", mention="closing fence")

    def test_plain_shapes_pass(self):
        runcase = load_runcase()
        text = ("﻿---\n# a comment\n\nname: probe\ndescription: probe agent: one\n"
                "tools: [Read, 'Grep']\nskills:\n  - a\n  - \"b\"\nexperimental:\n  cacheTtl: 1h\n"
                "empty:\n\tindented with a tab\n---\nbody { with } braces \\ and a backslash\n")
        runcase.check_case({"name": "t", "agents": {"probe": text},
                            "agent_files": [agent_file("project", "p.md", text)]})
        runcase.check_case({"name": "t", "agents": {"probe": "no frontmatter at all\n"}})
        runcase.check_case({"name": "t", "agents": {"probe": "---\nname: x\ntools: [a\n"}})


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
        self.assertEqual(env["GIT_CONFIG_NOSYSTEM"], "1")
        self.assertEqual(env["GIT_CONFIG_GLOBAL"], "/dev/null")
        self.assertTrue(env["ANTHROPIC_BASE_URL"].startswith("http://127.0.0.1:"),
                        env["ANTHROPIC_BASE_URL"])
        self.assertEqual(env["ANTHROPIC_API_KEY"], "sk-ant-fake-000")
        self.assertTrue(env["HOME"].startswith(self.scratch))
        self.assertTrue(env["CLAUDE_CONFIG_DIR"].startswith(self.scratch))

    def test_case_env_cannot_replace_the_git_config_values(self):
        # GIT_CONFIG_* are not on the env allowlist, so a case cannot set them, and a
        # caller value for them never reaches Claude Code.
        self.assert_refused({"name": "t", "env": {"GIT_CONFIG_GLOBAL": "/etc/gitconfig"}})
        r = self.run_case({"name": "ok"}, {"GIT_CONFIG_GLOBAL": "/etc/gitconfig",
                                           "GIT_CONFIG_NOSYSTEM": "0"})
        self.assertEqual(r.returncode, 0, "stdout=%r stderr=%r" % (r.stdout, r.stderr))
        with open(self.marker) as fh:
            env = json.load(fh)
        self.assertEqual(env["GIT_CONFIG_NOSYSTEM"], "1")
        self.assertEqual(env["GIT_CONFIG_GLOBAL"], "/dev/null")

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


class NewFields(GuardTestBase):
    def test_init_agents_keeps_strings_cut_to_100(self):
        runcase = load_runcase()
        self.assertEqual(runcase.init_agents({"agents": ["a", 5, None, "x" * 150, ["b"], {"c": 1},
                                                          True, "b"]}),
                         ["a", "x" * 100, "b"])
        self.assertEqual(runcase.init_agents({"agents": []}), [])

    def test_init_agents_is_none_without_a_list(self):
        runcase = load_runcase()
        for init in (None, {}, {"agents": None}, {"agents": "a"}, {"agents": {"a": 1}},
                     {"agents": 5}, "init", []):
            with self.subTest(init=init):
                self.assertIsNone(runcase.init_agents(init))

    def test_autocompact_prompt_is_accepted(self):
        runcase = load_runcase()
        runcase.check_case({"name": "t", "prompt": "/autocompact"})
        r = self.run_case({"name": "ok", "prompt": "/autocompact"})
        self.assertEqual(r.returncode, 0, "stdout=%r stderr=%r" % (r.stdout, r.stderr))
        with open(self.argv_marker) as fh:
            argv = json.load(fh)
        self.assertEqual(argv[argv.index("-p") + 1], "/autocompact")

    def test_init_agents_is_null_without_an_init_row(self):
        r = self.run_case({"name": "ok"})
        self.assertEqual(r.returncode, 0, "stdout=%r stderr=%r" % (r.stdout, r.stderr))
        self.assertIn("init_agents", json.loads(r.stdout))
        self.assertIsNone(json.loads(r.stdout)["init_agents"])

    def tree_claude(self):
        self.tree_marker = os.path.join(self.tmp, "tree.json")
        fake = os.path.join(self.bin, "claude")
        with open(fake, "w") as fh:
            fh.write(TREE_CLAUDE % self.tree_marker)

    def read_tree(self):
        with open(self.tree_marker) as fh:
            return json.load(fh)

    def test_agent_files_are_written_where_they_say(self):
        self.tree_claude()
        r = self.run_case({
            "name": "ok",
            "agents": {"old": "legacy"},
            "agent_files": [
                agent_file("user", "u.md", "user text"),
                agent_file("user", "u2.md.bak", "bak text"),
                agent_file("project", "p.md", "project text"),
                agent_file("project", "sub-d/p2.md", "project deep"),
                agent_file("nested", "n.md", "nested text"),
                agent_file("nested", "d.1/n_2-x.md.bak", "nested deep"),
            ]})
        self.assertEqual(r.returncode, 0, "stdout=%r stderr=%r" % (r.stdout, r.stderr))
        out = json.loads(r.stdout)
        self.assertEqual(out["init_agents"], ["general-purpose", "x" * 100])
        tree = self.read_tree()
        self.assertEqual(tree["cwd"], "project")
        files = tree["tree"]
        expected = {
            "config/agents/old.md": "legacy",
            "config/agents/u.md": "user text",
            "config/agents/u2.md.bak": "bak text",
            "project/.claude/agents/p.md": "project text",
            "project/.claude/agents/sub-d/p2.md": "project deep",
            "project/sub/.claude/agents/n.md": "nested text",
            "project/sub/.claude/agents/d.1/n_2-x.md.bak": "nested deep",
        }
        for path, text in expected.items():
            self.assertEqual(files.get(path), text, path)
        self.assertEqual(sorted(k for k in files if "agents" in k), sorted(expected))

    def test_cwd_nested_runs_claude_in_the_sub_folder(self):
        self.tree_claude()
        r = self.run_case({"name": "ok", "cwd": "nested"})
        self.assertEqual(r.returncode, 0, "stdout=%r stderr=%r" % (r.stdout, r.stderr))
        self.assertEqual(self.read_tree()["cwd"], os.path.join("project", "sub"))

    def test_cwd_project_is_the_default_and_can_be_named(self):
        self.tree_claude()
        for case in ({"name": "ok"}, {"name": "ok", "cwd": "project"}):
            with self.subTest(case=case):
                r = self.run_case(case)
                self.assertEqual(r.returncode, 0, "stdout=%r stderr=%r" % (r.stdout, r.stderr))
                self.assertEqual(self.read_tree()["cwd"], "project")

    def fake_git(self, code):
        self.git_marker = os.path.join(self.tmp, "git.json")
        fake = os.path.join(self.bin, "git")
        with open(fake, "w") as fh:
            fh.write(FAKE_GIT % (self.git_marker, code))
        os.chmod(fake, os.stat(fake).st_mode | stat.S_IXUSR)

    def test_git_init_runs_in_the_project_with_a_closed_environment(self):
        self.fake_git(0)
        r = self.run_case({"name": "ok", "git_init": True,
                           "env": {"ANTHROPIC_MODEL": "claude-haiku-5-5"}},
                          {"GIT_DIR": "/leak", "GIT_AUTHOR_NAME": "leak", "HTTPS_PROXY": "http://leak"})
        self.assertEqual(r.returncode, 0, "stdout=%r stderr=%r" % (r.stdout, r.stderr))
        with open(self.git_marker) as fh:
            seen = json.load(fh)
        self.assertEqual(seen["argv"], ["init", "-q"])
        self.assertTrue(seen["cwd"].endswith("/project"), seen["cwd"])
        with open(self.marker) as fh:
            claude_env = json.load(fh)
        self.assertEqual(seen["env"]["HOME"], claude_env["HOME"])
        self.assertEqual(seen["env"]["GIT_CONFIG_NOSYSTEM"], "1")
        self.assertEqual(seen["env"]["GIT_CONFIG_GLOBAL"], "/dev/null")
        extra = set(seen["env"]) - {"PATH", "TMPDIR", "LANG", "HOME", "GIT_CONFIG_NOSYSTEM",
                                    "GIT_CONFIG_GLOBAL"} - SYSTEM_ADDED
        self.assertEqual(extra, set())

    def test_git_init_false_or_missing_does_not_run_git(self):
        self.fake_git(0)
        for case in ({"name": "ok"}, {"name": "ok", "git_init": False}):
            with self.subTest(case=case):
                r = self.run_case(case)
                self.assertEqual(r.returncode, 0, "stdout=%r stderr=%r" % (r.stdout, r.stderr))
                self.assertFalse(os.path.exists(self.git_marker))

    def test_git_init_failure_removes_the_root_and_exits_non_zero(self):
        self.fake_git(3)
        r = self.run_case({"name": "ok", "git_init": True})
        self.assertEqual(r.returncode, 1, "stdout=%r stderr=%r" % (r.stdout, r.stderr))
        self.assertIn("git init", r.stderr)
        self.assertFalse(os.path.exists(self.marker), "claude started")
        self.assertEqual(os.listdir(self.scratch), [], "throwaway root left behind")

    def test_git_init_with_no_git_removes_the_root_and_exits_non_zero(self):
        # PATH holds only the fake claude folder, so there is no git to find.
        path = os.path.join(self.tmp, "case.json")
        with open(path, "w") as fh:
            json.dump({"name": "ok", "git_init": True}, fh)
        env = {"PATH": self.bin, "TMPDIR": self.scratch, "LANG": "en_US.UTF-8"}
        r = subprocess.run([PYTHON, RUNCASE, path, str(free_port())], env=env,
                           capture_output=True, text=True, timeout=60, stdin=subprocess.DEVNULL)
        self.assertEqual(r.returncode, 1, "stdout=%r stderr=%r" % (r.stdout, r.stderr))
        self.assertFalse(os.path.exists(self.marker), "claude started")
        self.assertEqual(os.listdir(self.scratch), [], "throwaway root left behind")


if __name__ == "__main__":
    unittest.main()
