"""测试 StampWidget 在各种 bullshit_nature 下的显示效果"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from PyQt6.QtWidgets import QApplication, QWidget, QHBoxLayout, QVBoxLayout, QLabel
from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QFont

app = QApplication(sys.argv)

from ui.result_window import StampWidget

CASES = [
    (72, "事实错误"),
    (45, "夸大渲染"),
    (15, "真实但离谱"),
    (60, "标题党"),
    (50, "断章取义"),
    (55, "逻辑混乱"),
    (30, ""),          # 无 nature → 按 bi 走
    (85, ""),          # 无 nature → 极度危险
]

container = QWidget()
container.setStyleSheet("background: #1e1e2e;")
layout = QHBoxLayout(container)
layout.setSpacing(20)

for bi, nature in CASES:
    col = QVBoxLayout()
    stamp = StampWidget(bi, nature)
    label = QLabel(f"bi={bi}\n'{nature or '(none)'}'")
    label.setFont(QFont("Arial", 9))
    label.setStyleSheet("color: #cdd6f4;")
    col.addWidget(stamp)
    col.addWidget(label)
    layout.addLayout(col)

container.adjustSize()
container.show()

OUTFILE = sys.argv[1] if len(sys.argv) > 1 else "tests/stamp_nature_test.png"

def _grab():
    px = container.grab()
    px.save(OUTFILE)
    print(f"[test] saved {OUTFILE}")
    app.quit()

QTimer.singleShot(400, _grab)
sys.exit(app.exec())
