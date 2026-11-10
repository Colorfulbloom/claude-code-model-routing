---
name: scout
description: Read-only scout from the plugin. Searches code and summarizes the result.
tools: Read, Glob, Grep
model: haiku
permissionMode: plan
hooks:
  PreToolUse:
    - matcher: Bash
      hooks:
        - type: command
          command: echo plugin-agent
---
You are a read-only scout.
