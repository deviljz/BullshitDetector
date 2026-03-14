import math

from PyQt6.QtWidgets import (
    QApplication,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QFrame,
    QSizePolicy,
    QGraphicsDropShadowEffect,
)
from PyQt6.QtCore import Qt, QTimer, QPoint, QRect, QSize
from PyQt6.QtGui import (
    QFont,
    QColor,
    QPainter,
    QPen,
    QBrush,
    QConicalGradient,
    QPainterPath,
    QTransform,
)
import pyperclip


# ── 印章配置 ──────────────────────────────────────────────────────────────────
_STAMP_LEVELS = [
    (80, "#ff5555", "一眼假"),
    (55, "#ffb86c", "高度存疑"),
    (30, "#f1fa8c", "有点水分"),
    (0,  "#50fa7b", "纯天然"),
]


def _stamp_config(bullshit_index: int) -> tuple[str, str]:
    """返回 (颜色hex, 文字)"""
    for threshold, color, text in _STAMP_LEVELS:
        if bullshit_index >= threshold:
            return color, text
    return "#50fa7b", "纯天然"


# ── 弧形仪表盘 ─────────────────────────────────────────────────────────────────
class GaugeWidget(QWidget):
    """半圆弧形仪表盘，显示扯淡指数 0-100。"""

    _SIZE = 140

    def __init__(self, value: int, parent=None):
        super().__init__(parent)
        self._value = max(0, min(100, value))
        self.setFixedSize(self._SIZE, self._SIZE // 2 + 24)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        cx = self.width() // 2
        cy = self.height() - 20
        r = (self._SIZE - 20) // 2

        rect = QRect(cx - r, cy - r, r * 2, r * 2)

        # 背景弧
        pen_bg = QPen(QColor("#313244"), 10, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        painter.setPen(pen_bg)
        painter.drawArc(rect, 0 * 16, 180 * 16)

        # 颜色：绿→黄→红渐变按值
        if self._value < 30:
            arc_color = QColor("#50fa7b")
        elif self._value < 55:
            arc_color = QColor("#f1fa8c")
        elif self._value < 80:
            arc_color = QColor("#ffb86c")
        else:
            arc_color = QColor("#ff5555")

        pen_fg = QPen(arc_color, 10, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        painter.setPen(pen_fg)
        # 从左侧 180° 开始，顺时针覆盖 value/100 * 180°
        span = int(self._value / 100 * 180 * 16)
        painter.drawArc(rect, 180 * 16, -span)

        # 数字
        painter.setPen(QPen(arc_color))
        painter.setFont(QFont("Microsoft YaHei", 18, QFont.Weight.Bold))
        painter.drawText(
            QRect(cx - 30, cy - 26, 60, 30),
            Qt.AlignmentFlag.AlignCenter,
            str(self._value),
        )
        # 副标签
        painter.setPen(QPen(QColor("#6c7086")))
        painter.setFont(QFont("Microsoft YaHei", 8))
        painter.drawText(
            QRect(cx - 40, cy - 2, 80, 18),
            Qt.AlignmentFlag.AlignCenter,
            "扯淡指数 / 100",
        )


# ── 印章部件 ───────────────────────────────────────────────────────────────────
class StampWidget(QWidget):
    """旋转印章，绘制在右上角。"""

    _W, _H = 110, 110

    def __init__(self, bullshit_index: int, parent=None):
        super().__init__(parent)
        self._color_hex, self._text = _stamp_config(bullshit_index)
        self.setFixedSize(self._W, self._H)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.translate(self._W / 2, self._H / 2)
        painter.rotate(-28)

        color = QColor(self._color_hex)
        border_color = QColor(color)
        border_color.setAlpha(200)

        # 外框矩形
        rect = QRect(-46, -22, 92, 44)
        pen = QPen(border_color, 3)
        painter.setPen(pen)
        painter.setBrush(QBrush(QColor(0, 0, 0, 0)))
        painter.drawRoundedRect(rect, 6, 6)

        # 文字
        font = QFont("Microsoft YaHei", 16, QFont.Weight.Black)
        painter.setFont(font)
        painter.setPen(QPen(color))
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, self._text)


# ── 可折叠区块 ─────────────────────────────────────────────────────────────────
class CollapsibleSection(QWidget):
    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self._toggle_btn = QPushButton(f"▼ {title}")
        self._toggle_btn.setCheckable(True)
        self._toggle_btn.setChecked(True)
        self._toggle_btn.setStyleSheet(
            "QPushButton { background: transparent; color: #6c7086; "
            "border: none; text-align: left; font-size: 12px; padding: 2px 0; }"
            "QPushButton:hover { color: #cdd6f4; }"
            "QPushButton:checked { color: #89b4fa; }"
        )
        self._toggle_btn.clicked.connect(self._on_toggle)
        layout.addWidget(self._toggle_btn)

        self._content = QWidget()
        self._content.setVisible(True)
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(12, 4, 0, 4)
        self._content_layout.setSpacing(3)
        layout.addWidget(self._content)

    def _on_toggle(self, checked: bool):
        self._toggle_btn.setText(
            f"{'▼' if checked else '▶'} {self._toggle_btn.text()[2:]}"
        )
        self._content.setVisible(checked)

    def add_line(self, text: str, color: str = "#a6adc8"):
        lbl = QLabel(text)
        lbl.setWordWrap(True)
        lbl.setStyleSheet(f"color: {color}; font-size: 12px;")
        self._content_layout.addWidget(lbl)


# ── 主卡片窗口 ─────────────────────────────────────────────────────────────────
class ResultWindow(QWidget):
    """赛博朋克风格无边框结果卡片。"""

    AUTO_CLOSE_MS = 60_000  # 60秒自动关闭

    def __init__(self, result: dict, position: tuple | None = None):
        super().__init__()
        self._result = result
        self._position = position
        self._drag_pos: QPoint | None = None
        self._init_window()
        self._init_ui()
        QTimer.singleShot(0, self._position_window)
        self._start_auto_close()

    # ── 窗口属性 ───────────────────────────────────────────────────────────────
    def _init_window(self):
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMinimumWidth(480)
        self.setMaximumWidth(560)

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(40)
        shadow.setOffset(0, 8)
        shadow.setColor(QColor(0, 0, 0, 180))
        self.setGraphicsEffect(shadow)

    # ── UI 构建 ────────────────────────────────────────────────────────────────
    def _init_ui(self):
        # 新 schema 解包
        header = self._result.get("header", {})
        bs_index = header.get("bullshit_index") or self._result.get("bullshit_index", 50) or 50
        truth_label = header.get("truth_label", "")
        risk_level = header.get("risk_level", "")
        verdict_text = header.get("verdict", "")

        radar = self._result.get("radar_chart", {})
        report = self._result.get("investigation_report", {})
        toxic = self._result.get("toxic_review", "")
        flaw_list: list = self._result.get("flaw_list", [])
        one_line = self._result.get("one_line_summary", "")
        error = self._result.get("error")

        # 外层容器（带圆角背景）
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        card = QFrame()
        card.setObjectName("card")
        card.setStyleSheet(
            "#card {"
            "  background: rgba(24, 24, 37, 242);"
            "  border-radius: 18px;"
            "  border: 1px solid #313244;"
            "}"
        )
        outer.addWidget(card)

        main_layout = QVBoxLayout(card)
        main_layout.setContentsMargins(24, 20, 24, 20)
        main_layout.setSpacing(14)

        # ── 顶部：仪表盘 + 印章 + 关闭 ────────────────────────────────────────
        top_row = QHBoxLayout()
        top_row.setSpacing(12)

        gauge = GaugeWidget(bs_index)
        top_row.addWidget(gauge, alignment=Qt.AlignmentFlag.AlignBottom)

        # risk_level + verdict 竖排
        meta_col = QVBoxLayout()
        meta_col.setAlignment(Qt.AlignmentFlag.AlignBottom)
        meta_col.setSpacing(4)
        if risk_level:
            rl_lbl = QLabel(risk_level)
            rl_lbl.setStyleSheet("color: #cdd6f4; font-size: 13px; font-weight: bold;")
            meta_col.addWidget(rl_lbl)
        if truth_label:
            tl_lbl = QLabel(truth_label)
            tl_lbl.setStyleSheet("color: #6c7086; font-size: 11px;")
            tl_lbl.setWordWrap(True)
            meta_col.addWidget(tl_lbl)
        top_row.addLayout(meta_col)

        top_row.addStretch()

        stamp = StampWidget(bs_index)
        top_row.addWidget(stamp, alignment=Qt.AlignmentFlag.AlignTop)

        close_btn = QPushButton("✕")
        close_btn.setFixedSize(28, 28)
        close_btn.setStyleSheet(
            "QPushButton { background: #313244; color: #6c7086; border-radius: 14px; font-size: 13px; }"
            "QPushButton:hover { background: #ff5555; color: #fff; }"
        )
        close_btn.clicked.connect(self.close)
        top_row.addWidget(close_btn, alignment=Qt.AlignmentFlag.AlignTop)

        main_layout.addLayout(top_row)

        # ── 核心判决 verdict ──────────────────────────────────────────────────
        if verdict_text:
            v_lbl = QLabel(verdict_text)
            v_lbl.setWordWrap(True)
            v_lbl.setStyleSheet(
                "color: #cdd6f4; font-size: 12px;"
                "background: rgba(69,71,90,120);"
                "border-radius: 8px; padding: 8px 12px;"
            )
            main_layout.addWidget(v_lbl)

        # ── 来源识别 source_origin ─────────────────────────────────────────────
        source_origin = report.get("source_origin", "")
        if source_origin and source_origin != "无法识别":
            src_lbl = QLabel(f"📌 来源：{source_origin}")
            src_lbl.setWordWrap(True)
            src_lbl.setStyleSheet("color: #6c7086; font-size: 11px; padding: 2px 0;")
            main_layout.addWidget(src_lbl)

        # ── 分割线 ──────────────────────────────────────────────────────────────
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: #313244;")
        main_layout.addWidget(sep)

        # ── 毒舌锐评 ─────────────────────────────────────────────────────────────
        if toxic:
            toxic_label = QLabel(toxic)
            toxic_label.setWordWrap(True)
            toxic_label.setFont(QFont("Microsoft YaHei", 13, QFont.Weight.Bold))
            toxic_label.setStyleSheet(
                "color: #f9e2af;"
                "background: rgba(249, 226, 175, 18);"
                "border-radius: 10px;"
                "padding: 12px 14px;"
            )
            main_layout.addWidget(toxic_label)

        # ── 错误提示 ──────────────────────────────────────────────────────────────
        if error:
            err = QLabel(f"⚠ {error}")
            err.setWordWrap(True)
            err.setStyleSheet("color: #f38ba8; font-size: 12px; padding: 4px 0;")
            main_layout.addWidget(err)

        # ── 声明逐条核查 ─────────────────────────────────────────────────────────
        claims: list = self._result.get("claim_verification", [])
        if claims:
            _VERDICT_COLOR = {
                "✓": "#a6e3a1",   # 绿：属实
                "✗": "#f38ba8",   # 红：伪造
                "?": "#f9e2af",   # 黄：无法核实
            }
            claim_frame = QFrame()
            claim_frame.setStyleSheet(
                "QFrame { background: rgba(69,71,90,80); border-radius: 8px; }"
            )
            claim_layout = QVBoxLayout(claim_frame)
            claim_layout.setContentsMargins(12, 8, 12, 8)
            claim_layout.setSpacing(6)

            title_lbl = QLabel("🔍 声明核查")
            title_lbl.setStyleSheet("color: #89b4fa; font-size: 12px; font-weight: bold;")
            claim_layout.addWidget(title_lbl)

            for c in claims:
                claim_text = c.get("claim", "")
                verdict = c.get("verdict", "?")
                note = c.get("note", "")
                # 取 verdict 首字符匹配颜色
                color = _VERDICT_COLOR.get(verdict[0] if verdict else "?", "#f9e2af")
                row = QHBoxLayout()
                row.setSpacing(6)
                v_lbl = QLabel(verdict)
                v_lbl.setFixedWidth(80)
                v_lbl.setStyleSheet(f"color: {color}; font-size: 11px; font-weight: bold;")
                row.addWidget(v_lbl)
                text_col = QVBoxLayout()
                text_col.setSpacing(1)
                c_lbl = QLabel(claim_text)
                c_lbl.setWordWrap(True)
                c_lbl.setStyleSheet("color: #cdd6f4; font-size: 12px;")
                text_col.addWidget(c_lbl)
                if note:
                    n_lbl = QLabel(note)
                    n_lbl.setWordWrap(True)
                    n_lbl.setStyleSheet("color: #6c7086; font-size: 11px;")
                    text_col.addWidget(n_lbl)
                row.addLayout(text_col)
                claim_layout.addLayout(row)

            main_layout.addWidget(claim_frame)

        # ── 折叠：多维评分雷达 ─────────────────────────────────────────────────
        if any(radar.values()):
            radar_sec = CollapsibleSection("多维评分雷达")
            _RADAR_LABELS = {
                "logic_consistency": ("逻辑自洽", "#89b4fa"),
                "source_authority":  ("来源权威", "#a6e3a1"),
                "agitation_level":   ("煽动烈度", "#f38ba8"),
                "search_match":      ("搜索核实", "#cba6f7"),
            }
            for key, (label, color) in _RADAR_LABELS.items():
                val = radar.get(key, 0)
                bar = "█" * val + "░" * (5 - val)
                radar_sec.add_line(f"{label}  [{bar}]  {val}/5", color)
            main_layout.addWidget(radar_sec)

        # ── 折叠：侦查报告 ────────────────────────────────────────────────────────
        if any(report.values()):
            inv_sec = CollapsibleSection("侦查报告")
            _REPORT_LABELS = [
                ("source_origin", "来源识别", "#89dceb"),
                ("time_check",    "时间核查", "#f9e2af"),
                ("entity_check",  "实体核查", "#f9e2af"),
                ("physics_check", "常识核查", "#f9e2af"),
            ]
            for key, label, color in _REPORT_LABELS:
                val = report.get(key, "")
                if val and val != "未核查":
                    inv_sec.add_line(f"[{label}] {val}", color)
            main_layout.addWidget(inv_sec)

        # ── 折叠：破绽列表 ────────────────────────────────────────────────────────
        if flaw_list:
            flaw_sec = CollapsibleSection("破绽列表")
            for item in flaw_list:
                flaw_sec.add_line(f"• {item}", "#f38ba8")
            main_layout.addWidget(flaw_sec)

        # ── 一句话总结 ───────────────────────────────────────────────────────────
        if one_line:
            ol_lbl = QLabel(one_line)
            ol_lbl.setWordWrap(True)
            ol_lbl.setStyleSheet(
                "color: #6c7086; font-size: 11px; font-style: italic; padding: 4px 0;"
            )
            main_layout.addWidget(ol_lbl)

        # ── 底部：复制按钮 ────────────────────────────────────────────────────────
        copy_btn = QPushButton("复制结果")
        copy_btn.setFixedHeight(32)
        copy_btn.setStyleSheet(
            "QPushButton { background: #313244; color: #89b4fa; "
            "border-radius: 8px; font-size: 12px; font-weight: bold; }"
            "QPushButton:hover { background: #45475a; }"
        )
        copy_btn.clicked.connect(self._copy_result)
        main_layout.addWidget(copy_btn)

    # ── 窗口定位 ──────────────────────────────────────────────────────────────
    def _position_window(self):
        self.adjustSize()
        if not self._position:
            screen = QApplication.primaryScreen()
            if screen:
                geo = screen.availableGeometry()
                self.move(
                    geo.x() + geo.width() - self.width() - 40,
                    geo.y() + 60,
                )
            return

        x, y = self._position
        screen = QApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            w, h = self.width(), self.height()
            x = min(x + 12, geo.x() + geo.width() - w - 8)
            y = min(y, geo.y() + geo.height() - h - 8)
            x = max(geo.x() + 8, x)
            y = max(geo.y() + 8, y)
            self.move(QPoint(x, y))

    # ── 点击外部关闭 ──────────────────────────────────────────────────────────
    def showEvent(self, event):
        super().showEvent(event)
        self.activateWindow()
        self.setFocus()

    def mousePressEvent(self, event):
        # 支持拖拽移动窗口
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event):
        if self._drag_pos and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)

    def mouseReleaseEvent(self, event):
        self._drag_pos = None

    # ── 自动关闭 ──────────────────────────────────────────────────────────────
    def _start_auto_close(self):
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.close)
        self._timer.start(self.AUTO_CLOSE_MS)

    # ── 复制 ──────────────────────────────────────────────────────────────────
    def _copy_result(self):
        lines = []
        header = self._result.get("header", {})
        bs = header.get("bullshit_index", 50)
        truth_label = header.get("truth_label", "")
        risk_level = header.get("risk_level", "")
        verdict = header.get("verdict", "")
        toxic = self._result.get("toxic_review", "")
        summary = self._result.get("one_line_summary", "")
        flaws = self._result.get("flaw_list", [])

        lines.append(f"扯淡指数：{bs}/100  {risk_level}")
        if truth_label:
            lines.append(f"真实度：{truth_label}")
        if verdict:
            lines.append(f"判决：{verdict}")
        if toxic:
            lines.append(f"\n锐评：{toxic}")
        if summary:
            lines.append(f"\n总结：{summary}")
        if flaws:
            lines.append("\n破绽：")
            for f in flaws:
                lines.append(f"  • {f}")

        text = "\n".join(lines)
        try:
            pyperclip.copy(text)
        except Exception:
            cb = QApplication.clipboard()
            if cb:
                cb.setText(text)
