from concurrent.futures import ThreadPoolExecutor, Future
from typing import Callable, Dict, Optional

from PySide6.QtCore import QObject, Signal, QRunnable, QThreadPool, Slot

from .models import VideoTask


class _ScanRunnable(QRunnable):
    def __init__(self, path: str, row: int, callback: Callable[[int, VideoTask], None]):
        super().__init__()
        self._path = path
        self._row = row
        self._callback = callback
        self.setAutoDelete(True)

    @Slot()
    def run(self) -> None:
        task = VideoTask(file_path=self._path)
        try:
            task.resolve_basic()
            if task.is_video and not task.error:
                task.status = "就绪"
            elif not task.is_video:
                task.status = "非视频"
                task.error = "不支持的文件格式"
        except Exception as e:
            task.status = "错误"
            task.error = str(e)
        self._callback(self._row, task)


class MetadataScanner(QObject):
    task_scanned = Signal(int, object)
    scan_finished = Signal()

    def __init__(self, parent: Optional[QObject] = None, max_threads: int = 8):
        super().__init__(parent)
        self._max_threads = max_threads
        self._thread_pool = QThreadPool.globalInstance()
        self._thread_pool.setMaxThreadCount(max_threads)
        self._pending_count = 0
        self._lock = False

    @Slot()
    def _on_task_done(self, row: int, task: VideoTask) -> None:
        self.task_scanned.emit(row, task)
        self._pending_count -= 1
        if self._pending_count <= 0:
            self.scan_finished.emit()

    def scan_paths(self, paths: list[str], start_row: int) -> int:
        count = len(paths)
        for i, path in enumerate(paths):
            row = start_row + i
            self._pending_count += 1
            runnable = _ScanRunnable(path, row, self._on_task_done)
            self._thread_pool.start(runnable)
        return count

    def active_count(self) -> int:
        return self._pending_count

    def wait_for_done(self) -> None:
        self._thread_pool.waitForDone()
