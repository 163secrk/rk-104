import re
from pathlib import Path
from typing import Dict, List, Optional

from PySide6.QtCore import QObject, QProcess, Signal, Slot

from .models import VideoTask


class TranscodeWorker(QObject):
    task_progress = Signal(int, int)
    task_finished = Signal(int, int)
    task_error = Signal(int, str)

    _ERROR_MESSAGES = {
        QProcess.FailedToStart: "无法启动 FFmpeg，请确认已安装并添加到 PATH",
        QProcess.Crashed: "FFmpeg 进程崩溃",
        QProcess.Timedout: "FFmpeg 进程超时",
        QProcess.WriteError: "FFmpeg 写入错误",
        QProcess.ReadError: "FFmpeg 读取错误",
    }

    def __init__(self, row: int, task: VideoTask, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._row = row
        self._task = task
        self._process: Optional[QProcess] = None
        self._duration: Optional[float] = task.duration
        self._stdout_buffer = ""
        self._stderr_buffer = ""
        self._error_handled = False

    @property
    def row(self) -> int:
        return self._row

    @property
    def is_running(self) -> bool:
        return self._process is not None and self._process.state() != QProcess.NotRunning

    def start(self, ffmpeg_path: str = "ffmpeg") -> None:
        input_path = self._task.file_path
        output_path = self._build_output_path()

        output_dir = Path(output_path).parent
        output_dir.mkdir(parents=True, exist_ok=True)

        args = [
            "-y",
            "-i", input_path,
            "-progress", "pipe:1",
            "-nostats",
            "-loglevel", "warning",
            output_path,
        ]

        self._process = QProcess(self)
        self._process.setProcessChannelMode(QProcess.SeparateChannels)
        self._process.readyReadStandardOutput.connect(self._on_ready_read)
        self._process.readyReadStandardError.connect(self._on_ready_read_stderr)
        self._process.finished.connect(self._on_finished)
        self._process.errorOccurred.connect(self._on_error)

        self._process.start(ffmpeg_path, args)

    def stop(self) -> None:
        if self.is_running:
            self._process.kill()
            self._process.waitForFinished(3000)

    def _build_output_path(self) -> str:
        p = Path(self._task.file_path)
        output_ext = self._task.output_format or ".mp4"
        return str(p.with_stem(p.stem + "_转码").with_suffix(output_ext))

    @Slot()
    def _on_ready_read(self) -> None:
        if not self._process:
            return
        data = self._process.readAllStandardOutput().data()
        text = data.decode("utf-8", errors="replace")
        self._stdout_buffer += text

        while "\n" in self._stdout_buffer:
            line, self._stdout_buffer = self._stdout_buffer.split("\n", 1)
            self._parse_line(line.strip())

    @Slot()
    def _on_ready_read_stderr(self) -> None:
        if not self._process:
            return
        data = self._process.readAllStandardError().data()
        self._stderr_buffer += data.decode("utf-8", errors="replace")

    def _parse_line(self, line: str) -> None:
        out_time_match = re.match(r"^out_time_us=(\d+)$", line)
        if out_time_match and self._duration and self._duration > 0:
            out_time_us = int(out_time_match.group(1))
            out_time_s = out_time_us / 1_000_000.0
            progress = min(100, int(out_time_s / self._duration * 100))
            self.task_progress.emit(self._row, progress)

    @Slot(int, QProcess.ExitStatus)
    def _on_finished(self, exit_code: int, exit_status: QProcess.ExitStatus) -> None:
        if self._error_handled:
            return

        if exit_status == QProcess.CrashExit:
            stderr = self._collect_stderr()
            msg = "FFmpeg 进程崩溃"
            if stderr:
                msg += f": {stderr[:200]}"
            self.task_error.emit(self._row, msg)
            return

        if exit_code != 0:
            stderr = self._collect_stderr()
            self.task_error.emit(self._row, f"FFmpeg 退出码 {exit_code}: {stderr[:200]}")
            return

        self.task_progress.emit(self._row, 100)
        self.task_finished.emit(self._row, exit_code)

    def _collect_stderr(self) -> str:
        if self._process:
            remaining = self._process.readAllStandardError().data().decode("utf-8", errors="replace")
            self._stderr_buffer += remaining
        return self._stderr_buffer.strip()

    @Slot(QProcess.ProcessError)
    def _on_error(self, error: QProcess.ProcessError) -> None:
        self._error_handled = True
        msg = self._ERROR_MESSAGES.get(error, f"FFmpeg 未知错误 ({error})")
        self.task_error.emit(self._row, msg)


class TranscodeScheduler(QObject):
    task_started = Signal(int)
    task_progress = Signal(int, int)
    task_completed = Signal(int)
    task_failed = Signal(int, str)
    all_completed = Signal()

    def __init__(self, parent: Optional[QObject] = None, max_concurrent: int = 1, ffmpeg_path: str = "ffmpeg"):
        super().__init__(parent)
        self._max_concurrent = max(1, max_concurrent)
        self._ffmpeg_path = ffmpeg_path
        self._queue: List[int] = []
        self._workers: Dict[int, TranscodeWorker] = {}
        self._tasks: Dict[int, VideoTask] = {}
        self._running_count = 0
        self._total_count = 0
        self._completed_count = 0
        self._is_running = False

    @property
    def is_running(self) -> bool:
        return self._is_running

    def start(self, tasks: Dict[int, VideoTask], output_format: str) -> None:
        if self._is_running:
            return

        self._tasks = {}
        self._queue = []
        self._completed_count = 0
        self._running_count = 0

        for row, task in tasks.items():
            if task.status != "就绪":
                continue
            task.output_format = output_format
            task.status = "排队中"
            task.progress = 0
            self._tasks[row] = task
            self._queue.append(row)

        self._total_count = len(self._queue)
        if self._total_count == 0:
            return

        self._is_running = True
        self._schedule_next()

    def stop(self) -> None:
        self._queue.clear()
        for worker in list(self._workers.values()):
            worker.stop()
        self._is_running = False

    def _schedule_next(self) -> None:
        while self._queue and self._running_count < self._max_concurrent:
            row = self._queue.pop(0)
            task = self._tasks.get(row)
            if not task:
                continue
            self._start_worker(row, task)

        if not self._queue and self._running_count == 0 and self._is_running:
            self._is_running = False
            self.all_completed.emit()

    def _start_worker(self, row: int, task: VideoTask) -> None:
        task.status = "转码中"
        task.progress = 0

        worker = TranscodeWorker(row, task, self)
        worker.task_progress.connect(self._on_worker_progress)
        worker.task_finished.connect(self._on_worker_finished)
        worker.task_error.connect(self._on_worker_error)

        self._workers[row] = worker
        self._running_count += 1

        self.task_started.emit(row)
        worker.start(self._ffmpeg_path)

    @Slot(int, int)
    def _on_worker_progress(self, row: int, progress: int) -> None:
        task = self._tasks.get(row)
        if task:
            task.progress = progress
        self.task_progress.emit(row, progress)

    @Slot(int, int)
    def _on_worker_finished(self, row: int, exit_code: int) -> None:
        task = self._tasks.get(row)
        if task:
            task.status = "完成"
            task.progress = 100
        self._cleanup_worker(row)
        self.task_completed.emit(row)
        self._completed_count += 1
        self._schedule_next()

    @Slot(int, str)
    def _on_worker_error(self, row: int, error_msg: str) -> None:
        task = self._tasks.get(row)
        if task:
            task.status = "错误"
            task.error = error_msg
        self._cleanup_worker(row)
        self.task_failed.emit(row, error_msg)
        self._completed_count += 1
        self._schedule_next()

    def _cleanup_worker(self, row: int) -> None:
        worker = self._workers.pop(row, None)
        if worker:
            worker.deleteLater()
        self._running_count -= 1
