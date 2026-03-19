"""usage_window.py —— Token 用量统计窗口（PyQt6 Charts 堆叠面积图 + Session 列表）"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QTreeWidget, QTreeWidgetItem, QSizeGrip,
)
from PyQt6.QtCore import Qt, QPoint, QDateTime, QMargins
from PyQt6.QtGui import QFont, QColor

try:
    from PyQt6.QtCharts import (
        QChart, QChartView, QLineSeries, QAreaSeries,
        QDateTimeAxis, QValueAxis,
    )
    _CHARTS_AVAILABLE = True
except ImportError:
    _CHARTS_AVAILABLE = False


_MODE_ICONS = {
    "analyze": "🔍",
    "summary": "📝",
    "explain": "❓",
    "source":  "🎬",
}

_MODEL_COLORS = [
    "#89b4fa",  # blue
    "#a6e3a1",  # green
    "#f38ba8",  # red
    "#fab387",  # peach
    "#cba6f7",  # mauve
    "#f9e2af",  # yellow
    "#94e2d5",  # teal
]


def _fmt_tokens(n: int) -> str:
    if n >= 1000:
        return f"{n / 1000:.1f}K"
    return str(n)


def _fmt_ts(ts_str: str) -> str:
    try:
        return ts_str[11:16]  # HH:MM
    except Exception:
        return ts_str


class UsageWindow(QWidget):
    """用量统计窗口：堆叠面积图 + Session 列表。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._drag_pos: QPoint | None = None
        self._days = 7  # default filter
        self._init_window()
        self._init_ui()
        self._load_data()

    def _init_window(self):
        self.setWindowFlags(
            Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowTitle("用量统计")
        self.resize(900, 700)
        self.setMinimumSize(600, 450)

    def _init_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        # 主卡片
        card = QFrame()
        card.setObjectName("usageCard")
        card.setStyleSheet(
            "#usageCard { background: rgba(24,24,37,242); border-radius: 18px;"
            " border: 1px solid #45475a; }"
        )
        outer.addWidget(card)

        main = QVBoxLayout(card)
        main.setContentsMargins(20, 16, 20, 16)
        main.setSpacing(12)

        # ── 标题行 ───────────────────────────────────────────────────────────
        title_row = QHBoxLayout()
        title_lbl = QLabel("📊 用量统计")
        title_lbl.setStyleSheet("color: #89b4fa; font-size: 16px; font-weight: bold;")
        title_row.addWidget(title_lbl)
        title_row.addStretch()

        # 时间过滤按钮
        self._filter_btns: dict[int, QPushButton] = {}
        for days, label in [(1, "1d"), (7, "7d"), (30, "30d")]:
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setChecked(days == self._days)
            btn.setFixedSize(44, 26)
            btn.setStyleSheet(self._filter_btn_style(days == self._days))
            btn.clicked.connect(lambda checked, d=days: self._set_days(d))
            self._filter_btns[days] = btn
            title_row.addWidget(btn)

        close_btn = QPushButton("✕")
        close_btn.setFixedSize(28, 28)
        close_btn.setStyleSheet(
            "QPushButton { background: transparent; color: #6c7086; font-size: 14px;"
            " border: none; border-radius: 6px; }"
            "QPushButton:hover { color: #f38ba8; }"
        )
        close_btn.clicked.connect(self.hide)
        title_row.addWidget(close_btn)
        main.addLayout(title_row)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: #313244;")
        main.addWidget(sep)

        # ── 图表区 ────────────────────────────────────────────────────────────
        if _CHARTS_AVAILABLE:
            self._chart = QChart()
            self._chart.setBackgroundBrush(QColor("#1e1e2e"))
            self._chart.setTitleBrush(QColor("#cdd6f4"))
            self._chart.legend().setLabelColor(QColor("#cdd6f4"))
            self._chart.legend().setAlignment(Qt.AlignmentFlag.AlignBottom)
            self._chart.setMargins(QMargins(4, 4, 4, 4))

            self._chart_view = QChartView(self._chart)
            self._chart_view.setFixedHeight(260)
            self._chart_view.setStyleSheet("background: transparent;")
            main.addWidget(self._chart_view)
        else:
            no_chart = QLabel("图表不可用（需要 PyQt6-Charts）")
            no_chart.setStyleSheet("color: #6c7086; font-size: 12px;")
            no_chart.setAlignment(Qt.AlignmentFlag.AlignCenter)
            no_chart.setFixedHeight(80)
            main.addWidget(no_chart)

        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.HLine)
        sep2.setStyleSheet("color: #313244;")
        main.addWidget(sep2)

        # ── Session 列表 ──────────────────────────────────────────────────────
        self._tree = QTreeWidget()
        self._tree.setColumnCount(4)
        self._tree.setHeaderLabels(["时间 / 模式", "模型", "输入 tokens", "输出 tokens"])
        self._tree.setStyleSheet(
            "QTreeWidget { background: #1e1e2e; color: #cdd6f4; border: none;"
            " font-size: 12px; }"
            "QTreeWidget::item { padding: 3px 4px; }"
            "QTreeWidget::item:selected { background: #313244; }"
            "QTreeWidget::branch { background: #1e1e2e; }"
            "QHeaderView::section { background: #181825; color: #6c7086;"
            " border: none; padding: 4px; font-size: 11px; }"
            "QScrollBar:vertical { width: 6px; background: transparent; }"
            "QScrollBar::handle:vertical { background: #45475a; border-radius: 3px; }"
        )
        self._tree.header().setStretchLastSection(True)
        self._tree.setColumnWidth(0, 240)
        self._tree.setColumnWidth(1, 160)
        self._tree.setColumnWidth(2, 100)
        main.addWidget(self._tree, 1)

        # 底部：size grip
        grip_row = QHBoxLayout()
        grip_row.addStretch()
        grip = QSizeGrip(card)
        grip_row.addWidget(grip)
        main.addLayout(grip_row)

    @staticmethod
    def _filter_btn_style(active: bool) -> str:
        if active:
            return (
                "QPushButton { background: #89b4fa; color: #11111b; font-size: 11px;"
                " border-radius: 6px; font-weight: bold; }"
            )
        return (
            "QPushButton { background: #313244; color: #cdd6f4; font-size: 11px;"
            " border-radius: 6px; }"
            "QPushButton:hover { background: #45475a; }"
        )

    def _set_days(self, days: int):
        self._days = days
        for d, btn in self._filter_btns.items():
            btn.setChecked(d == days)
            btn.setStyleSheet(self._filter_btn_style(d == days))
        self._load_data()

    def _load_data(self):
        try:
            import usage
            sessions = usage.get_sessions(self._days)
            daily = usage.get_daily_totals(self._days)
        except Exception:
            sessions = []
            daily = {}

        self._refresh_chart(daily)
        self._refresh_tree(sessions)

    def _refresh_chart(self, daily: dict):
        if not _CHARTS_AVAILABLE:
            return

        self._chart.removeAllSeries()
        for ax in self._chart.axes():
            self._chart.removeAxis(ax)

        if not daily:
            return

        # Collect all models
        models: set = set()
        for day_data in daily.values():
            models.update(day_data.keys())
        models_list = sorted(models)

        # Sort dates
        dates = sorted(daily.keys())

        # Build one AreaSeries per model (stacked)
        # Keep all series refs on self to prevent Python GC from collecting them
        # while Qt still holds C++ pointers (segfault cause).
        self._line_series_refs = []
        color_iter = iter(_MODEL_COLORS)
        area_series_list = []

        cumulative = {d: 0 for d in dates}

        for model in models_list:
            color = next(color_iter, "#cdd6f4")

            upper_series = QLineSeries()
            lower_series = QLineSeries()
            self._line_series_refs.extend([upper_series, lower_series])

            for date_str in dates:
                # 每天用首尾两个时间点，形成矩形色块而非斜线
                ms_s = QDateTime.fromString(date_str + "T00:00:01", Qt.DateFormat.ISODate).toMSecsSinceEpoch()
                ms_e = QDateTime.fromString(date_str + "T23:59:59", Qt.DateFormat.ISODate).toMSecsSinceEpoch()
                day_data = daily.get(date_str, {})
                model_data = day_data.get(model, {"input": 0, "output": 0})
                total = model_data["input"] + model_data["output"]
                lo = cumulative[date_str]
                hi = lo + total
                lower_series.append(ms_s, lo)
                lower_series.append(ms_e, lo)
                upper_series.append(ms_s, hi)
                upper_series.append(ms_e, hi)
                cumulative[date_str] = hi

            area = QAreaSeries(upper_series, lower_series)
            area.setName(model)
            area.setColor(QColor(color))
            area.setBorderColor(QColor(color))
            area_series_list.append(area)

        for area in area_series_list:
            self._chart.addSeries(area)

        # Axes — tickCount = 天数，避免同一天被重复标注
        axis_x = QDateTimeAxis()
        axis_x.setFormat("MM-dd")
        axis_x.setLabelsColor(QColor("#6c7086"))
        axis_x.setGridLineColor(QColor("#313244"))
        axis_x.setTickCount(max(2, len(dates)))
        min_dt = QDateTime.fromString(dates[0] + "T00:00:00", Qt.DateFormat.ISODate)
        max_dt = QDateTime.fromString(dates[-1] + "T23:59:59", Qt.DateFormat.ISODate)
        axis_x.setRange(min_dt, max_dt)
        self._chart.addAxis(axis_x, Qt.AlignmentFlag.AlignBottom)

        axis_y = QValueAxis()
        axis_y.setLabelsColor(QColor("#6c7086"))
        axis_y.setGridLineColor(QColor("#313244"))
        axis_y.setLabelFormat("%d")
        self._chart.addAxis(axis_y, Qt.AlignmentFlag.AlignLeft)

        for area in area_series_list:
            area.attachAxis(axis_x)
            area.attachAxis(axis_y)

        self._chart.setTitle("")

    def _refresh_tree(self, sessions: list):
        self._tree.clear()
        for s in sessions:
            mode = s.get("mode", "analyze")
            icon = _MODE_ICONS.get(mode, "")
            started = s.get("started_at", "")
            date_part = started[:10] if len(started) >= 10 else started
            time_part = started[11:16] if len(started) >= 16 else ""
            calls = s.get("calls", [])

            # Aggregate totals
            total_in = sum(c.get("input", 0) for c in calls)
            total_out = sum(c.get("output", 0) for c in calls)
            models_used = list(dict.fromkeys(c.get("model", "") for c in calls))
            model_str = models_used[0] if models_used else ""

            label = f"{date_part} {time_part}  {icon} {mode}"
            top = QTreeWidgetItem([
                label,
                model_str,
                _fmt_tokens(total_in),
                _fmt_tokens(total_out),
            ])
            top.setForeground(0, QColor("#cdd6f4"))
            top.setForeground(1, QColor("#6c7086"))
            top.setForeground(2, QColor("#a6e3a1"))
            top.setForeground(3, QColor("#89b4fa"))

            for call in calls:
                ts = _fmt_ts(call.get("ts", ""))
                ctype = call.get("type", "")
                child = QTreeWidgetItem([
                    f"  {ts}  {ctype}",
                    call.get("model", ""),
                    _fmt_tokens(call.get("input", 0)),
                    _fmt_tokens(call.get("output", 0)),
                ])
                child.setForeground(0, QColor("#6c7086"))
                child.setForeground(1, QColor("#45475a"))
                child.setForeground(2, QColor("#a6e3a1"))
                child.setForeground(3, QColor("#89b4fa"))
                top.addChild(child)

            self._tree.addTopLevelItem(top)
            # Top-level collapsed by default

    # ── Drag to move ─────────────────────────────────────────────────────────
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event):
        if self._drag_pos and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)

    def mouseReleaseEvent(self, event):
        self._drag_pos = None
