import math
import threading
from urllib.request import urlopen, Request as URLRequest

from PyQt6.QtWidgets import (
    QApplication,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizeGrip,
    QFrame,
    QSizePolicy,
    QScrollArea,
    QLineEdit,
)
from PyQt6.QtCore import Qt, QPoint, QRect, QSize, QTimer, pyqtSignal
from PyQt6.QtGui import (
    QFont,
    QColor,
    QPainter,
    QPen,
    QBrush,
    QConicalGradient,
    QPainterPath,
    QTransform,
    QImage,
    QPixmap,
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
    def __init__(self, title: str, collapsed: bool = False, max_content_height: int = 0, parent=None):
        super().__init__(parent)
        self._title = title
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        expanded = not collapsed
        self._toggle_btn = QPushButton(f"{'▼' if expanded else '▶'} {title}")
        self._toggle_btn.setCheckable(True)
        self._toggle_btn.setChecked(expanded)
        self._toggle_btn.setStyleSheet(
            "QPushButton { background: transparent; color: #6c7086; "
            "border: none; text-align: left; font-size: 12px; padding: 2px 0; }"
            "QPushButton:hover { color: #cdd6f4; }"
            "QPushButton:checked { color: #89b4fa; }"
        )
        self._toggle_btn.clicked.connect(self._on_toggle)
        layout.addWidget(self._toggle_btn)

        self._content = QWidget()
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(12, 4, 0, 4)
        self._content_layout.setSpacing(3)

        if max_content_height > 0:
            self._wrap: QScrollArea | None = QScrollArea()
            self._wrap.setWidget(self._content)
            self._wrap.setWidgetResizable(True)
            self._wrap.setMaximumHeight(max_content_height)
            self._wrap.setFrameShape(QFrame.Shape.NoFrame)
            self._wrap.setStyleSheet(
                "QScrollArea { background: transparent; }"
                "QScrollBar:vertical { width: 6px; background: #1e1e2e; border-radius: 3px; }"
                "QScrollBar::handle:vertical { background: #45475a; border-radius: 3px; }"
            )
            self._wrap.setVisible(expanded)
            layout.addWidget(self._wrap)
        else:
            self._wrap = None
            self._content.setVisible(expanded)
            layout.addWidget(self._content)

    def _on_toggle(self, checked: bool):
        self._toggle_btn.setText(f"{'▼' if checked else '▶'} {self._title}")
        target = self._wrap if self._wrap is not None else self._content
        target.setVisible(checked)

    def add_line(self, text: str, color: str = "#a6adc8"):
        lbl = QLabel(text)
        lbl.setWordWrap(True)
        lbl.setStyleSheet(f"color: {color}; font-size: 12px;")
        self._content_layout.addWidget(lbl)


# ── 主卡片窗口 ─────────────────────────────────────────────────────────────────
class ResultWindow(QWidget):
    """赛博朋克风格无边框结果卡片。"""

    _ref_image_loaded = pyqtSignal(object, object)      # (QLabel, QPixmap | None)
    _follow_up_received = pyqtSignal(str, str)           # (question, answer)

    def __init__(self, result: dict, position: tuple | None = None, images=None, image=None):
        super().__init__()
        self._result = result
        self._position = position
        # images 优先；image 为旧调用兼容
        if images is not None:
            self._images: list = images if isinstance(images, list) else [images]
        elif image is not None:
            self._images = [image]
        else:
            self._images = []
        self._image = self._images[0] if self._images else None
        self._drag_pos: QPoint | None = None
        self._follow_up_history: list[dict] = []
        self._chat_loading_bubble = None
        self._ref_image_loaded.connect(self._on_ref_image_loaded)
        self._follow_up_received.connect(self._on_follow_up_received)
        self._init_window()
        self._init_ui()
        self._make_labels_selectable()
        self._position_window()  # show() 前完成定位，避免窗口闪烁到默认位置

    # ── 窗口属性 ───────────────────────────────────────────────────────────────
    def _init_window(self):
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        self.setWindowTitle("")
        # 提前创建 HWND，避免 Windows DWM 在透明设置前闪白色原生窗口
        self.winId()
        screen = QApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            w = min(1200, geo.width() - 80)
            h = min(860, geo.height() - 80)
            self.resize(w, h)
        self.setMinimumWidth(480)
        self.setMinimumHeight(360)
        self.setWindowOpacity(0.0)  # show() 前不可见，showEvent 再设为 1

    def _make_labels_selectable(self):
        """让所有 QLabel 文字可鼠标选中复制。"""
        flags = Qt.TextInteractionFlag.TextSelectableByMouse | Qt.TextInteractionFlag.TextSelectableByKeyboard
        for label in self.findChildren(QLabel):
            if label.text():
                label.setTextInteractionFlags(flags)
                label.setCursor(Qt.CursorShape.IBeamCursor)

    # ── UI 构建 ────────────────────────────────────────────────────────────────
    def _init_ui(self):
        mode = self._result.get("_mode")

        # 根布局：[内容卡片 | 追问面板]
        self._root_h = QHBoxLayout(self)
        self._root_h.setContentsMargins(0, 0, 0, 0)
        self._root_h.setSpacing(8)

        if mode == "summary":
            self._init_summary_ui()
        elif mode == "explain":
            self._init_explain_ui()
        elif mode == "source":
            self._init_source_ui()
        else:
            self._init_analyze_ui()

        # 追问面板（默认折叠，点击💬展开；stretch=0 确保折叠时不占宽度）
        self._chat_panel = self._build_chat_panel(mode or "analyze")
        self._chat_panel.hide()
        self._root_h.addWidget(self._chat_panel, 0)

    def _init_analyze_ui(self):
        """鉴屎模式 UI（原 _init_ui 内联代码）。"""
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

        # 内容卡片（加入根 HBoxLayout，stretch=3 占大部分宽度）
        card = QFrame()
        card.setObjectName("card")
        card.setStyleSheet(
            "#card {"
            "  background: rgba(24, 24, 37, 242);"
            "  border-radius: 18px;"
            "  border: 1px solid #45475a;"
            "}"
        )
        self._root_h.addWidget(card, 3)

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

        top_row.addWidget(self._make_chat_toggle_btn(), alignment=Qt.AlignmentFlag.AlignTop)
        top_row.addWidget(self._make_close_btn(), alignment=Qt.AlignmentFlag.AlignTop)

        main_layout.addLayout(top_row)

        # ── 列布局（有截图3列，无截图2列）──────────────────────────────────────
        cols = QHBoxLayout()
        cols.setSpacing(16)
        cols.setContentsMargins(0, 0, 0, 0)

        # ── 截图预览列（仅截图模式）────────────────────────────────────────────
        if self._images:
            max_thumb = (380, 700) if len(self._images) == 1 else (190, 190)
            img_widget = QWidget()
            img_widget.setStyleSheet("background: transparent;")
            img_layout = QVBoxLayout(img_widget)
            img_layout.setContentsMargins(0, 0, 0, 0)
            img_layout.setSpacing(6)
            for img_src in self._images:
                img = img_src.copy()
                img.thumbnail(max_thumb)
                w, h = img.size
                data = img.tobytes("raw", "RGB")
                qimg = QImage(data, w, h, w * 3, QImage.Format.Format_RGB888)
                pixmap = QPixmap.fromImage(qimg)
                img_lbl = QLabel()
                img_lbl.setPixmap(pixmap)
                img_lbl.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
                img_lbl.setStyleSheet(
                    "border: 1px solid #313244; border-radius: 6px; background: #0a0a14; padding: 4px;"
                )
                img_lbl.setScaledContents(False)
                img_layout.addWidget(img_lbl)
            img_layout.addStretch()
            if len(self._images) > 1:
                scroll = QScrollArea()
                scroll.setWidget(img_widget)
                scroll.setWidgetResizable(True)
                scroll.setFrameShape(QFrame.Shape.NoFrame)
                scroll.setStyleSheet(
                    "QScrollArea { background: transparent; }"
                    "QScrollBar:vertical { width: 6px; background: #1e1e2e; border-radius: 3px; }"
                    "QScrollBar::handle:vertical { background: #45475a; border-radius: 3px; }"
                )
                cols.addWidget(scroll, 25)
            else:
                cols.addWidget(img_widget, 33)

        # 中列：核心信息
        left_col = QVBoxLayout()
        left_col.setSpacing(10)
        left_col.setContentsMargins(0, 0, 0, 0)

        # 右列：可折叠详情
        right_col = QVBoxLayout()
        right_col.setSpacing(8)
        right_col.setContentsMargins(0, 0, 0, 0)

        # ── 左列：核心判决 ─────────────────────────────────────────────────────
        if verdict_text:
            v_lbl = QLabel(verdict_text)
            v_lbl.setWordWrap(True)
            v_lbl.setStyleSheet(
                "color: #cdd6f4; font-size: 12px;"
                "background: rgba(69,71,90,120);"
                "border-radius: 8px; padding: 8px 12px;"
            )
            left_col.addWidget(v_lbl)

        # ── 左列：来源识别 ─────────────────────────────────────────────────────
        source_origin = report.get("source_origin", "")
        if source_origin and source_origin != "无法识别":
            src_lbl = QLabel(f"📌 来源：{source_origin}")
            src_lbl.setWordWrap(True)
            src_lbl.setStyleSheet("color: #6c7086; font-size: 11px; padding: 2px 0;")
            left_col.addWidget(src_lbl)

        # ── 左列：分割线 ───────────────────────────────────────────────────────
        if verdict_text or source_origin:
            sep = QFrame()
            sep.setFrameShape(QFrame.Shape.HLine)
            sep.setStyleSheet("color: #313244;")
            left_col.addWidget(sep)

        # ── 左列：锐评 ─────────────────────────────────────────────────────────
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
            left_col.addWidget(toxic_label)

        # ── 左列：错误提示 ─────────────────────────────────────────────────────
        if error:
            err = QLabel(f"⚠ {error}")
            err.setWordWrap(True)
            err.setStyleSheet("color: #f38ba8; font-size: 12px; padding: 4px 0;")
            left_col.addWidget(err)

        # ── 左列：一句话总结 ───────────────────────────────────────────────────
        if one_line:
            ol_lbl = QLabel(one_line)
            ol_lbl.setWordWrap(True)
            ol_lbl.setStyleSheet(
                "color: #6c7086; font-size: 11px; font-style: italic; padding: 4px 0;"
            )
            left_col.addWidget(ol_lbl)

        left_col.addStretch()

        # ── 右列：声明核查（默认展开）──────────────────────────────────────────
        claims: list = self._result.get("claim_verification", [])
        if claims:
            _VERDICT_COLOR = {"✓": "#a6e3a1", "✗": "#f38ba8", "?": "#f9e2af"}
            claim_sec = CollapsibleSection("声明核查", collapsed=False)
            for c in claims:
                claim_text = c.get("claim", "")
                verdict = c.get("verdict", "?")
                note = c.get("note", "")
                color = _VERDICT_COLOR.get(verdict[0] if verdict else "?", "#f9e2af")
                v_lbl = QLabel(f"{verdict}  {claim_text}")
                v_lbl.setWordWrap(True)
                v_lbl.setStyleSheet(f"color: {color}; font-size: 11px;")
                claim_sec._content_layout.addWidget(v_lbl)
                eff = c.get("effective_sources")
                src_type = c.get("best_source_type", "")
                if eff is not None or (src_type and src_type not in ("", "none")):
                    _TYPE_ZH = {
                        "primary": "官方/原始",
                        "independent": "独立媒体",
                        "syndicated": "转载",
                        "self_reported": "当事方自述",
                    }
                    meta_parts = []
                    if eff is not None:
                        meta_parts.append(f"有效信源 {eff} 个")
                    if src_type and src_type not in ("", "none"):
                        meta_parts.append(f"最高级别: {_TYPE_ZH.get(src_type, src_type)}")
                    meta_lbl = QLabel(f"    {'  ·  '.join(meta_parts)}")
                    meta_lbl.setWordWrap(True)
                    meta_lbl.setStyleSheet("color: #45475a; font-size: 10px;")
                    claim_sec._content_layout.addWidget(meta_lbl)
                if note:
                    n_lbl = QLabel(f"    {note}")
                    n_lbl.setWordWrap(True)
                    n_lbl.setStyleSheet("color: #6c7086; font-size: 10px;")
                    claim_sec._content_layout.addWidget(n_lbl)
            right_col.addWidget(claim_sec)

        # ── 右列：破绽列表（默认展开）──────────────────────────────────────────
        if flaw_list:
            flaw_sec = CollapsibleSection("破绽列表", collapsed=False)
            for item in flaw_list:
                flaw_sec.add_line(f"• {item}", "#f38ba8")
            right_col.addWidget(flaw_sec)

        # ── 右列：多维评分雷达（默认折叠）──────────────────────────────────────
        if any(radar.values()):
            radar_sec = CollapsibleSection("多维评分雷达", collapsed=False)
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
            right_col.addWidget(radar_sec)

        # ── 右列：侦查报告（默认折叠）──────────────────────────────────────────
        _ALL_REPORT_KEYS = ("content_nature", "source_origin", "time_check", "entity_check",
                            "physics_check", "source_independence_note", "hype_check",
                            "missing_info", "intent_check")
        if any(report.get(k, "") for k in _ALL_REPORT_KEYS):
            inv_sec = CollapsibleSection("侦查报告", collapsed=False)
            _REPORT_LABELS = [
                ("content_nature",          "内容性质", "#cba6f7"),
                ("source_origin",           "来源识别", "#89dceb"),
                ("time_check",              "时间核查", "#f9e2af"),
                ("entity_check",            "实体核查", "#f9e2af"),
                ("physics_check",           "常识核查", "#f9e2af"),
                ("source_independence_note","信源独立性", "#a6e3a1"),
                ("hype_check",              "夸大检测", "#ffb86c"),
                ("missing_info",            "遗漏信息", "#ffb86c"),
                ("intent_check",            "意图检测", "#ffb86c"),
            ]
            for key, label, color in _REPORT_LABELS:
                val = report.get(key, "")
                if val and val != "未核查":
                    inv_sec.add_line(f"[{label}] {val}", color)
            right_col.addWidget(inv_sec)

        # ── 右列：搜索过程（默认折叠，标题显示次数）──────────────────────────
        _search_log_temp: list = self._result.get("_search_log", [])
        if _search_log_temp:
            _sl_sec = CollapsibleSection(f"搜索过程（{len(_search_log_temp)} 次）", collapsed=True, max_content_height=220)
            for _sl_entry in _search_log_temp:
                _sl_query = _sl_entry.get("query", "")
                _sl_preview = _sl_entry.get("result_preview", "").strip()
                if len(_sl_preview) > 120:
                    _sl_preview = _sl_preview[:120] + "…"
                _sl_sec.add_line(f"🔍 {_sl_query}", "#89b4fa")
                if _sl_preview:
                    _sl_sec.add_line(f"    → {_sl_preview}", "#585b70")
            right_col.addWidget(_sl_sec)

        right_col.addStretch()

        # 左列 45% / 右列 55%
        left_widget = QWidget()
        left_widget.setStyleSheet("background: transparent;")
        left_widget.setLayout(left_col)
        right_widget = QWidget()
        right_widget.setStyleSheet("background: transparent;")
        right_widget.setLayout(right_col)

        mid_stretch, right_stretch = (33, 34) if self._image is not None else (45, 55)
        cols.addWidget(left_widget, mid_stretch)
        cols.addWidget(right_widget, right_stretch)
        main_layout.addLayout(cols)

        # ── 底部：复制按钮（右下）+ 缩放手柄 ────────────────────────────────
        bottom_row = QHBoxLayout()
        bottom_row.addStretch()
        copy_btn = QPushButton("复制结果")
        copy_btn.setFixedHeight(32)
        copy_btn.setStyleSheet(
            "QPushButton { background: #313244; color: #89b4fa; "
            "border-radius: 8px; font-size: 12px; font-weight: bold; padding: 0 16px; }"
            "QPushButton:hover { background: #45475a; }"
        )
        copy_btn.clicked.connect(self._copy_result)
        bottom_row.addWidget(copy_btn)
        grip = QSizeGrip(self)
        grip.setStyleSheet("background: transparent;")
        bottom_row.addWidget(grip, alignment=Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignRight)
        main_layout.addLayout(bottom_row)

    # ── 窗口定位 ──────────────────────────────────────────────────────────────
    def _init_summary_ui(self):
        headline = self._result.get("headline", "")
        key_points: list = self._result.get("key_points", [])
        bias_note = self._result.get("bias_note", "")
        orig_lang = self._result.get("original_language", "zh")
        error = self._result.get("error")

        main_layout = self._make_card()

        # ── 顶栏：标题 + 语言标签 + 关闭 ───────────────────────────────────────
        top_row = QHBoxLayout()
        title_lbl = QLabel("📝 内容总结")
        title_lbl.setStyleSheet("color: #a6e3a1; font-size: 16px; font-weight: bold;")
        top_row.addWidget(title_lbl)

        if orig_lang and orig_lang != "zh":
            lang_lbl = QLabel(f"原文: {orig_lang}")
            lang_lbl.setStyleSheet(
                "color: #6c7086; font-size: 11px; background: #313244;"
                " border-radius: 4px; padding: 2px 8px;"
            )
            top_row.addWidget(lang_lbl)

        top_row.addStretch()
        top_row.addWidget(self._make_chat_toggle_btn())
        top_row.addWidget(self._make_close_btn())
        main_layout.addLayout(top_row)

        # ── 分隔线 ──────────────────────────────────────────────────────────────
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: #313244;")
        main_layout.addWidget(sep)

        # ── 一句话结论 ──────────────────────────────────────────────────────────
        if error:
            hl_lbl = QLabel(f"💥 {error}")
            hl_lbl.setStyleSheet("color: #f38ba8; font-size: 14px;")
        else:
            hl_lbl = QLabel(headline or "（无法提取结论）")
            hl_lbl.setStyleSheet(
                "color: #cdd6f4; font-size: 17px; font-weight: bold;"
                " background: #1e1e2e; border-radius: 8px; padding: 10px 14px;"
            )
        hl_lbl.setWordWrap(True)
        main_layout.addWidget(hl_lbl)

        # ── 要点列表 ────────────────────────────────────────────────────────────
        if key_points:
            pts_lbl = QLabel("要点")
            pts_lbl.setStyleSheet("color: #6c7086; font-size: 11px; font-weight: bold;")
            main_layout.addWidget(pts_lbl)
            for pt in key_points:
                row = QHBoxLayout()
                dot = QLabel("▸")
                dot.setFixedWidth(16)
                dot.setStyleSheet("color: #a6e3a1; font-size: 13px;")
                txt = QLabel(pt)
                txt.setWordWrap(True)
                txt.setStyleSheet("color: #cdd6f4; font-size: 13px;")
                row.addWidget(dot, 0, Qt.AlignmentFlag.AlignTop)
                row.addWidget(txt, 1)
                main_layout.addLayout(row)

        # ── 偏向备注 ────────────────────────────────────────────────────────────
        if bias_note:
            bias_lbl = QLabel(f"⚠️ {bias_note}")
            bias_lbl.setWordWrap(True)
            bias_lbl.setStyleSheet(
                "color: #f9e2af; font-size: 12px;"
                " background: #2a2018; border-radius: 6px; padding: 8px 12px;"
            )
            main_layout.addWidget(bias_lbl)

        main_layout.addStretch()
        self._append_image_preview(main_layout)

    def _init_explain_ui(self):
        _TYPE_LABEL = {
            "identify": "角色识别",
            "meme":     "网络梗",
            "concept":  "概念解释",
        }
        explain_type = self._result.get("type", "concept")
        subject = self._result.get("subject", "")
        short_answer = self._result.get("short_answer", "")
        detail = self._result.get("detail", "")
        origin = self._result.get("origin", "")
        usage = self._result.get("usage", "")
        orig_lang = self._result.get("original_language", "zh")
        error = self._result.get("error")

        main_layout = self._make_card()

        # ── 顶栏：标题 + 类型标签 + 语言标签 + 关闭 ────────────────────────────
        top_row = QHBoxLayout()
        title_lbl = QLabel("❓ 解释")
        title_lbl.setStyleSheet("color: #89b4fa; font-size: 16px; font-weight: bold;")
        top_row.addWidget(title_lbl)

        type_lbl = QLabel(_TYPE_LABEL.get(explain_type, explain_type))
        type_lbl.setStyleSheet(
            "color: #89b4fa; font-size: 11px; background: #1a2a3e;"
            " border: 1px solid #89b4fa; border-radius: 4px; padding: 2px 8px;"
        )
        top_row.addWidget(type_lbl)

        if orig_lang and orig_lang != "zh":
            lang_lbl = QLabel(f"原文: {orig_lang}")
            lang_lbl.setStyleSheet(
                "color: #6c7086; font-size: 11px; background: #313244;"
                " border-radius: 4px; padding: 2px 8px;"
            )
            top_row.addWidget(lang_lbl)

        top_row.addStretch()
        top_row.addWidget(self._make_chat_toggle_btn())
        top_row.addWidget(self._make_close_btn())
        main_layout.addLayout(top_row)

        # ── 分隔线 ───────────────────────────────────────────────────────────────
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: #313244;")
        main_layout.addWidget(sep)

        # ── subject 大字 ─────────────────────────────────────────────────────────
        if error:
            subj_lbl = QLabel(f"💥 {error}")
            subj_lbl.setStyleSheet("color: #f38ba8; font-size: 14px;")
        else:
            subj_lbl = QLabel(subject or "（无法识别对象）")
            subj_lbl.setStyleSheet(
                "color: #89b4fa; font-size: 18px; font-weight: bold; padding: 2px 0;"
            )
        subj_lbl.setWordWrap(True)
        main_layout.addWidget(subj_lbl)

        # ── 一句话回答 ───────────────────────────────────────────────────────────
        if short_answer:
            ans_lbl = QLabel(short_answer)
            ans_lbl.setWordWrap(True)
            ans_lbl.setStyleSheet(
                "color: #cdd6f4; font-size: 15px; font-weight: bold;"
                " background: #1e1e2e; border-radius: 8px; padding: 10px 14px;"
            )
            main_layout.addWidget(ans_lbl)

        # ── 多角色列表 ───────────────────────────────────────────────────────────
        characters = self._result.get("characters", [])
        if characters and explain_type == "identify":
            from PyQt6.QtWidgets import QTableWidget, QTableWidgetItem, QHeaderView
            n = len(characters)
            n_rows = math.ceil(n / 2)
            table = QTableWidget(n_rows, 4)
            table.setHorizontalHeaderLabels(["角色名", "作品", "角色名", "作品"])
            for col in range(4):
                mode = (QHeaderView.ResizeMode.ResizeToContents if col % 2 == 0
                        else QHeaderView.ResizeMode.Stretch)
                table.horizontalHeader().setSectionResizeMode(col, mode)
            table.verticalHeader().setVisible(False)
            table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
            table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
            ROW_H = 26
            table.verticalHeader().setDefaultSectionSize(ROW_H)
            table.setStyleSheet(
                "QTableWidget { background: #1e1e2e; color: #cdd6f4; font-size: 12px;"
                "  gridline-color: #313244; border: none; border-radius: 6px; }"
                "QHeaderView::section { background: #181825; color: #89b4fa; font-size: 11px;"
                "  border: none; padding: 4px 8px; }"
                "QTableWidget::item { padding: 4px 8px; }"
            )
            # 推算原图网格列数（25格→5列，16格→4列）
            grid_cols_img = math.ceil(math.sqrt(n))
            # 列优先填充：左列先填 0..n_rows-1，再右列 n_rows..2*n_rows-1
            for col_pair in range(2):
                for row_i in range(n_rows):
                    idx = col_pair * n_rows + row_i
                    if idx < n:
                        ch = characters[idx]
                        img_row = idx // grid_cols_img + 1
                        img_col = idx % grid_cols_img + 1
                        name_label = f"{img_row}行{img_col}列 {ch.get('name', '')}"
                        table.setItem(row_i, col_pair * 2,     QTableWidgetItem(name_label))
                        table.setItem(row_i, col_pair * 2 + 1, QTableWidgetItem(ch.get("work", "")))
            HEADER_H = 28
            max_visible = 13
            table.setFixedHeight(HEADER_H + ROW_H * min(n_rows, max_visible))
            main_layout.addWidget(table)

        # ── 详细说明 ─────────────────────────────────────────────────────────────
        if detail:
            detail_lbl = QLabel(detail)
            detail_lbl.setWordWrap(True)
            detail_lbl.setStyleSheet("color: #a6adc8; font-size: 13px; padding: 4px 0;")
            main_layout.addWidget(detail_lbl)

        # ── 来源/出处 ────────────────────────────────────────────────────────────
        if origin:
            orig_lbl = QLabel(f"📌 来源：{origin}")
            orig_lbl.setWordWrap(True)
            orig_lbl.setStyleSheet("color: #6c7086; font-size: 12px; padding: 2px 0;")
            main_layout.addWidget(orig_lbl)

        # ── 用法（仅非空时显示，黄色块）──────────────────────────────────────────
        if usage:
            usage_lbl = QLabel(f"💬 用法：{usage}")
            usage_lbl.setWordWrap(True)
            usage_lbl.setStyleSheet(
                "color: #f9e2af; font-size: 12px;"
                " background: #2a2018; border-radius: 6px; padding: 8px 12px;"
            )
            main_layout.addWidget(usage_lbl)

        main_layout.addStretch()
        self._append_image_preview(main_layout)

    def _init_source_ui(self):
        _MEDIA_TYPE_ZH = {
            "anime": "动画", "manga": "漫画", "movie": "电影",
            "game": "游戏", "tv": "剧集", "other": "其他",
        }
        _CONFIDENCE_CONFIG = {
            "high":   ("✓ 高置信", "#a6e3a1", "#1a2e1e"),
            "medium": ("~ 中置信", "#f9e2af", "#2a2018"),
            "low":    ("? 低置信", "#fab387", "#2e1e0e"),
        }

        found = self._result.get("found", False)
        title = self._result.get("title", "")
        original_title = self._result.get("original_title", "")
        media_type = self._result.get("media_type", "other")
        year = self._result.get("year", "")
        studio = self._result.get("studio", "")
        episode = self._result.get("episode", "")
        episode_title = self._result.get("episode_title", "")
        scene = self._result.get("scene", "")
        characters: list = self._result.get("characters", [])
        confidence = self._result.get("confidence", "low")
        note = self._result.get("note", "")
        error = self._result.get("error")
        search_log: list = self._result.get("_search_log", [])

        main_layout = self._make_card(spacing=14)

        # ── 顶栏 ────────────────────────────────────────────────────────────────
        top_row = QHBoxLayout()
        title_lbl = QLabel("🎬 求出处")
        title_lbl.setStyleSheet("color: #fab387; font-size: 16px; font-weight: bold;")
        top_row.addWidget(title_lbl)

        media_zh = _MEDIA_TYPE_ZH.get(media_type, "其他")
        media_lbl = QLabel(media_zh)
        media_lbl.setStyleSheet(
            "color: #fab387; font-size: 11px; background: #2e1e0e;"
            " border: 1px solid #fab387; border-radius: 4px; padding: 2px 8px;"
        )
        top_row.addWidget(media_lbl)

        conf_text, conf_color, conf_bg = _CONFIDENCE_CONFIG.get(confidence, _CONFIDENCE_CONFIG["low"])
        conf_lbl = QLabel(conf_text)
        conf_lbl.setStyleSheet(
            f"color: {conf_color}; font-size: 11px; background: {conf_bg};"
            f" border: 1px solid {conf_color}; border-radius: 4px; padding: 2px 8px;"
        )
        top_row.addWidget(conf_lbl)

        top_row.addStretch()
        top_row.addWidget(self._make_chat_toggle_btn())
        top_row.addWidget(self._make_close_btn())
        main_layout.addLayout(top_row)

        # ── 分隔线 ───────────────────────────────────────────────────────────────
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: #313244;")
        main_layout.addWidget(sep)

        if not self._result.get("_vision_used", True):
            vision_tip = QLabel(
                "⚠️ 未启用以图搜图（未配置 Google Vision Key），冷门作品识别准确率可能偏低。"
                "  配置方法见 docs/API_KEYS.md"
            )
            vision_tip.setWordWrap(True)
            vision_tip.setStyleSheet(
                "color: #f9e2af; font-size: 11px;"
                " background: #2a2018; border-radius: 6px; padding: 7px 12px;"
            )
            main_layout.addWidget(vision_tip)

        if error or not found:
            # 未能识别
            err_lbl = QLabel(f"💥 {error or '未能识别该截图来自哪部作品'}")
            err_lbl.setWordWrap(True)
            err_lbl.setStyleSheet("color: #f38ba8; font-size: 14px; padding: 8px 0;")
            main_layout.addWidget(err_lbl)
            if scene and scene != "（无法识别）":
                scene_lbl = QLabel(scene)
                scene_lbl.setWordWrap(True)
                scene_lbl.setStyleSheet(
                    "color: #cdd6f4; font-size: 13px;"
                    " background: rgba(69,71,90,120);"
                    " border-radius: 8px; padding: 10px 12px;"
                )
                main_layout.addWidget(scene_lbl)
            if note:
                note_lbl = QLabel(note)
                note_lbl.setWordWrap(True)
                note_lbl.setStyleSheet(
                    "color: #f9e2af; font-size: 12px;"
                    " background: #2a2018; border-radius: 6px; padding: 8px 12px;"
                )
                main_layout.addWidget(note_lbl)
        else:
            # ── 作品标题 ────────────────────────────────────────────────────────
            title_main = QLabel(title or "（未知作品）")
            title_main.setWordWrap(True)
            title_main.setStyleSheet(
                "color: #fab387; font-size: 18px; font-weight: bold; padding: 2px 0;"
            )
            main_layout.addWidget(title_main)

            if original_title and original_title != title:
                orig_lbl = QLabel(original_title)
                orig_lbl.setWordWrap(True)
                orig_lbl.setStyleSheet("color: #6c7086; font-size: 13px; padding: 0;")
                main_layout.addWidget(orig_lbl)

            # ── 年份 · 制作公司 ─────────────────────────────────────────────────
            meta_parts = []
            if year:
                meta_parts.append(year)
            if studio:
                meta_parts.append(studio)
            if meta_parts:
                meta_lbl = QLabel("  ·  ".join(meta_parts))
                meta_lbl.setStyleSheet("color: #6c7086; font-size: 12px; padding: 2px 0;")
                main_layout.addWidget(meta_lbl)

            # ── 集数 + 集名 ─────────────────────────────────────────────────────
            ep_parts = []
            if episode:
                ep_parts.append(episode)
            if episode_title:
                ep_parts.append(f"「{episode_title}」")
            if ep_parts:
                ep_lbl = QLabel("  ".join(ep_parts))
                ep_lbl.setWordWrap(True)
                ep_lbl.setStyleSheet("color: #89b4fa; font-size: 13px; padding: 2px 0;")
                main_layout.addWidget(ep_lbl)

            # ── 场景描述 ────────────────────────────────────────────────────────
            if scene and scene != "（无法识别）":
                scene_lbl = QLabel(scene)
                scene_lbl.setWordWrap(True)
                scene_lbl.setStyleSheet(
                    "color: #cdd6f4; font-size: 13px;"
                    " background: rgba(69,71,90,120);"
                    " border-radius: 8px; padding: 10px 12px;"
                )
                main_layout.addWidget(scene_lbl)

            # ── 出现角色 ────────────────────────────────────────────────────────
            if characters:
                chars_lbl = QLabel(f"出现角色：{', '.join(characters)}")
                chars_lbl.setWordWrap(True)
                chars_lbl.setStyleSheet("color: #a6adc8; font-size: 12px; padding: 2px 0;")
                main_layout.addWidget(chars_lbl)

            # ── note 黄色块 ─────────────────────────────────────────────────────
            if note:
                note_lbl = QLabel(note)
                note_lbl.setWordWrap(True)
                note_lbl.setStyleSheet(
                    "color: #f9e2af; font-size: 12px;"
                    " background: #2a2018; border-radius: 6px; padding: 8px 12px;"
                )
                main_layout.addWidget(note_lbl)

        self._append_search_log(main_layout, search_log)

        main_layout.addStretch()

        # 对比图区域：输入截图 + AI 搜索到的参考图并排
        ref_urls = self._result.get("reference_image_urls", [])
        page_urls = self._result.get("source_page_urls", [])
        if found or ref_urls:
            self._load_ref_images(main_layout, ref_urls, self._image, page_urls)

    def _on_ref_image_loaded(self, label, pixmap):
        """Slot: update reference image label from background thread."""
        if pixmap is not None:
            label.setPixmap(pixmap)
            label.setText("")
            label.setStyleSheet("border: 1px solid #45475a; border-radius: 4px; background: #0a0a14;")
        else:
            url = label.toolTip()
            label.setText(f'<a href="{url}" style="color:#585b70;font-size:10px;text-decoration:none;">🔗 点击查看</a>')
            label.setTextFormat(Qt.TextFormat.RichText)
            label.setOpenExternalLinks(True)
            label.setStyleSheet(
                "border: 1px dashed #313244; border-radius: 4px; background: #0a0a14;"
                " color: #585b70;"
            )

    def _load_ref_images(self, layout: "QVBoxLayout", urls: list, input_image=None, page_urls: list | None = None):
        """
        Build a comparison strip: [输入截图] | [参考图1] | [参考图2] ...
        Each cell has an image label + caption below.
        Reference images are fetched asynchronously.
        """
        if not urls and input_image is None:
            return

        strip_label = QLabel("对比参考")
        strip_label.setStyleSheet("color: #6c7086; font-size: 11px; font-weight: bold; padding: 4px 0 2px 0;")
        layout.addWidget(strip_label)

        row = QHBoxLayout()
        row.setSpacing(12)
        row.setContentsMargins(0, 0, 0, 0)

        def _make_cell(caption: str, border_style: str) -> tuple:
            """Returns (img_label, cell_widget)."""
            cell = QWidget()
            cell.setStyleSheet("background: transparent;")
            cell_layout = QVBoxLayout(cell)
            cell_layout.setContentsMargins(0, 0, 0, 0)
            cell_layout.setSpacing(4)

            img_lbl = QLabel()
            img_lbl.setFixedSize(160, 120)
            img_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            img_lbl.setStyleSheet(border_style)

            cap_lbl = QLabel(caption)
            cap_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            cap_lbl.setStyleSheet("color: #6c7086; font-size: 10px;")

            cell_layout.addWidget(img_lbl)
            cell_layout.addWidget(cap_lbl)
            return img_lbl, cell

        # 输入截图
        if input_image is not None:
            img_lbl, cell = _make_cell("原图", "border: 2px solid #fab387; border-radius: 4px; background: #0a0a14;")
            img = input_image.copy()
            img.thumbnail((160, 120))
            w, h = img.size
            data = img.tobytes("raw", "RGB")
            qimg = QImage(data, w, h, w * 3, QImage.Format.Format_RGB888)
            img_lbl.setPixmap(QPixmap.fromImage(qimg))
            img_lbl.setToolTip("输入截图")
            row.addWidget(cell)

        # 参考图占位 + 异步加载
        ref_labels = []
        for i, url in enumerate(urls[:3], 1):
            img_lbl, cell = _make_cell(
                f"参考 {i}",
                "border: 1px solid #45475a; border-radius: 4px; background: #181825; color: #585b70; font-size: 11px;",
            )
            img_lbl.setText("加载中…")
            img_lbl.setToolTip(url)
            row.addWidget(cell)
            ref_labels.append((url, img_lbl))

        row.addStretch()
        container = QWidget()
        container.setStyleSheet("background: transparent;")
        container.setLayout(row)
        layout.addWidget(container)

        # 来源链接（Vision pagesWithMatchingImages）
        if page_urls:
            links_lbl = QLabel("相关来源")
            links_lbl.setStyleSheet("color: #6c7086; font-size: 11px; font-weight: bold; padding: 4px 0 2px 0;")
            layout.addWidget(links_lbl)
            for p in page_urls:
                title = p.get("title") or p.get("url", "")
                url = p.get("url", "")
                if not url:
                    continue
                display = title if title else url
                link_lbl = QLabel(f'<a href="{url}" style="color:#89b4fa; text-decoration:none;">🔗 {display}</a>')
                link_lbl.setTextFormat(Qt.TextFormat.RichText)
                link_lbl.setOpenExternalLinks(True)
                link_lbl.setWordWrap(True)
                link_lbl.setStyleSheet("font-size: 11px; padding: 1px 0;")
                layout.addWidget(link_lbl)

        if not ref_labels:
            return

        def _load_one(url_lbl):
            url, lbl = url_lbl
            try:
                req = URLRequest(url, headers={"User-Agent": "Mozilla/5.0"})
                data = urlopen(req, timeout=8).read()
                qimg = QImage()
                if qimg.loadFromData(data) and not qimg.isNull():
                    px = QPixmap.fromImage(qimg).scaled(
                        160, 120,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                    self._ref_image_loaded.emit(lbl, px)
                else:
                    self._ref_image_loaded.emit(lbl, None)
            except Exception:
                self._ref_image_loaded.emit(lbl, None)

        def _fetch():
            from concurrent.futures import ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=len(ref_labels)) as ex:
                list(ex.map(_load_one, ref_labels))

        threading.Thread(target=_fetch, daemon=True).start()

    # ── 追问面板 ───────────────────────────────────────────────────────────────

    def _make_chat_toggle_btn(self) -> "QPushButton":
        btn = QPushButton("💬")
        btn.setFixedSize(28, 28)
        btn.setStyleSheet(
            "QPushButton { background: #1e1e2e; color: #6c7086; border-radius: 6px;"
            " border: 1px solid #45475a; font-size: 14px; }"
            "QPushButton:hover { color: #89b4fa; border-color: #89b4fa; }"
        )
        btn.clicked.connect(self._toggle_chat_panel)
        return btn

    def _toggle_chat_panel(self):
        visible = self._chat_panel.isVisible()
        self._chat_panel.setVisible(not visible)
        delta = 408  # 400px chat + 8px spacing
        if not visible:
            self.resize(self.width() + delta, self.height())
        else:
            self.resize(self.width() - delta, self.height())

    _QUICK_ACTIONS: dict[str, list[str]] = {
        "analyze": ["求详细", "有没有更多证据", "帮我反驳"],
        "summary": ["更详细一点", "关键争议是什么"],
        "explain": ["讲详细", "历史背景", "举个例子"],
        "source":  ["这部作品讲什么", "还有哪些类似作品"],
    }

    def _build_chat_panel(self, mode: str) -> "QWidget":
        panel = QFrame()
        panel.setObjectName("chatPanel")
        panel.setFixedWidth(400)
        panel.setStyleSheet(
            "#chatPanel { background: rgba(17,17,27,230); border-radius: 18px;"
            " border: 1px solid #313244; }"
        )
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(14, 16, 14, 14)
        layout.setSpacing(8)

        header = QLabel("💬 追问")
        header.setStyleSheet("color: #89b4fa; font-size: 14px; font-weight: bold;")
        layout.addWidget(header)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: #313244;")
        layout.addWidget(sep)

        # 消息气泡区（滚动）
        self._chat_msg_widget = QWidget()
        self._chat_msg_widget.setStyleSheet("background: transparent;")
        self._chat_msg_layout = QVBoxLayout(self._chat_msg_widget)
        self._chat_msg_layout.setContentsMargins(0, 0, 0, 0)
        self._chat_msg_layout.setSpacing(6)
        self._chat_msg_layout.addStretch()

        self._chat_scroll = QScrollArea()
        self._chat_scroll.setWidget(self._chat_msg_widget)
        self._chat_scroll.setWidgetResizable(True)
        self._chat_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._chat_scroll.setStyleSheet(
            "QScrollArea { background: transparent; }"
            "QScrollBar:vertical { width: 4px; background: transparent; }"
            "QScrollBar::handle:vertical { background: #45475a; border-radius: 2px; }"
        )
        layout.addWidget(self._chat_scroll, 1)

        # 快捷追问按钮
        quick_actions = self._QUICK_ACTIONS.get(mode, [])
        if quick_actions:
            quick_row = QHBoxLayout()
            quick_row.setSpacing(4)
            for text in quick_actions:
                btn = QPushButton(text)
                btn.setStyleSheet(
                    "QPushButton { background: #1e1e2e; color: #6c7086; font-size: 10px;"
                    " border: 1px solid #313244; border-radius: 6px; padding: 3px 7px; }"
                    "QPushButton:hover { color: #89b4fa; border-color: #89b4fa; }"
                )
                btn.clicked.connect(lambda checked, t=text: self._send_follow_up(t))
                quick_row.addWidget(btn)
            quick_row.addStretch()
            layout.addLayout(quick_row)

        # 输入行
        input_row = QHBoxLayout()
        input_row.setSpacing(6)
        self._chat_input = QLineEdit()
        self._chat_input.setPlaceholderText("输入追问…")
        self._chat_input.setStyleSheet(
            "QLineEdit { background: #1e1e2e; color: #cdd6f4; font-size: 12px;"
            " border: 1px solid #313244; border-radius: 8px; padding: 6px 10px; }"
            "QLineEdit:focus { border-color: #89b4fa; }"
        )
        self._chat_input.returnPressed.connect(lambda: self._send_follow_up(self._chat_input.text()))

        self._chat_send_btn = QPushButton("→")
        self._chat_send_btn.setFixedSize(32, 32)
        self._chat_send_btn.setStyleSheet(
            "QPushButton { background: #1a2a4a; color: #89b4fa; border-radius: 8px;"
            " font-size: 14px; font-weight: bold; border: 1px solid #89b4fa; }"
            "QPushButton:hover { background: #89b4fa; color: #11111b; }"
            "QPushButton:disabled { background: #313244; color: #45475a; border-color: #313244; }"
        )
        self._chat_send_btn.clicked.connect(lambda: self._send_follow_up(self._chat_input.text()))

        input_row.addWidget(self._chat_input, 1)
        input_row.addWidget(self._chat_send_btn)
        layout.addLayout(input_row)

        return panel

    def _add_chat_bubble(self, text: str, is_user: bool) -> "QLabel":
        lbl = QLabel(text)
        lbl.setWordWrap(True)
        lbl.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
            | Qt.TextInteractionFlag.TextSelectableByKeyboard
        )
        if is_user:
            lbl.setStyleSheet(
                "background: #1a2a4a; color: #89b4fa; font-size: 12px;"
                " border-radius: 10px; padding: 8px 12px;"
            )
            lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
        else:
            lbl.setStyleSheet(
                "background: #1e1e2e; color: #cdd6f4; font-size: 12px;"
                " border-radius: 10px; padding: 8px 12px;"
            )
            lbl.setAlignment(Qt.AlignmentFlag.AlignLeft)
        # 插入到 stretch 之前
        count = self._chat_msg_layout.count()
        self._chat_msg_layout.insertWidget(count - 1, lbl)
        QTimer.singleShot(50, lambda: self._chat_scroll.verticalScrollBar().setValue(
            self._chat_scroll.verticalScrollBar().maximum()
        ))
        return lbl

    def _send_follow_up(self, text: str):
        text = text.strip()
        if not text:
            return
        self._chat_input.clear()
        self._chat_input.setEnabled(False)
        self._chat_send_btn.setEnabled(False)
        self._add_chat_bubble(text, is_user=True)
        self._chat_loading_bubble = self._add_chat_bubble("思考中…", is_user=False)

        result = self._result
        history = list(self._follow_up_history)

        def _call():
            from ai.analyzer import follow_up_text
            resp = follow_up_text(result, history, text)
            self._follow_up_received.emit(text, resp)

        threading.Thread(target=_call, daemon=True).start()

    def _on_follow_up_received(self, question: str, answer: str):
        if self._chat_loading_bubble is not None:
            self._chat_msg_layout.removeWidget(self._chat_loading_bubble)
            self._chat_loading_bubble.deleteLater()
            self._chat_loading_bubble = None
        self._add_chat_bubble(answer, is_user=False)
        self._follow_up_history.append({"user": question, "ai": answer})
        self._chat_input.setEnabled(True)
        self._chat_send_btn.setEnabled(True)

    def _make_card(self, h_margin: int = 28, v_margin: int = 22, spacing: int = 16) -> "QVBoxLayout":
        """Create standard card frame, add to root HBoxLayout. Returns inner main_layout."""
        card = QFrame()
        card.setObjectName("card")
        card.setStyleSheet(
            "#card { background: rgba(24,24,37,242); border-radius: 18px; border: 1px solid #45475a; }"
        )
        self._root_h.addWidget(card, 3)
        inner = QVBoxLayout(card)
        inner.setContentsMargins(h_margin, v_margin, h_margin, v_margin)
        inner.setSpacing(spacing)
        return inner

    def _make_close_btn(self) -> "QPushButton":
        """Create standard ✕ close button."""
        btn = QPushButton("✕")
        btn.setFixedSize(28, 28)
        btn.setStyleSheet(
            "QPushButton { background: #313244; color: #6c7086; border-radius: 14px; font-size: 13px; }"
            "QPushButton:hover { background: #ff5555; color: #fff; }"
        )
        btn.clicked.connect(self.close)
        return btn

    def _append_image_preview(self, layout: "QVBoxLayout"):
        """Append screenshot thumbnail to layout if image is available."""
        if self._image is None:
            return
        img = self._image.copy()
        img.thumbnail((320, 240))
        w, h = img.size
        data = img.tobytes("raw", "RGB")
        qimg = QImage(data, w, h, w * 3, QImage.Format.Format_RGB888)
        lbl = QLabel()
        lbl.setPixmap(QPixmap.fromImage(qimg))
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setStyleSheet("border: 1px solid #313244; border-radius: 6px; background: #0a0a14;")
        layout.addWidget(lbl)

    def _append_search_log(self, layout: "QVBoxLayout", search_log: list):
        """Append collapsible search log section to layout."""
        if not search_log:
            return
        sec = CollapsibleSection(f"搜索过程（{len(search_log)} 次）", collapsed=True, max_content_height=220)
        for entry in search_log:
            query = entry.get("query", "")
            preview = entry.get("result_preview", "").strip()
            if len(preview) > 120:
                preview = preview[:120] + "…"
            sec.add_line(f"🔍 {query}", "#89b4fa")
            if preview:
                sec.add_line(f"    → {preview}", "#585b70")
        layout.addWidget(sec)

    def _position_window(self):
        screen = QApplication.primaryScreen()
        if not screen:
            return
        geo = screen.availableGeometry()

        # self.width() may not reflect final layout size before show(), use target width
        target_w = min(1200, geo.width() - 80)
        target_h = min(860, geo.height() - 80)

        if not self._position:
            self.move(
                geo.x() + geo.width() - target_w - 40,
                geo.y() + 60,
            )
            return

        x, y = self._position
        x = min(x + 12, geo.x() + geo.width() - target_w - 8)
        y = min(y, geo.y() + geo.height() - target_h - 8)
        x = max(geo.x() + 8, x)
        y = max(geo.y() + 8, y)
        self.move(QPoint(x, y))

    # ── 点击外部关闭 ──────────────────────────────────────────────────────────
    def showEvent(self, event):
        super().showEvent(event)
        self.setWindowOpacity(1.0)  # 首帧渲染完成后才显示，消除白色闪烁
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
            lines.append(f"\n评语：{toxic}")
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
