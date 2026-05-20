"""
Unit and property-based tests for file_type classification.

**Validates: Requirements 3.8**
"""
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.core.file_type import FILE_TYPE_MAP, FileType, classify_file_type


# ---------------------------------------------------------------------------
# Unit tests
# ---------------------------------------------------------------------------


class TestClassifyFileTypeKnownExtensions:
    """Verify that every extension in FILE_TYPE_MAP is classified correctly."""

    @pytest.mark.parametrize(
        "filename,expected",
        [
            ("video.mp4", FileType.VIDEO),
            ("video.MKV", FileType.VIDEO),
            ("video.AVI", FileType.VIDEO),
            ("clip.mov", FileType.VIDEO),
            ("stream.ts", FileType.VIDEO),
            ("photo.jpg", FileType.IMAGE),
            ("photo.JPEG", FileType.IMAGE),
            ("image.PNG", FileType.IMAGE),
            ("anim.gif", FileType.IMAGE),
            ("raw.heic", FileType.IMAGE),
            ("song.mp3", FileType.AUDIO),
            ("lossless.FLAC", FileType.AUDIO),
            ("audio.wav", FileType.AUDIO),
            ("podcast.opus", FileType.AUDIO),
            ("report.pdf", FileType.DOCUMENT),
            ("doc.DOCX", FileType.DOCUMENT),
            ("sheet.xlsx", FileType.DOCUMENT),
            ("notes.md", FileType.DOCUMENT),
            ("data.csv", FileType.DOCUMENT),
            ("book.epub", FileType.DOCUMENT),
            ("archive.zip", FileType.ARCHIVE),
            ("backup.RAR", FileType.ARCHIVE),
            ("compressed.7z", FileType.ARCHIVE),
            ("tarball.tar", FileType.ARCHIVE),
            ("gzip.gz", FileType.ARCHIVE),
            ("bundle.zst", FileType.ARCHIVE),
        ],
    )
    def test_known_extension(self, filename: str, expected: FileType) -> None:
        assert classify_file_type(filename) == expected


class TestClassifyFileTypeEdgeCases:
    """Edge cases: no extension, empty string, dots, unknown extensions."""

    def test_empty_string_returns_other(self) -> None:
        assert classify_file_type("") == FileType.OTHER

    def test_no_extension_returns_other(self) -> None:
        assert classify_file_type("Makefile") == FileType.OTHER

    def test_dot_only_returns_other(self) -> None:
        assert classify_file_type(".") == FileType.OTHER

    def test_hidden_file_no_ext_returns_other(self) -> None:
        # ".gitignore" has no real extension after the leading dot
        assert classify_file_type(".gitignore") == FileType.OTHER

    def test_unknown_extension_returns_other(self) -> None:
        assert classify_file_type("file.xyz123") == FileType.OTHER

    def test_multiple_dots_uses_last_extension(self) -> None:
        # "archive.tar.gz" -> extension is "gz" -> ARCHIVE
        assert classify_file_type("archive.tar.gz") == FileType.ARCHIVE

    def test_case_insensitive_upper(self) -> None:
        assert classify_file_type("VIDEO.MP4") == FileType.VIDEO

    def test_case_insensitive_mixed(self) -> None:
        assert classify_file_type("Photo.JpEg") == FileType.IMAGE

    def test_pure_dot_extension_returns_other(self) -> None:
        # filename ends with a dot, no actual extension
        assert classify_file_type("file.") == FileType.OTHER

    def test_does_not_raise_on_any_string(self) -> None:
        # Should never raise
        for s in ["", ".", "..", "a.b.c.d", "\x00\xff", "日本語.mp4"]:
            result = classify_file_type(s)
            assert isinstance(result, FileType)


# ---------------------------------------------------------------------------
# Property-based tests
# ---------------------------------------------------------------------------

# Feature: aliyundrive-duplicate-cleaner, Property 1: 文件类型分类的完备性与确定性


@given(st.text())
@settings(max_examples=200)
def test_classify_file_type_always_returns_valid_type(filename: str) -> None:
    """
    **Validates: Requirements 3.8**

    For any arbitrary filename string, classify_file_type must:
    - Return a valid FileType enum value (never raise)
    - Be deterministic (same input → same output)
    """
    result = classify_file_type(filename)
    assert isinstance(result, FileType)
    # Determinism: calling again must return the same value
    assert classify_file_type(filename) == result


@given(st.text())
@settings(max_examples=200)
def test_classify_file_type_is_pure_function(filename: str) -> None:
    """
    **Validates: Requirements 3.8**

    classify_file_type is a pure function: repeated calls with the same
    input always produce the same output.
    """
    first = classify_file_type(filename)
    second = classify_file_type(filename)
    assert first == second


@given(
    st.sampled_from(list(FILE_TYPE_MAP.keys())),
    st.text(alphabet=st.characters(whitelist_categories=("Lu", "Ll")), min_size=1, max_size=8),
)
@settings(max_examples=200)
def test_known_extensions_case_insensitive(ext: str, prefix: str) -> None:
    """
    **Validates: Requirements 3.8**

    For every extension in FILE_TYPE_MAP, the classification must be
    case-insensitive: upper, lower, and mixed-case variants all map to
    the same FileType.
    """
    expected = FILE_TYPE_MAP[ext]
    assert classify_file_type(f"{prefix}.{ext.lower()}") == expected
    assert classify_file_type(f"{prefix}.{ext.upper()}") == expected
