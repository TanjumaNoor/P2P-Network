"""
main.py - Simple Tkinter user interface.   Run with:  python main.py

The GUI only talks to P2PNode. Network threads never touch widgets
directly (Tkinter is not thread-safe); they put events in a queue and the
GUI reads that queue every 100 ms.
"""

import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk

from p2p_node import P2PNode


class App:
    def __init__(self, root):
        self.root = root
        root.title("UAP P2P Network")
        root.geometry("820x560")
        self.node = None
        self.events = queue.Queue()
        self.peer_ids = []              # same order as the listbox rows

        self._build_ui()
        self._set_running(False)
        self.root.after(100, self._process_events)
        root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ----------------------------------------------------------- layout
    def _build_ui(self):
        # --- My Peer ---
        f1 = ttk.LabelFrame(self.root, text="My Peer")
        f1.pack(fill="x", padx=8, pady=4)
        ttk.Label(f1, text="Name:").pack(side="left", padx=4)
        self.name_var = tk.StringVar(value="Alice")
        self.name_entry = ttk.Entry(f1, textvariable=self.name_var, width=14)
        self.name_entry.pack(side="left")
        ttk.Label(f1, text="Port:").pack(side="left", padx=4)
        self.port_var = tk.StringVar(value="5000")
        self.port_entry = ttk.Entry(f1, textvariable=self.port_var, width=7)
        self.port_entry.pack(side="left")
        self.start_btn = ttk.Button(f1, text="Start Peer", command=self.start_peer)
        self.start_btn.pack(side="left", padx=6, pady=4)
        self.stop_btn = ttk.Button(f1, text="Stop", command=self.stop_peer)
        self.stop_btn.pack(side="left")
        self.info_var = tk.StringVar(value="Not running")
        ttk.Label(f1, textvariable=self.info_var).pack(side="left", padx=10)

        # --- Connect ---
        f2 = ttk.LabelFrame(self.root, text="Connect to Another Peer")
        f2.pack(fill="x", padx=8, pady=4)
        ttk.Label(f2, text="IP:").pack(side="left", padx=4)
        self.ip_var = tk.StringVar(value="127.0.0.1")
        self.ip_entry = ttk.Entry(f2, textvariable=self.ip_var, width=16)
        self.ip_entry.pack(side="left")
        ttk.Label(f2, text="Port:").pack(side="left", padx=4)
        self.rport_var = tk.StringVar(value="5001")
        self.rport_entry = ttk.Entry(f2, textvariable=self.rport_var, width=7)
        self.rport_entry.pack(side="left")
        self.connect_btn = ttk.Button(f2, text="Connect", command=self.connect_peer)
        self.connect_btn.pack(side="left", padx=6, pady=4)

        # --- peer list + log ---
        mid = ttk.Frame(self.root)
        mid.pack(fill="both", expand=True, padx=8, pady=4)
        left = ttk.LabelFrame(mid, text="Connected Peers")
        left.pack(side="left", fill="y")
        self.peer_list = tk.Listbox(left, width=32, exportselection=False)
        self.peer_list.pack(fill="y", expand=True, padx=4, pady=4)
        right = ttk.LabelFrame(mid, text="Messages / Events")
        right.pack(side="left", fill="both", expand=True, padx=(6, 0))
        self.log = scrolledtext.ScrolledText(right, state="disabled",
                                             font=("Consolas", 10))
        self.log.pack(fill="both", expand=True, padx=4, pady=4)

        # --- send text ---
        f3 = ttk.LabelFrame(self.root, text="Send Text (select a peer first)")
        f3.pack(fill="x", padx=8, pady=4)
        self.msg_var = tk.StringVar()
        self.msg_entry = ttk.Entry(f3, textvariable=self.msg_var)
        self.msg_entry.pack(side="left", fill="x", expand=True, padx=4, pady=4)
        self.msg_entry.bind("<Return>", lambda e: self.send_text())
        self.send_btn = ttk.Button(f3, text="Send", command=self.send_text)
        self.send_btn.pack(side="left", padx=4)

        # --- send file ---
        f4 = ttk.LabelFrame(self.root, text="Send File")
        f4.pack(fill="x", padx=8, pady=(4, 8))
        ttk.Label(f4, text="Text, image, audio, video, PDF, ZIP, etc.").pack(
            side="left", padx=4)
        self.file_btn = ttk.Button(f4, text="Choose File & Send",
                                   command=self.send_file)
        self.file_btn.pack(side="right", padx=4, pady=4)

    def _set_running(self, running):
        """Enable/disable widgets depending on whether the peer is running."""
        on, off = ("normal", "disabled")
        for w in (self.name_entry, self.port_entry, self.start_btn):
            w.config(state=off if running else on)
        for w in (self.stop_btn, self.ip_entry, self.rport_entry,
                  self.connect_btn, self.msg_entry, self.send_btn,
                  self.file_btn):
            w.config(state=on if running else off)

    # ---------------------------------------------------------- actions
    def start_peer(self):
        name = self.name_var.get().strip()
        if not name:
            return messagebox.showerror("Error", "Please enter a peer name.")
        try:
            port = int(self.port_var.get())
            if not 1024 <= port <= 65535:
                raise ValueError
        except ValueError:
            return messagebox.showerror(
                "Error", "Port must be a number between 1024 and 65535.")

        node = P2PNode(name, port, on_event=self.events.put,
                       on_peers_changed=lambda: self.events.put("__PEERS__"))
        try:
            node.start()
        except OSError as e:
            return messagebox.showerror("Error", f"Cannot start peer: {e}")
        self.node = node
        self.info_var.set(f"{name} | ID: {node.peer_id} | Port: {port}")
        self._set_running(True)

    def stop_peer(self):
        if self.node:
            self.node.stop()
            self.node = None
        self.info_var.set("Not running")
        self._refresh_peers([])
        self._set_running(False)

    def connect_peer(self):
        ip = self.ip_var.get().strip()
        try:
            port = int(self.rport_var.get())
        except ValueError:
            return self._error("Invalid port")
        self.connect_btn.config(state="disabled")

        def worker():                  # connect in a thread so the GUI won't freeze
            try:
                self.node.connect_to(ip, port)
            except Exception as e:
                self.events.put(f"[ERROR] Connection failed: {e}")
            finally:
                self.events.put("__ENABLE_CONNECT__")
        threading.Thread(target=worker, daemon=True).start()

    def _selected_peer_id(self):
        sel = self.peer_list.curselection()
        if not sel:
            self._error("Please select a peer from the list first.")
            return None
        return self.peer_ids[sel[0]]

    def send_text(self):
        text = self.msg_var.get().strip()
        if not text:
            return
        peer_id = self._selected_peer_id()
        if not peer_id:
            return
        try:
            self.node.send_text(peer_id, text)
            self.msg_var.set("")
        except Exception as e:
            self._error(str(e))

    def send_file(self):
        peer_id = self._selected_peer_id()
        if not peer_id:
            return
        path = filedialog.askopenfilename(title="Choose a file to send")
        if not path:
            return

        def worker():                  # send in a thread so the GUI won't freeze
            try:
                self.node.send_file(peer_id, path)
            except Exception as e:
                self.events.put(f"[ERROR] {e}")
        threading.Thread(target=worker, daemon=True).start()

    # ------------------------------------------------------- event queue
    def _process_events(self):
        try:
            while True:
                item = self.events.get_nowait()
                if item == "__PEERS__":
                    if self.node:
                        self._refresh_peers(self.node.get_peers())
                elif item == "__ENABLE_CONNECT__":
                    if self.node:
                        self.connect_btn.config(state="normal")
                else:
                    self._log(item)
        except queue.Empty:
            pass
        self.root.after(100, self._process_events)

    def _refresh_peers(self, peers):
        self.peer_list.delete(0, "end")
        self.peer_ids = []
        for p in peers:
            self.peer_list.insert("end", p.label())
            self.peer_ids.append(p.peer_id)

    def _log(self, text):
        self.log.config(state="normal")
        self.log.insert("end", text + "\n")
        self.log.see("end")
        self.log.config(state="disabled")

    def _error(self, text):
        self._log(f"[ERROR] {text}")
        messagebox.showwarning("Warning", text)

    def _on_close(self):
        if self.node:
            self.node.stop()
        self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    App(root)
    root.mainloop()
