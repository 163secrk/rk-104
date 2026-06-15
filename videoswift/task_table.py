from pathlib import Path
from typing import List, Optional

from PySide6.QtCore import Qt, Signal, QMimeData
from PySide6.QtGui import QDragEnterEvent, QDropEvent, QDragMoveEvent
from PySide6.QtWidgets import (
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView, QProgressBar
)

from .models import VideoTask, VIDEO_EXTENSIONS


COLUMN_LABELS = ["状态", "文件名", "大小", "格式", "进度", "绝对路径"]
STATUS_COLUMN = 0
NAME_COLUMN = 1
SIZE_COLUMN = 2
EXT_COLUMN = 3
PROGRESS_COLUMN = 4
PATH_COLUMN = 5


class TaskTableWidget(QTableWidget):
    files_dropped = Signal(list)
    row_clicked = Signal(int, object)
    row_double_clicked = Signal(int, object)

    def __init__(self, parent=None):
        super().__init__(0, len(COLUMN_LABELS), parent)
        self.setHorizontalHeaderLabels(COLUMN_LABELS)
        self.setAlternatingRowColors(True)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.setAcceptDrops(True)
        self.setDragDropMode(QAbstractItemView.DropOnly)
        self.verticalHeader().setDefaultSectionSize(30)

        self._tasks: dict[int, VideoTask] = {}
        self.clicked.connect(self._on_clicked)
        self.doubleClicked.connect(self._on_double_clicked)

        header = self.horizontalHeader()
        header.setSectionResizeMode(STATUS_COLUMN, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(NAME_COLUMN, QHeaderView.Stretch)
        header.setSectionResizeMode(SIZE_COLUMN, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(EXT_COLUMN, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(PROGRESS_COLUMN, QHeaderView.Interactive)
        self.setColumnWidth(PROGRESS_COLUMN, 180)
        header.setSectionResizeMode(PATH_COLUMN, QHeaderView.Stretch)

        self._existing_paths: set[str] = set()
        self._drag_hover_inside = False
        self._progress_bars: dict[int, QProgressBar] = {}

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

    def _create_progress_bar(self) -> QProgressBar:
        bar = QProgressBar()
        bar.setRange(0, 100)
        bar.setValue(0)
        bar.setTextVisible(True)
        bar.setFormat("%p%")
        bar.setStyleSheet("""
            QProgressBar {
                border: 1px solid #bbb;
                border-radius: 4px;
                text-align: center;
                background: #f5f5f5;
                height: 20px;
            }
            QProgressBar::chunk {
                background: #4a90e2;
                border-radius: 3px;
            }
        """)
        return bar

    def add_task_row(self, task: VideoTask) -> int:
        row = self.rowCount()
        self.insertRow(row)
        self._tasks[row] = task

        progress_bar = self._create_progress_bar()
        self._progress_bars[row] = progress_bar
        self.setCellWidget(row, PROGRESS_COLUMN, progress_bar)

        self._update_row(row, task)
        return row

    def _on_clicked(self, index) -> None:
        row = index.row()
        task = self._tasks.get(row)
        if task:
            self.row_clicked.emit(row, task)

    def _on_double_clicked(self, index) -> None:
        row = index.row()
        task = self._tasks.get(row)
        if task:
            self.row_double_clicked.emit(row, task)

    def update_task_row(self, row: int, task: VideoTask) -> None:
        if 0 <= row < self.rowCount():
            self._tasks[row] = task
            self._update_row(row, task)

    def _apply_row_style(self, row: int, is_error: bool) -> None:
        for col in range(self.columnCount()):
            item = self.item(row, col)
            if item:
                if is_error:
                    item.setForeground(Qt.red)
                else:
                    item.setForeground(Qt.black)

    def _update_row(self, row: int, task: VideoTask) -> None:
        status_item = QTableWidgetItem(task.status)
        if (task.status == "失败" or task.status == "错误") and task.error:
            status_item.setToolTip(task.error)
        name_item = QTableWidgetItem(task.file_name or Path(task.file_path).name)
        size_item = QTableWidgetItem(VideoTask.format_size(task.file_size))
        ext_item = QTableWidgetItem(task.extension.lstrip(".").upper())
        path_item = QTableWidgetItem(task.file_path)

        items = [status_item, name_item, size_item, ext_item, path_item]
        cols = [STATUS_COLUMN, NAME_COLUMN, SIZE_COLUMN, EXT_COLUMN, PATH_COLUMN]

        for col, item in zip(cols, items):
            item.setTextAlignment(
                Qt.AlignVCenter | (Qt.AlignHCenter if col in (STATUS_COLUMN, SIZE_COLUMN, EXT_COLUMN) else Qt.AlignLeft)
            )
            self.setItem(row, col, item)

        is_error = task.status in ("失败", "错误")
        self._apply_row_style(row, is_error)

        progress_bar = self._progress_bars.get(row)
        if progress_bar is None:
            progress_bar = self._create_progress_bar()
            self._progress_bars[row] = progress_bar
            self.setCellWidget(row, PROGRESS_COLUMN, progress_bar)
        progress_bar.setValue(task.progress)

        if task.status == "已完成" or task.progress == 100:
            progress_bar.setStyleSheet("""
                QProgressBar {
                    border: 1px solid #bbb;
                    border-radius: 4px;
                    text-align: center;
                    background: #f5f5f5;
                    height: 20px;
                }
                QProgressBar::chunk {
                    background: #5cb85c;
                    border-radius: 3px;
                }
            """)
        elif task.status in ("失败", "错误"):
            progress_bar.setStyleSheet("""
                QProgressBar {
                    border: 1px solid #bbb;
                    border-radius: 4px;
                    text-align: center;
                    background: #f5f5f5;
                    height: 20px;
                }
                QProgressBar::chunk {
                    background: #d9534f;
                    border-radius: 3px;
                }
            """)
        else:
            progress_bar.setStyleSheet("""
                QProgressBar {
                    border: 1px solid #bbb;
                    border-radius: 4px;
                    text-align: center;
                    background: #f5f5f5;
                    height: 20px;
                }
                QProgressBar::chunk {
                    background: #4a90e2;
                    border-radius: 3px;
                }
            """)

    def clear_tasks(self) -> None:
        self._progress_bars.clear()
        self._tasks.clear()
        self.setRowCount(0)
        self._existing_paths.clear()

    def remove_selected_rows(self) -> None:
        rows = sorted({index.row() for index in self.selectedIndexes()}, reverse=True)
        for row in rows:
            path_item = self.item(row, PATH_COLUMN)
            if path_item:
                self._existing_paths.discard(path_item.text())
            self._progress_bars.pop(row, None)
            self._tasks.pop(row, None)
            self.removeRow(row)
        self._rebuild_progress_bars()
        self._rebuild_tasks_index()

    def _rebuild_progress_bars(self) -> None:
        new_bars: dict[int, QProgressBar] = {}
        for new_row in range(self.rowCount()):
            bar = self.cellWidget(new_row, PROGRESS_COLUMN)
            if isinstance(bar, QProgressBar):
                new_bars[new_row] = bar
        self._progress_bars = new_bars

    def _rebuild_tasks_index(self) -> None:
        new_tasks: dict[int, VideoTask] = {}
        for new_row in range(self.rowCount()):
            path_item = self.item(new_row, PATH_COLUMN)
            if not path_item:
                continue
            path = path_item.text()
            for task in self._tasks.values():
                if task.file_path == path:
                    new_tasks[new_row] = task
                    break
        self._tasks = new_tasks
