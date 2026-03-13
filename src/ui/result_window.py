from PyQt6.QtWidgets import (
    QApplication,
    QWidget,
    QVBoxLayout,
    QTextEdit,
    QPushButton,
    QHBoxLayout,
    QLabel,
    QProgressBar,
)
from PyQt6.QtCore import Qt, QTimer, QPoint
from PyQt6.QtGui import QFont
import pyperclip


class ResultWindow(QWidget):
    """显示 AI 分析结果的浮动窗口。"""

    AUTO_CLOSE_MS = 30000  # 30秒自动关闭

    def __init__(self, result: dict, position: tuple | None = None):
        super().__init__()
        self._result = result
        self._position = position
        self._init_ui()
        self._position_window()
        self._start_auto_close()

    def _init_ui(self):
        self.setWindowTitle("BullshitDetector - 鉴定结果")
        self.setWindowFlags(
            Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Window
        )
        self.setMinimumSize(520, 400)
        self.resize(600, 560)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # 标题
        is_fake = self._result.get("is_fake", False)
        confidence = self._result.get("confidence", 0.5)
        bs_index = self._result.get("bullshit_index", 50)

        verdict_text = "假的！" if is_fake else "基本属实"
        verdict_color = "#f38ba8" if is_fake else "#a6e3a1"

        title = QLabel(f"鉴定结果：{verdict_text}")
        title.setFont(QFont("Microsoft YaHei", 16, QFont.Weight.Bold))
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(f"color: {verdict_color};")
        layout.addWidget(title)

        # Bullshit 指数进度条
        bs_label = QLabel(f"扯淡指数：{bs_index}/100（置信度 {confidence:.0%}）")
        bs_label.setFont(QFont("Microsoft YaHei", 11))
        bs_label.setStyleSheet("color: #cdd6f4;")
        layout.addWidget(bs_label)

        bs_bar = QProgressBar()
        bs_bar.setRange(0, 100)
        bs_bar.setValue(bs_index)
        bar_color = "#a6e3a1" if bs_index < 30 else "#f9e2af" if bs_index < 70 else "#f38ba8"
        bs_bar.setStyleSheet(
            f"QProgressBar {{ background: #313244; border-radius: 6px; height: 18px; text-align: center; color: #cdd6f4; }}"
            f"QProgressBar::chunk {{ background: {bar_color}; border-radius: 6px; }}"
        )
        layout.addWidget(bs_bar)

        # 毒舌锐评
        roast = self._result.get("roast", "")
        if roast:
            roast_label = QLabel(f"💬 {roast}")
            roast_label.setFont(QFont("Microsoft YaHei", 12, QFont.Weight.Bold))
            roast_label.setWordWrap(True)
            roast_label.setStyleSheet(
                "color: #f9e2af; background: #313244; border-radius: 8px; padding: 12px;"
            )
            layout.addWidget(roast_label)

        # 详细分析
        detail_text = self._build_detail_markdown()
        text_edit = QTextEdit()
        text_edit.setReadOnly(True)
        text_edit.setMarkdown(detail_text)
        text_edit.setFont(QFont("Microsoft YaHei", 11))
        text_edit.setStyleSheet(
            "QTextEdit { background: #1e1e2e; color: #cdd6f4; "
            "border: 1px solid #45475a; border-radius: 8px; padding: 12px; }"
        )
        layout.addWidget(text_edit)

        # 错误提示
        error = self._result.get("error")
        if error:
            err_label = QLabel(f"⚠️ {error}")
            err_label.setStyleSheet("color: #f38ba8; padding: 4px;")
            layout.addWidget(err_label)

        # 按钮
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

    def _build_detail_markdown(self) -> str:
        lines = []
        claims = self._result.get("claims", [])
        if claims:
            lines.append("### 逐条分析")
            for c in claims:
                verdict = c.get("verdict", "")
                claim = c.get("claim", "")
                reason = c.get("reason", "")
                lines.append(f"- {verdict} **{claim}**\n  {reason}")

        tactics = self._result.get("tactics", [])
        if tactics:
            lines.append("\n### 识别话术")
            lines.append("、".join(tactics))

        return "\n\n".join(lines) if lines else "*暂无详细分析*"

    def _position_window(self):
        if self._position:
            x, y = self._position
            screen = QApplication.primaryScreen()
            if screen:
                geo = screen.availableGeometry()
                # 确保窗口不超出屏幕（考虑多显示器偏移）
                win_w, win_h = self.width(), self.height()
                x = min(x, geo.x() + geo.width() - win_w)
                y = min(y, geo.y() + geo.height() - win_h)
                x = max(geo.x(), x)
                y = max(geo.y(), y)
                self.move(QPoint(x, y))

    def _start_auto_close(self):
        self._auto_close_timer = QTimer(self)
        self._auto_close_timer.setSingleShot(True)
        self._auto_close_timer.timeout.connect(self.close)
        self._auto_close_timer.start(self.AUTO_CLOSE_MS)

    def _copy_result(self):
        text = self._format_copy_text()
        try:
            pyperclip.copy(text)
        except Exception:
            clipboard = QApplication.clipboard()
            if clipboard:
                clipboard.setText(text)

    def _format_copy_text(self) -> str:
        lines = []
        is_fake = self._result.get("is_fake", False)
        confidence = self._result.get("confidence", 0.5)
        bs_index = self._result.get("bullshit_index", 50)
        roast = self._result.get("roast", "")

        lines.append(f"鉴定结果：{'假的！' if is_fake else '基本属实'}")
        lines.append(f"扯淡指数：{bs_index}/100（置信度 {confidence:.0%}）")
        if roast:
            lines.append(f"锐评：{roast}")

        claims = self._result.get("claims", [])
        if claims:
            lines.append("\n逐条分析：")
            for c in claims:
                lines.append(f"  {c.get('verdict', '')} {c.get('claim', '')} - {c.get('reason', '')}")

        return "\n".join(lines)
