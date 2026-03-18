"""
usage_test.py — Token 用量模块单元测试 + UsageWindow 截图
运行: F:\Project\BullshitDetector\.venv\Scripts\python.exe tests/usage_test.py
"""
import sys
import os
import uuid
import time

# 将 src 加入路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

# ── 使用临时文件隔离测试数据 ────────────────────────────────────────────────
import tempfile
import usage as usage_mod

_tmp = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
_tmp.close()
usage_mod._USAGE_FILE = __import__("pathlib").Path(_tmp.name)
print(f"[test] 使用临时文件: {_tmp.name}")

# ── Test 1: create_session + record_call ────────────────────────────────────
print("\n=== Test 1: create_session + record_call ===")
sid = str(uuid.uuid4())
usage_mod.create_session(sid, "analyze", history_id="hist-001")

usage_mod.record_call(sid, "analyze",    "gemini-2.5-flash", 2500, 800)
usage_mod.record_call(sid, "follow_up",  "gemini-2.5-flash", 1200, 300)
usage_mod.record_call(sid, "follow_up",  "gemini-2.5-flash",  800, 150)

sessions = usage_mod.get_sessions(days=30)
assert len(sessions) == 1, f"expected 1 session, got {len(sessions)}"
assert sessions[0]["id"] == sid
assert len(sessions[0]["calls"]) == 3
print("  PASS: session created, 3 calls recorded")

# ── Test 2: get_sessions filtering ──────────────────────────────────────────
print("\n=== Test 2: get_sessions() returns correct data ===")
s = sessions[0]
assert s["mode"] == "analyze"
assert s["history_id"] == "hist-001"
calls = s["calls"]
assert calls[0]["input"] == 2500
assert calls[0]["output"] == 800
assert calls[1]["type"] == "follow_up"
print("  PASS: get_sessions data correct")

# ── Test 3: get_daily_totals ────────────────────────────────────────────────
print("\n=== Test 3: get_daily_totals() structure ===")
daily = usage_mod.get_daily_totals(days=30)
assert len(daily) >= 1, "expected at least 1 date"
from datetime import datetime
today = datetime.now().strftime("%Y-%m-%d")
assert today in daily, f"today {today} not in daily: {list(daily.keys())}"
model_data = daily[today].get("gemini-2.5-flash", {})
assert model_data["input"] == 2500 + 1200 + 800, f"input mismatch: {model_data}"
assert model_data["output"] == 800 + 300 + 150, f"output mismatch: {model_data}"
print("  PASS: get_daily_totals structure correct")

# ── Test 4: UsageWindow screenshot ──────────────────────────────────────────
print("\n=== Test 4: UsageWindow screenshot ===")
# Add a second session for richer UI
sid2 = str(uuid.uuid4())
usage_mod.create_session(sid2, "summary")
usage_mod.record_call(sid2, "summarize", "gemini-2.5-flash", 900, 250)

from PyQt6.QtWidgets import QApplication
app = QApplication.instance() or QApplication(sys.argv)

from ui.usage_window import UsageWindow
win = UsageWindow()
win.show()

# Let Qt process events
for _ in range(5):
    app.processEvents()
    time.sleep(0.05)

out_path = os.path.join(os.path.dirname(__file__), "usage_test.png")
from PyQt6.QtGui import QPixmap
px = win.grab()
px.save(out_path)
print(f"  Screenshot saved: {out_path}")

win.hide()

# Cleanup temp file
os.unlink(_tmp.name)

print("\n=== ALL TESTS PASSED ===")
