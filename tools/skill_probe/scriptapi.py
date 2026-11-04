"""Scripted fake Anthropic API on 127.0.0.1. No real call is made.

A request's plan comes from markers in the trailing human text:
  TAG=<name> PLAN=<step>,<step>,...
Steps: bash (Bash "echo <tag>-<i>"), L.<words> (Bash with the plugin's bin/routing-dashboard
launcher and <words> as arguments, the way the skill's ! line runs it), c.<words> (Bash
"./tool.sh <words>"), agent:<subtag>[:<plan>] (foreground Agent), bgagent:<subtag>[:<plan>]
(background Agent), hold (sleep 8 seconds, then bash), text (end the turn). In a subagent's
plan, "+" stands for ",". A step can start with ws~ (wait until the main skill turn has
ended), wt3~ (wait until turn 3 starts) or wk~ (wait until the skill's request arrives),
for example ws~bash.
A subagent's first user message holds MARKER-SUBAGENT. Every tool_result is logged with
the command it answers, and every request logs whether Bash was offered.
"""
import json, os, re, sys, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

LOG = sys.argv[2]
lock = threading.Lock()
state = {"n": 0, "ids": {}, "skill_done": threading.Event(), "t3": threading.Event(), "wk": threading.Event()}


def log(rec):
    rec["t"] = round(time.time(), 2)
    with lock, open(LOG, "a") as fh:
        fh.write(json.dumps(rec) + "\n")


def blocks(msg):
    c = msg.get("content")
    if isinstance(c, str):
        return [{"type": "text", "text": c}]
    return [b for b in c or [] if isinstance(b, dict)]


def text_of(msg):
    out = []
    for b in blocks(msg):
        if b.get("type") == "text":
            out.append(b.get("text", ""))
        elif b.get("type") == "tool_result":
            pass
    return "\n".join(out)


def is_tool_result(msg):
    return any(b.get("type") == "tool_result" for b in blocks(msg))


def next_id():
    with lock:
        state["n"] += 1
        return state["n"]


def sse(model, block, stop):
    ev = [("message_start", {"type": "message_start", "message": {"id": "msg_probe%d" % next_id(), "type": "message", "role": "assistant", "model": model, "content": [], "stop_reason": None, "stop_sequence": None, "usage": {"input_tokens": 1, "output_tokens": 1}}})]
    if block["type"] == "tool_use":
        ev.append(("content_block_start", {"type": "content_block_start", "index": 0, "content_block": {"type": "tool_use", "id": block["id"], "name": block["name"], "input": {}}}))
        ev.append(("content_block_delta", {"type": "content_block_delta", "index": 0, "delta": {"type": "input_json_delta", "partial_json": json.dumps(block["input"])}}))
    else:
        ev.append(("content_block_start", {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}}))
        ev.append(("content_block_delta", {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": block["text"]}}))
    ev += [("content_block_stop", {"type": "content_block_stop", "index": 0}),
           ("message_delta", {"type": "message_delta", "delta": {"stop_reason": stop, "stop_sequence": None}, "usage": {"output_tokens": 1}}),
           ("message_stop", {"type": "message_stop"})]
    return "".join("event: %s\ndata: %s\n\n" % (n, json.dumps(d)) for n, d in ev).encode()


def tool(name, inp, cmd_label):
    with lock:
        state["n"] += 1
        tid = "toolu_probe%04d" % state["n"]
        state["ids"][tid] = cmd_label
    return {"type": "tool_use", "id": tid, "name": name, "input": inp}


class H(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def send(self, code, body, ctype):
        self.send_response(code)
        self.send_header("content-type", ctype)
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        n = int(self.headers.get("content-length") or 0)
        raw = self.rfile.read(n) if n else b""
        try:
            body = json.loads(raw or b"{}")
        except ValueError:
            body = {}
        if "/messages" not in self.path or "count_tokens" in self.path:
            return self.send(200, json.dumps({"input_tokens": 1}).encode(), "application/json")
        model = body.get("model")
        with lock, open(LOG + ".bodies", "a") as fh:
            fh.write(json.dumps({"system": str(body.get("system"))[:300], "messages": body.get("messages")})[:20000] + "\n")
        tools = [t.get("name") for t in body.get("tools") or [] if isinstance(t, dict)]
        msgs = body.get("messages") or []
        first = text_of(msgs[0]) if msgs else ""
        who = "subagent" if "MARKER-SUBAGENT" in first else "main"
        # Log every tool_result in the last user message.
        last_user = [m for m in msgs if m.get("role") == "user"]
        if last_user:
            for b in blocks(last_user[-1]):
                if b.get("type") == "tool_result":
                    c = b.get("content")
                    if isinstance(c, list):
                        c = " ".join(x.get("text", "") for x in c if isinstance(x, dict))
                    label = state["ids"].get(b.get("tool_use_id"))
                    if label and not label.startswith("agent"):
                        log({"ev": "result", "who": who, "cmd": label, "is_error": bool(b.get("is_error")),
                             "content": str(c)[:300], "bash_offered": "Bash" in tools})
        # Drop role "system" messages, then find the last human message (text, no tool_result).
        um = [m for m in msgs if m.get("role") in ("user", "assistant")]
        h = -1
        for j in range(len(um) - 1, -1, -1):
            if um[j].get("role") == "user" and not is_tool_result(um[j]) and re.search(r"PLAN=|TAG=", text_of(um[j])):
                h = j
                break
        step = sum(1 for m in um[h + 1:] if m.get("role") == "assistant" for b in blocks(m) if b.get("type") == "tool_use") if h >= 0 else 0
        human = text_of(um[h]) if h >= 0 else ""
        # A later plain user message (no markers) after h means a new turn with no plan.
        if h >= 0 and any(m.get("role") == "user" and not is_tool_result(m) and "<command-" not in text_of(m) and "system-reminder" not in text_of(m)[:30] for m in um[h + 1:]):
            human = ""
        plan_m = re.findall(r"PLAN=([A-Za-z0-9:.,+~_-]+)", human)
        tag_m = re.findall(r"TAG=(\w+)", human)
        if who == "main" and "SKILLMARK" in human:
            state["wk"].set()
        if who == "main" and "TAG=t3" in human:
            state["t3"].set()
        log({"ev": "req", "who": who, "model": model, "bash_offered": "Bash" in tools, "ntools": len(tools),
             "tag": tag_m[-1] if tag_m else None, "step": step, "bang": "BANG" in human,
             "skill": "SKILLMARK" in human, "launch": "LAUNCH" in human, "body": human[-160:] if "SKILLMARK" in human else None})
        with lock:
            state["reqs"] = state.get("reqs", 0) + 1
            capped = state["reqs"] > 150
        if not plan_m or not tools or capped:
            return self.send(200, sse(model, {"type": "text", "text": "done"}, "end_turn"), "text/event-stream")
        plan = plan_m[-1].split(",")
        tag = tag_m[-1] if tag_m else "x"
        act = plan[step] if step < len(plan) else "text"
        if act == "hold":
            time.sleep(8)
            act = "bash"
        if act.startswith("ws~") or act.startswith("wt3~") or act.startswith("wk~"):
            pre, act = act.split("~", 1)
            ev = {"ws": state["skill_done"], "wt3": state["t3"], "wk": state["wk"]}[pre]
            ev.wait(120)
            time.sleep(1 if pre == "wk" else 3)  # let the main turn settle on the client side first
            log({"ev": "waited", "who": who, "tag": tag, "for": pre, "set": ev.is_set()})
        if act == "bash" or act.startswith("c.") or act.startswith("L."):
            words = " ".join(act.split(".")[1:])
            if act == "bash":
                cmd = "echo %s-%d" % (tag, step)
            elif act.startswith("L."):
                # The launcher the way the skill's ! line runs it, with the plugin root spelled out.
                cmd = 'python3 "%s/bin/routing-dashboard" --data "/x" --session "s" %s' % (os.environ.get("PLUGROOT", ""), words)
            else:
                cmd = "./tool.sh " + words
            blk = tool("Bash", {"command": cmd, "description": "probe"}, cmd)
            return self.send(200, sse(model, blk, "tool_use"), "text/event-stream")
        if act.startswith("agent:") or act.startswith("bgagent:"):
            parts = act.split(":")
            sub = parts[1]
            subplan = parts[2].replace("+", ",") if len(parts) > 2 else "bash,text"
            inp = {"description": "probe " + sub, "subagent_type": "general-purpose",
                   "prompt": "MARKER-SUBAGENT TAG=%s PLAN=%s" % (sub, subplan)}
            if act.startswith("bg"):
                inp["run_in_background"] = True
            blk = tool("Agent", inp, "agent " + sub)
            return self.send(200, sse(model, blk, "tool_use"), "text/event-stream")
        if "SKILLMARK" in human and who == "main":
            state["skill_done"].set()
            log({"ev": "skill_turn_end"})
        return self.send(200, sse(model, {"type": "text", "text": "done"}, "end_turn"), "text/event-stream")

    do_GET = do_POST


ThreadingHTTPServer(("127.0.0.1", int(sys.argv[1])), H).serve_forever()
