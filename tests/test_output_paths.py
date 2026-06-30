"""Focused pytest coverage for export path helpers and stale-export cleanup."""

from __future__ import annotations

import os
import time
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace

import pytest

import registral_dispersion.output_paths as output_paths
from registral_dispersion.output_paths import (
    cleanup_stale_exports,
    export_directory,
    new_export_path,
)

# ---------------------------------------------------------------------------
# Fake Path-like helpers for OSError branches
# ---------------------------------------------------------------------------


class _FakeExportFile:
    def __init__(
        self,
        name: str,
        mtime: float,
        *,
        stat_raises: bool = False,
        unlink_raises: bool = False,
    ) -> None:
        self.name = name
        self._mtime = mtime
        self.stat_raises = stat_raises
        self.unlink_raises = unlink_raises
        self.unlink_calls = 0

    def is_file(self) -> bool:
        return True

    def stat(self):
        if self.stat_raises:
            raise OSError(f"stat failed for {self.name}")
        return SimpleNamespace(st_mtime=self._mtime)

    def unlink(self) -> None:
        self.unlink_calls += 1
        if self.unlink_raises:
            raise OSError(f"unlink failed for {self.name}")


class _FakeExportDir:
    def __init__(self, files: list[_FakeExportFile] | None = None) -> None:
        self._files = list(files or [])
        self.iterdir_calls = 0

    def iterdir(self) -> Iterator[_FakeExportFile]:
        self.iterdir_calls += 1
        return iter(self._files)


class _FakeExportDirSecondIterdirFails:
    def __init__(self, files: list[_FakeExportFile] | None = None) -> None:
        self._files = list(files or [])
        self.iterdir_calls = 0

    def iterdir(self) -> Iterator[_FakeExportFile]:
        self.iterdir_calls += 1
        if self.iterdir_calls == 1:
            return iter(self._files)
        raise OSError("directory listing failed")


class _FakeExportDirIterdirAlwaysFails:
    def iterdir(self) -> Iterator[_FakeExportFile]:
        raise OSError("directory access denied")
        yield  # pragma: no cover


# ---------------------------------------------------------------------------
# cleanup_stale_exports — safe return on directory errors
# ---------------------------------------------------------------------------


def test_cleanup_returns_safely_when_directory_iterdir_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        output_paths,
        "export_directory",
        lambda: _FakeExportDirIterdirAlwaysFails(),
    )
    cleanup_stale_exports(max_age_seconds=3600, max_files=10)


def test_cleanup_returns_safely_when_second_iterdir_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = time.time()
    old = _FakeExportFile("old.csv", now - 10_000)
    monkeypatch.setattr(
        output_paths,
        "export_directory",
        lambda: _FakeExportDirSecondIterdirFails([old]),
    )
    cleanup_stale_exports(max_age_seconds=3600, max_files=10)


# ---------------------------------------------------------------------------
# cleanup_stale_exports — age-based deletion
# ---------------------------------------------------------------------------


def test_cleanup_removes_old_files_and_keeps_recent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REGISTRAL_DISPERSION_CACHE_DIR", str(tmp_path))
    old_file = tmp_path / "old.csv"
    recent_file = tmp_path / "recent.csv"
    old_file.write_text("old", encoding="utf-8")
    recent_file.write_text("recent", encoding="utf-8")

    now = time.time()
    os.utime(old_file, (now - 100_000, now - 100_000))
    os.utime(recent_file, (now, now))

    cleanup_stale_exports(max_age_seconds=3600, max_files=400)

    assert not old_file.exists()
    assert recent_file.exists()


# ---------------------------------------------------------------------------
# cleanup_stale_exports — per-file stat/unlink OSError
# ---------------------------------------------------------------------------


def test_cleanup_continues_when_individual_stat_or_unlink_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = time.time()
    bad_stat = _FakeExportFile("bad-stat.csv", now, stat_raises=True)
    bad_unlink = _FakeExportFile("bad-unlink.csv", now - 10_000, unlink_raises=True)
    monkeypatch.setattr(
        output_paths,
        "export_directory",
        lambda: _FakeExportDir([bad_stat, bad_unlink]),
    )

    cleanup_stale_exports(max_age_seconds=3600, max_files=10)

    assert bad_unlink.unlink_calls == 1


# ---------------------------------------------------------------------------
# cleanup_stale_exports — max_files pruning
# ---------------------------------------------------------------------------


def test_cleanup_prunes_to_max_files_by_mtime(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REGISTRAL_DISPERSION_CACHE_DIR", str(tmp_path))
    now = time.time()
    paths: list[Path] = []
    for i in range(5):
        path = tmp_path / f"export_{i}.csv"
        path.write_text(str(i), encoding="utf-8")
        mtime = now - (5 - i) * 100
        os.utime(path, (mtime, mtime))
        paths.append(path)

    cleanup_stale_exports(max_age_seconds=1_000_000, max_files=2)

    assert not paths[0].exists()
    assert not paths[1].exists()
    assert not paths[2].exists()
    assert paths[3].exists()
    assert paths[4].exists()


def test_cleanup_max_files_pruning_survives_unlink_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = time.time()
    oldest = _FakeExportFile("oldest.csv", now - 400, unlink_raises=True)
    middle = _FakeExportFile("middle.csv", now - 300)
    newer = _FakeExportFile("newer.csv", now - 200)
    newest = _FakeExportFile("newest.csv", now)
    monkeypatch.setattr(
        output_paths,
        "export_directory",
        lambda: _FakeExportDir([oldest, middle, newer, newest]),
    )

    cleanup_stale_exports(max_age_seconds=1_000_000, max_files=2)

    assert oldest.unlink_calls == 1
    assert middle.unlink_calls == 1
    assert newer.unlink_calls == 0
    assert newest.unlink_calls == 0


# ---------------------------------------------------------------------------
# export_directory / new_export_path
# ---------------------------------------------------------------------------


def test_export_directory_creates_missing_parent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    export_dir = tmp_path / "nested" / "exports"
    monkeypatch.setenv("REGISTRAL_DISPERSION_CACHE_DIR", str(export_dir))
    result = export_directory()
    assert result == export_dir
    assert export_dir.is_dir()


@pytest.mark.parametrize(
    "env_var",
    [
        "REGISTRAL_DISPERSION_CACHE_DIR",
        "REGISTER_UNIFORMITY_CACHE_DIR",
        "HOMOGENEITY_CACHE_DIR",
    ],
)
def test_export_directory_respects_env_aliases(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, env_var: str) -> None:
    for key in (
        "REGISTRAL_DISPERSION_CACHE_DIR",
        "REGISTER_UNIFORMITY_CACHE_DIR",
        "HOMOGENEITY_CACHE_DIR",
    ):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv(env_var, str(tmp_path))
    assert export_directory() == tmp_path


def test_new_export_path_uses_prefix_and_suffix(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REGISTRAL_DISPERSION_CACHE_DIR", str(tmp_path))
    path = Path(new_export_path("dispersion_", ".csv"))
    assert path.parent == tmp_path
    assert path.name.startswith("dispersion_")
    assert path.suffix == ".csv"


def test_new_export_path_supports_empty_suffix(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REGISTRAL_DISPERSION_CACHE_DIR", str(tmp_path))
    path = Path(new_export_path("data_", ""))
    assert path.parent == tmp_path
    assert path.name.startswith("data_")


def test_new_export_path_preserves_spaces_and_dots_in_prefix(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REGISTRAL_DISPERSION_CACHE_DIR", str(tmp_path))
    prefix = "my export.v2."
    path = Path(new_export_path(prefix, ".png"))
    assert path.parent == tmp_path
    assert path.name.startswith(prefix)
    assert path.name.endswith(".png")
