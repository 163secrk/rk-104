from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Dict, Any


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


@dataclass
class VideoMetadata:
    file_path: str
    raw_data: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None

    @property
    def video_codec(self) -> Optional[str]:
        for stream in self.raw_data.get("streams", []):
            if stream.get("codec_type") == "video":
                codec_name = stream.get("codec_name", "")
                codec_long_name = stream.get("codec_long_name", "")
                if codec_name == "h264":
                    return "H.264 (AVC)"
                elif codec_name == "hevc":
                    return "H.265 (HEVC)"
                elif codec_name == "vp9":
                    return "VP9"
                elif codec_name == "av1":
                    return "AV1"
                elif codec_long_name:
                    return codec_long_name
                elif codec_name:
                    return codec_name.upper()
        return None

    @property
    def pixel_format(self) -> Optional[str]:
        for stream in self.raw_data.get("streams", []):
            if stream.get("codec_type") == "video":
                return stream.get("pix_fmt")
        return None

    @property
    def video_resolution(self) -> Optional[str]:
        for stream in self.raw_data.get("streams", []):
            if stream.get("codec_type") == "video":
                width = stream.get("width")
                height = stream.get("height")
                if width and height:
                    return f"{width} × {height}"
        return None

    @property
    def frame_rate(self) -> Optional[str]:
        for stream in self.raw_data.get("streams", []):
            if stream.get("codec_type") == "video":
                r_frame_rate = stream.get("r_frame_rate", "")
                if r_frame_rate and "/" in r_frame_rate:
                    num, den = map(int, r_frame_rate.split("/"))
                    if den != 0:
                        fps = num / den
                        return f"{fps:.2f} fps"
                elif r_frame_rate:
                    return f"{r_frame_rate} fps"
        return None

    @property
    def bitrate(self) -> Optional[str]:
        br = self.raw_data.get("format", {}).get("bit_rate")
        if br:
            try:
                br_int = int(br)
                if br_int >= 1000000:
                    return f"{br_int / 1000000:.2f} Mbps"
                elif br_int >= 1000:
                    return f"{br_int / 1000:.2f} kbps"
                else:
                    return f"{br_int} bps"
            except (ValueError, TypeError):
                return None
        return None

    @property
    def audio_codec(self) -> Optional[str]:
        for stream in self.raw_data.get("streams", []):
            if stream.get("codec_type") == "audio":
                codec_name = stream.get("codec_name", "")
                codec_long_name = stream.get("codec_long_name", "")
                if codec_long_name:
                    return codec_long_name
                elif codec_name:
                    return codec_name.upper()
        return None

    @property
    def sample_rate(self) -> Optional[str]:
        for stream in self.raw_data.get("streams", []):
            if stream.get("codec_type") == "audio":
                sr = stream.get("sample_rate")
                if sr:
                    try:
                        sr_int = int(sr)
                        return f"{sr_int} Hz"
                    except (ValueError, TypeError):
                        return None
        return None

    @property
    def audio_channels(self) -> Optional[str]:
        for stream in self.raw_data.get("streams", []):
            if stream.get("codec_type") == "audio":
                channels = stream.get("channels")
                channel_layout = stream.get("channel_layout")
                if channel_layout:
                    return channel_layout
                elif channels:
                    return f"{channels} 声道"
        return None

    @property
    def duration(self) -> Optional[str]:
        d = self.raw_data.get("format", {}).get("duration")
        if d:
            try:
                seconds = float(d)
                hours = int(seconds // 3600)
                minutes = int((seconds % 3600) // 60)
                secs = seconds % 60
                if hours > 0:
                    return f"{hours}:{minutes:02d}:{secs:06.3f}"
                else:
                    return f"{minutes}:{secs:06.3f}"
            except (ValueError, TypeError):
                return None
        return None

    @property
    def format_name(self) -> Optional[str]:
        fmt = self.raw_data.get("format", {})
        name = fmt.get("format_name")
        long_name = fmt.get("format_long_name")
        if long_name:
            return long_name
        return name

    def get_display_data(self) -> Dict[str, Dict[str, Optional[str]]]:
        return {
            "文件信息": {
                "文件路径": self.file_path,
                "容器格式": self.format_name,
                "时长": self.duration,
                "总码率": self.bitrate,
            },
            "视频流": {
                "编码器": self.video_codec,
                "像素格式": self.pixel_format,
                "分辨率": self.video_resolution,
                "帧率": self.frame_rate,
            },
            "音频流": {
                "编码器": self.audio_codec,
                "采样率": self.sample_rate,
                "声道": self.audio_channels,
            },
        }
