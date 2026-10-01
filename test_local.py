"""
Quick self-test (no GUI):  python test_local.py
Starts 3 peers on this computer, then tests text + file transfer.
"""
import hashlib, os, shutil, time
from p2p_node import P2PNode

def sha(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()

for d in ("t_a", "t_b", "t_c"):
    shutil.rmtree(d, ignore_errors=True)
log = lambda tag: (lambda m: print(f"  [{tag}] {m}"))
a = P2PNode("Alice", 5000, log("A"), lambda: None, "t_a")
b = P2PNode("Bob", 5001, log("B"), lambda: None, "t_b")
c = P2PNode("Charlie", 5002, log("C"), lambda: None, "t_c")
for n in (a, b, c):
    n.start()

b.connect_to("127.0.0.1", 5000)      # Bob -> Alice
c.connect_to("127.0.0.1", 5000)      # Charlie -> Alice
c.connect_to("127.0.0.1", 5001)      # Charlie -> Bob
time.sleep(0.3)
print("Peers A:", [p.name for p in a.get_peers()])
print("Peers B:", [p.name for p in b.get_peers()])
print("Peers C:", [p.name for p in c.get_peers()])

b.send_text(b.get_peers()[0].peer_id, "Hello from Bob")

with open("sample.bin", "wb") as f:       # 5 MB random binary file
    f.write(os.urandom(5 * 1024 * 1024 + 123))
alice_to_bob = [p for p in a.get_peers() if p.name == "Bob"][0]
a.send_file(alice_to_bob.peer_id, "sample.bin")
time.sleep(1)
ok = sha("sample.bin") == sha("t_b/sample.bin")
print("File identical after transfer:", ok)

try:
    a.connect_to("127.0.0.1", 6999)
except Exception as e:
    print("Expected error:", e)
c.stop(); time.sleep(0.3)
print("Alice peers after Charlie stopped:", [p.name for p in a.get_peers()])
for n in (a, b):
    n.stop()
os.remove("sample.bin")
for d in ("t_a", "t_b", "t_c"):
    shutil.rmtree(d, ignore_errors=True)
print("ALL OK" if ok else "FAILED")
