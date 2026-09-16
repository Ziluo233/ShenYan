#!/usr/bin/env python3
# jiq_mcp.py 的迷你替身：不需要官方 mcp 包（其依赖需要 Rust 编译），照样跑 stdio MCP 协议。
import sys, os, json, types, inspect, io, asyncio

_real_out = sys.stdout

class _MiniServer:
    def __init__(self, name="jiq"):
        self.name = name
        self.tools = {}

    def tool(self, *a, **k):
        def deco(fn):
            self.tools[fn.__name__] = fn
            return fn
        if len(a) == 1 and callable(a[0]) and not k:
            return deco(a[0])
        return deco

    def _send(self, obj):
        _real_out.write(json.dumps(obj, ensure_ascii=False) + "\n")
        _real_out.flush()

    def _schema(self, fn):
        props, req = {}, []
        for pn, p in inspect.signature(fn).parameters.items():
            if pn in ("ctx", "context"):
                continue
            t = "string"
            if p.annotation is int:
                t = "integer"
            elif p.annotation is bool:
                t = "boolean"
            elif p.annotation is float:
                t = "number"
            props[pn] = {"type": t}
            if p.default is inspect._empty:
                req.append(pn)
        return {"type": "object", "properties": props, "required": req}

    def _call(self, name, args):
        fn = self.tools.get(name)
        if fn is None:
            return {"content": [{"type": "text", "text": "未知工具: " + str(name)}], "isError": True}
        args = args or {}
        kw = {}
        for pn, p in inspect.signature(fn).parameters.items():
            if pn in ("ctx", "context"):
                kw[pn] = None
            elif pn in args:
                kw[pn] = args[pn]
        try:
            r = fn(**kw)
            if inspect.iscoroutine(r):
                r = asyncio.run(r)
            return {"content": [{"type": "text", "text": r if isinstance(r, str) else json.dumps(r, ensure_ascii=False)}], "isError": False}
        except Exception as e:
            return {"content": [{"type": "text", "text": "工具执行出错: %s" % e}], "isError": True}

    def run(self, *a, **k):
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except Exception:
                continue
            mid, method = msg.get("id"), msg.get("method")
            params = msg.get("params") or {}
            if mid is None:
                continue
            try:
                if method == "initialize":
                    pv = params.get("protocolVersion") or "2024-11-05"
                    result = {"protocolVersion": pv, "capabilities": {"tools": {}},
                              "serverInfo": {"name": self.name, "version": "1.0.0"}}
                elif method == "ping":
                    result = {}
                elif method == "tools/list":
                    result = {"tools": [{"name": n, "description": inspect.getdoc(f) or "",
                                         "inputSchema": self._schema(f)} for n, f in self.tools.items()]}
                elif method == "tools/call":
                    result = self._call(params.get("name"), params.get("arguments"))
                elif method == "resources/list":
                    result = {"resources": []}
                elif method == "prompts/list":
                    result = {"prompts": []}
                else:
                    self._send({"jsonrpc": "2.0", "id": mid,
                                "error": {"code": -32601, "message": "Method not found: " + str(method)}})
                    continue
                self._send({"jsonrpc": "2.0", "id": mid, "result": result})
            except Exception as e:
                self._send({"jsonrpc": "2.0", "id": mid, "error": {"code": -32603, "message": str(e)}})

# 伪造 mcp 包，注入 sys.modules
_f = types.ModuleType("mcp")
_s = types.ModuleType("mcp.server")
_fm = types.ModuleType("mcp.server.fastmcp")
_ms = types.ModuleType("mcp.server.mcpserver")
_fm.FastMCP = _MiniServer
_ms.MCPServer = _MiniServer
_s.fastmcp = _fm
_s.mcpserver = _ms
_f.server = _s
sys.modules["mcp"] = _f
sys.modules["mcp.server"] = _s
sys.modules["mcp.server.fastmcp"] = _fm
sys.modules["mcp.server.mcpserver"] = _ms

# 给网络调用加自动重试（扛瞬时抖动）
import time
import urllib.request as _ur
_orig_open = _ur.urlopen

def _retry_open(*a, **k):
    if not k.get("timeout"):
        k["timeout"] = 10
    else:
        k["timeout"] = min(k["timeout"], 10)
    last = None
    for _i in range(4):
        try:
            return _orig_open(*a, **k)
        except Exception as _e:
            last = _e
            time.sleep(1.2)
    raise last

_ur.urlopen = _retry_open

# 跑真正的 jiq_mcp.py（期间的杂散 print 会被吞掉，不污染协议流）
_t = os.path.join(os.path.dirname(os.path.abspath(__file__)), "jiq_mcp.py")
sys.stdout = io.StringIO()
_g = {"__name__": "__main__", "__file__": _t}
exec(compile(open(_t, encoding="utf-8").read(), _t, "exec"), _g)
