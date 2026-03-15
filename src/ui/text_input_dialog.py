"""text_input_dialog.py —— 文字/链接鉴定输入对话框"""

from PyQt6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QTextEdit, QPushButton, QLabel
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QColor, QPalette

from text_fetcher import fetch_article


_STYLE = """
QDialog {
    background-color: #1e1e2e;
    border: 1px solid #cba6f7;
    border-radius: 8px;
}
QLabel {
    color: #cba6f7;
    font-size: 14px;
    font-weight: bold;
}
QTextEdit {
    background-color: #181825;
    color: #cdd6f4;
    border: 1px solid #45475a;
    border-radius: 6px;
    padding: 8px;
    font-size: 13px;
}
QTextEdit:focus {
    border: 1px solid #cba6f7;
}
QPushButton {
    background-color: #313244;
    color: #cdd6f4;
    border: 1px solid #45475a;
    border-radius: 6px;
    padding: 6px 20px;
    font-size: 13px;
}
QPushButton:hover {
    background-color: #45475a;
}
QPushButton#btn_confirm {
    background-color: #cba6f7;
    color: #1e1e2e;
    font-weight: bold;
    border: none;
}
QPushButton#btn_confirm:hover {
    background-color: #d0bcff;
}
QPushButton#btn_confirm:disabled {
    background-color: #45475a;
    color: #6c7086;
}
"""


class TextInputDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._content: str = ""
        self._build_ui()
        self.setStyleSheet(_STYLE)

    def _build_ui(self):
        self.setWindowTitle("文字 / 链接鉴定")
        self.setWindowFlags(
            Qt.WindowType.Dialog
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.FramelessWindowHint
        )
        self.setMinimumWidth(480)
        self.setMinimumHeight(300)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 16)
        layout.setSpacing(12)

        title = QLabel("🔍 文字 / 链接鉴定")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        self._edit = QTextEdit()
        self._edit.setPlaceholderText(
            "粘贴文章内容或链接…\n\n• 支持多行文章全文\n• 粘贴 http(s):// 开头的链接将自动提取正文"
        )
        self._edit.setMinimumHeight(160)
        self._edit.textChanged.connect(self._on_text_changed)
        layout.addWidget(self._edit)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        btn_cancel = QPushButton("取消")
        btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(btn_cancel)

        self._btn_confirm = QPushButton("开始鉴定")
        self._btn_confirm.setObjectName("btn_confirm")
        self._btn_confirm.setEnabled(False)
        self._btn_confirm.clicked.connect(self._on_confirm)
        btn_row.addWidget(self._btn_confirm)

        layout.addLayout(btn_row)

    def _on_text_changed(self):
        self._btn_confirm.setEnabled(bool(self._edit.toPlainText().strip()))

    def _on_confirm(self):
        raw = self._edit.toPlainText().strip()
        if raw.startswith("http://") or raw.startswith("https://"):
            if "\n" not in raw:
                self._content = fetch_article(raw)
                self.accept()
                return
        self._content = raw
        self.accept()

    def get_content(self) -> str:
        return self._content
