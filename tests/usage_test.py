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
# 补充各模式估算数据（仅数值，与历史记录一致：summary/explain/analyze，无追问）
sid_sum1 = str(uuid.uuid4())
usage_mod.create_session(sid_sum1, "summary")
usage_mod.record_call(sid_sum1, "summary", "gemini-2.5-flash", 1150, 320)

sid_exp1 = str(uuid.uuid4())
usage_mod.create_session(sid_exp1, "explain")
usage_mod.record_call(sid_exp1, "explain", "gemini-2.5-flash", 1820, 410)

sid_exp2 = str(uuid.uuid4())
usage_mod.create_session(sid_exp2, "explain")
usage_mod.record_call(sid_exp2, "explain", "gemini-2.5-flash", 1760, 390)

sid_sum2 = str(uuid.uuid4())
usage_mod.create_session(sid_sum2, "summary")
usage_mod.record_call(sid_sum2, "summary", "gemini-2.5-flash", 980, 270)

sid_ana1 = str(uuid.uuid4())
usage_mod.create_session(sid_ana1, "analyze")
usage_mod.record_call(sid_ana1, "analyze", "gemini-2.5-flash", 4620, 1180)

sid_sum3 = str(uuid.uuid4())
usage_mod.create_session(sid_sum3, "summary")
usage_mod.record_call(sid_sum3, "summary", "gemini-2.5-flash", 1050, 300)

sid_ana2 = str(uuid.uuid4())
usage_mod.create_session(sid_ana2, "analyze")
usage_mod.record_call(sid_ana2, "analyze", "gemini-2.5-flash", 4890, 1240)

sid_sum4 = str(uuid.uuid4())
usage_mod.create_session(sid_sum4, "summary")
usage_mod.record_call(sid_sum4, "summary", "gemini-2.5-flash", 1100, 290)

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
