# P2P Network – Chat & File Sharing (CSE 433)

A beginner-level peer-to-peer application written in Python using TCP sockets.
Several peers connect **directly** to each other (no central server) and
exchange text messages and files (text, images, audio, video, PDF, ZIP, ...).

## How it works
Every peer plays two roles at the same time:

| Role | What it does | Python calls |
|------|--------------|--------------|
| **Server** | Listens on its own TCP port and accepts incoming connections from other peers | `socket()`, `bind()`, `listen()`, `accept()` |
| **Client** | Connects directly to a remote peer using its IP address and port | `socket()`, `connect()` |

Each connection is handled in its own **thread**, so one peer can talk to many peers at once.

**Protocol** (`protocol.py`): every message is `[4-byte length][JSON]`.
1. Connecting peer sends `hello`; the other replies `hello_ack` (handshake – exchanges name, ID, listening port).
2. `text` messages carry the chat text.
3. `file` messages carry metadata (`filename`, `filesize`), followed by exactly `filesize` raw bytes sent in 64 KB chunks. The receiver reads exactly that many bytes, so it knows when the file is complete.

## Files
```
main.py          Tkinter GUI
p2p_node.py      Server + client roles, threads, text and file transfer
protocol.py      Message framing and message builders
test_local.py    Optional automatic test (no GUI)
downloads/       Received files are saved here
```

## Requirements
- Python 3.9+ (Tkinter is included with the Windows/macOS installers; on Ubuntu: `sudo apt install python3-tk`)
- No third-party packages

## Run
```
python main.py
```

## Connect two peers (same computer)
1. Start the app twice (two terminals).
2. Peer 1: Name `Tanju`, Port `5000` → **Start Peer**.
3. Peer 2: Name `Priyo`, Port `5001` → **Start Peer**.
4. In Priyo's window: IP `127.0.0.1`, Port `5000` → **Connect**.
5. Both windows now show the other peer in **Connected Peers**.

## Connect over Wi-Fi/LAN
Find the other computer's IP (`ipconfig` on Windows, `ip a` / `ifconfig` on Linux/macOS), e.g. `192.168.1.10`, and connect to `192.168.1.10:5000`.
If it fails, allow Python through the firewall for that port.

## Send a message
Select a peer in the list → type text → **Send** (or press Enter).

## Transfer a file
Select a peer in the list → **Choose File & Send** → pick any file.
The receiver finds it in the `downloads/` folder (existing files are never overwritten: `photo (1).jpg`).

## Multiple peers
Start a third peer (`Noor`, port `5002`) and connect it to Tanju and/or Priyo. Select any peer in the list to talk to that specific peer.

## Error handling
Invalid IP/port, connection refused, unreachable peer, missing file, sending with no peer selected, and peers disconnecting (even mid-transfer) all show a message instead of crashing.

## Automatic test
`python test_local.py` starts 3 peers, transfers a 5 MB binary file and checks it is identical.

## Screenshots
Add your screenshots here (Peer 1, Peer 2, Peer 3 windows).
