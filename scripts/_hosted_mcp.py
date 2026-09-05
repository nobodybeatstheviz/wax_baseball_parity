"""Minimal client for the Salesforce Hosted MCP servers, reusing Claude Code's OAuth.

Claude Code stores each server's token under ~/.claude/.credentials.json →
mcpOAuth/"<serverName>|<hash>"/{accessToken, refreshToken, serverUrl, clientId}.
This module reads the ACCESS token by server name and speaks MCP streamable-HTTP
JSON-RPC directly (initialize → notifications/initialized → tools/call), so the
parity harness and the observability captures are deterministic — no model in
the loop, no browser.

Deliberately NEVER refreshes: the ECA has refresh-token rotation on, so a refresh
here would invalidate the token Claude Code holds. On 401, run any
`claude -p --allowedTools "mcp__<server>__*" "..."` (Claude refreshes + persists)
or `claude mcp login <server>`, then rerun.
"""

from __future__ import annotations

import json
import pathlib
import urllib.error
import urllib.request

CREDS = pathlib.Path.home() / ".claude" / ".credentials.json"
PROTOCOL = "2025-03-26"


class HostedMcpAuthError(RuntimeError):
    pass


def _entry(server: str) -> dict:
    d = json.loads(CREDS.read_text(encoding="utf-8"))
    for key, val in (d.get("mcpOAuth") or {}).items():
        if key.split("|", 1)[0] == server or val.get("serverName") == server:
            if not val.get("accessToken"):
                break
            return val
    raise HostedMcpAuthError(
        f"no access token for hosted MCP server '{server}' in {CREDS} — "
        f"run: claude mcp login {server}"
    )


class HostedMcp:
    """One MCP session against one hosted server. Use as a context manager or call close()."""

    def __init__(self, server: str):
        e = _entry(server)
        self.server = server
        self.url = e["serverUrl"]
        self.token = e["accessToken"]
        self.session_id: str | None = None
        self._id = 0
        self._initialize()

    # ---- transport -------------------------------------------------------------------

    def _post(self, body: dict, notification: bool = False) -> dict | None:
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "MCP-Protocol-Version": PROTOCOL,
        }
        if self.session_id:
            headers["Mcp-Session-Id"] = self.session_id
        req = urllib.request.Request(self.url, data=json.dumps(body).encode(), headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=180) as resp:
                sid = resp.headers.get("Mcp-Session-Id")
                if sid:
                    self.session_id = sid
                raw = resp.read().decode("utf-8", "replace")
                ctype = resp.headers.get("Content-Type", "")
        except urllib.error.HTTPError as exc:
            text = exc.read().decode("utf-8", "replace")[:400]
            if exc.code == 401:
                raise HostedMcpAuthError(
                    f"401 from {self.server}: token expired/invalid — run any `claude -p --allowedTools "
                    f"\"mcp__{self.server}__*\" ...` or `claude mcp login {self.server}` to refresh. {text}"
                ) from exc
            raise RuntimeError(f"HTTP {exc.code} from {self.server}: {text}") from exc
        if notification or not raw.strip():
            return None
        if "text/event-stream" in ctype:
            # take the last `data:` payload that carries a JSON-RPC result/error
            last = None
            for line in raw.splitlines():
                if line.startswith("data:"):
                    try:
                        last = json.loads(line[5:].strip())
                    except json.JSONDecodeError:
                        continue
            return last
        return json.loads(raw)

    def _rpc(self, method: str, params: dict | None = None) -> dict:
        self._id += 1
        msg = {"jsonrpc": "2.0", "id": self._id, "method": method, "params": params or {}}
        resp = self._post(msg)
        if resp is None:
            raise RuntimeError(f"empty response to {method}")
        if "error" in resp:
            raise RuntimeError(f"{method} error: {json.dumps(resp['error'])[:400]}")
        return resp.get("result", {})

    def _initialize(self) -> None:
        self._rpc("initialize", {
            "protocolVersion": PROTOCOL,
            "capabilities": {},
            "clientInfo": {"name": "wax_baseball_parity", "version": "1"},
        })
        self._post({"jsonrpc": "2.0", "method": "notifications/initialized"}, notification=True)

    # ---- API -------------------------------------------------------------------------

    def list_tools(self) -> list[dict]:
        return self._rpc("tools/list").get("tools", [])

    def call(self, tool: str, arguments: dict) -> dict:
        """Return {'raw': <tools/call result>, 'text': <first text content or None>, 'json': <parsed text or None>}."""
        res = self._rpc("tools/call", {"name": tool, "arguments": arguments})
        text = next((c.get("text") for c in res.get("content", []) if c.get("type") == "text"), None)
        parsed = None
        if text is not None:
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                parsed = None
        if res.get("isError"):
            raise RuntimeError(f"{tool} isError: {(text or json.dumps(res))[:400]}")
        return {"raw": res, "text": text, "json": parsed if parsed is not None else res.get("structuredContent")}

    def close(self) -> None:
        if self.session_id:
            try:
                req = urllib.request.Request(self.url, method="DELETE", headers={
                    "Authorization": f"Bearer {self.token}", "Mcp-Session-Id": self.session_id,
                    "MCP-Protocol-Version": PROTOCOL,
                })
                urllib.request.urlopen(req, timeout=30).read()
            except Exception:  # noqa: BLE001 — best-effort session teardown
                pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def semantic_query_rows(result: dict) -> list[list]:
    """Unwrap tableau-next-pilot run_semantic_query: the tool text is JSON with a
    `defaultExc` field that is ITSELF a JSON string holding queryResults."""
    j = result["json"] if isinstance(result, dict) and "json" in result else result
    if isinstance(j, list) and j and "errorCode" in j[0]:
        raise RuntimeError(f"semantic query error: {j[0].get('message', '')[:400]}")
    inner = j.get("defaultExc") if isinstance(j, dict) else None
    if isinstance(inner, str):
        inner = json.loads(inner)
    if not isinstance(inner, dict) or inner.get("status") != "SUCCESS":
        raise RuntimeError(f"semantic query failed: {json.dumps(j)[:400]}")
    return [list(r["values"]) for r in inner["queryResults"]["queryData"]["rows"]]


def to_snake_query(query: dict) -> dict:
    """Convert the harness's camelCase gateway query (semanticField / tableField /
    rowGrouping / limitOptions) to the proto-shaped snake_case the Beta MCP wants."""
    fields = []
    for f in query["fields"]:
        expr = f["expression"]
        if "semanticField" in expr:
            e = {"semantic_field": {"name": expr["semanticField"]["name"]}}
        else:
            tf = expr["tableField"]
            e = {"table_field": {"name": tf["name"], "table_name": tf["tableName"]}}
        nf = {"expression": e, "alias": f["alias"]}
        if f.get("rowGrouping"):
            nf["grouping"] = "ROW_GROUPING"
        fields.append(nf)
    out = {"fields": fields}
    lim = (query.get("options") or {}).get("limitOptions", {}).get("limit")
    if lim:
        out["options"] = {"limit_options": {"limit": lim}}
    return out
