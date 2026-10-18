#!/usr/bin/env python3
"""PreToolUse hook for the Agent tool.
Blocks a dispatch that names no model and targets an agent with no pinned model,
any use of general-purpose, and any found agent with no pinned effort.
Exit 0 = allow. Exit 2 = block; stderr is shown to Claude."""
import glob
import json
import os
import re
import sys

BUILTINS = {"Explore", "Plan"}


def frontmatter(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            lines = fh.read().splitlines()
    except OSError:
        return {}
    if not lines or lines[0].strip() != "---":
        return {}
    fm = {}
    for line in lines[1:]:
        if line.strip() == "---":
            break
        m = re.match(r"^([A-Za-z_-]+):\s*(.*?)\s*$", line)
        if m:
            fm[m.group(1)] = m.group(2)
    return fm


def agent_dirs(project_dir):
    return [
        os.path.join(project_dir, ".claude", "agents"),
        os.path.join(os.path.expanduser(os.environ.get("CLAUDE_CONFIG_DIR") or "~/.claude"), "agents"),
    ]


def find_agent(name, project_dir):
    for d in agent_dirs(project_dir):
        for f in sorted(glob.glob(os.path.join(d, "*.md"))):
            fm = frontmatter(f)
            fname = fm.get("name") or os.path.splitext(os.path.basename(f))[0]
            if fname == name:
                return f, fm
    return None, None


def block(msg):
    sys.stderr.write(msg + "\n")
    sys.exit(2)


def check_effort(agent, path, fm):
    model = (fm.get("model") or "").strip()
    if not (fm.get("effort") or "").strip():
        block(f"Model routing: agent '{agent}' ({path}) has no pinned effort. Without one it runs at the session's effort, which is observed behaviour the docs do not state. Add `effort:` to its frontmatter.")


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)
    if data.get("tool_name") != "Agent":
        sys.exit(0)
    ti = data.get("tool_input") or {}
    agent = ti.get("subagent_type") or ""
    if agent == "general-purpose":
        block("Model routing: use the pinned `judge` agent (Sonnet, medium) instead of built-in general-purpose.")
    if not agent or ":" in agent:
        sys.exit(0)  # unknown shape or plugin agent: let it through
    if ti.get("model"):
        # A passed model skips the model checks, but a found agent still needs a pinned effort.
        path, fm = find_agent(agent, os.environ.get("CLAUDE_PROJECT_DIR") or data.get("cwd") or os.getcwd())
        if path is not None:
            check_effort(agent, path, fm)
        sys.exit(0)
    if agent in BUILTINS:
        block(f"Model routing: built-in agent '{agent}' has no pinned model and would run on the session model. Pass a model (haiku, sonnet, or opus) for this dispatch, or use scout / fast-worker / deep-reasoner.")
    project_dir = os.environ.get("CLAUDE_PROJECT_DIR") or data.get("cwd") or os.getcwd()
    path, fm = find_agent(agent, project_dir)
    if path is None:
        project_agents_dir, user_agents_dir = agent_dirs(project_dir)
        block(f"Model routing: agent '{agent}' was not found in {project_agents_dir} or {user_agents_dir}. Pass a model (haiku, sonnet, or opus) for this dispatch.")
    model = (fm.get("model") or "").strip()
    if not model or model == "inherit":
        block(f"Model routing: agent '{agent}' ({path}) has no pinned model and would run on the session model. Pass a model (haiku, sonnet, or opus) for this dispatch, and run /route-project to pin it.")
    check_effort(agent, path, fm)
    sys.exit(0)


if __name__ == "__main__":
    main()
