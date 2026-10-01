"""
p2p_node.py - The peer-to-peer networking layer

Every peer = TCP SERVER + TCP CLIENT

  SERVER ROLE: listens on a dedicated TCP port and accepts incoming
               connections from other peers  (socket, bind, listen, accept)
  CLIENT ROLE: connects directly to a remote peer using its IP address
               and port number                (socket, connect)

Each connection (no matter which side started it) gets its own thread,
so one peer can talk to many peers at the same time.
"""

import os
import socket
import threading
import uuid

import protocol


class Peer:
    """Information about ONE connected remote peer."""

    def __init__(self, sock, peer_id, name, ip, listen_port):
        self.sock = sock
        self.peer_id = peer_id
        self.name = name
        self.ip = ip
        self.listen_port = listen_port
        # Stops two threads writing to the same socket at once
        # (e.g. a text message in the middle of a file transfer).
        self.send_lock = threading.Lock()

    def label(self):
        return f"{self.name} [{self.peer_id}] {self.ip}:{self.listen_port}"


class P2PNode:
    def __init__(self, name, port, on_event, on_peers_changed,
                 download_dir="downloads"):
        self.name = name
        self.port = port
        self.peer_id = uuid.uuid4().hex[:8]       # e.g. "a83f21c4"
        self.download_dir = download_dir
        self.on_event = on_event                  # callback(text)
        self.on_peers_changed = on_peers_changed  # callback()

        self.server_socket = None
        self.running = False
        self.peers = {}                           # peer_id -> Peer
        self.peers_lock = threading.Lock()

        os.makedirs(self.download_dir, exist_ok=True)

    # =============================================================
    #                       SERVER ROLE
    # =============================================================
    def start(self):
        """Create the server socket and start accepting connections."""
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        # Lets us restart quickly on the same port after stopping.
        self.server_socket.setsockopt(socket.SOL_SOCKET,
                                      socket.SO_REUSEADDR, 1)
        try:
            # "0.0.0.0" = listen on all network interfaces (LAN + localhost)
            self.server_socket.bind(("0.0.0.0", self.port))
        except OSError:
            self.server_socket.close()
            raise
        self.server_socket.listen()
        self.running = True
        threading.Thread(target=self._accept_loop, daemon=True).start()
        self.on_event(f"[SYSTEM] Peer started: {self.name} "
                      f"[{self.peer_id}] listening on port {self.port}")

    def _accept_loop(self):
        """Keep accepting new connections; each gets its own thread."""
        while self.running:
            try:
                conn, addr = self.server_socket.accept()
            except OSError:
                break                      # server socket was closed (Stop)
            threading.Thread(target=self._handle_incoming,
                             args=(conn, addr), daemon=True).start()

    def _handle_incoming(self, conn, addr):
        """Someone connected to us: do the HELLO handshake (server side)."""
        try:
            conn.settimeout(10)            # don't wait forever for a HELLO
            hello = protocol.recv_message(conn)
            if hello.get("type") != "hello":
                raise ValueError("First message was not 'hello'")

            if hello["peer_id"] == self.peer_id or self._is_connected(hello["peer_id"]):
                conn.close()               # connecting to self / duplicate
                return

            protocol.send_message(conn, protocol.make_hello_ack(
                self.peer_id, self.name, self.port))
            conn.settimeout(None)          # normal blocking mode from now on

            peer = Peer(conn, hello["peer_id"], hello["peer_name"],
                        addr[0], hello["port"])
            self._register(peer)
            self._receive_loop(peer)
        except Exception as e:
            self.on_event(f"[ERROR] Incoming connection from "
                          f"{addr[0]} failed: {e}")
            try:
                conn.close()
            except OSError:
                pass

    # =============================================================
    #                       CLIENT ROLE
    # =============================================================
    def connect_to(self, ip, port):
        """Connect directly to another peer using its IP address and port."""
        # --- validate the input ---
        try:
            socket.inet_aton(ip)
        except OSError:
            raise ValueError("Invalid IP address")
        if not (1 <= port <= 65535):
            raise ValueError("Port must be between 1 and 65535")

        # --- client socket + connect() ---
        conn = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        conn.settimeout(5)
        try:
            conn.connect((ip, port))

            # HELLO handshake (client side): we speak first.
            protocol.send_message(conn, protocol.make_hello(
                self.peer_id, self.name, self.port))
            ack = protocol.recv_message(conn)
            if ack.get("type") != "hello_ack":
                raise ValueError("Peer did not reply with 'hello_ack'")
            conn.settimeout(None)
        except Exception:
            conn.close()
            raise

        if ack["peer_id"] == self.peer_id:
            conn.close()
            raise ValueError("You cannot connect to yourself")
        if self._is_connected(ack["peer_id"]):
            conn.close()
            raise ValueError(f"Already connected to {ack['peer_name']}")

        peer = Peer(conn, ack["peer_id"], ack["peer_name"], ip, ack["port"])
        self._register(peer)
        threading.Thread(target=self._receive_loop, args=(peer,),
                         daemon=True).start()
        return peer

    # =============================================================
    #              RECEIVING (same for both roles)
    # =============================================================
    def _receive_loop(self, peer):
        """Read messages from one peer until it disconnects."""
        try:
            while self.running:
                msg = protocol.recv_message(peer.sock)
                kind = msg.get("type")
                if kind == "text":
                    self.on_event(f"{peer.name} -> You: {msg['message']}")
                elif kind == "file":
                    self._receive_file(peer, msg)
                # unknown types are ignored
        except (ConnectionError, OSError, ValueError) as e:
            if self.running and peer.peer_id in self.peers:
                self.on_event(f"[SYSTEM] {peer.name} disconnected ({e})")
        finally:
            self._remove(peer)

    def _receive_file(self, peer, meta):
        """Read exactly `filesize` bytes and save them to downloads/."""
        filename = os.path.basename(str(meta.get("filename", "")))  # safety
        filesize = meta.get("filesize")
        if not filename or not isinstance(filesize, int) or filesize < 0:
            raise ValueError("Invalid file metadata")

        path = self._unique_path(filename)
        self.on_event(f"[SYSTEM] Receiving {filename} "
                      f"({filesize} bytes) from {peer.name}...")
        remaining = filesize
        try:
            with open(path, "wb") as f:
                while remaining > 0:
                    chunk = peer.sock.recv(min(protocol.CHUNK_SIZE, remaining))
                    if not chunk:
                        raise ConnectionError("Disconnected during file transfer")
                    f.write(chunk)
                    remaining -= len(chunk)
        except Exception:
            if os.path.exists(path):
                os.remove(path)            # delete the incomplete file
            raise
        self.on_event(f"{peer.name} -> You: File received: "
                      f"{os.path.basename(path)}  (saved in {self.download_dir}/)")

    def _unique_path(self, filename):
        """Don't overwrite: photo.jpg -> photo (1).jpg if it already exists."""
        base, ext = os.path.splitext(filename)
        path = os.path.join(self.download_dir, filename)
        n = 1
        while os.path.exists(path):
            path = os.path.join(self.download_dir, f"{base} ({n}){ext}")
            n += 1
        return path

    # =============================================================
    #                         SENDING
    # =============================================================
    def send_text(self, peer_id, text):
        peer = self._get_peer(peer_id)
        try:
            with peer.send_lock:
                protocol.send_message(peer.sock, protocol.make_text(
                    self.peer_id, self.name, text))
        except OSError as e:
            self._remove(peer)
            raise ConnectionError(f"Could not send to {peer.name}: {e}")
        self.on_event(f"You -> {peer.name}: {text}")

    def send_file(self, peer_id, filepath):
        peer = self._get_peer(peer_id)
        if not os.path.isfile(filepath):
            raise FileNotFoundError(f"File does not exist: {filepath}")
        filesize = os.path.getsize(filepath)
        filename = os.path.basename(filepath)

        self.on_event(f"[SYSTEM] Sending {filename} ({filesize} bytes) "
                      f"to {peer.name}...")
        try:
            with peer.send_lock:
                # Stage 1: metadata (JSON)
                protocol.send_message(peer.sock, protocol.make_file(
                    self.peer_id, self.name, filename, filesize))
                # Stage 2: raw bytes, in 64 KB chunks (never the whole file)
                with open(filepath, "rb") as f:
                    while True:
                        chunk = f.read(protocol.CHUNK_SIZE)
                        if not chunk:
                            break
                        peer.sock.sendall(chunk)
        except OSError as e:
            self._remove(peer)
            raise ConnectionError(f"File transfer to {peer.name} failed: {e}")
        self.on_event(f"You -> {peer.name}: File sent: {filename}")

    # =============================================================
    #                    PEER LIST / CLEANUP
    # =============================================================
    def _register(self, peer):
        with self.peers_lock:
            self.peers[peer.peer_id] = peer
        self.on_event(f"[SYSTEM] Connected to {peer.name} "
                      f"({peer.ip}:{peer.listen_port})")
        self.on_peers_changed()

    def _remove(self, peer):
        with self.peers_lock:
            removed = self.peers.pop(peer.peer_id, None)
        try:
            # shutdown() wakes up any thread blocked in recv() and tells the
            # other side we are gone; close() alone may not do that.
            peer.sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        try:
            peer.sock.close()
        except OSError:
            pass
        if removed:
            self.on_peers_changed()

    def _is_connected(self, peer_id):
        with self.peers_lock:
            return peer_id in self.peers

    def _get_peer(self, peer_id):
        with self.peers_lock:
            peer = self.peers.get(peer_id)
        if peer is None:
            raise ConnectionError("That peer is no longer connected")
        return peer

    def get_peers(self):
        with self.peers_lock:
            return list(self.peers.values())

    def stop(self):
        """Close the server socket and every peer connection."""
        self.running = False
        for peer in self.get_peers():
            self._remove(peer)
        if self.server_socket:
            try:
                self.server_socket.close()
            except OSError:
                pass
        self.on_event("[SYSTEM] Peer stopped")
