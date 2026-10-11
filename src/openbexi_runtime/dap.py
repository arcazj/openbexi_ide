"""Bounded standard DAP framing. Debugging itself is supplied by debugpy."""
import json


class ProtocolError(ValueError):
    pass


def encode_message(message: dict) -> bytes:
    body = json.dumps(message, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return f"Content-Length: {len(body)}\r\n\r\n".encode("ascii") + body


class MessageReader:
    def __init__(self, max_message=8_000_000):
        self.buffer = bytearray()
        self.length = None
        self.max_message = max_message

    def feed(self, data: bytes) -> list[dict]:
        self.buffer.extend(data)
        messages = []
        while True:
            if self.length is None:
                end = self.buffer.find(b"\r\n\r\n")
                if end == -1:
                    if len(self.buffer) > 16_384:
                        raise ProtocolError("DAP header exceeds its size limit")
                    break
                if end > 16_384:
                    raise ProtocolError("DAP header exceeds its size limit")
                try:
                    headers = self.buffer[:end].decode("ascii").split("\r\n")
                    sizes = [line.split(":", 1)[1].strip() for line in headers
                             if line.split(":", 1)[0].lower() == "content-length"]
                    if len(sizes) != 1:
                        raise ValueError("Missing or duplicate Content-Length")
                    self.length = int(sizes[0])
                except (ValueError, UnicodeError, IndexError) as exc:
                    raise ProtocolError("Invalid DAP Content-Length header") from exc
                if not 0 < self.length <= self.max_message:
                    raise ProtocolError("DAP message exceeds its size limit")
                del self.buffer[:end + 4]
            if len(self.buffer) < self.length:
                break
            payload = self.buffer[:self.length]
            del self.buffer[:self.length]
            self.length = None
            try:
                message = json.loads(payload)
            except (ValueError, UnicodeError) as exc:
                raise ProtocolError("Invalid DAP JSON message") from exc
            if not isinstance(message, dict) or message.get("type") not in {"request", "response", "event"}:
                raise ProtocolError("Invalid DAP message envelope")
            messages.append(message)
        return messages
