"""快速截图测试 UsageWindow 图表渲染"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer
import usage  # 用真实数据

OUTFILE = sys.argv[1] if len(sys.argv) > 1 else None

app = QApplication(sys.argv)

from ui.usage_window import UsageWindow
win = UsageWindow()
win.show()

def _grab():
    if OUTFILE:
        px = win.grab()
        px.save(OUTFILE)
        print(f"[test] saved to {OUTFILE}")
        app.quit()

QTimer.singleShot(800, _grab)
sys.exit(app.exec())
