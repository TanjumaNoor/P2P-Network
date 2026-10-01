"""
protocol.py - Application-level protocol (message encoding / decoding)

TCP is a byte stream: it does NOT keep message boundaries. So we use
"message framing". Every message is sent as:

    [4-byte length][JSON payload]

The receiver reads the 4-byte length first, then reads EXACTLY that many
bytes. For files, a JSON "file" message (metadata) is sent first, followed
by the raw file bytes (exactly `filesize` bytes).

Message types:
    hello      - first message from the peer that connects
    hello_ack  - reply from the peer that was connected to
    text       - a chat message
    file       - file metadata (raw bytes follow immediately after)
"""

import json
import struct

HEADER_SIZE = 4                  # 4 bytes hold the length of the JSON message
MAX_MESSAGE_SIZE = 1024 * 1024   # refuse JSON messages bigger than 1 MB
CHUNK_SIZE = 64 * 1024           # files are sent/received 64 KB at a time


# ---------------------------------------------------------------- framing
def recv_exact(sock, size):
    """Read EXACTLY `size` bytes. One recv() may return fewer, so we loop."""
    data = bytearray()
    while len(data) < size:
        chunk = sock.recv(size - len(data))
        if not chunk:                       # empty = other side closed
            raise ConnectionError("Peer closed the connection")
        data.extend(chunk)
    return bytes(data)


def send_message(sock, message):
    """Turn a dict into JSON and send it as [length][json]."""
    payload = json.dumps(message).encode("utf-8")
    header = struct.pack("!I", len(payload))   # "!I" = 4-byte big-endian int
    sock.sendall(header + payload)


def recv_message(sock):
    """Receive one framed JSON message and return it as a dict."""
    header = recv_exact(sock, HEADER_SIZE)
    (length,) = struct.unpack("!I", header)
    if length == 0 or length > MAX_MESSAGE_SIZE:
        raise ValueError(f"Invalid message length: {length}")
    payload = recv_exact(sock, length)
    return json.loads(payload.decode("utf-8"))


# ------------------------------------------------------- message builders
def make_hello(peer_id, peer_name, port):
    return {"type": "hello", "peer_id": peer_id,
            "peer_name": peer_name, "port": port}


def make_hello_ack(peer_id, peer_name, port):
    return {"type": "hello_ack", "peer_id": peer_id,
            "peer_name": peer_name, "port": port}


def make_text(sender_id, sender_name, message):
    return {"type": "text", "sender_id": sender_id,
            "sender_name": sender_name, "message": message}


def make_file(sender_id, sender_name, filename, filesize):
    return {"type": "file", "sender_id": sender_id,
            "sender_name": sender_name,
            "filename": filename, "filesize": filesize}
