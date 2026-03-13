from PyQt6.QtWidgets import (
    QApplication,
    QWidget,
    QVBoxLayout,
    QTextEdit,
    QPushButton,
    QHBoxLayout,
    QLabel,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
import pyperclip


class ResultWindow(QWidget):
    """显示 AI 分析结果的浮动窗口。"""

    def __init__(self, result_text: str):
        super().__init__()
        self._result_text = result_text
        self._init_ui()

    def _init_ui(self):
        self.setWindowTitle("BullshitDetector - 分析结果")
        self.setWindowFlags(
            Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Window
        )
        self.setMinimumSize(520, 400)
        self.resize(600, 500)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        title = QLabel("分析结果")
        title.setFont(QFont("Microsoft YaHei", 14, QFont.Weight.Bold))
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        text_edit = QTextEdit()
        text_edit.setReadOnly(True)
        text_edit.setMarkdown(self._result_text)
        text_edit.setFont(QFont("Microsoft YaHei", 11))
        text_edit.setStyleSheet(
            "QTextEdit { background: #1e1e2e; color: #cdd6f4; "
            "border: 1px solid #45475a; border-radius: 8px; padding: 12px; }"
        )
        layout.addWidget(text_edit)

        btn_layout = QHBoxLayout()

        copy_btn = QPushButton("复制结果")
        copy_btn.setStyleSheet(
            "QPushButton { background: #89b4fa; color: #1e1e2e; "
            "border-radius: 6px; padding: 8px 20px; font-weight: bold; }"
            "QPushButton:hover { background: #74c7ec; }"
        )
        copy_btn.clicked.connect(self._copy_result)
        btn_layout.addWidget(copy_btn)

        close_btn = QPushButton("关闭")
        close_btn.setStyleSheet(
            "QPushButton { background: #45475a; color: #cdd6f4; "
            "border-radius: 6px; padding: 8px 20px; font-weight: bold; }"
            "QPushButton:hover { background: #585b70; }"
        )
        close_btn.clicked.connect(self.close)
        btn_layout.addWidget(close_btn)

        layout.addLayout(btn_layout)

        self.setStyleSheet("QWidget { background: #181825; }")

    def _copy_result(self):
        try:
            pyperclip.copy(self._result_text)
        except Exception:
            clipboard = QApplication.clipboard()
            if clipboard:
                clipboard.setText(self._result_text)
