from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


VIDEO_EXTENSIONS = {
    ".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm",
    ".m4v", ".mpg", ".mpeg", ".ts", ".rmvb", ".rm", ".3gp",
    ".vob", ".ogv", ".dv", ".asf"
}


OUTPUT_FORMATS = {".mp4", ".mkv", ".avi"}


@dataclass
class VideoTask:
    file_path: str
    file_name: str = ""
    file_size: int = 0
    extension: str = ""
    status: str = "等待解析"
    duration: Optional[float] = None
    error: Optional[str] = None
    output_format: str = ""
    progress: int = 0

    def resolve_basic(self) -> None:
        p = Path(self.file_path)
        self.file_name = p.name
        self.extension = p.suffix.lower()
        try:
            self.file_size = p.stat().st_size
        except OSError:
            self.file_size = 0
            self.error = "无法读取文件"
            self.status = "失败"

    @property
    def is_video(self) -> bool:
        return self.extension in VIDEO_EXTENSIONS

    @staticmethod
    def format_size(size_bytes: int) -> str:
        if size_bytes <= 0:
            return "0 B"
        units = ["B", "KB", "MB", "GB", "TB"]
        idx = 0
        size = float(size_bytes)
        while size >= 1024.0 and idx < len(units) - 1:
            size /= 1024.0
            idx += 1
        return f"{size:.2f} {units[idx]}"
