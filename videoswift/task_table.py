from pathlib import Path
from typing import List, Optional

from PySide6.QtCore import Qt, Signal, QMimeData
from PySide6.QtGui import QDragEnterEvent, QDropEvent, QDragMoveEvent
from PySide6.QtWidgets import QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView

from .models import VideoTask, VIDEO_EXTENSIONS


COLUMN_LABELS = ["状态", "文件名", "大小", "格式", "绝对路径"]


class TaskTableWidget(QTableWidget):
    files_dropped = Signal(list)

    def __init__(self, parent=None):
        super().__init__(0, len(COLUMN_LABELS), parent)
        self.setHorizontalHeaderLabels(COLUMN_LABELS)
        self.setAlternatingRowColors(True)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.setAcceptDrops(True)
        self.setDragDropMode(QAbstractItemView.DropOnly)
        self.verticalHeader().setDefaultSectionSize(28)

        header = self.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.Stretch)

        self._existing_paths: set[str] = set()
        self._drag_hover_inside = False

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self._drag_hover_inside = True
            self.update()
        else:
            event.ignore()

    def dragMoveEvent(self, event: QDragMoveEvent) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragLeaveEvent(self, event) -> None:
        self._drag_hover_inside = False
        self.update()
        super().dragLeaveEvent(event)

    def dropEvent(self, event: QDropEvent) -> None:
        self._drag_hover_inside = False
        self.update()
        mime_data: QMimeData = event.mimeData()
        if not mime_data.hasUrls():
            event.ignore()
            return

        collected: List[str] = []
        for url in mime_data.urls():
            if not url.isLocalFile():
                continue
            raw_path = url.toLocalFile()
            collected.extend(self._expand_path(raw_path))

        new_paths = [p for p in collected if p not in self._existing_paths]
        if new_paths:
            for p in new_paths:
                self._existing_paths.add(p)
            self.files_dropped.emit(new_paths)

        event.acceptProposedAction()

    def _expand_path(self, raw_path: str) -> List[str]:
        p = Path(raw_path)
        results: List[str] = []
        try:
            if p.is_dir():
                for sub in p.rglob("*"):
                    if sub.is_file() and sub.suffix.lower() in VIDEO_EXTENSIONS:
                        results.append(str(sub.resolve()))
            elif p.is_file():
                if p.suffix.lower() in VIDEO_EXTENSIONS:
                    results.append(str(p.resolve()))
        except OSError:
            pass
        return results

    def add_task_row(self, task: VideoTask) -> int:
        row = self.rowCount()
        self.insertRow(row)
        self._update_row(row, task)
        return row

    def update_task_row(self, row: int, task: VideoTask) -> None:
        if 0 <= row < self.rowCount():
            self._update_row(row, task)

    def _update_row(self, row: int, task: VideoTask) -> None:
        status_item = QTableWidgetItem(task.status)
        name_item = QTableWidgetItem(task.file_name or Path(task.file_path).name)
        size_item = QTableWidgetItem(VideoTask.format_size(task.file_size))
        ext_item = QTableWidgetItem(task.extension.lstrip(".").upper())
        path_item = QTableWidgetItem(task.file_path)

        for col, item in enumerate([status_item, name_item, size_item, ext_item, path_item]):
            item.setTextAlignment(Qt.AlignVCenter | (Qt.AlignHCenter if col in (0, 2, 3) else Qt.AlignLeft))
            if task.status == "错误":
                item.setForeground(Qt.red)
            self.setItem(row, col, item)

    def clear_tasks(self) -> None:
        self.setRowCount(0)
        self._existing_paths.clear()

    def remove_selected_rows(self) -> None:
        rows = sorted({index.row() for index in self.selectedIndexes()}, reverse=True)
        for row in rows:
            path_item = self.item(row, 4)
            if path_item:
                self._existing_paths.discard(path_item.text())
            self.removeRow(row)
