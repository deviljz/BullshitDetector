"""history_window.py —— 历史记录列表窗口"""

from datetime import datetime

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)


def _relative_time(iso: str) -> str:
    try:
        dt = datetime.fromisoformat(iso)
        secs = int((datetime.now() - dt).total_seconds())
        if secs < 60:
            return "刚刚"
        elif secs < 3600:
            return f"{secs // 60} 分钟前"
        elif secs < 86400:
            return f"{secs // 3600} 小时前"
        elif secs < 86400 * 30:
            return f"{secs // 86400} 天前"
        else:
            return dt.strftime("%Y-%m-%d")
    except Exception:
        return iso


class HistoryWindow(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("历史记录")
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.WindowCloseButtonHint
        )
        self.setFixedSize(560, 640)
        self.setStyleSheet(
            "QWidget { background: #1e1e2e; color: #cdd6f4; font-family: 'Segoe UI', sans-serif; }"
        )
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(10)

        # 标题栏
        title_row = QHBoxLayout()
        title_lbl = QLabel("📋 历史记录")
        title_lbl.setStyleSheet("color: #cdd6f4; font-size: 16px; font-weight: bold;")
        title_row.addWidget(title_lbl)
        title_row.addStretch()
        clear_btn = QPushButton("清空")
        clear_btn.setFixedSize(44, 26)
        clear_btn.setStyleSheet(
            "QPushButton { background: #313244; color: #f38ba8; border-radius: 4px; font-size: 11px; }"
            "QPushButton:hover { background: #45475a; }"
        )
        clear_btn.clicked.connect(self._clear_all)
        title_row.addWidget(clear_btn)

        refresh_btn = QPushButton("刷新")
        refresh_btn.setFixedSize(44, 26)
        refresh_btn.setStyleSheet(
            "QPushButton { background: #313244; color: #a6adc8; border-radius: 4px; font-size: 11px; }"
            "QPushButton:hover { background: #45475a; }"
        )
        refresh_btn.clicked.connect(self._reload)
        title_row.addWidget(refresh_btn)
        root.addLayout(title_row)

        # 搜索栏
        self._search_bar = QLineEdit()
        self._search_bar.setPlaceholderText("搜索标题、类型…")
        self._search_bar.setStyleSheet(
            "QLineEdit { background: #313244; color: #cdd6f4; border-radius: 6px;"
            " border: 1px solid #45475a; padding: 4px 10px; font-size: 12px; }"
            "QLineEdit:focus { border-color: #89b4fa; }"
        )
        self._search_bar.textChanged.connect(self._on_search)
        root.addWidget(self._search_bar)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: #313244;")
        root.addWidget(sep)

        # 条目列表（QScrollArea 固定高度，内容可滚动）
        self._list_widget = QWidget()
        self._list_widget.setStyleSheet("background: transparent;")
        self._list_layout = QVBoxLayout(self._list_widget)
        self._list_layout.setContentsMargins(0, 0, 4, 0)
        self._list_layout.setSpacing(6)

        _scroll = QScrollArea()
        _scroll.setWidget(self._list_widget)
        _scroll.setWidgetResizable(True)
        _scroll.setFrameShape(QFrame.Shape.NoFrame)
        _scroll.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }"
            "QScrollBar:vertical { width: 6px; background: #1e1e2e; border-radius: 3px; }"
            "QScrollBar::handle:vertical { background: #45475a; border-radius: 3px; min-height: 20px; }"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }"
        )
        root.addWidget(_scroll, 1)

        self._all_entries: list = []
        self._reload()

    def _reload(self):
        import history as hs
        self._all_entries = hs.load_all()
        query = self._search_bar.text() if hasattr(self, "_search_bar") else ""
        self._render_entries(self._all_entries, query)

    def _render_entries(self, entries: list, query: str = ""):
        # 清空旧条目
        while self._list_layout.count() > 0:
            item = self._list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if query:
            q = query.lower()
            entries = [
                e for e in entries
                if q in (e.get("title") or "").lower()
                or q in (e.get("type_label") or "").lower()
                or q in (e.get("mode") or "").lower()
            ]

        if not entries:
            msg = "没有匹配的记录" if query else "暂无历史记录"
            empty = QLabel(msg)
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setStyleSheet("color: #6c7086; font-size: 13px; padding: 40px;")
            self._list_layout.addWidget(empty)
        else:
            for entry in entries:
                self._list_layout.addWidget(self._make_row(entry))

        pass  # 固定高度窗口，不需要 adjustSize

    def _on_search(self, text: str):
        self._render_entries(self._all_entries, text)

    def _make_row(self, entry: dict) -> QWidget:
        row = QFrame()
        row.setStyleSheet(
            "QFrame { background: #313244; border-radius: 8px; }"
            "QFrame:hover { background: #3a3c4e; }"
        )
        row.setCursor(Qt.CursorShape.PointingHandCursor)
        h = QHBoxLayout(row)
        h.setContentsMargins(10, 8, 8, 8)
        h.setSpacing(8)

        # 类型标签（最前）
        type_lbl = QLabel(entry.get("type_label", ""))
        type_lbl.setFixedWidth(72)
        type_lbl.setStyleSheet(
            "color: #89b4fa; font-size: 12px; font-weight: bold; background: transparent;"
        )
        h.addWidget(type_lbl)

        # 缩略图（固定宽度，紧跟类型）
        thumb_b64 = entry.get("thumbnail")
        if thumb_b64:
            try:
                import base64
                from PyQt6.QtGui import QPixmap
                px = QPixmap()
                px.loadFromData(base64.b64decode(thumb_b64))
                thumb_lbl = QLabel()
                thumb_lbl.setFixedSize(36, 36)
                thumb_lbl.setPixmap(px.scaled(36, 36,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation))
                thumb_lbl.setStyleSheet("background: #1e1e2e; border-radius: 3px;")
                thumb_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
                h.addWidget(thumb_lbl)
            except Exception:
                pass

        title = entry.get("title") or "（无标题）"
        title_lbl = QLabel(title)
        title_lbl.setStyleSheet("color: #cdd6f4; font-size: 13px; background: transparent;")
        title_lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        title_lbl.setWordWrap(False)
        title_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        h.addWidget(title_lbl, 1)

        chat_count = len(entry.get("chat", []))
        if chat_count:
            chat_lbl = QLabel(f"💬{chat_count}")
            chat_lbl.setStyleSheet("color: #6c7086; font-size: 11px; background: transparent;")
            h.addWidget(chat_lbl)

        time_lbl = QLabel(_relative_time(entry.get("timestamp", "")))
        time_lbl.setStyleSheet(
            "color: #6c7086; font-size: 11px; background: transparent;"
        )
        time_lbl.setFixedWidth(64)
        time_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        h.addWidget(time_lbl)

        del_btn = QPushButton("✕")
        del_btn.setFixedSize(22, 22)
        del_btn.setStyleSheet(
            "QPushButton { background: transparent; color: #6c7086; border: none; font-size: 11px; }"
            "QPushButton:hover { color: #f38ba8; }"
        )
        del_btn.clicked.connect(lambda _, eid=entry["id"]: self._delete(eid))
        h.addWidget(del_btn)

        row.mousePressEvent = lambda e, ent=entry: self._open_entry(ent)
        return row

    @staticmethod
    def _thumb_to_pil(thumb_b64: str):
        """base64 缩略图 → PIL Image，失败返回 None。"""
        try:
            import base64
            from io import BytesIO
            from PIL import Image
            return Image.open(BytesIO(base64.b64decode(thumb_b64)))
        except Exception:
            return None

    def _open_entry(self, entry: dict):
        from ui.result_window import ResultWindow

        thumb_b64 = entry.get("thumbnail")
        image = self._thumb_to_pil(thumb_b64) if thumb_b64 else None
        result = entry.get("result", {})
        chat = entry.get("chat", [])
        history_id = entry.get("id")

        old = getattr(self, "_result_win", None)
        if old is not None and old.isVisible():
            # 原地刷新内容，窗口不销毁重建，零闪烁
            old.reload(result=result, image=image, history_id=history_id, chat_history=chat)
        else:
            win = ResultWindow(result, position=None, image=image,
                               history_id=history_id, chat_history=chat)
            win.show()
            self._result_win = win

    def _clear_all(self):
        from PyQt6.QtWidgets import QMessageBox
        if QMessageBox.question(
            self, "确认清空", "清空全部历史记录？此操作不可撤销。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        ) == QMessageBox.StandardButton.Yes:
            import history as hs
            hs.clear_all()
            self._reload()

    def _delete(self, entry_id: str):
        import history as hs
        hs.delete(entry_id)
        self._all_entries = [e for e in self._all_entries if e.get("id") != entry_id]
        self._render_entries(self._all_entries, self._search_bar.text())
