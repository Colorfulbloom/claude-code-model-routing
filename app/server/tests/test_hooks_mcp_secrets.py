"""No secret reaches an answer from the hooks, MCP or masked-reader parts.

The corpus plants made-up secrets in every place a hook or an MCP server can hold one
(``corpus/secrets.json``). Here every case runs through the whole chain, and the joined
answers (items, problem rows, Couldn't read rows, handed-on data) must hold none of
them. A sweep then plants a fresh secret in each place by hand, so the corpus is not the
only oracle, and checks that logs and exception texts stay clean too.
"""

import json
import logging
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/ is not on sys.path
import hook_mcp_helpers as hm
import setup_case_helpers as sc

import claude_json
import collect_hooks
import collect_mcp
from setup_contract import SetupContext


def put(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


@pytest.mark.parametrize("case", sc.CASES)
def test_no_planted_secret_is_in_any_answer(
    case: str, tmp_path: Path, setup_corpus: Path, caplog: pytest.LogCaptureFixture
) -> None:
    root = sc.world(case, tmp_path / "w", setup_corpus)
    with caplog.at_level(logging.DEBUG):
        answers = hm.chain(sc.context(root))
    blob = hm.everything(answers) + caplog.text
    for entry in hm.secrets():
        assert entry["value"] not in blob, (case, entry["kind"])
    for entry in hm.never():
        assert entry["value"] not in blob, (case, entry["kind"])


@pytest.mark.parametrize("case", ["typical", "complex"])
def test_the_planted_secrets_are_really_in_the_case_and_shown_masked(
    case: str, tmp_path: Path, setup_corpus: Path
) -> None:
    """The check above has teeth: the secrets are in the files, and the text shows."""
    root = sc.world(case, tmp_path / "w", setup_corpus)
    present = [
        e
        for e in hm.secrets()
        if e["case"] == case and e["value"] in (root / e["file"]).read_text("utf-8")
    ]
    assert len(present) >= 6
    answers = hm.chain(sc.context(root))
    blob = hm.everything(answers)
    assert blob.count('"masked": true') >= 6
    assert "hidden" in blob


def test_the_demo_overlay_secrets_are_never_in_an_answer_either(
    tmp_path: Path, setup_corpus: Path
) -> None:
    """Their files are not in a corpus case, so a case's answer must not hold them."""
    root = sc.world("complex", tmp_path / "w", setup_corpus)
    blob = hm.everything(hm.chain(sc.context(root)))
    for entry in hm.secrets():
        if entry["case"] == "demo-overlay":
            assert entry["value"] not in blob


# ---------------------------------------------------------------- the sweep

SECRETS = {
    "hook_command": "SWEEP-HOOK-CMD-0001",
    "hook_arg": "SWEEP-HOOK-ARG-0002",
    "hook_url": "SWEEP-HOOK-URL-0003",
    "agent_hook": "SWEEP-AGENT-HOOK-0004",
    "plugin_hook": "SWEEP-PLUGIN-HOOK-0005",
    "mcp_command": "SWEEP-MCP-CMD-0006",
    "mcp_arg": "SWEEP-MCP-ARG-0007",
    "mcp_env": "SWEEP-MCP-ENV-0008",
    "mcp_url": "SWEEP-MCP-URL-0009",
    "mcp_header": "SWEEP-MCP-HDR-0010",
    "json_user": "SWEEP-JSON-USER-0011",
    "json_local": "SWEEP-JSON-LOCAL-0012",
    "plugin_mcp": "SWEEP-PLUGIN-MCP-0013",
    "inline_mcp": "SWEEP-INLINE-MCP-0014",
    "managed_mcp": "SWEEP-MANAGED-MCP-0015",
    "skill_hook": "SWEEP-SKILL-HOOK-0016",
    "plugin_skill_hook": "SWEEP-PLUGIN-SKILL-HOOK-0017",
    "agent_mcp": "SWEEP-AGENT-MCP-0018",
}


def sweep_world(tmp_path: Path) -> SetupContext:
    s = SECRETS
    home = tmp_path / "home" / ".claude"
    install = home / "plugins" / "cache" / "m" / "p" / "1.0"
    quick = home / "plugins" / "cache" / "m" / "q" / "1.0"
    put(
        home / "settings.json",
        json.dumps(
            {
                "enabledPlugins": {"p@m": True, "q@m": True},
                "hooks": {
                    "PreToolUse": [
                        {
                            "matcher": "Bash",
                            "hooks": [
                                {
                                    "type": "command",
                                    "command": f"run.sh --api-key {s['hook_command']}",
                                },
                                {
                                    "type": "command",
                                    "command": "py",
                                    "args": ["--token", s["hook_arg"]],
                                },
                                {
                                    "type": "http",
                                    "url": f"https://u:{s['hook_url']}@h.test/x",
                                },
                            ],
                        }
                    ]
                },
            }
        ),
    )
    put(
        home / "plugins" / "installed_plugins.json",
        json.dumps(
            {
                "version": 2,
                "plugins": {
                    "p@m": [
                        {"scope": "user", "installPath": str(install), "version": "1"}
                    ],
                    "q@m": [
                        {"scope": "user", "installPath": str(quick), "version": "1"}
                    ],
                },
            }
        ),
    )
    put(install / ".claude-plugin" / "plugin.json", json.dumps({"name": "p"}))
    # A manifest that writes its servers inline replaces the plugin's ``.mcp.json``.
    put(
        quick / ".claude-plugin" / "plugin.json",
        json.dumps(
            {
                "name": "q",
                "mcpServers": {
                    "inline": {"command": "x", "env": {"A_SECRET": s["inline_mcp"]}}
                },
            }
        ),
    )
    put(
        install / "hooks" / "hooks.json",
        json.dumps(
            {
                "hooks": {
                    "Stop": [
                        {
                            "hooks": [
                                {
                                    "type": "command",
                                    "command": f"x --password={s['plugin_hook']}",
                                }
                            ]
                        }
                    ]
                }
            }
        ),
    )
    put(
        install / ".mcp.json",
        json.dumps(
            {
                "mcpServers": {
                    "pm": {"command": "x", "env": {"PM_TOKEN": s["plugin_mcp"]}}
                }
            }
        ),
    )
    put(
        tmp_path / "proj" / ".claude" / "agents" / "a.md",
        "---\nname: a\ndescription: x.\nhooks:\n  Stop:\n    - hooks:\n"
        "        - type: command\n"
        f"          command: z --secret {s['agent_hook']}\n---\nBODY\n",
    )
    put(
        tmp_path / "proj" / ".claude" / "skills" / "s" / "SKILL.md",
        "---\nname: s\ndescription: x.\nhooks:\n  Stop:\n    - hooks:\n"
        "        - type: command\n"
        f"          command: z --password {s['skill_hook']}\n---\nBODY\n",
    )
    put(
        install / "skills" / "ps" / "SKILL.md",
        "---\nname: ps\ndescription: x.\nhooks:\n  Stop:\n    - hooks:\n"
        "        - type: command\n"
        f"          command: z --token {s['plugin_skill_hook']}\n---\nBODY\n",
    )
    put(
        tmp_path / "proj" / ".claude" / "agents" / "m.md",
        "---\nname: m\ndescription: x.\nmcpServers:\n  inl:\n"
        f"    command: z --api-key {s['agent_mcp']}\n---\nBODY\n",
    )
    put(
        tmp_path / "proj" / ".mcp.json",
        json.dumps(
            {
                "mcpServers": {
                    "all": {
                        "command": f"run --token {s['mcp_command']}",
                        "args": ["--secret", s["mcp_arg"]],
                        "env": {"MY_KEY": s["mcp_env"]},
                    },
                    "remote": {
                        "type": "http",
                        "url": f"https://a:{s['mcp_url']}@h.test/m",
                        "headers": {"Authorization": f"Bearer {s['mcp_header']}"},
                    },
                }
            }
        ),
    )
    put(
        tmp_path / "proj" / ".claude" / "settings.json",
        json.dumps({"enableAllProjectMcpServers": True}),
    )
    put(
        tmp_path / "managed" / "managed-mcp.json",
        json.dumps(
            {
                "mcpServers": {
                    "mg": {
                        "type": "sse",
                        "url": "https://h.test/s",
                        "headers": {"X-Api-Key": s["managed_mcp"]},
                    }
                }
            }
        ),
    )
    ctx = sc.scratch(tmp_path, {})
    put(
        tmp_path / "home" / ".claude.json",
        json.dumps(
            {
                "mcpServers": {
                    "uu": {"command": "x", "env": {"U_PASSWORD": s["json_user"]}}
                },
                "projects": {
                    str(ctx.project_dir): {
                        "mcpServers": {
                            "ll": {"command": "x", "args": [f"--key={s['json_local']}"]}
                        }
                    }
                },
            }
        ),
    )
    return ctx


def test_a_secret_in_every_place_is_masked_in_every_answer(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    ctx = sweep_world(tmp_path)
    with caplog.at_level(logging.DEBUG):
        answers = hm.chain(ctx)
    blob = hm.everything(answers) + caplog.text
    items = {i.id for a in answers.values() for part in a.items.values() for i in part}
    # The sweep reached every kind of item it plants a secret in.
    assert {"mcp:all", "mcp:remote", "mcp:mg", "mcp:uu", "mcp:ll"} <= items
    assert {"mcp:p:pm", "mcp:q:inline"} <= items
    assert "hooks:PreToolUse:Bash:2" in items
    assert "hooks:Stop:*:0" in items
    assert "hooks:SubagentStop:*:0" in items
    for name, secret in SECRETS.items():
        assert secret not in blob, name


def test_the_agents_part_does_not_show_a_secret_in_an_agent_hook_command(
    tmp_path: Path,
) -> None:
    answers = hm.chain(sweep_world(tmp_path))
    blob = hm.everything({"agents": answers["agents"]})
    assert SECRETS["agent_hook"] not in blob
    assert SECRETS["agent_mcp"] not in blob
    assert "hidden" in blob  # the masking ran, the field was not just dropped


def test_skill_hook_commands_are_masked_in_the_hooks_and_skills_parts(
    tmp_path: Path,
) -> None:
    answers = hm.chain(sweep_world(tmp_path))
    files = [
        h.sources[0].file or ""
        for h in answers["hooks"].items["hooks"]
        if h.id.startswith("hooks:Stop")
    ]
    assert sum(f.endswith("SKILL.md") for f in files) == 2  # project and plugin skill
    blob = hm.everything({"hooks": answers["hooks"], "skills": answers["skills"]})
    assert SECRETS["skill_hook"] not in blob
    assert SECRETS["plugin_skill_hook"] not in blob


def test_a_value_nested_too_deep_to_check_is_hidden_whole() -> None:
    import agent_files

    deep: object = "z --password SWEEP-DEEP-0019"
    for _ in range(20):
        deep = {"x": deep}
    field = agent_files.front_matter_field("hooks", deep, 1)
    assert field.value is not None
    assert "SWEEP-DEEP-0019" not in field.value.text


def test_the_planted_secret_kinds_cover_the_spec() -> None:
    """sk-, Bearer, JWT, URL userinfo, secret-named flags and headers (task 8)."""
    kinds = {e["kind"] for e in hm.secrets()}
    for wanted in (
        "sk_prefix_in_hook_command",
        "sk_prefix_in_mcp_env",
        "bearer_header",
        "jwt_in_env",
        "url_userinfo",
        "secret_named_header",
        "secret_named_flag_in_args",
        "secret_named_flag_equals_in_args",
    ):
        assert wanted in kinds


def test_a_masked_value_is_flagged_and_an_unmasked_one_is_not(
    tmp_path: Path,
) -> None:
    ctx = sweep_world(tmp_path)
    got = hm.chain(ctx)["mcp"]
    facts = {i.id: i.facts.mcp for i in got.items["mcp"]}
    remote = facts["mcp:remote"]
    assert remote is not None
    assert remote.url is not None
    assert remote.url.masked is True
    assert remote.headers["Authorization"].masked is True
    allfacts = facts["mcp:all"]
    assert allfacts is not None
    assert allfacts.command is not None
    assert allfacts.command.masked is True
    managed = facts["mcp:mg"]
    assert managed is not None
    assert managed.url is not None
    assert managed.url.masked is False


def test_no_log_record_is_written_by_the_new_collectors(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    ctx = sweep_world(tmp_path)
    (tmp_path / "home" / ".claude.json").write_text("{ not json SWEEP-X", "utf-8")
    with caplog.at_level(logging.DEBUG):
        claude_json.clear_cache()
        collect_hooks.COLLECTOR.read(ctx, {})
        collect_mcp.COLLECTOR.read(ctx, {})
    assert [
        r for r in caplog.records if r.name.startswith(("claude_json", "collect_"))
    ] == []
    assert "SWEEP-X" not in caplog.text


def test_an_exception_text_from_the_reader_holds_no_value(tmp_path: Path) -> None:
    """A text the reader cannot parse must not leak through ``ValueError``."""
    with pytest.raises(ValueError, match="nested too deeply") as caught:
        claude_json.validate("[" * 100_000 + "SWEEP-DEEP")
    assert "SWEEP-DEEP" not in str(caught.value)
    ctx = sc.scratch(tmp_path, {})
    (tmp_path / "home" / ".claude.json").write_text(
        "[" * 100_000 + "SWEEP-DEEP", "utf-8"
    )
    claude_json.clear_cache()
    got = claude_json.COLLECTOR.read(ctx, {})
    assert [r.code for r in got.problems] == ["json_invalid"]
    assert "SWEEP-DEEP" not in hm.everything({"claude_json": got})
