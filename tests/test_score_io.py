"""Focused pytest coverage for score_io validation and parsing."""

from __future__ import annotations

import sys
import zipfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

import registral_dispersion.score_io as score_io
from registral_dispersion.score_io import (
    ScoreValidationError,
    _unsafe_zip_member_name,
    parse_score,
    validate_score_path,
    validate_zip_archive,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURE_XML = REPO_ROOT / "tests" / "fixtures" / "single_note.xml"


# ---------------------------------------------------------------------------
# _unsafe_zip_member_name
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("score.xml", False),
        ("META-INF/container.xml", False),
        ("../score.xml", True),
        ("META-INF/../score.xml", True),
        (r"..\score.xml", True),
        ("/tmp/score.xml", True),
    ],
)
def test_unsafe_zip_member_name(name: str, expected: bool) -> None:
    assert _unsafe_zip_member_name(name) is expected


@pytest.mark.skipif(sys.platform != "win32", reason="Windows drive-letter paths")
def test_unsafe_zip_member_name_windows_absolute() -> None:
    assert _unsafe_zip_member_name(r"C:\Users\evil.xml") is True


# ---------------------------------------------------------------------------
# validate_zip_archive
# ---------------------------------------------------------------------------


def test_validate_zip_archive_rejects_non_zip(tmp_path: Path) -> None:
    bad = tmp_path / "broken.mxl"
    bad.write_text("not a zip file")
    with pytest.raises(ScoreValidationError, match="Invalid or corrupted ZIP"):
        validate_zip_archive(str(bad))


def test_validate_zip_archive_rejects_unsafe_member(tmp_path: Path) -> None:
    zpath = tmp_path / "unsafe.mxl"
    with zipfile.ZipFile(zpath, "w") as zf:
        zf.writestr("../evil.xml", "<score-partwise/>")
    with pytest.raises(ScoreValidationError, match="Unsafe path inside ZIP"):
        validate_zip_archive(str(zpath))


def test_validate_zip_archive_rejects_too_many_members(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(score_io, "MAX_ZIP_MEMBERS", 2)
    zpath = tmp_path / "many.mxl"
    with zipfile.ZipFile(zpath, "w") as zf:
        for i in range(3):
            zf.writestr(f"entry{i}.xml", f"<part{i}/>")
    with pytest.raises(ScoreValidationError, match="too many entries"):
        validate_zip_archive(str(zpath))


def test_validate_zip_archive_rejects_huge_single_member(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    zpath = tmp_path / "huge.mxl"
    with zipfile.ZipFile(zpath, "w") as zf:
        zf.writestr("score.xml", "<score-partwise/>")

    real_zipfile = zipfile.ZipFile

    class ZipFileWithHugeMember(real_zipfile):
        def infolist(self):
            infos = super().infolist()
            infos[0].file_size = score_io.MAX_ZIP_SINGLE_UNCOMPRESSED_BYTES + 1
            return infos

    monkeypatch.setattr(score_io.zipfile, "ZipFile", ZipFileWithHugeMember)
    with pytest.raises(ScoreValidationError, match="declares uncompressed size"):
        validate_zip_archive(str(zpath))


def test_validate_zip_archive_rejects_excessive_total_uncompressed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(score_io, "MAX_ZIP_TOTAL_UNCOMPRESSED_BYTES", 10)
    zpath = tmp_path / "total.mxl"
    with zipfile.ZipFile(zpath, "w") as zf:
        zf.writestr("a.xml", "0123456789")
        zf.writestr("b.xml", "0123456789")
    with pytest.raises(ScoreValidationError, match="excessive total uncompressed size"):
        validate_zip_archive(str(zpath))


def test_validate_zip_archive_accepts_safe_zip(tmp_path: Path) -> None:
    zpath = tmp_path / "ok.mxl"
    with zipfile.ZipFile(zpath, "w") as zf:
        zf.writestr("META-INF/container.xml", "<container/>")
        zf.writestr("score.xml", "<score-partwise/>")
    validate_zip_archive(str(zpath))


# ---------------------------------------------------------------------------
# validate_score_path
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bad_path", [None, ""])
def test_validate_score_path_rejects_missing_path(bad_path) -> None:
    with pytest.raises(ScoreValidationError, match="No file path provided"):
        validate_score_path(bad_path)  # type: ignore[arg-type]


def test_validate_score_path_rejects_missing_file(tmp_path: Path) -> None:
    missing = tmp_path / "ghost.xml"
    with pytest.raises(ScoreValidationError, match="Score file not found"):
        validate_score_path(str(missing))


def test_validate_score_path_rejects_unsupported_extension(tmp_path: Path) -> None:
    bad = tmp_path / "notes.txt"
    bad.write_text("hello")
    with pytest.raises(ScoreValidationError, match="Unsupported extension"):
        validate_score_path(str(bad))


def test_validate_score_path_rejects_empty_file(tmp_path: Path) -> None:
    empty = tmp_path / "empty.xml"
    empty.write_bytes(b"")
    with pytest.raises(ScoreValidationError, match="File is empty"):
        validate_score_path(str(empty))


def test_validate_score_path_rejects_file_too_large(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(score_io, "MAX_SCORE_FILE_BYTES", 5)
    big = tmp_path / "big.xml"
    big.write_text("0123456789")
    with pytest.raises(ScoreValidationError, match="File too large"):
        validate_score_path(str(big))


def test_validate_score_path_mxl_calls_validate_zip_archive(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    zpath = tmp_path / "score.mxl"
    with zipfile.ZipFile(zpath, "w") as zf:
        zf.writestr("score.xml", "<score-partwise/>")
    called: list[str] = []

    def _spy(path: str) -> None:
        called.append(path)
        validate_zip_archive(path)

    monkeypatch.setattr(score_io, "validate_zip_archive", _spy)
    validate_score_path(str(zpath))
    assert called == [str(zpath)]


def test_validate_score_path_accepts_valid_xml(tmp_path: Path) -> None:
    xml = tmp_path / "ok.xml"
    xml.write_text("<score-partwise/>")
    validate_score_path(str(xml))


# ---------------------------------------------------------------------------
# parse_score
# ---------------------------------------------------------------------------


@pytest.fixture
def patched_parse(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    mock_parse = MagicMock(return_value="parsed-score")
    monkeypatch.setattr(score_io.m21.converter, "parse", mock_parse)
    return mock_parse


def test_parse_score_calls_validate_before_parse(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, patched_parse: MagicMock
) -> None:
    xml = tmp_path / "score.xml"
    xml.write_text("<score-partwise/>")
    order: list[str] = []

    def _validate(path: str) -> None:
        order.append("validate")
        validate_score_path(path)

    monkeypatch.setattr(score_io, "validate_score_path", _validate)

    def _parse(path: str, **kwargs):
        order.append("parse")
        return "parsed-score"

    monkeypatch.setattr(score_io.m21.converter, "parse", _parse)

    result = parse_score(str(xml))
    assert result == "parsed-score"
    assert order == ["validate", "parse"]


@pytest.mark.parametrize("suffix", [".xml", ".musicxml", ".mxl"])
def test_parse_score_musicxml_extensions_use_musicxml_format(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    patched_parse: MagicMock,
    suffix: str,
) -> None:
    monkeypatch.setattr(score_io, "validate_score_path", lambda _path: None)
    if suffix == ".mxl":
        path = tmp_path / f"score{suffix}"
        with zipfile.ZipFile(path, "w") as zf:
            zf.writestr("score.xml", "<score-partwise/>")
    else:
        path = tmp_path / f"score{suffix}"
        path.write_text("<score-partwise/>")

    parse_score(str(path))
    patched_parse.assert_called_once_with(str(path), format="musicxml")


@pytest.mark.parametrize("suffix", [".mid", ".midi"])
def test_parse_score_midi_extensions_without_musicxml_format(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    patched_parse: MagicMock,
    suffix: str,
) -> None:
    monkeypatch.setattr(score_io, "validate_score_path", lambda _path: None)
    path = tmp_path / f"score{suffix}"
    path.write_bytes(b"MThd\x00\x00\x00\x06\x00\x00\x00\x01\x00\x00")

    parse_score(str(path))
    patched_parse.assert_called_once_with(str(path))


def test_parse_score_integration_with_fixture(monkeypatch: pytest.MonkeyPatch, patched_parse: MagicMock) -> None:
    if not FIXTURE_XML.is_file():
        pytest.skip("Fixture not found")
    monkeypatch.setattr(score_io, "validate_score_path", lambda _path: None)
    parse_score(str(FIXTURE_XML))
    patched_parse.assert_called_once_with(str(FIXTURE_XML), format="musicxml")
