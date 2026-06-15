import json
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QObject, QProcess, Signal, Slot

from .models import VideoMetadata


class FFProbeClient(QObject):
    metadata_ready = Signal(object)
    metadata_error = Signal(str)

    _ERROR_MESSAGES = {
        QProcess.FailedToStart: "无法启动 FFprobe，请确认已安装并添加到 PATH",
        QProcess.Crashed: "FFprobe 进程崩溃",
        QProcess.Timedout: "FFprobe 进程超时",
        QProcess.WriteError: "FFprobe 写入错误",
        QProcess.ReadError: "FFprobe 读取错误",
    }

    def __init__(
        self,
        parent: Optional[QObject] = None,
        ffprobe_path: str = r"D:\soft\ffmpeg-8.1.1-essentials_build\bin\ffprobe.exe",
    ):
        super().__init__(parent)
        self._ffprobe_path = ffprobe_path
        self._process: Optional[QProcess] = None
        self._current_file: str = ""
        self._stdout_buffer = ""
        self._stderr_buffer = ""
        self._error_handled = False

    @property
    def is_running(self) -> bool:
        return self._process is not None and self._process.state() != QProcess.NotRunning

    def probe(self, file_path: str) -> None:
        if self.is_running:
            self.stop()

        self._current_file = file_path
        self._stdout_buffer = ""
        self._stderr_buffer = ""
        self._error_handled = False

        args = [
            "-v", "quiet",
            "-print_format", "json",
            "-show_format",
            "-show_streams",
            file_path,
        ]

        self._process = QProcess(self)
        self._process.setProcessChannelMode(QProcess.SeparateChannels)
        self._process.readyReadStandardOutput.connect(self._on_ready_read_stdout)
        self._process.readyReadStandardError.connect(self._on_ready_read_stderr)
        self._process.finished.connect(self._on_finished)
        self._process.errorOccurred.connect(self._on_error)

        self._process.start(self._ffprobe_path, args)

    def stop(self) -> None:
        if self.is_running:
            self._process.kill()
            self._process.waitForFinished(3000)

    @Slot()
    def _on_ready_read_stdout(self) -> None:
        if not self._process:
            return
        data = self._process.readAllStandardOutput().data()
        text = data.decode("utf-8", errors="replace")
        self._stdout_buffer += text

    @Slot()
    def _on_ready_read_stderr(self) -> None:
        if not self._process:
            return
        data = self._process.readAllStandardError().data()
        text = data.decode("utf-8", errors="replace")
        self._stderr_buffer += text

    @Slot(int, QProcess.ExitStatus)
    def _on_finished(self, exit_code: int, exit_status: QProcess.ExitStatus) -> None:
        if self._error_handled:
            return

        if exit_status == QProcess.CrashExit:
            stderr = self._collect_stderr()
            msg = "FFprobe 进程崩溃"
            if stderr:
                msg += f": {stderr[:200]}"
            self._emit_error(msg)
            return

        if exit_code != 0:
            stderr = self._collect_stderr()
            self._emit_error(f"FFprobe 退出码 {exit_code}: {stderr[:200]}")
            return

        try:
            raw_data = json.loads(self._stdout_buffer.strip())
            metadata = VideoMetadata(
                file_path=self._current_file,
                raw_data=raw_data,
                error=None,
            )
            self.metadata_ready.emit(metadata)
        except json.JSONDecodeError as e:
            self._emit_error(f"解析 FFprobe 输出失败: {e}")
        except Exception as e:
            self._emit_error(f"处理元数据失败: {e}")

    def _collect_stderr(self) -> str:
        if self._process:
            remaining = self._process.readAllStandardError().data().decode("utf-8", errors="replace")
            self._stderr_buffer += remaining
        return self._stderr_buffer.strip()

    @Slot(QProcess.ProcessError)
    def _on_error(self, error: QProcess.ProcessError) -> None:
        self._error_handled = True
        msg = self._ERROR_MESSAGES.get(error, f"FFprobe 未知错误 ({error})")
        self._emit_error(msg)

    def _emit_error(self, msg: str) -> None:
        metadata = VideoMetadata(
            file_path=self._current_file,
            raw_data={},
            error=msg,
        )
        self.metadata_error.emit(msg)
        self.metadata_ready.emit(metadata)
