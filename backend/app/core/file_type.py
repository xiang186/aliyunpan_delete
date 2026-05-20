"""
File type classification utilities.
"""
from enum import Enum


class FileType(str, Enum):
    VIDEO = "video"
    IMAGE = "image"
    AUDIO = "audio"
    DOCUMENT = "document"
    ARCHIVE = "archive"
    OTHER = "other"


FILE_TYPE_MAP: dict[str, FileType] = {
    # 视频
    "mp4": FileType.VIDEO,
    "mkv": FileType.VIDEO,
    "avi": FileType.VIDEO,
    "mov": FileType.VIDEO,
    "wmv": FileType.VIDEO,
    "flv": FileType.VIDEO,
    "webm": FileType.VIDEO,
    "m4v": FileType.VIDEO,
    "ts": FileType.VIDEO,
    # 图片
    "jpg": FileType.IMAGE,
    "jpeg": FileType.IMAGE,
    "png": FileType.IMAGE,
    "gif": FileType.IMAGE,
    "bmp": FileType.IMAGE,
    "webp": FileType.IMAGE,
    "heic": FileType.IMAGE,
    "heif": FileType.IMAGE,
    "tiff": FileType.IMAGE,
    # 音频
    "mp3": FileType.AUDIO,
    "flac": FileType.AUDIO,
    "wav": FileType.AUDIO,
    "aac": FileType.AUDIO,
    "ogg": FileType.AUDIO,
    "m4a": FileType.AUDIO,
    "wma": FileType.AUDIO,
    "opus": FileType.AUDIO,
    # 文档
    "pdf": FileType.DOCUMENT,
    "doc": FileType.DOCUMENT,
    "docx": FileType.DOCUMENT,
    "xls": FileType.DOCUMENT,
    "xlsx": FileType.DOCUMENT,
    "ppt": FileType.DOCUMENT,
    "pptx": FileType.DOCUMENT,
    "txt": FileType.DOCUMENT,
    "md": FileType.DOCUMENT,
    "csv": FileType.DOCUMENT,
    "epub": FileType.DOCUMENT,
    # 压缩包
    "zip": FileType.ARCHIVE,
    "rar": FileType.ARCHIVE,
    "7z": FileType.ARCHIVE,
    "tar": FileType.ARCHIVE,
    "gz": FileType.ARCHIVE,
    "bz2": FileType.ARCHIVE,
    "xz": FileType.ARCHIVE,
    "zst": FileType.ARCHIVE,
}


def classify_file_type(filename: str) -> FileType:
    """
    Classify a file by its extension.

    - Case-insensitive: extension is lowercased before lookup.
    - Files with no extension or unknown extensions return FileType.OTHER.
    - Never raises an exception (pure function).
    """
    try:
        if not filename:
            return FileType.OTHER
        # Use rsplit to handle filenames with multiple dots (e.g. "archive.tar.gz")
        parts = filename.rsplit(".", 1)
        if len(parts) < 2 or not parts[1]:
            return FileType.OTHER
        ext = parts[1].lower()
        return FILE_TYPE_MAP.get(ext, FileType.OTHER)
    except Exception:
        return FileType.OTHER
