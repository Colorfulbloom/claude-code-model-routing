"""Fake Anthropic API on localhost. Logs model, effort and cache TTLs per request.
If AGENT_INPUT (JSON) is set, the first main request that offers the Agent tool gets
a streamed tool_use calling it; every other request gets a 400. No real call is made."""
import json, os, sys
from http.server import BaseHTTPRequestHandler, HTTPServer
LOG = sys.argv[2]; AGENT_INPUT = os.environ.get("AGENT_INPUT"); state = {"served": False}
def cache_ttls(body):
    out = set()
    def walk(x):
        if isinstance(x, dict):
            cc = x.get("cache_control")
            if isinstance(cc, dict): out.add(cc.get("ttl", "5m(default)"))
            for v in x.values(): walk(v)
        elif isinstance(x, list):
            for v in x: walk(v)
    walk(body); return sorted(out)
def sse(model, inp):
    ev = [("message_start", {"type": "message_start", "message": {"id": "msg_fake1", "type": "message", "role": "assistant", "model": model, "content": [], "stop_reason": None, "stop_sequence": None, "usage": {"input_tokens": 1, "output_tokens": 1}}}),
          ("content_block_start", {"type": "content_block_start", "index": 0, "content_block": {"type": "tool_use", "id": "toolu_fake1", "name": "Agent", "input": {}}}),
          ("content_block_delta", {"type": "content_block_delta", "index": 0, "delta": {"type": "input_json_delta", "partial_json": json.dumps(inp)}}),
          ("content_block_stop", {"type": "content_block_stop", "index": 0}),
          ("message_delta", {"type": "message_delta", "delta": {"stop_reason": "tool_use", "stop_sequence": None}, "usage": {"output_tokens": 1}}),
          ("message_stop", {"type": "message_stop"})]
    return "".join("event: %s\ndata: %s\n\n" % (n, json.dumps(d)) for n, d in ev).encode()
class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_POST(self):
        n = int(self.headers.get("content-length") or 0)
        raw = self.rfile.read(n) if n else b""
        try: body = json.loads(raw or b"{}")
        except ValueError: body = {}
        tools = [t.get("name") for t in body.get("tools") or [] if isinstance(t, dict)]
        text = raw.decode("utf-8", "replace")
        who = "subagent" if "MARKER-SUBAGENT" in text and "MARKER-MAIN-ONLY" not in text else "main"
        rec = {"path": self.path, "who": who, "model": body.get("model"),
               "effort": (body.get("output_config") or {}).get("effort"),
               "cache_ttls": cache_ttls(body), "has_agent_tool": "Agent" in tools,
               "context_management": body.get("context_management")}
        with open(LOG, "a") as fh: fh.write(json.dumps(rec) + "\n")
        if AGENT_INPUT and not state["served"] and "Agent" in tools and who == "main" and "/messages" in self.path and "count_tokens" not in self.path:
            state["served"] = True; out = sse(body.get("model"), json.loads(AGENT_INPUT))
            self.send_response(200); self.send_header("content-type", "text/event-stream")
            self.send_header("content-length", str(len(out))); self.end_headers(); self.wfile.write(out); return
        msg = json.dumps({"type": "error", "error": {"type": "invalid_request_error", "message": "fake api"}}).encode()
        self.send_response(400); self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(msg))); self.end_headers(); self.wfile.write(msg)
    do_GET = do_POST
# Loopback only, so nothing outside this machine can reach it.
HTTPServer(("127.0.0.1", int(sys.argv[1])), H).serve_forever()
