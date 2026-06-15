from pathlib import Path
from typing import Dict, List

from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QStatusBar, QLabel, QMessageBox, QFileDialog, QToolBar
)

from . import __app_name__, __version__
from .models import VideoTask
from .task_table import TaskTableWidget
from .metadata_scanner import MetadataScanner


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{__app_name__} v{__version__}")
        self.resize(1100, 650)
        self.setAcceptDrops(True)

        self._tasks: Dict[int, VideoTask] = {}
        self._scanner = MetadataScanner(self, max_threads=8)

        self._build_ui()
        self._connect_signals()

    def _build_ui(self) -> None:
        central = QWidget(self)
        self.setCentralWidget(central)

        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(10)

        toolbar = self._create_toolbar()
        main_layout.addWidget(toolbar)

        self.table = TaskTableWidget(self)
        main_layout.addWidget(self.table, stretch=1)

        bottom_bar = self._create_bottom_bar()
        main_layout.addLayout(bottom_bar)

        status_bar = QStatusBar(self)
        self.setStatusBar(status_bar)
        self._status_label = QLabel("就绪")
        self._count_label = QLabel("任务数：0")
        status_bar.addWidget(self._status_label)
        status_bar.addPermanentWidget(self._count_label)

    def _create_toolbar(self) -> QWidget:
        bar = QWidget(self)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.btn_add_files = QPushButton("添加文件", bar)
        self.btn_add_folder = QPushButton("添加文件夹", bar)
        self.btn_remove = QPushButton("移除选中", bar)
        self.btn_clear = QPushButton("清空列表", bar)

        for btn in [self.btn_add_files, self.btn_add_folder, self.btn_remove, self.btn_clear]:
            btn.setMinimumHeight(32)
            layout.addWidget(btn)

        layout.addStretch()

        hint = QLabel("提示：可直接拖入视频文件或文件夹到列表中", bar)
        hint.setStyleSheet("color: #888;")
        layout.addWidget(hint)

        return bar

    def _create_bottom_bar(self) -> QHBoxLayout:
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)

        self.btn_start = QPushButton("开始转码（待实现）")
        self.btn_start.setMinimumHeight(36)
        self.btn_start.setMinimumWidth(140)
        self.btn_start.setEnabled(False)
        layout.addStretch()
        layout.addWidget(self.btn_start)

        return layout

    def _connect_signals(self) -> None:
        self.table.files_dropped.connect(self._on_files_dropped)
        self.btn_add_files.clicked.connect(self._on_add_files)
        self.btn_add_folder.clicked.connect(self._on_add_folder)
        self.btn_remove.clicked.connect(self._on_remove_selected)
        self.btn_clear.clicked.connect(self._on_clear)

        self._scanner.task_scanned.connect(self._on_task_scanned)
        self._scanner.scan_finished.connect(self._on_scan_finished)

    def _on_files_dropped(self, paths: List[str]) -> None:
        if not paths:
            return
        self._add_paths(paths)

    def _on_add_files(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "选择视频文件",
            "",
            "视频文件 (*.mp4 *.mkv *.avi *.mov *.wmv *.flv *.webm *.m4v *.mpg *.mpeg *.ts *.rmvb *.rm *.3gp *.vob *.ogv *.dv *.asf);;所有文件 (*.*)"
        )
        if files:
            resolved = [str(Path(f).resolve()) for f in files]
            self._add_paths(resolved)

    def _on_add_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "选择视频文件夹", "")
        if folder:
            from .task_table import VIDEO_EXTENSIONS
            collected = []
            for sub in Path(folder).rglob("*"):
                if sub.is_file() and sub.suffix.lower() in VIDEO_EXTENSIONS:
                    collected.append(str(sub.resolve()))
            if collected:
                self._add_paths(collected)
            else:
                QMessageBox.information(self, "提示", "所选文件夹中未找到支持的视频文件。")

    def _add_paths(self, paths: List[str]) -> None:
        existing = {t.file_path for t in self._tasks.values()}
        new_paths = [p for p in paths if p not in existing]
        if not new_paths:
            return

        start_row = self.table.rowCount()
        for i, path in enumerate(new_paths):
            row = start_row + i
            task = VideoTask(file_path=path, status="正在解析...")
            self._tasks[row] = task
            self.table.add_task_row(task)

        self._update_count()
        self._status_label.setText(f"正在解析 {len(new_paths)} 个文件...")
        self._scanner.scan_paths(new_paths, start_row)

    def _on_task_scanned(self, row: int, task: VideoTask) -> None:
        if row in self._tasks:
            self._tasks[row] = task
            self.table.update_task_row(row, task)
            self._update_count()

    def _on_scan_finished(self) -> None:
        self._status_label.setText("解析完成")
        ready_count = sum(1 for t in self._tasks.values() if t.status == "就绪")
        if ready_count > 0:
            self.btn_start.setEnabled(True)

    def _on_remove_selected(self) -> None:
        selected_rows = sorted({index.row() for index in self.table.selectedIndexes()}, reverse=True)
        if not selected_rows:
            return
        for row in selected_rows:
            self._tasks.pop(row, None)
        self.table.remove_selected_rows()
        self._rebuild_tasks_index()
        self._update_count()

    def _on_clear(self) -> None:
        if self.table.rowCount() == 0:
            return
        reply = QMessageBox.question(
            self, "确认清空", "确定要清空所有任务吗？",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self._tasks.clear()
            self.table.clear_tasks()
            self._update_count()
            self.btn_start.setEnabled(False)

    def _rebuild_tasks_index(self) -> None:
        new_tasks: Dict[int, VideoTask] = {}
        for new_row in range(self.table.rowCount()):
            path_item = self.table.item(new_row, 4)
            if not path_item:
                continue
            path = path_item.text()
            for task in self._tasks.values():
                if task.file_path == path:
                    new_tasks[new_row] = task
                    break
        self._tasks = new_tasks

    def _update_count(self) -> None:
        total = len(self._tasks)
        ready = sum(1 for t in self._tasks.values() if t.status == "就绪")
        parsing = sum(1 for t in self._tasks.values() if t.status == "正在解析...")
        error = sum(1 for t in self._tasks.values() if t.status == "错误")
        self._count_label.setText(f"共 {total} 个 | 就绪 {ready} | 解析中 {parsing} | 错误 {error}")

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            self.table.dropEvent(event)
        else:
            super().dropEvent(event)
