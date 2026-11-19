"""Deep module for observing and interacting with the Gimkit page over CDP.

Callers cross one interface: read_state, click_option, click_text,
click_text_containing, click_xy and viewport. Everything about target discovery,
the WebSocket handshake, frame decoding and mouse dispatch stays private here.
"""

import base64
import json
import os
import socket
import struct
import time
import urllib.request
from urllib.parse import urlparse

DEFAULT_ENDPOINT = "http://127.0.0.1:9222/json/list"
DEFAULT_URL_MARKER = "gimkit.com/join"

READ_JS = (
    "(function(){"
    "var spans=[...document.querySelectorAll('span.notranslate')].map(e=>e.textContent.trim()).filter(Boolean);"
    "var q=spans.find(t=>t.length>20);"
    "var hasAns=document.body.innerText.indexOf('Answer Questions')>=0;"
    "return {spans:spans,q:q||null,inQuiz:!hasAns,body:document.body.innerText.slice(-600)};"
    "})()"
)

VIEWPORT_JS = (
    "(function(){var c=document.querySelector('canvas');"
    "if(!c) return null;var b=c.getBoundingClientRect();"
    "return {w:b.width,h:b.height};})()"
)

EMPTY_STATE = {"spans": [], "q": None, "inQuiz": True, "body": ""}


class PageError(Exception):
    """The page cannot be reached or a CDP call failed."""


class _SocketAdapter:
    """Private adapter: WebSocket frames over a raw socket."""

    def __init__(self, raw, initial=b""):
        self._raw = raw
        self._buffer = bytearray(initial)
        self._fragment = None
        self._fragment_opcode = None

    def settimeout(self, seconds):
        self._raw.settimeout(seconds)

    def send_frame(self, payload, opcode=1):
        mask = os.urandom(4)
        size = len(payload)
        if size < 126:
            header = bytes([0x80 | opcode, 0x80 | size])
        elif size < 65536:
            header = bytes([0x80 | opcode, 0xFE]) + struct.pack("!H", size)
        else:
            header = bytes([0x80 | opcode, 0xFF]) + struct.pack("!Q", size)
        masked = bytes(byte ^ mask[i % 4] for i, byte in enumerate(payload))
        self._raw.sendall(header + mask + masked)

    def _read_exact(self, size):
        while len(self._buffer) < size:
            chunk = self._raw.recv(max(4096, size - len(self._buffer)))
            if not chunk:
                raise PageError("socket closed by peer")
            self._buffer.extend(chunk)
        data = bytes(self._buffer[:size])
        del self._buffer[:size]
        return data

    def recv_frame(self):
        """Return (opcode, payload) for one complete message, reassembling fragments."""
        while True:
            first, second = self._read_exact(2)
            fin = bool(first & 0x80)
            opcode = first & 0x0F
            masked = bool(second & 0x80)
            length = second & 0x7F
            if length == 126:
                length = struct.unpack("!H", self._read_exact(2))[0]
            elif length == 127:
                length = struct.unpack("!Q", self._read_exact(8))[0]
            mask = self._read_exact(4) if masked else None
            payload = self._read_exact(length) if length else b""
            if mask:
                payload = bytes(byte ^ mask[i % 4] for i, byte in enumerate(payload))

            if opcode == 8:
                raise PageError("socket closed by peer")
            if opcode == 9:
                self.send_frame(payload, opcode=10)
                continue
            if opcode == 10:
                continue
            if opcode == 0:
                if self._fragment is None:
                    continue
                self._fragment += payload
                if not fin:
                    continue
                payload, opcode = self._fragment, self._fragment_opcode
                self._fragment = None
                self._fragment_opcode = None
                return opcode, payload
            if opcode in (1, 2):
                if not fin:
                    self._fragment = payload
                    self._fragment_opcode = opcode
                    continue
                return opcode, payload

    def close(self):
        self._raw.close()


class Page:
    """One seam between the quiz loop and the browser page."""

    def __init__(self, adapter):
        self._adapter = adapter
        self._next_id = 1001

    @classmethod
    def _from_socket(cls, adapter):
        """Internal seam used by connect() and by tests."""
        return cls(adapter)

    @classmethod
    def connect(cls, endpoint=DEFAULT_ENDPOINT, url_marker=DEFAULT_URL_MARKER, timeout=10):
        with urllib.request.urlopen(endpoint, timeout=timeout) as response:
            targets = json.load(response)
        target = next(
            (
                item
                for item in targets
                if url_marker in item.get("url", "") and item.get("type") == "page"
            ),
            None,
        )
        if target is None:
            raise PageError("no page target matches %r" % url_marker)
        address = target.get("webSocketDebuggerUrl", "")
        parsed = urlparse(address)
        if parsed.scheme != "ws" or not parsed.hostname:
            raise PageError("unsupported debugger URL: %r" % address)
        port = parsed.port or 80
        raw = socket.create_connection((parsed.hostname, port), timeout=timeout)
        try:
            key = base64.b64encode(os.urandom(16)).decode("ascii")
            request = (
                "GET %s HTTP/1.1\r\n"
                "Host: %s:%d\r\n"
                "Upgrade: websocket\r\n"
                "Connection: Upgrade\r\n"
                "Sec-WebSocket-Key: %s\r\n"
                "Sec-WebSocket-Version: 13\r\n\r\n" % (parsed.path, parsed.hostname, port, key)
            )
            raw.sendall(request.encode("ascii"))
            data = b""
            while b"\r\n\r\n" not in data:
                chunk = raw.recv(4096)
                if not chunk:
                    raise PageError("handshake closed before headers")
                data += chunk
            headers, trailing = data.split(b"\r\n\r\n", 1)
            status = headers.split(b"\r\n", 1)[0]
            if b" 101 " not in status + b" ":
                raise PageError("handshake failed: %s" % status.decode("latin-1", "replace"))
            return cls._from_socket(_SocketAdapter(raw, trailing))
        except Exception:
            raw.close()
            raise

    def close(self):
        self._adapter.close()

    def _call(self, method, params=None, timeout=10):
        message_id = self._next_id
        self._next_id += 1
        payload = json.dumps(
            {"id": message_id, "method": method, "params": params or {}}
        ).encode("utf-8")
        self._adapter.send_frame(payload)
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise PageError("CDP timeout for %s" % method)
            self._adapter.settimeout(remaining)
            try:
                frame = self._adapter.recv_frame()
            except socket.timeout:
                continue
            if frame is None or frame[0] != 1:
                continue
            try:
                message = json.loads(frame[1])
            except (ValueError, UnicodeDecodeError):
                continue
            if message.get("id") != message_id:
                continue
            if "error" in message:
                error = message["error"]
                text = error.get("message", str(error)) if isinstance(error, dict) else str(error)
                raise PageError("CDP error in %s: %s" % (method, text))
            return message.get("result")

    def _eval(self, expression):
        result = self._call(
            "Runtime.evaluate",
            {"expression": expression, "returnByValue": True, "awaitPromise": True},
        )
        if not isinstance(result, dict):
            return None
        inner = result.get("result", result)
        if isinstance(inner, dict) and "value" in inner:
            return inner["value"]
        return None

    def read_state(self):
        """Return the current question, options and recent page text."""
        try:
            state = self._eval(READ_JS)
        except PageError as error:
            return dict(EMPTY_STATE, error=str(error))
        if not isinstance(state, dict):
            return dict(EMPTY_STATE)
        return state

    def _click_center(self, locate_js, x_name, y_name):
        try:
            if not self._eval(locate_js):
                return False
            x = self._eval("window.%s" % x_name)
            y = self._eval("window.%s" % y_name)
            if not isinstance(x, (int, float)) or not isinstance(y, (int, float)):
                return False
            return self.click_xy(x, y)
        except PageError:
            return False

    def click_option(self, text):
        js = (
            "(function(){var sp=[...document.querySelectorAll('span.notranslate')]"
            ".find(e=>e.textContent.trim()===%s);"
            "if(!sp) return false;var r=sp.getBoundingClientRect();"
            "window.__ox=r.left+r.width/2;window.__oy=r.top+r.height/2;return true;})()"
            % json.dumps(text)
        )
        return self._click_center(js, "__ox", "__oy")

    def click_text(self, text):
        js = (
            "(function(){var els=[...document.querySelectorAll('*')]"
            ".filter(e=>e.children.length===0 && (e.textContent||'').trim()===%s);"
            "if(!els.length) return false;var r=els[0].getBoundingClientRect();"
            "window.__tx=r.left+r.width/2;window.__ty=r.top+r.height/2;return true;})()"
            % json.dumps(text)
        )
        return self._click_center(js, "__tx", "__ty")

    def click_text_containing(self, fragment):
        js = (
            "(function(){var e=[...document.querySelectorAll('button,[role=button]')]"
            ".find(x=>(x.textContent||'').includes(%s));"
            "if(!e) return false;e.click();return true;})()" % json.dumps(fragment)
        )
        try:
            return self._eval(js) is True
        except PageError:
            return False

    def click_xy(self, x, y):
        try:
            for event_type in ("mousePressed", "mouseReleased"):
                self._call(
                    "Input.dispatchMouseEvent",
                    {"type": event_type, "x": x, "y": y, "button": "left", "clickCount": 1},
                )
            return True
        except PageError:
            return False

    def viewport(self):
        try:
            size = self._eval(VIEWPORT_JS)
        except PageError:
            return (944, 1546)
        if not isinstance(size, dict):
            return (944, 1546)
        return (size.get("w", 944), size.get("h", 1546))


if __name__ == "__main__":
    page = Page.connect()
    try:
        print("QUESTION_STATE", json.dumps(page.read_state(), ensure_ascii=False))
    finally:
        page.close()
