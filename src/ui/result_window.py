import math

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
)
from PyQt6.QtCore import Qt, QPoint, QRect, QSize
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
    def __init__(self, title: str, collapsed: bool = False, parent=None):
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
        self._content.setVisible(expanded)
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(12, 4, 0, 4)
        self._content_layout.setSpacing(3)
        layout.addWidget(self._content)

    def _on_toggle(self, checked: bool):
        self._toggle_btn.setText(f"{'▼' if checked else '▶'} {self._title}")
        self._content.setVisible(checked)

    def add_line(self, text: str, color: str = "#a6adc8"):
        lbl = QLabel(text)
        lbl.setWordWrap(True)
        lbl.setStyleSheet(f"color: {color}; font-size: 12px;")
        self._content_layout.addWidget(lbl)


# ── 主卡片窗口 ─────────────────────────────────────────────────────────────────
class ResultWindow(QWidget):
    """赛博朋克风格无边框结果卡片。"""

    def __init__(self, result: dict, position: tuple | None = None, image=None):
        super().__init__()
        self._result = result
        self._position = position
        self._image = image
        self._drag_pos: QPoint | None = None
        self._init_window()
        self._init_ui()
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
            h = min(800, geo.height() - 80)
            self.resize(w, h)
        self.setMinimumWidth(480)
        self.setMinimumHeight(360)
        self.setWindowOpacity(0.0)  # show() 前不可见，showEvent 再设为 1

    # ── UI 构建 ────────────────────────────────────────────────────────────────
    def _init_ui(self):
        if self._result.get("_mode") == "summary":
            self._init_summary_ui()
            return
        if self._result.get("_mode") == "explain":
            self._init_explain_ui()
            return

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
            "  border: 1px solid #45475a;"
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

        # ── 列布局（有截图3列，无截图2列）──────────────────────────────────────
        cols = QHBoxLayout()
        cols.setSpacing(16)
        cols.setContentsMargins(0, 0, 0, 0)

        # ── 截图预览列（仅截图模式）────────────────────────────────────────────
        if self._image is not None:
            img = self._image.copy()
            img.thumbnail((400, 800))
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
            img_widget = QWidget()
            img_widget.setStyleSheet("background: transparent;")
            img_layout = QVBoxLayout(img_widget)
            img_layout.setContentsMargins(0, 0, 0, 0)
            img_layout.addWidget(img_lbl)
            img_layout.addStretch()
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
        search_log: list = self._result.get("_search_log", [])
        if search_log:
            search_sec = CollapsibleSection(f"搜索过程（{len(search_log)} 次）", collapsed=True)
            for entry in search_log:
                query = entry.get("query", "")
                preview = entry.get("result_preview", "").strip()
                if len(preview) > 120:
                    preview = preview[:120] + "…"
                search_sec.add_line(f"🔍 {query}", "#89b4fa")
                if preview:
                    search_sec.add_line(f"    → {preview}", "#585b70")
            right_col.addWidget(search_sec)

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

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        card = QFrame()
        card.setObjectName("card")
        card.setStyleSheet(
            "#card {"
            "  background: rgba(24, 24, 37, 242);"
            "  border-radius: 18px;"
            "  border: 1px solid #45475a;"
            "}"
        )
        outer.addWidget(card)

        main_layout = QVBoxLayout(card)
        main_layout.setContentsMargins(28, 22, 28, 22)
        main_layout.setSpacing(16)

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
        close_btn = QPushButton("✕")
        close_btn.setFixedSize(28, 28)
        close_btn.setStyleSheet(
            "QPushButton { background: #313244; color: #6c7086; border-radius: 14px; font-size: 13px; }"
            "QPushButton:hover { background: #ff5555; color: #fff; }"
        )
        close_btn.clicked.connect(self.close)
        top_row.addWidget(close_btn)
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

        # ── 截图预览（若有）────────────────────────────────────────────────────
        if self._image is not None:
            img = self._image.copy()
            img.thumbnail((320, 240))
            w, h = img.size
            data = img.tobytes("raw", "RGB")
            from PyQt6.QtGui import QImage, QPixmap
            qimg = QImage(data, w, h, w * 3, QImage.Format.Format_RGB888)
            img_lbl = QLabel()
            img_lbl.setPixmap(QPixmap.fromImage(qimg))
            img_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            img_lbl.setStyleSheet(
                "border: 1px solid #313244; border-radius: 6px; background: #0a0a14;"
            )
            main_layout.addWidget(img_lbl)

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

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        card = QFrame()
        card.setObjectName("card")
        card.setStyleSheet(
            "#card {"
            "  background: rgba(24, 24, 37, 242);"
            "  border-radius: 18px;"
            "  border: 1px solid #45475a;"
            "}"
        )
        outer.addWidget(card)

        main_layout = QVBoxLayout(card)
        main_layout.setContentsMargins(28, 22, 28, 22)
        main_layout.setSpacing(16)

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
        close_btn = QPushButton("✕")
        close_btn.setFixedSize(28, 28)
        close_btn.setStyleSheet(
            "QPushButton { background: #313244; color: #6c7086; border-radius: 14px; font-size: 13px; }"
            "QPushButton:hover { background: #ff5555; color: #fff; }"
        )
        close_btn.clicked.connect(self.close)
        top_row.addWidget(close_btn)
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
            from PyQt6.QtWidgets import QScrollArea, QTableWidget, QTableWidgetItem, QHeaderView
            table = QTableWidget(len(characters), 3)
            table.setHorizontalHeaderLabels(["角色名", "作品", "备注"])
            table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
            table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
            table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
            table.verticalHeader().setVisible(False)
            table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
            table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
            table.setStyleSheet(
                "QTableWidget { background: #1e1e2e; color: #cdd6f4; font-size: 12px;"
                "  gridline-color: #313244; border: none; border-radius: 6px; }"
                "QHeaderView::section { background: #181825; color: #89b4fa; font-size: 11px;"
                "  border: none; padding: 4px 8px; }"
                "QTableWidget::item { padding: 4px 8px; }"
            )
            for i, ch in enumerate(characters):
                table.setItem(i, 0, QTableWidgetItem(ch.get("name", "")))
                table.setItem(i, 1, QTableWidgetItem(ch.get("work", "")))
                table.setItem(i, 2, QTableWidgetItem(ch.get("note", "")))
            row_h = 26
            max_visible = 10
            visible_rows = min(len(characters), max_visible)
            table.setFixedHeight(table.horizontalHeader().height() + row_h * visible_rows + 4)
            scroll = QScrollArea()
            scroll.setWidget(table)
            scroll.setWidgetResizable(True)
            scroll.setFixedHeight(table.height() + 4)
            scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
            main_layout.addWidget(scroll)

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

        # ── 截图预览（若有）─────────────────────────────────────────────────────
        if self._image is not None:
            img = self._image.copy()
            img.thumbnail((320, 240))
            w, h = img.size
            data = img.tobytes("raw", "RGB")
            qimg = QImage(data, w, h, w * 3, QImage.Format.Format_RGB888)
            img_lbl = QLabel()
            img_lbl.setPixmap(QPixmap.fromImage(qimg))
            img_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            img_lbl.setStyleSheet(
                "border: 1px solid #313244; border-radius: 6px; background: #0a0a14;"
            )
            main_layout.addWidget(img_lbl)

    def _position_window(self):
        screen = QApplication.primaryScreen()
        if not screen:
            return
        geo = screen.availableGeometry()

        if not self._position:
            self.move(
                geo.x() + geo.width() - self.width() - 40,
                geo.y() + 60,
            )
            return

        x, y = self._position
        w, h = self.width(), self.height()
        x = min(x + 12, geo.x() + geo.width() - w - 8)
        y = min(y, geo.y() + geo.height() - h - 8)
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
