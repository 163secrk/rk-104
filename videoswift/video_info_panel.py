from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTreeWidget, QTreeWidgetItem,
    QPushButton, QFrame
)

from .models import VideoMetadata, VideoTask
from .ffprobe_client import FFProbeClient


class VideoInfoPanel(QWidget):
    close_requested = Signal()

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._ffprobe = FFProbeClient(self)
        self._current_task: Optional[VideoTask] = None
        self._build_ui()
        self._connect_signals()
        self.setMinimumWidth(340)
        self.setMaximumWidth(420)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = self._build_header()
        layout.addWidget(header)

        separator = QFrame(self)
        separator.setFrameShape(QFrame.HLine)
        separator.setFrameShadow(QFrame.Sunken)
        separator.setStyleSheet("color: #ddd;")
        layout.addWidget(separator)

        self.tree = QTreeWidget(self)
        self.tree.setHeaderLabels(["属性", "值"])
        self.tree.setColumnWidth(0, 130)
        self.tree.setAlternatingRowColors(True)
        self.tree.setRootIsDecorated(True)
        self.tree.setStyleSheet("""
            QTreeWidget {
                border: none;
                background: #fafafa;
            }
            QTreeWidget::item {
                padding: 4px 8px;
                min-height: 24px;
            }
            QTreeWidget::item:selected {
                background: #e8f0fe;
                color: #1a73e8;
            }
            QTreeWidget::branch:has-children:!has-siblings:closed,
            QTreeWidget::branch:closed:has-children:has-siblings {
                image: none;
            }
            QTreeWidget::branch:open:has-children:!has-siblings,
            QTreeWidget::branch:open:has-children:has-siblings {
                image: none;
            }
        """)
        self.tree.setFont(QFont("Microsoft YaHei", 9))
        layout.addWidget(self.tree, stretch=1)

        footer = self._build_footer()
        layout.addWidget(footer)

    def _build_header(self) -> QWidget:
        header = QWidget(self)
        header.setStyleSheet("background: #f5f5f5; padding: 8px;")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(12, 8, 8, 8)
        header_layout.setSpacing(8)

        title_label = QLabel("视频详细信息", header)
        title_font = QFont("Microsoft YaHei", 11)
        title_font.setBold(True)
        title_label.setFont(title_font)
        title_label.setStyleSheet("color: #333;")
        header_layout.addWidget(title_label)

        header_layout.addStretch()

        self.btn_refresh = QPushButton("刷新", header)
        self.btn_refresh.setMinimumHeight(28)
        self.btn_refresh.setMinimumWidth(60)
        self.btn_refresh.setStyleSheet("""
            QPushButton {
                background: #1a73e8;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 4px 12px;
            }
            QPushButton:hover {
                background: #1557b0;
            }
            QPushButton:disabled {
                background: #9ab8e8;
            }
        """)
        header_layout.addWidget(self.btn_refresh)

        self.btn_close = QPushButton("×", header)
        self.btn_close.setFixedSize(28, 28)
        self.btn_close.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #666;
                border: none;
                border-radius: 4px;
                font-size: 18px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: #e0e0e0;
                color: #333;
            }
        """)
        header_layout.addWidget(self.btn_close)

        return header

    def _build_footer(self) -> QWidget:
        footer = QWidget(self)
        footer.setStyleSheet("background: #f5f5f5; padding: 6px;")
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(12, 6, 12, 6)

        self.status_label = QLabel("", footer)
        self.status_label.setStyleSheet("color: #666; font-size: 9pt;")
        self.status_label.setWordWrap(True)
        footer_layout.addWidget(self.status_label)

        return footer

    def _connect_signals(self) -> None:
        self.btn_close.clicked.connect(self.close_requested.emit)
        self.btn_refresh.clicked.connect(self._on_refresh)
        self._ffprobe.metadata_ready.connect(self._on_metadata_ready)
        self._ffprobe.metadata_error.connect(self._on_metadata_error)

    def set_task(self, task: VideoTask) -> None:
        self._current_task = task
        self.btn_refresh.setEnabled(True)
        self._clear_tree()
        self._show_loading(task.file_name)
        self._ffprobe.probe(task.file_path)

    def _on_refresh(self) -> None:
        if self._current_task:
            self._clear_tree()
            self._show_loading(self._current_task.file_name)
            self._ffprobe.probe(self._current_task.file_path)

    def _show_loading(self, file_name: str) -> None:
        self.status_label.setText(f"正在分析：{file_name}")
        loading_item = QTreeWidgetItem(["正在读取视频信息...", ""])
        loading_item.setForeground(0, Qt.gray)
        loading_item.setForeground(1, Qt.gray)
        loading_font = QFont("Microsoft YaHei", 9)
        loading_font.setItalic(True)
        loading_item.setFont(0, loading_font)
        self.tree.addTopLevelItem(loading_item)

    def _clear_tree(self) -> None:
        self.tree.clear()

    def _on_metadata_ready(self, metadata: VideoMetadata) -> None:
        self._clear_tree()

        if metadata.error:
            self._show_error(metadata.error)
            return

        display_data = metadata.get_display_data()
        has_data = False

        for section_name, fields in display_data.items():
            section_item = QTreeWidgetItem([section_name, ""])
            section_font = QFont("Microsoft YaHei", 10)
            section_font.setBold(True)
            section_item.setFont(0, section_font)
            section_item.setForeground(0, Qt.darkBlue)
            section_item.setExpanded(True)

            has_section_data = False
            for field_name, value in fields.items():
                if value:
                    field_item = QTreeWidgetItem([field_name, str(value)])
                    field_item.setToolTip(1, str(value))
                    section_item.addChild(field_item)
                    has_section_data = True
                    has_data = True

            if has_section_data:
                self.tree.addTopLevelItem(section_item)

        if not has_data:
            self._show_error("未获取到有效的视频信息")
        else:
            self.status_label.setText("分析完成")

    def _on_metadata_error(self, error_msg: str) -> None:
        self._show_error(error_msg)

    def _show_error(self, error_msg: str) -> None:
        self._clear_tree()
        error_item = QTreeWidgetItem(["错误", error_msg])
        error_item.setForeground(0, Qt.red)
        error_item.setForeground(1, Qt.red)
        self.tree.addTopLevelItem(error_item)
        self.status_label.setText(f"分析失败：{error_msg[:40]}...")

    def clear_panel(self) -> None:
        self._current_task = None
        self._clear_tree()
        self.btn_refresh.setEnabled(False)
        self.status_label.setText("请选择一个视频文件查看详细信息")
        hint_item = QTreeWidgetItem(["提示", "点击左侧列表中的视频文件"])
        hint_item.setForeground(0, Qt.gray)
        hint_item.setForeground(1, Qt.gray)
        self.tree.addTopLevelItem(hint_item)
