"""Tests for the Page module, driven entirely through its interface and an injected socket adapter."""

import json
import socket
import struct
import unittest
from unittest.mock import patch

import page


STATE = {
    "spans": ["What is the capital of France?", "Paris", "Rome"],
    "q": "What is the capital of France?",
    "inQuiz": True,
    "body": "Question body",
}


def server_frame(payload, opcode=1, fin=True):
    first = (0x80 if fin else 0) | opcode
    size = len(payload)
    if size < 126:
        header = bytes([first, size])
    elif size < 65536:
        header = bytes([first, 126]) + struct.pack("!H", size)
    else:
        header = bytes([first, 127]) + struct.pack("!Q", size)
    return header + payload


def client_payload(frame):
    second = frame[1]
    size = second & 0x7F
    offset = 2
    if size == 126:
        size = struct.unpack("!H", frame[2:4])[0]
        offset = 4
    elif size == 127:
        size = struct.unpack("!Q", frame[2:10])[0]
        offset = 10
    mask = None
    if second & 0x80:
        mask = frame[offset : offset + 4]
        offset += 4
    body = frame[offset : offset + size]
    if mask:
        body = bytes(byte ^ mask[i % 4] for i, byte in enumerate(body))
    return body


class FakeSocket:
    def __init__(self, responder, preamble=b"", handshake=False):
        self.responder = responder
        self.incoming = bytearray(preamble)
        self.handshake = handshake
        self.sent = []
        self.closed = False

    def sendall(self, data):
        if self.handshake:
            self.handshake = False
            self.request = data
            self.incoming = bytearray(b"HTTP/1.1 101 Switching Protocols\r\n\r\n") + self.incoming
            return
        message = json.loads(client_payload(data))
        self.sent.append(message)
        reply = self.responder(message)
        if reply is not None:
            self.incoming.extend(server_frame(json.dumps(reply).encode("utf-8")))

    def recv(self, size):
        if not self.incoming:
            raise socket.timeout()
        chunk = bytes(self.incoming[:size])
        del self.incoming[:size]
        return chunk

    def settimeout(self, seconds):
        pass

    def close(self):
        self.closed = True


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def read(self):
        return self.payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def state_reply(message):
    return {
        "id": message["id"],
        "result": {"result": {"type": "object", "value": STATE}},
    }


def make_page(responder, preamble=b""):
    raw = FakeSocket(responder, preamble=preamble)
    return page.Page._from_socket(page._SocketAdapter(raw)), raw


class PageTest(unittest.TestCase):
    def test_handshake_preserves_frame_arriving_with_headers(self):
        reply = state_reply({"id": 1001})
        preamble = server_frame(json.dumps(reply).encode("utf-8"))
        raw = FakeSocket(state_reply, preamble=preamble, handshake=True)
        targets = [
            {
                "url": "https://gimkit.com/join/ABC",
                "type": "page",
                "webSocketDebuggerUrl": "ws://127.0.0.1:9222/devtools/page/1",
            }
        ]
        with patch("page.urllib.request.urlopen", return_value=FakeResponse(json.dumps(targets).encode())), patch(
            "page.socket.create_connection", return_value=raw
        ):
            subject = page.Page.connect()
        self.assertEqual(subject.read_state(), STATE)
        self.assertIn(b"Upgrade: websocket", raw.request)

    def test_fragmented_response_is_reassembled(self):
        reply = json.dumps(state_reply({"id": 1001})).encode("utf-8")
        first, second = reply[:20], reply[20:]
        preamble = server_frame(first, opcode=1, fin=False) + server_frame(second, opcode=0, fin=True)
        subject, _ = make_page(state_reply, preamble=preamble)
        self.assertEqual(subject.read_state(), STATE)

    def test_cdp_error_is_reported_instead_of_returned_as_result(self):
        def responder(message):
            return {"id": message["id"], "error": {"code": -32000, "message": "boom"}}

        subject, _ = make_page(responder)
        state = subject.read_state()
        self.assertEqual(state["body"], "")
        self.assertIn("boom", state["error"])

    def test_click_option_uses_one_mouse_sequence(self):
        def responder(message):
            if message["method"] == "Input.dispatchMouseEvent":
                return {"id": message["id"], "result": {}}
            expression = message["params"]["expression"]
            if "getBoundingClientRect" in expression:
                value = True
            elif "__ox" in expression:
                value = 120
            elif "__oy" in expression:
                value = 240
            else:
                value = None
            return {"id": message["id"], "result": {"result": {"value": value}}}

        subject, raw = make_page(responder)
        self.assertTrue(subject.click_option("Paris"))
        dispatches = [m for m in raw.sent if m["method"] == "Input.dispatchMouseEvent"]
        self.assertEqual([m["params"]["type"] for m in dispatches], ["mousePressed", "mouseReleased"])
        self.assertEqual({m["params"]["x"] for m in dispatches}, {120})
        self.assertEqual({m["params"]["y"] for m in dispatches}, {240})

    def test_click_text_containing_uses_dom_click(self):
        def responder(message):
            expression = message["params"]["expression"]
            value = ".includes(" in expression and "Answer Questions" in expression
            return {"id": message["id"], "result": {"result": {"value": value}}}

        subject, raw = make_page(responder)
        self.assertTrue(subject.click_text_containing("Answer Questions"))
        self.assertEqual(len(raw.sent), 1)
        self.assertNotIn("Input.dispatchMouseEvent", raw.sent[0]["method"])

    def test_viewport_falls_back_when_no_canvas(self):
        def responder(message):
            return {"id": message["id"], "result": {"result": {"value": None}}}

        subject, _ = make_page(responder)
        self.assertEqual(subject.viewport(), (944, 1546))

    def test_connect_rejects_target_list_without_matching_page(self):
        targets = [{"url": "https://example.com", "type": "page"}]
        with patch("page.urllib.request.urlopen", return_value=FakeResponse(json.dumps(targets).encode())):
            with self.assertRaises(page.PageError):
                page.Page.connect()


if __name__ == "__main__":
    unittest.main()
