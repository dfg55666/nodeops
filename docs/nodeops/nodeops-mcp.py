#!/usr/bin/env python3
from __future__ import annotations

import argparse
import concurrent.futures
import dataclasses
import datetime as dt
import json
import random
import re
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

NODEOPS_URL = "https://createos.nodeops.network/"
# Keep legacy naming to minimize churn; the target site is NodeOps.
ORCHIDS_URL = NODEOPS_URL
DEFAULT_PASSWORD = ""  # NodeOps is email+OTP; kept for CLI compatibility.
DEFAULT_MCP_URL = "http://127.0.0.1:12307/mcp"
DEFAULT_MCP_TIMEOUT_S = 30.0
DEFAULT_MAIL_TIMEOUT_S = 120.0
DEFAULT_MAILTM_PASSWORD = "@#Dfg55666"
HUMAN_NAME_PREFIXES = (
    "liam",
    "noah",
    "oliver",
    "emma",
    "sophia",
    "ava",
    "mia",
    "lucas",
    "jack",
    "ryan",
    "zoe",
    "nora",
    "chris",
    "alex",
    "ella",
    "ivy",
    "leo",
    "luna",
    "mason",
    "ethan",
)
OTP_INPUT_SELECTOR = 'input[inputmode="numeric"][maxlength="1"]'
IAMNOTABOT_COORD_CACHE_FILE = Path(__file__).with_name("iamnotabot_coord_cache.json")
IAMNOTABOT_KEYWORDS = (
    "turnstile",
    "cloudflare",
    "challenge",
    "captcha",
    "iamnotabot",
    "i am not a bot",
    "not a bot",
    "verify you are human",
    "security check",
)
_IAMNOTABOT_CACHE_LOCK = threading.Lock()


class ContinueButtonDisabledAbort(RuntimeError):
    """Abort the batch when Continue stays disabled and keep the page untouched."""


class StreamableHttpMCPClient:
    def __init__(self, base_url: str, timeout: float = DEFAULT_MCP_TIMEOUT_S) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session_id: Optional[str] = None
        self._request_id = 1

    def _next_id(self) -> int:
        value = self._request_id
        self._request_id += 1
        return value

    def _post(self, payload: Dict[str, Any], with_session: bool = True) -> Dict[str, Any]:
        body = json.dumps(payload).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        if with_session and self.session_id:
            headers["mcp-session-id"] = self.session_id

        request = urllib.request.Request(self.base_url, data=body, method="POST", headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                if not self.session_id:
                    self.session_id = response.headers.get("mcp-session-id") or self.session_id
                raw = response.read().decode("utf-8")
        except urllib.error.HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"HTTP {error.code}: {detail}") from error
        except urllib.error.URLError as error:
            raise RuntimeError(f"Request failed: {error}") from error

        raw_stripped = raw.strip()
        if raw_stripped.startswith("event:") or raw_stripped.startswith("data:"):
            data_lines: List[str] = []
            for line in raw.splitlines():
                if line.startswith("data:"):
                    data_lines.append(line[len("data:") :].strip())
            if not data_lines:
                raise RuntimeError(f"Invalid SSE response: {raw}")
            parsed_json_text = data_lines[-1]
        else:
            parsed_json_text = raw

        try:
            data = json.loads(parsed_json_text)
        except json.JSONDecodeError as error:
            raise RuntimeError(f"Invalid JSON response: {raw}") from error

        if isinstance(data, dict) and "error" in data:
            raise RuntimeError(f"MCP error: {json.dumps(data['error'], ensure_ascii=False)}")
        if not isinstance(data, dict):
            raise RuntimeError(f"Unexpected response: {data}")
        return data

    def initialize(self) -> Dict[str, Any]:
        payload = {
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "nodeops-mcp-auth", "version": "0.1.0"},
            },
        }
        result = self._post(payload, with_session=False)
        if not self.session_id:
            raise RuntimeError("initialize succeeded but mcp-session-id header is missing")
        return result

    def call_tool(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        if not self.session_id:
            raise RuntimeError("MCP session is not initialized. Call initialize() first.")
        payload = {
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        }
        return self._post(payload, with_session=True)

    def call_tool_json(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        response = self.call_tool(name, arguments)
        text = _extract_tool_text(response)
        if not text:
            return {}
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {"raw_text": text}

    def list_tools(self) -> List[Dict[str, Any]]:
        if not self.session_id:
            raise RuntimeError("MCP session is not initialized. Call initialize() first.")
        payload = {
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": "tools/list",
            "params": {},
        }
        response = self._post(payload, with_session=True)
        result = response.get("result", {})
        tools = result.get("tools", [])
        if isinstance(tools, list):
            return [tool for tool in tools if isinstance(tool, dict)]
        return []


def _extract_tool_text(response: Dict[str, Any]) -> str:
    result = response.get("result", {})
    content = result.get("content", [])
    if not content:
        return ""
    first = content[0]
    if isinstance(first, dict) and first.get("type") == "text":
        return str(first.get("text", ""))
    return ""


def _now() -> str:
    return dt.datetime.now().strftime("%H:%M:%S")


def _log(message: str) -> None:
    print(f"[{_now()}] {message}", file=sys.stderr)


def _utc_now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def _normalize_mcp_cache_key(mcp_url: str) -> str:
    return str(mcp_url or "").strip().rstrip("/").lower()


def _load_iamnotabot_coord_cache() -> Dict[str, Any]:
    if not IAMNOTABOT_COORD_CACHE_FILE.exists():
        return {"version": 1, "items": {}}
    try:
        with IAMNOTABOT_COORD_CACHE_FILE.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        if not isinstance(payload, dict):
            return {"version": 1, "items": {}}
        items = payload.get("items", {})
        if not isinstance(items, dict):
            items = {}
        payload["items"] = items
        payload.setdefault("version", 1)
        return payload
    except Exception as exc:
        _log(f"read iamnotabot coord cache failed: {exc}")
        return {"version": 1, "items": {}}


def _save_iamnotabot_coord_cache(payload: Dict[str, Any]) -> None:
    try:
        payload = payload if isinstance(payload, dict) else {"version": 1, "items": {}}
        payload.setdefault("version", 1)
        payload.setdefault("items", {})
        IAMNOTABOT_COORD_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            delete=False,
            dir=str(IAMNOTABOT_COORD_CACHE_FILE.parent),
            prefix=IAMNOTABOT_COORD_CACHE_FILE.name + ".",
            suffix=".tmp",
        ) as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            tmp_path = Path(handle.name)
        tmp_path.replace(IAMNOTABOT_COORD_CACHE_FILE)
    except Exception as exc:
        _log(f"write iamnotabot coord cache failed: {exc}")


def _get_cached_iamnotabot_coord(mcp_url: str) -> Optional[Dict[str, float]]:
    key = _normalize_mcp_cache_key(mcp_url)
    if not key:
        return None
    with _IAMNOTABOT_CACHE_LOCK:
        payload = _load_iamnotabot_coord_cache()
        item = payload.get("items", {}).get(key)
        if not isinstance(item, dict):
            return None
        try:
            x = float(item.get("x"))
            y = float(item.get("y"))
        except (TypeError, ValueError):
            return None
        if x <= 0 or y <= 0:
            return None
        return {"x": x, "y": y}


def _set_cached_iamnotabot_coord(
    mcp_url: str,
    x: float,
    y: float,
    source: str,
    meta: Optional[Dict[str, Any]] = None,
) -> None:
    key = _normalize_mcp_cache_key(mcp_url)
    if not key:
        return
    if x <= 0 or y <= 0:
        return

    with _IAMNOTABOT_CACHE_LOCK:
        payload = _load_iamnotabot_coord_cache()
        items = payload.setdefault("items", {})
        if not isinstance(items, dict):
            items = {}
            payload["items"] = items

        prev = items.get(key, {})
        hits = 0
        if isinstance(prev, dict):
            prev_hits = prev.get("hits")
            if isinstance(prev_hits, (int, float)):
                hits = int(prev_hits)

        next_item: Dict[str, Any] = {
            "x": round(float(x), 2),
            "y": round(float(y), 2),
            "source": str(source or ""),
            "updated_at": _utc_now_iso(),
            "hits": hits + 1,
        }
        if isinstance(meta, dict) and meta:
            next_item["meta"] = meta
        items[key] = next_item
        _save_iamnotabot_coord_cache(payload)


def _parse_maybe_json_text(value: Any) -> Any:
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return ""
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return text
    return value


def _run_js(client: StreamableHttpMCPClient, tab_id: int, code: str) -> Any:
    payload = client.call_tool_json("chrome_javascript", {"tabId": tab_id, "code": code})
    if "result" in payload:
        return _parse_maybe_json_text(payload.get("result"))
    if "raw_text" in payload:
        return _parse_maybe_json_text(payload.get("raw_text"))
    return payload


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "ok"}
    return bool(value)


def _wait_for_condition(
    client: StreamableHttpMCPClient,
    tab_id: int,
    code: str,
    timeout_s: float,
    poll_s: float = 0.5,
) -> bool:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            if _truthy(_run_js(client, tab_id, code)):
                return True
        except Exception:
            pass
        time.sleep(poll_s)
    return False


def _read_otp_state(client: StreamableHttpMCPClient, tab_id: int) -> Dict[str, Any]:
    state = _run_js(
        client,
        tab_id,
        f"""
const inputs = Array.from(document.querySelectorAll('{OTP_INPUT_SELECTOR}'))
  .filter(el => el && el.offsetParent !== null);
if (inputs.length < 6) return {{ ok: false, reason: 'not_found', count: inputs.length }};
const digits = inputs.slice(0, 6).map(el => String(el.value || '').trim());
const value = digits.join('');
return {{
  ok: value.length === 6 && /^\\d{{6}}$/.test(value),
  valueLength: value.length,
  value,
  filledCount: digits.filter(x => x.length === 1).length,
  count: inputs.length,
}};
""",
    )
    if isinstance(state, dict):
        return state
    return {"ok": False, "reason": "invalid_state", "raw": state}


def _otp_state_ok(state: Dict[str, Any], min_len: int = 6) -> bool:
    if not isinstance(state, dict):
        return False
    value_len = int(state.get("valueLength") or 0)
    if value_len < min_len:
        return False
    filled = int(state.get("filledCount") or 0)
    return filled >= min_len


def _set_otp_code(client: StreamableHttpMCPClient, tab_id: int, code: str) -> None:
    code_text = str(code or "").strip()
    if not code_text:
        raise RuntimeError("empty otp code")
    if not re.fullmatch(r"\d{6}", code_text):
        raise RuntimeError(f"invalid otp code format: {code_text}")

    # 1) Prefer direct DOM write to avoid focus contention across concurrent workers.
    direct = _run_js(
        client,
        tab_id,
        f"""
const inputs = Array.from(document.querySelectorAll('{OTP_INPUT_SELECTOR}'))
  .filter(el => el && el.offsetParent !== null);
if (inputs.length < 6) return {{ ok: false, reason: 'not_found', count: inputs.length }};
const digits = String({json.dumps(code_text)}).split('');
const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
for (let i = 0; i < 6; i += 1) {{
  const el = inputs[i];
  if (!el) continue;
  setter.call(el, digits[i] || '');
  el.dispatchEvent(new Event('input', {{ bubbles: true }}));
  el.dispatchEvent(new Event('change', {{ bubbles: true }}));
}}
const value = inputs.slice(0, 6).map(el => String(el.value || '').trim()).join('');
return {{ ok: value.length === 6 && /^\\d{{6}}$/.test(value), valueLength: value.length, value, count: inputs.length }};
""",
    )
    time.sleep(0.15)
    state = _read_otp_state(client, tab_id)
    if _otp_state_ok(state):
        _log(f"tab={tab_id} otp set via direct DOM write")
        return

    # 2) Form-fill fallback (first input + keyboard type).
    try:
        client.call_tool_json(
            "chrome_fill_or_select",
            {
                "tabId": tab_id,
                "selector": OTP_INPUT_SELECTOR,
                "value": code_text[:1],
            },
        )
        time.sleep(0.15)
        fill_state = _read_otp_state(client, tab_id)
        if _otp_state_ok(fill_state):
            _log(f"tab={tab_id} otp set via fill_or_select")
            return
    except Exception as exc:
        _log(f"tab={tab_id} otp fill fallback failed: {exc}")

    # 3) Last resort: real keyboard input (can contend under high parallelism).
    try:
        client.call_tool_json(
            "chrome_click_element",
            {"tabId": tab_id, "selector": OTP_INPUT_SELECTOR, "timeout": 10000},
        )
    except Exception:
        pass

    client.call_tool_json(
        "chrome_keyboard",
        {
            "tabId": tab_id,
            "keys": code_text,
            "delay": 80,
        },
    )
    time.sleep(0.25)
    keyboard_state = _read_otp_state(client, tab_id)
    if _otp_state_ok(keyboard_state):
        _log(f"tab={tab_id} otp set via keyboard fallback")
        return

    raise RuntimeError(
        "failed to set otp code, "
        f"direct={direct}, state={state}, keyboard={keyboard_state}"
    )


def _verify_chrome_mcp_tools(client: StreamableHttpMCPClient, require_clear_site_data: bool = True) -> None:
    required = {
        "chrome_navigate",
        "chrome_click_element",
        "chrome_fill_or_select",
        "chrome_keyboard",
        "chrome_javascript",
        "chrome_export_cookies",
        "chrome_close_tabs",
        "get_windows_and_tabs",
    }
    if require_clear_site_data:
        required.add("chrome_clear_site_data")
    tools = client.list_tools()
    names = {str(item.get("name", "")) for item in tools}
    missing = sorted(name for name in required if name not in names)
    if missing:
        guidance = ""
        if "chrome_clear_site_data" in missing:
            guidance = (
                "; this MCP profile cannot clear login cookies. "
                "Use a profile/port that exposes chrome_clear_site_data."
            )
        raise RuntimeError("chrome-mcp missing required tools: " + ", ".join(missing) + guidance)


def _verify_inspect_tools(client: StreamableHttpMCPClient) -> None:
    required = {
        "get_windows_and_tabs",
        "chrome_export_cookies",
        "chrome_javascript",
    }
    tools = client.list_tools()
    names = {str(item.get("name", "")) for item in tools}
    missing = sorted(name for name in required if name not in names)
    if missing:
        raise RuntimeError("chrome-mcp missing inspect tools: " + ", ".join(missing))


def _extract_tab_id(payload: Dict[str, Any]) -> int:
    if not isinstance(payload, dict):
        return 0
    for key in ("tabId", "tab_id", "id"):
        value = payload.get(key)
        if isinstance(value, int) and value > 0:
            return value
        if isinstance(value, str) and value.isdigit():
            return int(value)
    tab = payload.get("tab")
    if isinstance(tab, dict):
        return _extract_tab_id(tab)
    return 0


def _active_tab_info(payload: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        raise RuntimeError(f"get_windows_and_tabs returned invalid payload: {payload}")

    windows = payload.get("windows", [])
    if not isinstance(windows, list):
        raise RuntimeError(f"get_windows_and_tabs missing windows: {payload}")

    fallback: Optional[Dict[str, Any]] = None
    for win in windows:
        if not isinstance(win, dict):
            continue
        tabs = win.get("tabs", [])
        if not isinstance(tabs, list):
            continue
        for tab in tabs:
            if not isinstance(tab, dict):
                continue
            tab_id = _extract_tab_id(tab)
            if tab_id <= 0:
                continue
            info = {
                "tab_id": tab_id,
                "window_id": win.get("windowId"),
                "url": str(tab.get("url", "") or ""),
                "title": str(tab.get("title", "") or ""),
                "active": bool(tab.get("active")),
            }
            if fallback is None:
                fallback = info
            if info["active"]:
                return info

    if fallback is not None:
        return fallback
    raise RuntimeError("no browser tab found in get_windows_and_tabs payload")


def _extract_paths_from_obj(value: Any, out: List[str]) -> None:
    if isinstance(value, str):
        if value.lower().endswith(".json"):
            out.append(value)
        return
    if isinstance(value, dict):
        for nested in value.values():
            _extract_paths_from_obj(nested, out)
        return
    if isinstance(value, list):
        for nested in value:
            _extract_paths_from_obj(nested, out)


def _resolve_cookie_export_path(payload: Dict[str, Any], output_dir: str) -> Path:
    candidates: List[str] = []
    _extract_paths_from_obj(payload, candidates)

    raw_text = payload.get("raw_text")
    if isinstance(raw_text, str):
        for match in re.findall(r"[A-Za-z]:\\[^\n\r\"']+\.json|/[^\s\"']+\.json", raw_text):
            candidates.append(match)

    for candidate in candidates:
        path = Path(candidate)
        if not path.is_absolute():
            path = Path(output_dir) / candidate
        if path.exists():
            return path

    files = sorted(Path(output_dir).glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if files:
        return files[0]
    raise RuntimeError(f"cookie export file not found, payload={payload}")


def _click_continue(client: StreamableHttpMCPClient, tab_id: int) -> None:
    # NodeOps flow uses submit buttons for both steps:
    # - "Continue with Email"
    # - "Verify & Enter CreateOS"
    clicked = _run_js(
        client,
        tab_id,
        """
function isDisabled(btn) {
  return !!(btn.disabled || btn.getAttribute('aria-disabled') === 'true');
}

const submitButtons = Array.from(document.querySelectorAll('button[type="submit"]'));
for (const btn of submitButtons) {
  const text = String(btn.innerText || btn.textContent || '').trim();
  if (!text) continue;
  if (!isDisabled(btn)) {
    btn.click();
    return { ok: true, via: 'submit', text };
  }
}

// Fallback: find any enabled button that looks like a continue/verify action.
const candidates = Array.from(document.querySelectorAll('button'));
for (const btn of candidates) {
  const text = String(btn.innerText || btn.textContent || '').trim();
  if (!text) continue;
  if (!/(continue|verify)/i.test(text)) continue;
  if (isDisabled(btn)) continue;
  btn.click();
  return { ok: true, via: 'text_match', text };
}

return { ok: false };
""",
    )
    if not (isinstance(clicked, dict) and _truthy(clicked.get("ok"))):
        raise RuntimeError(f"continue/verify button not found or disabled, state={clicked}")


def _read_continue_button_state(client: StreamableHttpMCPClient, tab_id: int) -> Dict[str, Any]:
    state = _run_js(
        client,
        tab_id,
        """
function isDisabled(btn) {
  return !!(btn.disabled || btn.getAttribute('aria-disabled') === 'true');
}

const submitButtons = Array.from(document.querySelectorAll('button[type="submit"]'));
for (const btn of submitButtons) {
  const text = String(btn.innerText || btn.textContent || '').trim();
  if (!text) continue;
  return { found: true, disabled: isDisabled(btn), text };
}

const candidates = Array.from(document.querySelectorAll('button'));
for (const btn of candidates) {
  const text = String(btn.innerText || btn.textContent || '').trim();
  if (!text) continue;
  if (!/(continue|verify)/i.test(text)) continue;
  return { found: true, disabled: isDisabled(btn), text };
}

return { found: false, disabled: true, text: '' };
""",
    )
    if isinstance(state, dict):
        return state
    return {"found": False, "disabled": True, "text": "", "raw": state}


def _wait_continue_enabled(
    client: StreamableHttpMCPClient,
    tab_id: int,
    timeout_s: float = 5.0,
    poll_s: float = 0.25,
) -> bool:
    deadline = time.monotonic() + timeout_s
    last_state: Dict[str, Any] = {"found": False, "disabled": True}
    while time.monotonic() < deadline:
        last_state = _read_continue_button_state(client, tab_id)
        if _truthy(last_state.get("found")) and not _truthy(last_state.get("disabled")):
            return True
        time.sleep(poll_s)
    _log(f"tab={tab_id} continue button still disabled after {timeout_s:.1f}s, state={last_state}")
    return False


def _run_iframe_js(client: StreamableHttpMCPClient, tab_id: int, frame_id: str, code: str) -> Dict[str, Any]:
    payload = client.call_tool_json(
        "chrome_iframe_javascript",
        {
            "tabId": tab_id,
            "frameId": frame_id,
            "code": code,
        },
    )
    if "result" in payload:
        result = _parse_maybe_json_text(payload.get("result"))
        if isinstance(result, dict):
            return result
        return {"raw": result}
    if "raw_text" in payload:
        result = _parse_maybe_json_text(payload.get("raw_text"))
        if isinstance(result, dict):
            return result
        return {"raw": result}
    if isinstance(payload, dict):
        return payload
    return {"raw": payload}


def _list_frames(client: StreamableHttpMCPClient, tab_id: int) -> List[Dict[str, Any]]:
    payload = client.call_tool_json("chrome_list_frames", {"tabId": tab_id})
    frames = payload.get("frames", [])
    if isinstance(frames, list):
        return [item for item in frames if isinstance(item, dict)]
    return []


def _collect_top_iframe_rects(client: StreamableHttpMCPClient, tab_id: int) -> List[Dict[str, Any]]:
    raw = _run_js(
        client,
        tab_id,
        f"""
const keywords = {json.dumps(list(IAMNOTABOT_KEYWORDS))}.map(x => String(x).toLowerCase());
const list = [];
const iframes = Array.from(document.querySelectorAll('iframe'));
for (let i = 0; i < iframes.length; i++) {{
  const el = iframes[i];
  const rect = el.getBoundingClientRect();
  if (!rect || rect.width < 20 || rect.height < 20) continue;
  const style = window.getComputedStyle(el);
  if (!style || style.display === 'none' || style.visibility === 'hidden' || Number(style.opacity || '1') <= 0) continue;

  const attrs = [
    el.src || '',
    el.id || '',
    el.name || '',
    el.title || '',
    el.getAttribute('aria-label') || '',
    el.className || ''
  ].join(' ').toLowerCase();

  let score = 0;
  for (const kw of keywords) {{
    if (kw && attrs.includes(kw)) score += 2;
  }}
  if (rect.width >= 220 && rect.width <= 460 && rect.height >= 40 && rect.height <= 200) score += 1;

  list.push({{
    idx: i,
    src: String(el.src || ''),
    id: String(el.id || ''),
    name: String(el.name || ''),
    title: String(el.title || ''),
    x: Number(rect.left || 0),
    y: Number(rect.top || 0),
    width: Number(rect.width || 0),
    height: Number(rect.height || 0),
    cx: Number(rect.left + rect.width / 2),
    cy: Number(rect.top + rect.height / 2),
    score
  }});
}}
list.sort((a, b) => Number(b.score || 0) - Number(a.score || 0));
return {{ items: list }};
""",
    )
    if isinstance(raw, dict):
        items = raw.get("items", [])
        if isinstance(items, list):
            return [item for item in items if isinstance(item, dict)]
    return []


def _score_iframe_attrs(*values: str) -> int:
    text = " ".join(str(value or "") for value in values).lower()
    score = 0
    for keyword in IAMNOTABOT_KEYWORDS:
        if keyword in text:
            score += 3
    return score


def _match_top_iframe_rect_for_frame(
    frame: Dict[str, Any],
    top_iframes: List[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    frame_url = str(frame.get("url", "") or "")
    frame_name = str(frame.get("name", "") or "")
    best: Optional[Dict[str, Any]] = None
    best_score = -1

    for rect in top_iframes:
        src = str(rect.get("src", "") or "")
        name = str(rect.get("name", "") or "")
        title = str(rect.get("title", "") or "")
        rect_score = int(rect.get("score", 0) or 0)
        score = rect_score + _score_iframe_attrs(src, name, title)
        if frame_url and src:
            if frame_url == src:
                score += 8
            elif frame_url in src or src in frame_url:
                score += 5
        if frame_name and name and frame_name == name:
            score += 3
        if score > best_score:
            best_score = score
            best = rect
    return best


def _clamp(value: float, low: float, high: float) -> float:
    if high < low:
        return low
    return max(low, min(high, value))


def _rect_default_click_point(rect: Dict[str, Any]) -> Optional[Dict[str, float]]:
    try:
        x = float(rect.get("x", 0))
        y = float(rect.get("y", 0))
        width = float(rect.get("width", 0))
        height = float(rect.get("height", 0))
    except (TypeError, ValueError):
        return None

    if width <= 1 or height <= 1:
        return None

    # Turnstile-style widgets are usually a wide short iframe; click near the checkbox on left side.
    if width >= 220 and height <= 180:
        click_x = x + min(max(26.0, width * 0.12), max(30.0, width * 0.35))
        click_y = y + height * 0.5
    else:
        click_x = x + width * 0.5
        click_y = y + height * 0.5

    return {"x": click_x, "y": click_y}


def _compute_iamnotabot_coord_via_iframe_tools(
    client: StreamableHttpMCPClient,
    tab_id: int,
) -> Optional[Dict[str, Any]]:
    frames = _list_frames(client, tab_id)
    if not frames:
        return None
    top_iframes = _collect_top_iframe_rects(client, tab_id)
    if not top_iframes:
        return None

    candidates: List[Dict[str, Any]] = []
    for frame in frames:
        url = str(frame.get("url", "") or "")
        name = str(frame.get("name", "") or "")
        if _score_iframe_attrs(url, name) <= 0:
            continue
        rect = _match_top_iframe_rect_for_frame(frame, top_iframes)
        if rect is None:
            continue

        local_click = _run_iframe_js(
            client,
            tab_id,
            str(frame.get("frameId", "")),
            """
const selectors = [
  'input[type="checkbox"]',
  '[role="checkbox"]',
  'label',
  'button'
];
for (const selector of selectors) {
  const el = document.querySelector(selector);
  if (!el) continue;
  const rect = el.getBoundingClientRect();
  if (rect && rect.width > 0 && rect.height > 0) {
    return {
      found: true,
      x: Number(rect.left + rect.width / 2),
      y: Number(rect.top + rect.height / 2),
      text: String((el.innerText || el.textContent || '').slice(0, 80))
    };
  }
}
return { found: false, body: String((document.body?.innerText || '').slice(0, 120)) };
""",
        )

        point = _rect_default_click_point(rect)
        if point is None:
            continue

        score = _score_iframe_attrs(url, name, str(rect.get("src", "") or ""), str(rect.get("title", "") or ""))
        if _truthy(local_click.get("found")):
            try:
                local_x = float(local_click.get("x", 0))
                local_y = float(local_click.get("y", 0))
                frame_x = float(rect.get("x", 0))
                frame_y = float(rect.get("y", 0))
                frame_w = float(rect.get("width", 0))
                frame_h = float(rect.get("height", 0))
                if frame_w > 1 and frame_h > 1:
                    point = {
                        "x": frame_x + _clamp(local_x, 1, frame_w - 1),
                        "y": frame_y + _clamp(local_y, 1, frame_h - 1),
                    }
                    score += 3
            except (TypeError, ValueError):
                pass

        candidates.append(
            {
                "x": point["x"],
                "y": point["y"],
                "score": score,
                "source": "iframe-tools",
                "meta": {
                    "frame_url": url,
                    "frame_name": name,
                    "frame_id": str(frame.get("frameId", "") or ""),
                },
            }
        )

    if not candidates:
        return None
    candidates.sort(key=lambda item: float(item.get("score", 0)), reverse=True)
    return candidates[0]


def _compute_iamnotabot_coord_via_dom(
    client: StreamableHttpMCPClient,
    tab_id: int,
) -> Optional[Dict[str, Any]]:
    top_iframes = _collect_top_iframe_rects(client, tab_id)
    if not top_iframes:
        return None

    candidates: List[Dict[str, Any]] = []
    for rect in top_iframes:
        point = _rect_default_click_point(rect)
        if point is None:
            continue
        score = int(rect.get("score", 0) or 0)
        score += _score_iframe_attrs(
            str(rect.get("src", "") or ""),
            str(rect.get("title", "") or ""),
            str(rect.get("name", "") or ""),
            str(rect.get("id", "") or ""),
        )
        candidates.append(
            {
                "x": point["x"],
                "y": point["y"],
                "score": score,
                "source": "dom-iframe",
                "meta": {
                    "iframe_src": str(rect.get("src", "") or ""),
                    "iframe_title": str(rect.get("title", "") or ""),
                    "iframe_idx": rect.get("idx"),
                },
            }
        )

    if not candidates:
        return None
    candidates.sort(key=lambda item: float(item.get("score", 0)), reverse=True)
    return candidates[0]


def _resolve_iamnotabot_click_coord(
    client: StreamableHttpMCPClient,
    tab_id: int,
) -> Optional[Dict[str, Any]]:
    try:
        coord = _compute_iamnotabot_coord_via_iframe_tools(client, tab_id)
        if coord is not None:
            return coord
    except Exception as exc:
        _log(f"tab={tab_id} iframe-tools coord detect failed: {exc}")

    try:
        coord = _compute_iamnotabot_coord_via_dom(client, tab_id)
        if coord is not None:
            return coord
    except Exception as exc:
        _log(f"tab={tab_id} dom iframe coord detect failed: {exc}")

    return None


def _click_coordinate_cdp_only(client: StreamableHttpMCPClient, tab_id: int, x: float, y: float) -> None:
    px = int(round(x))
    py = int(round(y))
    try:
        client.call_tool_json(
            "chrome_computer",
            {
                "action": "left_click",
                "clickMode": "cdp_only",
                "tabId": tab_id,
                "coordinates": {
                    "x": px,
                    "y": py,
                },
            },
        )
        return
    except Exception as exc:
        _log(f"tab={tab_id} chrome_computer cdp_only click unavailable, fallback: {exc}")

    # Some mcp profiles do not expose chrome_computer. Fallback to coordinate click.
    client.call_tool_json(
        "chrome_click_element",
        {
            "tabId": tab_id,
            "coordinates": {
                "x": px,
                "y": py,
            },
            "timeout": 5000,
        },
    )


def _try_click_iamnotabot_for_continue(
    client: StreamableHttpMCPClient,
    tab_id: int,
    mcp_url: str,
    wait_after_click_s: float = 4.0,
) -> bool:
    cached = _get_cached_iamnotabot_coord(mcp_url)
    if cached is not None:
        _log(
            f"tab={tab_id} try cached iamnotabot coord ({cached['x']:.1f}, {cached['y']:.1f}) "
            f"for mcp={mcp_url}"
        )
        try:
            _click_coordinate_cdp_only(client, tab_id, cached["x"], cached["y"])
            time.sleep(0.6)
            if _wait_continue_enabled(client, tab_id, timeout_s=wait_after_click_s, poll_s=0.2):
                _log(f"tab={tab_id} continue enabled after cached cdp click")
                return True
            _log(f"tab={tab_id} cached cdp click did not enable continue")
        except Exception as exc:
            _log(f"tab={tab_id} cached cdp click failed: {exc}")

    detected = _resolve_iamnotabot_click_coord(client, tab_id)
    if detected is None:
        _log(f"tab={tab_id} iamnotabot iframe coordinate not found")
        return False

    x = float(detected.get("x", 0))
    y = float(detected.get("y", 0))
    source = str(detected.get("source", "detected") or "detected")
    meta = detected.get("meta", {}) if isinstance(detected.get("meta"), dict) else {}
    _log(
        f"tab={tab_id} detected iamnotabot coord ({x:.1f}, {y:.1f}) via {source}, "
        f"try cdp_only click"
    )
    try:
        _click_coordinate_cdp_only(client, tab_id, x, y)
    except Exception as exc:
        _log(f"tab={tab_id} detected cdp click failed: {exc}")
        return False

    _set_cached_iamnotabot_coord(mcp_url, x, y, source=source, meta=meta)
    time.sleep(0.6)
    if _wait_continue_enabled(client, tab_id, timeout_s=wait_after_click_s, poll_s=0.2):
        _log(f"tab={tab_id} continue enabled after detected cdp click")
        return True
    _log(f"tab={tab_id} detected cdp click did not enable continue")
    return False


def _wait_for_otp_or_continue_stuck(
    client: StreamableHttpMCPClient,
    tab_id: int,
    timeout_s: float = 60.0,
    poll_s: float = 0.5,
    continue_stuck_s: float = 8.0,
) -> tuple[str, Dict[str, Any]]:
    deadline = time.monotonic() + timeout_s
    disabled_since: Optional[float] = None
    last_state: Dict[str, Any] = {"found": False, "disabled": True}

    while time.monotonic() < deadline:
        has_otp_inputs = _truthy(
            _run_js(
                client,
                tab_id,
                f"return document.querySelectorAll({json.dumps(OTP_INPUT_SELECTOR)}).length >= 6;",
            )
        )
        if has_otp_inputs:
            return "otp", {"hasOtp": True}

        state = _read_continue_button_state(client, tab_id)
        last_state = state
        if _truthy(state.get("found")) and _truthy(state.get("disabled")):
            now = time.monotonic()
            if disabled_since is None:
                disabled_since = now
            elif now - disabled_since >= continue_stuck_s:
                return "continue_stuck", state
        else:
            disabled_since = None

        time.sleep(poll_s)

    return "timeout", last_state


def _dismiss_nodeops_intro_guide(
    client: StreamableHttpMCPClient,
    tab_id: int,
    timeout_s: float = 6.0,
) -> bool:
    """
    NodeOps occasionally shows a multi-step onboarding guide after clearing storage.
    This blocks the Login button/email form. Close it if present.
    """

    selector = "svg.guide-skip-btn[data-intro-skip], .guide-skip-btn[data-intro-skip], [data-intro-skip]"
    deadline = time.monotonic() + timeout_s
    clicked = False

    while time.monotonic() < deadline:
        state = _run_js(
            client,
            tab_id,
            f"""
const el = document.querySelector({json.dumps(selector)});
if (!el) return {{ found: false }};
const rect = el.getBoundingClientRect();
const style = window.getComputedStyle(el);
const visible = rect.width > 1 && rect.height > 1 && style.visibility !== 'hidden' && style.display !== 'none';
return {{ found: true, visible }};
""",
        )
        if not isinstance(state, dict) or not _truthy(state.get("found")):
            return clicked

        if not _truthy(state.get("visible")):
            time.sleep(0.25)
            continue

        # Prefer DOM click (works even when element is an <svg>).
        _run_js(
            client,
            tab_id,
            f"""
const el = document.querySelector({json.dumps(selector)});
if (!el) return false;
try {{ el.scrollIntoView({{ block: 'center', inline: 'center' }}); }} catch (_) {{}}
try {{ el.click(); }} catch (_) {{}}
try {{
  el.dispatchEvent(new MouseEvent('click', {{ bubbles: true, cancelable: true, view: window }}));
}} catch (_) {{}}
return true;
""",
        )
        clicked = True
        time.sleep(0.4)

    return clicked


def _prepare_signup_form(
    client: StreamableHttpMCPClient,
    tab_id: int,
    mcp_url: str,
    email: str,
    password: str,
    headless: bool,
    max_restarts: int = 3,
    exit_on_continue_disabled: bool = False,
) -> None:
    # NodeOps login flow:
    # 1) Click Login
    # 2) Enter email
    # 3) Wait submit enabled ("Continue with Email")
    _ = password  # unused (kept for CLI compatibility)

    email_selector = 'input[type="email"], input[placeholder*="email" i]'

    for attempt in range(1, max_restarts + 1):
        if attempt > 1:
            _log(
                f"tab={tab_id} submit stayed disabled after email input, "
                f"refresh and restart login (attempt {attempt}/{max_restarts})"
            )
            client.call_tool_json(
                "chrome_navigate",
                {
                    "tabId": tab_id,
                    "url": ORCHIDS_URL,
                    "background": bool(headless),
                },
            )
            time.sleep(0.8)

        # If OTP inputs are already shown, we're already past the email step.
        has_otp = _truthy(_run_js(client, tab_id, f"return document.querySelectorAll('{OTP_INPUT_SELECTOR}').length >= 6;"))
        if has_otp:
            return

        # New-user guide can appear after clearing storage; close it so we can access the login UI.
        # The guide sometimes renders asynchronously, so keep trying to dismiss it while opening Login.
        login_deadline = time.monotonic() + 35.0
        while time.monotonic() < login_deadline:
            if _truthy(_run_js(client, tab_id, f"return !!document.querySelector({json.dumps(email_selector)});")):
                break

            _dismiss_nodeops_intro_guide(client, tab_id, timeout_s=1.0)

            # Click "Login" if present (best-effort).
            try:
                client.call_tool_json(
                    "chrome_click_element",
                    {
                        "tabId": tab_id,
                        "selector": "//button[contains(normalize-space(.), 'Login')]",
                        "selectorType": "xpath",
                        "timeout": 3000,
                    },
                )
            except Exception:
                # Some states may require scrolling first or render the button later.
                pass

            # JS fallback: find and click by text (more resilient to DOM structure changes).
            _run_js(
                client,
                tab_id,
                """
return (() => {
  try { window.scrollTo(0, 0); } catch (_) {}
  const btn = Array.from(document.querySelectorAll('button'))
    .find(b => /\\blogin\\b/i.test(String(b.innerText || '').trim()));
  if (!btn) return { ok: false, reason: 'not_found' };
  try { btn.scrollIntoView({ block: 'center', inline: 'center' }); } catch (_) {}
  try { btn.click(); } catch (_) {}
  try { btn.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, view: window })); } catch (_) {}
  return { ok: true };
})();
""",
            )

            if _wait_for_condition(
                client,
                tab_id,
                f"return !!document.querySelector({json.dumps(email_selector)});",
                timeout_s=2.5,
                poll_s=0.25,
            ):
                break

            time.sleep(0.25)

        if not _truthy(_run_js(client, tab_id, f"return !!document.querySelector({json.dumps(email_selector)});")):
            raise RuntimeError("email input not visible")

        client.call_tool_json(
            "chrome_fill_or_select",
            {
                "tabId": tab_id,
                "selector": email_selector,
                "value": email,
            },
        )

        if _wait_continue_enabled(client, tab_id, timeout_s=5.0, poll_s=0.25):
            return
        if _try_click_iamnotabot_for_continue(client, tab_id, mcp_url, wait_after_click_s=4.0):
            return
        if exit_on_continue_disabled:
            state = _read_continue_button_state(client, tab_id)
            raise ContinueButtonDisabledAbort(
                "submit button remained disabled within 5s after email input, "
                f"state={state}"
            )

    raise RuntimeError(
        f"submit button remained disabled within 5s after email input "
        f"(restarted {max_restarts} times)"
    )


_CODE_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in [
        r"Your verification code is[:\s]+(\d{6})",
        r"verification code[:\s]+(?:is[:\s]+)?(\d{6})",
        r"verify(?:ing)? code[:\s]+(?:is[:\s]+)?(\d{6})",
        r"code[:\s]+(\d{6})",
        r"<strong>(\d{6})</strong>",
        r"<span[^>]*>(\d{6})</span>",
        r"\b(\d{6})\b",
    ]
]


def _extract_verification_code(content: str) -> str:
    if not content:
        return ""

    candidates = [content]
    try:
        import html as _html

        # Many OTP emails render each digit in its own HTML element; strip tags to make
        # the code easier to parse from `text/html` bodies.
        stripped = re.sub(r"<[^>]+>", " ", content)
        stripped = _html.unescape(stripped)
        if stripped and stripped != content:
            candidates.append(stripped)
    except Exception:
        pass

    for candidate in candidates:
        for regex in _CODE_PATTERNS:
            match = regex.search(candidate)
            if match:
                return match.group(1)

    # Keyword-window fallback: reduce false positives from dates/IDs in footers.
    keyword_match = re.search(r"(verification|verify|otp|code)", content, flags=re.IGNORECASE)
    if keyword_match:
        window = content[keyword_match.end() : keyword_match.end() + 3000]
        digits = re.sub(r"\D", "", window)
        match = re.search(r"\d{6}", digits)
        if match:
            return match.group(0)

    # Generic fallback: 6 digits with arbitrary separators (HTML tags, whitespace, etc).
    spaced = re.search(r"(\d)\D{0,200}(\d)\D{0,200}(\d)\D{0,200}(\d)\D{0,200}(\d)\D{0,200}(\d)", content)
    if spaced:
        return "".join(spaced.groups())

    # Last resort: take the first 6-digit run from all digits.
    digits = re.sub(r"\D", "", content)
    match = re.search(r"\d{6}", digits)
    if match:
        return match.group(0)

    return ""


def _generate_random_string(length: int) -> str:
    chars = "abcdefghijklmnopqrstuvwxyz0123456789"
    return "".join(random.choice(chars) for _ in range(length))


def _generate_human_like_username() -> str:
    prefix = random.choice(HUMAN_NAME_PREFIXES)
    suffix = random.randint(10000, 99999)
    return f"{prefix}{suffix}"


class MailTMInbox:
    def __init__(self) -> None:
        self.password = DEFAULT_MAILTM_PASSWORD
        self.email = ""
        self.token = ""

    def _request_json(
        self,
        method: str,
        url: str,
        body: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> tuple[int, Any, str]:
        payload = None
        req_headers = {"Accept": "application/json"}
        if headers:
            req_headers.update(headers)
        if body is not None:
            payload = json.dumps(body).encode("utf-8")
            req_headers.setdefault("Content-Type", "application/json")

        request = urllib.request.Request(url, data=payload, method=method, headers=req_headers)
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                status = response.getcode()
                text = response.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as error:
            status = error.code
            text = error.read().decode("utf-8", errors="replace")

        try:
            parsed = json.loads(text) if text else {}
        except json.JSONDecodeError:
            parsed = text
        return status, parsed, text

    def _login(self) -> None:
        status, payload, raw = self._request_json(
            "POST",
            "https://api.mail.tm/token",
            body={"address": self.email, "password": self.password},
        )
        if status != 200 or not isinstance(payload, dict) or not payload.get("token"):
            raise RuntimeError(f"mail.tm login failed ({status}): {raw}")
        self.token = str(payload.get("token"))

    def _create_inbox_once(self) -> str:
        status, payload, raw = self._request_json("GET", "https://api.mail.tm/domains")
        if status == 429:
            raise RuntimeError("mail.tm rate limited (429)")
        if status != 200:
            raise RuntimeError(f"mail.tm domains failed ({status}): {raw}")

        members: List[Dict[str, Any]] = []
        if isinstance(payload, list):
            members = [item for item in payload if isinstance(item, dict)]
        elif isinstance(payload, dict):
            value = payload.get("hydra:member")
            if isinstance(value, list):
                members = [item for item in value if isinstance(item, dict)]
            elif isinstance(payload.get("domains"), list):
                members = [
                    item
                    for item in payload.get("domains", [])
                    if isinstance(item, dict)
                ]
        if not members:
            raw_preview = raw[:240].replace("\n", " ")
            raise RuntimeError(f"mail.tm has no domain, payload={raw_preview}")

        first = members[0] if isinstance(members[0], dict) else {}
        domain = str(first.get("domain", "")).strip()
        if not domain:
            raise RuntimeError("mail.tm domain missing")

        username = _generate_human_like_username()
        email = f"{username}@{domain}"
        status, _, raw = self._request_json(
            "POST",
            "https://api.mail.tm/accounts",
            body={"address": email, "password": self.password},
        )
        if status == 429:
            raise RuntimeError("mail.tm rate limited (429)")
        if status != 201:
            raise RuntimeError(f"mail.tm create account failed ({status}): {raw}")

        self.email = email
        self._login()
        return email

    def generate_email(self, max_retries: int = 5) -> str:
        for retry in range(max_retries):
            if retry > 0:
                wait_s = 3 + retry * 3
                _log(f"mail.tm retry #{retry}, wait {wait_s}s")
                time.sleep(wait_s)
            try:
                return self._create_inbox_once()
            except Exception as exc:
                if "429" in str(exc) and retry + 1 < max_retries:
                    continue
                raise
        raise RuntimeError("mail.tm retries exhausted")

    def wait_for_verification_code(self, timeout_s: float, debug: bool = False) -> str:
        if not self.token:
            raise RuntimeError("mail.tm token missing")

        deadline = time.monotonic() + timeout_s
        seen_ids: set[str] = set()
        last_preview = ""
        while time.monotonic() < deadline:
            status, payload, _ = self._request_json(
                "GET",
                "https://api.mail.tm/messages",
                headers={"Authorization": f"Bearer {self.token}"},
            )
            if status != 200:
                time.sleep(3)
                continue

            members: List[Dict[str, Any]] = []
            if isinstance(payload, list):
                members = [item for item in payload if isinstance(item, dict)]
            elif isinstance(payload, dict):
                value = payload.get("hydra:member")
                if isinstance(value, list):
                    members = [item for item in value if isinstance(item, dict)]
                elif isinstance(payload.get("messages"), list):
                    members = [
                        item
                        for item in payload.get("messages", [])
                        if isinstance(item, dict)
                    ]

            if debug:
                subjects = []
                for msg in members[:5]:
                    subj = str(msg.get("subject") or "")
                    if subj:
                        subjects.append(subj[:80])
                _log(f"mail.tm inbox poll: messages={len(members)}, subjects={subjects}")

            for msg in members:
                if not isinstance(msg, dict):
                    continue
                msg_id = str(msg.get("id", "")).strip()
                if not msg_id:
                    continue
                if msg_id in seen_ids:
                    continue
                seen_ids.add(msg_id)
                status, detail, _ = self._request_json(
                    "GET",
                    f"https://api.mail.tm/messages/{msg_id}",
                    headers={"Authorization": f"Bearer {self.token}"},
                )
                if status != 200 or not isinstance(detail, dict):
                    continue

                subject = str(detail.get("subject") or "")
                text = str(detail.get("text") or "")
                html_list = detail.get("html")
                chunks: List[str] = [subject, text]
                if isinstance(html_list, list):
                    chunks.extend(str(html) for html in html_list)

                combined = "\n".join(chunks)
                code = _extract_verification_code(combined)
                if code:
                    return code
                if debug:
                    preview = re.sub(r"\s+", " ", combined).strip()
                    last_preview = preview[:360]
                    _log(f"mail.tm message {msg_id} parsed no code; preview={last_preview!r}")

            time.sleep(3)

        suffix = f"; last_preview={last_preview!r}" if last_preview else ""
        raise RuntimeError("mail.tm wait for verification code timeout" + suffix)


@dataclasses.dataclass
class RegisterResult:
    task_id: int = 0
    email: str = ""
    password: str = DEFAULT_PASSWORD
    cookie_file: str = ""
    cookie_count: int = 0
    success: bool = False
    error: str = ""


def _export_cookies_file(
    client: StreamableHttpMCPClient,
    tab_id: int,
    output_dir: str,
    url: str,
) -> tuple[str, int]:
    out = Path(output_dir).expanduser()
    if not out.is_absolute():
        out = Path.cwd() / out
    out.mkdir(parents=True, exist_ok=True)

    payload = client.call_tool_json(
        "chrome_export_cookies",
        {
            "tabId": tab_id,
            "url": url,
            "outputDir": str(out),
            "format": "json",
        },
    )

    cookie_count = 0
    try:
        cookie_count = int(payload.get("cookieCount") or 0) if isinstance(payload, dict) else 0
    except Exception:
        cookie_count = 0

    # Prefer explicit filePath when available.
    file_path = ""
    if isinstance(payload, dict):
        file_path = str(payload.get("filePath") or payload.get("path") or payload.get("filename") or "").strip()
    if file_path:
        candidate = Path(file_path)
        if not candidate.is_absolute():
            candidate = out / file_path
        if candidate.exists():
            return str(candidate), cookie_count

    export_path = _resolve_cookie_export_path(payload if isinstance(payload, dict) else {}, str(out))
    return str(export_path), cookie_count


def _wait_for_cookie_export(
    client: StreamableHttpMCPClient,
    tab_id: int,
    output_dir: str,
    url: str,
    timeout_s: float = 45.0,
) -> tuple[str, int]:
    deadline = time.monotonic() + timeout_s
    last_error = ""
    while time.monotonic() < deadline:
        try:
            path, count = _export_cookies_file(client, tab_id, output_dir=output_dir, url=url)
            if path:
                return path, count
        except Exception as exc:
            last_error = str(exc)
        time.sleep(2)
    raise RuntimeError(f"wait cookie export timeout: {last_error}")


def _close_tab(client: StreamableHttpMCPClient, tab_id: int) -> None:
    try:
        client.call_tool_json("chrome_close_tabs", {"tabIds": [tab_id]})
    except Exception:
        pass


def _perform_logout(client: StreamableHttpMCPClient, tab_id: int, retries: int = 2) -> bool:
    # Clear local browser state so the next login starts logged out.
    domains = ["createos.nodeops.network", "nodeops.network"]

    for attempt in range(retries + 1):
        attempt_no = attempt + 1
        try:
            _run_js(
                client,
                tab_id,
                """
return await (async () => {
  try {
    localStorage.clear();
    sessionStorage.clear();
  } catch (_) {}
  return true;
})();
""",
            )
        except Exception as exc:
            _log(f"tab={tab_id} local pre-clean failed (attempt#{attempt_no}): {exc}")

        for domain in domains:
            try:
                client.call_tool_json(
                    "chrome_clear_site_data",
                    {
                        "tabId": tab_id,
                        "domain": domain,
                        "includeSubdomains": True,
                        "cookies": True,
                        "localStorage": True,
                        "sessionStorage": True,
                        "indexedDB": True,
                        "cacheStorage": True,
                        "reload": domain == "createos.nodeops.network",
                    },
                )
            except Exception as exc:
                _log(
                    f"tab={tab_id} clear site data failed for {domain} "
                    f"(attempt#{attempt_no}): {exc}"
                )

        time.sleep(0.8)
        _log(f"tab={tab_id} local logout attempt#{attempt_no} finished")
        return True

    _log(f"tab={tab_id} local logout failed after {retries + 1} attempts")
    return False


def _register_once(task_id: int, args: argparse.Namespace, mcp_url: str) -> RegisterResult:
    result = RegisterResult(task_id=task_id, password=args.password)
    client: Optional[StreamableHttpMCPClient] = None
    tab_id = 0
    keep_page_untouched = False

    try:
        mailbox = MailTMInbox()
        email = mailbox.generate_email()
        result.email = email
        _log(f"task#{task_id} email generated: {email}")

        client = StreamableHttpMCPClient(mcp_url, timeout=args.mcp_timeout)
        client.initialize()

        nav = client.call_tool_json(
            "chrome_navigate",
            {
                "url": ORCHIDS_URL,
                "newWindow": int(args.workers) > 1,
                "background": bool(args.headless),
            },
        )
        tab_id = _extract_tab_id(nav)
        if tab_id <= 0:
            raise RuntimeError(f"task#{task_id} invalid tab id from chrome_navigate: {nav}")

        # Always start from a locally logged-out browser state before creating a new account.
        # This isolates parallel workers without invalidating previous accounts' server sessions.
        _log(f"task#{task_id} clearing local login state on tab={tab_id} before register")
        _perform_logout(client, tab_id)
        client.call_tool_json(
            "chrome_navigate",
            {
                "tabId": tab_id,
                "url": ORCHIDS_URL,
                "background": bool(args.headless),
            },
        )
        time.sleep(0.8)

        otp_ready = False
        max_flow_restarts = 3
        for flow_attempt in range(1, max_flow_restarts + 1):
            if flow_attempt > 1:
                _log(
                    f"task#{task_id} continue stayed disabled after submit, refresh and restart flow "
                    f"(attempt {flow_attempt}/{max_flow_restarts})"
                )
                client.call_tool_json(
                    "chrome_navigate",
                    {
                        "tabId": tab_id,
                        "url": ORCHIDS_URL,
                        "background": bool(args.headless),
                    },
                )
                time.sleep(0.8)

            _prepare_signup_form(
                client,
                tab_id,
                mcp_url,
                email,
                args.password,
                bool(args.headless),
                max_restarts=3,
                exit_on_continue_disabled=bool(args.exit_on_continue_disabled),
            )

            _click_continue(client, tab_id)

            wait_status, wait_state = _wait_for_otp_or_continue_stuck(
                client,
                tab_id,
                timeout_s=60,
                poll_s=0.5,
                continue_stuck_s=8.0,
            )
            if wait_status == "otp":
                otp_ready = True
                break
            if wait_status == "continue_stuck":
                _log(f"task#{task_id} continue still disabled after submit: {wait_state}")
                if _try_click_iamnotabot_for_continue(client, tab_id, mcp_url, wait_after_click_s=4.0):
                    _click_continue(client, tab_id)
                    wait_status2, wait_state2 = _wait_for_otp_or_continue_stuck(
                        client,
                        tab_id,
                        timeout_s=20,
                        poll_s=0.4,
                        continue_stuck_s=6.0,
                    )
                    if wait_status2 == "otp":
                        otp_ready = True
                        break
                    _log(
                        f"task#{task_id} continue remains blocked after iamnotabot click: "
                        f"{wait_status2}, state={wait_state2}"
                    )
                if args.exit_on_continue_disabled:
                    raise ContinueButtonDisabledAbort(
                        "continue button stayed disabled after submit, "
                        f"state={wait_state}"
                    )
                continue
            raise RuntimeError(f"otp page not reached ({wait_status}), state={wait_state}")

        if not otp_ready:
            raise RuntimeError("otp page not reached: continue button stayed disabled after refresh retries")

        code = mailbox.wait_for_verification_code(args.mail_timeout, debug=bool(getattr(args, "mail_debug", False)))
        _log(f"task#{task_id} code received: {code}")  # Log the actual code

        # OTP email can arrive before the input UI fully renders. Wait briefly so we don't
        # mis-diagnose a transient UI delay as a missing selector.
        if not _wait_for_condition(
            client,
            tab_id,
            f"return document.querySelectorAll({json.dumps(OTP_INPUT_SELECTOR)}).length >= 6;",
            timeout_s=20,
            poll_s=0.25,
        ):
            raise RuntimeError("otp input fields not visible after receiving code")

        _set_otp_code(client, tab_id, code)

        time.sleep(0.6)
        _click_continue(client, tab_id)

        # Best-effort: wait until OTP modal disappears (login finished).
        login_done = _wait_for_condition(
            client,
            tab_id,
            f"return document.querySelectorAll('{OTP_INPUT_SELECTOR}').length < 6;",
            timeout_s=30,
            poll_s=0.5,
        )
        if not login_done:
            _log(f"task#{task_id} OTP inputs still visible after verify; continue to export cookies anyway")

        cookie_file, cookie_count = _wait_for_cookie_export(
            client,
            tab_id,
            output_dir=str(getattr(args, "cookie_output_dir", "") or Path(__file__).parent),
            url=ORCHIDS_URL,
            timeout_s=45,
        )
        result.cookie_file = cookie_file
        result.cookie_count = int(cookie_count or 0)
        result.success = True
        _log(
            f"task#{task_id} register success: {email}, tab={tab_id}, cookies={cookie_count}, file={cookie_file}"
        )

        return result

    except ContinueButtonDisabledAbort as exc:
        keep_page_untouched = True
        _log(f"task#{task_id} abort on continue-disabled: {exc}")
        raise

    except Exception as exc:
        result.error = str(exc)
        result.success = False
        _log(f"task#{task_id} register failed: {exc}")
        return result

    finally:
        if client is not None and tab_id > 0:
            if keep_page_untouched:
                _log(
                    f"task#{task_id} skip cleanup to keep page untouched for manual check "
                    f"(tab={tab_id})"
                )
            elif not args.keep_login_state:
                _perform_logout(client, tab_id)
            else:
                _log(f"task#{task_id} keep login state enabled, skip logout cleanup")
            if args.close_tab and not keep_page_untouched:
                _close_tab(client, tab_id)


def _register_with_retries(task_id: int, args: argparse.Namespace, mcp_url: str) -> RegisterResult:
    retries = max(0, int(getattr(args, "task_retries", 0)))
    attempt = 0
    last: RegisterResult = RegisterResult(
        task_id=task_id,
        password=args.password,
        success=False,
        error="not started",
    )
    while attempt <= retries:
        attempt += 1
        if attempt > 1:
            backoff = min(5.0, 1.2 * attempt) + random.uniform(0.1, 0.5)
            _log(
                f"task#{task_id} retry attempt {attempt}/{retries + 1} on {mcp_url}, "
                f"waiting {backoff:.1f}s"
            )
            time.sleep(backoff)
        try:
            last = _register_once(task_id, args, mcp_url)
        except ContinueButtonDisabledAbort:
            raise
        if last.success:
            _log("TASK_RESULT_JSON: " + json.dumps(dataclasses.asdict(last), ensure_ascii=False))
            return last
    _log("TASK_RESULT_JSON: " + json.dumps(dataclasses.asdict(last), ensure_ascii=False))
    return last


def _export_current_cookie_and_session(args: argparse.Namespace) -> Dict[str, Any]:
    mcp_url = str(args.mcp_url or "").strip() or DEFAULT_MCP_URL
    client = StreamableHttpMCPClient(mcp_url, timeout=args.mcp_timeout)
    client.initialize()
    _verify_inspect_tools(client)

    windows_payload = client.call_tool_json("get_windows_and_tabs", {})
    tab = _active_tab_info(windows_payload)
    tab_id = int(tab.get("tab_id", 0))
    if tab_id <= 0:
        raise RuntimeError("active tab id is invalid")

    cookie_file = ""
    cookie_count = 0
    cookie_error = ""
    try:
        cookie_file, cookie_count = _export_cookies_file(
            client,
            tab_id,
            output_dir=str(getattr(args, "cookie_output_dir", "") or Path(__file__).parent),
            url=str(tab.get("url", "") or ORCHIDS_URL),
        )
    except Exception as exc:
        cookie_error = str(exc)

    payload: Dict[str, Any] = {
        "mode": "export_current_cookie",
        "mcp_url": mcp_url,
        "tab_id": tab_id,
        "tab_url": tab.get("url", ""),
        "tab_title": tab.get("title", ""),
        "active_tab": bool(tab.get("active")),
        "cookie_file": cookie_file,
        "cookie_count": int(cookie_count or 0),
        "cookie_export_ok": bool(cookie_file),
        "timestamp": dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    if cookie_error:
        payload["cookie_error"] = cookie_error

    out_path = str(getattr(args, "export_current_cookie_file", "") or "").strip()
    if out_path:
        target = Path(out_path).expanduser()
        if not target.is_absolute():
            target = Path.cwd() / target
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
        payload["output_file"] = str(target)

    return payload


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Batch login/register NodeOps accounts via chrome-mcp")
    parser.add_argument("--count", type=int, default=1)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--headless", action="store_true", help="map to background navigation")
    parser.add_argument("--password", default=DEFAULT_PASSWORD)
    parser.add_argument("--mcp-url", default=DEFAULT_MCP_URL)
    parser.add_argument("--mcp-url-secondary", default="", help="secondary MCP endpoint for parallel workers")
    parser.add_argument("--mcp-timeout", type=float, default=DEFAULT_MCP_TIMEOUT_S)
    parser.add_argument("--mail-timeout", type=float, default=DEFAULT_MAIL_TIMEOUT_S)
    parser.add_argument(
        "--mail-debug",
        action="store_true",
        help="log mail.tm inbox polling details (helps debug OTP delivery/parsing)",
    )
    parser.add_argument(
        "--cookie-output-dir",
        default=str(Path(__file__).parent),
        help="directory to store exported cookie JSON files",
    )
    parser.add_argument(
        "--task-retries",
        type=int,
        default=1,
        help="retry failed registration task N times (default: 1)",
    )
    parser.add_argument("--close-tab", action="store_true", help="close tabs after registration (default: keep open)")
    parser.add_argument(
        "--keep-login-state",
        action="store_true",
        help="do not clear nodeops login state after each task",
    )
    parser.add_argument(
        "--exit-on-continue-disabled",
        action="store_true",
        help="abort immediately when Continue stays disabled and keep page/tab untouched",
    )
    parser.add_argument(
        "--export-current-cookie",
        action="store_true",
        help="export active tab cookies to JSON",
    )
    parser.add_argument(
        "--export-current-cookie-file",
        default="",
        help="optional JSON output path used with --export-current-cookie",
    )
    return parser.parse_args()


def _build_mcp_url_pool(args: argparse.Namespace, workers: int) -> List[str]:
    primary = str(args.mcp_url or "").strip()
    secondary = str(args.mcp_url_secondary or "").strip()
    if not primary:
        primary = DEFAULT_MCP_URL

    if workers <= 1:
        return [primary]

    if not secondary:
        raise RuntimeError("workers >= 2 requires --mcp-url-secondary")

    urls = [primary, secondary]
    # For workers >2, rotate between the provided MCP endpoints.
    return [urls[idx % len(urls)] for idx in range(workers)]


def _run_batch(args: argparse.Namespace) -> Dict[str, Any]:
    count = max(1, int(args.count))
    workers = max(1, min(int(args.workers), count))
    mcp_pool = _build_mcp_url_pool(args, workers)

    for mcp_url in sorted(set(mcp_pool)):
        probe = StreamableHttpMCPClient(mcp_url, timeout=args.mcp_timeout)
        probe.initialize()
        _verify_chrome_mcp_tools(probe, require_clear_site_data=True)

    start = time.time()
    results: List[RegisterResult] = [RegisterResult(password=args.password) for _ in range(count)]

    if workers == 1:
        for idx in range(count):
            results[idx] = _register_with_retries(idx + 1, args, mcp_pool[0])
    else:
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
            future_map = {
                executor.submit(
                    _register_with_retries,
                    idx + 1,
                    args,
                    mcp_pool[idx % len(mcp_pool)],
                ): idx
                for idx in range(count)
            }
            for future in concurrent.futures.as_completed(future_map):
                idx = future_map[future]
                try:
                    results[idx] = future.result()
                except ContinueButtonDisabledAbort as exc:
                    for pending in future_map:
                        if pending is not future:
                            pending.cancel()
                    raise ContinueButtonDisabledAbort(
                        f"task#{idx + 1} aborted: {exc}"
                    ) from exc
                except Exception as exc:
                    results[idx] = RegisterResult(
                        password=args.password,
                        success=False,
                        error=f"worker crash: {exc}",
                    )

    success = sum(1 for item in results if item.success)
    failed = count - success

    end = time.time()
    payload = {
        "total": count,
        "success": success,
        "failed": failed,
        "results": [dataclasses.asdict(item) for item in results],
        "start_time": dt.datetime.fromtimestamp(start, tz=dt.timezone.utc).isoformat().replace("+00:00", "Z"),
        "end_time": dt.datetime.fromtimestamp(end, tz=dt.timezone.utc).isoformat().replace("+00:00", "Z"),
        "duration": f"{end - start:.3f}s",
    }
    return payload


def main() -> int:
    random.seed()
    args = _parse_args()
    try:
        if args.export_current_cookie:
            payload = _export_current_cookie_and_session(args)
        else:
            payload = _run_batch(args)
    except ContinueButtonDisabledAbort as exc:
        _log(f"batch aborted on continue-disabled: {exc}")
        return 3
    except Exception as exc:
        _log(f"batch failed: {exc}")
        return 2

    print(json.dumps(payload, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
