"""测试新版 LoadingOverlay 布局：左侧图标+文字，右侧动态阶段"""
import sys, time
sys.path.insert(0, "src")

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer
import ui.loading_overlay as _lo_mod
from ui.loading_overlay import LoadingOverlay

app = QApplication(sys.argv)

stages = ["提取关键声明", "核查声明", "搜索：Ghost of Yotei sales…", "交叉核查", "综合分析中"]
stage_idx = [0]

overlay = LoadingOverlay("analyze")
_lo_mod._active_overlay = overlay
overlay.show()

def next_stage():
    i = stage_idx[0]
    if i < len(stages):
        _lo_mod.update_stage(stages[i])
        stage_idx[0] += 1
    else:
        # 截图
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(300, lambda: (
            overlay.grab().save("tests/loading_overlay_test.png"),
            print("saved tests/loading_overlay_test.png"),
            app.quit()
        ))

timer = QTimer()
timer.setInterval(800)
timer.timeout.connect(next_stage)
timer.start()

QTimer.singleShot(200, next_stage)
app.exec()
