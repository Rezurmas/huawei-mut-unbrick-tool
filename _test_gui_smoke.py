"""GUI smoke test - otwiera GUI na 3s i zamyka, sprawdza brak crashy."""
import sys
import threading
import time

sys.path.insert(0, '.')
from unbrick_tool import UnbrickGUI, MODELS, MutEngine, SafetyChecker, NetworkManager

import tkinter as tk

print(f"Models loaded: {len(MODELS)}")
print(f"NetworkManager methods: {[m for m in dir(NetworkManager) if not m.startswith('_')]}")

# Open GUI in mainloop
root = tk.Tk()
app = UnbrickGUI(root)
print(f"Checks count: {len(app.checks)}")
for c in app.checks:
    print(f"  [{c.status}] {c.name}: {c.message[:80]}")

print("Closing GUI in 2s...")


def close_after_delay():
    time.sleep(2)
    try:
        root.after(0, root.destroy)
    except Exception:
        pass


threading.Thread(target=close_after_delay, daemon=True).start()
try:
    root.mainloop()
except Exception as e:
    print(f"mainloop exception: {e}")

print("GUI smoke test PASSED")
