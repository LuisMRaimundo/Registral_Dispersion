"""Focused pytest coverage for json_export serialization and export helpers."""

from __future__ import annotations

import json
import math
from importlib.metadata import PackageNotFoundError
from pathlib import Path
from typing import Any, ClassVar

import numpy as np
import pytest

import registral_dispersion.json_export as json_export
from registral_dispersion.json_export import (
    JSON_EXPORT_SCHEMA_VERSION,
    TOOL_SCOPE_STATEMENT,
    _export_provenance,
    _package_version,
    build_registral_dispersion_export,
    to_json_serializable,
    write_global_summary_csv,
    write_json_export,
)
from registral_dispersion.metric_documentation import CANONICAL_TOOL_NAME

# ---------------------------------------------------------------------------
# _package_version / _export_provenance
# ---------------------------------------------------------------------------


def test_package_version_fallback_unknown(monkeypatch: pytest.MonkeyPatch) -> None:
    def _raise(_name: str) -> str:
        raise PackageNotFoundError("registral-dispersion")

    monkeypatch.setattr(json_export, "version", _raise)
    assert _package_version() == "unknown"


def test_export_provenance_includes_required_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _raise(_name: str) -> str:
        raise PackageNotFoundError("registral-dispersion")

    monkeypatch.setattr(json_export, "version", _raise)
    prov = _export_provenance()
    assert prov["package_version"] == "unknown"
    assert prov["canonical_tool_name"] == CANONICAL_TOOL_NAME
    assert prov["package_name"] == "registral-dispersion"
    assert prov["symbolic_score_only"] is True
    assert prov["tool_role"] == "research_software"
    assert prov["tool_scope_statement"] == TOOL_SCOPE_STATEMENT


# ---------------------------------------------------------------------------
# to_json_serializable
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, None),
        ("hello", "hello"),
        (True, True),
        (42, 42),
        (3.14, 3.14),
    ],
)
def test_to_json_serializable_scalars(value: Any, expected: Any) -> None:
    assert to_json_serializable(value) == expected


def test_to_json_serializable_nan_and_inf_become_none() -> None:
    assert to_json_serializable(float("nan")) is None
    assert to_json_serializable(float("inf")) is None
    assert to_json_serializable(float("-inf")) is None


def test_to_json_serializable_numpy_array() -> None:
    arr = np.array([1, 2, 3])
    assert to_json_serializable(arr) == [1, 2, 3]


def test_to_json_serializable_numpy_scalar() -> None:
    assert to_json_serializable(np.float64(2.5)) == 2.5
    assert to_json_serializable(np.int32(7)) == 7


def test_to_json_serializable_dict_recursive() -> None:
    data = {"a": np.array([1.0]), "b": {"c": float("nan")}}
    assert to_json_serializable(data) == {"a": [1.0], "b": {"c": None}}


def test_to_json_serializable_list_and_tuple_recursive() -> None:
    data = [1, (2, np.int64(3))]
    assert to_json_serializable(data) == [1, [2, 3]]


def test_to_json_serializable_unknown_object_becomes_str() -> None:
    class Odd:
        def __str__(self) -> str:
            return "odd-object"

    assert to_json_serializable(Odd()) == "odd-object"


# ---------------------------------------------------------------------------
# write_global_summary_csv
# ---------------------------------------------------------------------------


def test_write_global_summary_csv_handles_mixed_values(tmp_path: Path) -> None:
    global_summary = {
        "aggregation_method": "duration_weighted",
        "finite_val": 1.25,
        "none_val": None,
        "nan_val": float("nan"),
        "inf_val": float("inf"),
        "semicolon_val": "hello; world",
        "comma_val": "a,b",
    }
    csv_path = tmp_path / "global_summary.csv"
    write_global_summary_csv(csv_path, global_summary)

    assert csv_path.is_file()
    text = csv_path.read_text(encoding="utf-8")
    lines = text.splitlines()
    assert lines[0].startswith(f"# {CANONICAL_TOOL_NAME} global summary")
    assert "aggregation_method: duration_weighted" in lines[1]
    assert lines[2] == "key,value"

    rows = {line.split(",", 1)[0]: line.split(",", 1)[1] for line in lines[3:] if "," in line}
    assert rows["finite_val"] == repr(1.25)
    assert rows["none_val"] == ""
    assert rows["nan_val"] == ""
    assert rows["inf_val"] == ""
    assert rows["semicolon_val"] == "hello; world"
    assert rows["comma_val"] == "a;b"


# ---------------------------------------------------------------------------
# build_registral_dispersion_export — helpers
# ---------------------------------------------------------------------------


def _minimal_results() -> dict[str, Any]:
    return {
        "t": [0.0],
        "interval_start": [0.0],
        "interval_end": [1.0],
        "interval_duration": [1.0],
        "window_start": [0.0],
        "window_end": [4.0],
        "active_note_count": [1.0],
        "min_pitch": [60.0],
        "max_pitch": [60.0],
        "dispersion_degree": [0.0],
        "normalized_dispersion_degree": [0.0],
        "registral_span": [0.0],
        "mean_pairwise_registral_distance": [0.0],
        "registral_centroid": [60.0],
        "registral_std": [0.0],
        "normalized_registral_span": [0.0],
        "normalized_mean_pairwise_registral_distance": [0.0],
        "normalized_registral_centroid": [0.5],
        "normalized_registral_std": [0.0],
        "occupancy_entropy": [0.0],
    }


def _minimal_out(*, warnings: list[str] | None = None, analyzer: Any | None = None) -> dict[str, Any]:
    out: dict[str, Any] = {
        "summary": {"n_windows": 1},
        "results": _minimal_results(),
        "global_summary": {"mean_dispersion": 0.5, "bad": float("nan")},
        "params": {
            "pitch_sampling_mode": "event_instances",
            "analysis_profile": "occupied_space",
            "pitch_sampling_source": "analysis_profile",
            "observation_mode": "fixed_window",
            "tie_policy": "as_imported",
        },
    }
    if warnings is not None:
        out["warnings"] = warnings
    if analyzer is not None:
        out["analyzer"] = analyzer
    return out


class _FakeAnalyzer:
    register_low = 48.0
    register_high = 72.0
    register_width_semitones = 24.0
    pitch_sampling_mode = "event_instances"
    analysis_profile = "component_weighted"
    pitch_sampling_source = "explicit"
    end_time = 8.0
    events: ClassVar[list[object]] = [object(), object(), object()]
    tie_policy = "merge_ties"


# ---------------------------------------------------------------------------
# JSON export — successful output
# ---------------------------------------------------------------------------


def test_build_registral_dispersion_export_minimal_success(tmp_path: Path) -> None:
    out = _minimal_out(warnings=["caution: test"])
    doc = build_registral_dispersion_export("/path/to/score.xml", {}, out)

    assert doc["schema_version"] == JSON_EXPORT_SCHEMA_VERSION
    assert doc["kind"] == "registral_dispersion"
    assert doc["score_path"] == "/path/to/score.xml"
    assert doc["summary"] == {"n_windows": 1}
    assert doc["error"] is None
    assert doc["canonical_tool_name"] == CANONICAL_TOOL_NAME
    assert doc["package_name"] == "registral-dispersion"
    assert doc["symbolic_score_only"] is True
    assert doc["tool_scope_statement"] == TOOL_SCOPE_STATEMENT
    assert doc["warnings"] == ["caution: test"]
    assert doc["global_summary"]["mean_dispersion"] == 0.5
    assert doc["global_summary"]["bad"] is None
    assert isinstance(doc["results"]["t"], list)

    json_path = tmp_path / "export.json"
    write_json_export(json_path, doc)
    loaded = json.loads(json_path.read_text(encoding="utf-8"))
    assert loaded["schema_version"] == JSON_EXPORT_SCHEMA_VERSION
    assert loaded["global_summary"]["bad"] is None
    assert math.isfinite(loaded["global_summary"]["mean_dispersion"])


# ---------------------------------------------------------------------------
# JSON export — error output
# ---------------------------------------------------------------------------


def test_build_registral_dispersion_export_with_error() -> None:
    out = {
        "error": "Analysis failed",
        "params": {
            "window_size": 4.0,
            "pitch_sampling_mode": "event_instances",
            "analysis_profile": "occupied_space",
            "pitch_sampling_source": "analysis_profile",
            "observation_mode": "event_boundaries",
            "tie_policy": "as_imported",
        },
    }
    doc = build_registral_dispersion_export("/missing.xml", {"register_low": "C4"}, out)
    assert doc["error"] == "Analysis failed"
    assert doc["schema_version"] == JSON_EXPORT_SCHEMA_VERSION
    assert doc["parameters"]["window_size"] == 4.0
    assert doc["pitch_sampling_mode"] == "event_instances"
    assert doc["analysis_profile"] == "occupied_space"
    assert doc["pitch_sampling_source"] == "analysis_profile"
    assert "summary" not in doc
    assert "results" not in doc


# ---------------------------------------------------------------------------
# JSON export — with / without analyzer
# ---------------------------------------------------------------------------


def test_build_registral_dispersion_export_with_analyzer() -> None:
    out = _minimal_out(analyzer=_FakeAnalyzer())
    doc = build_registral_dispersion_export("score.xml", {}, out)

    assert doc["register_low_midi"] == 48.0
    assert doc["register_high_midi"] == 72.0
    assert doc["register_width_semitones"] == 24.0
    assert doc["pitch_sampling_mode"] == "event_instances"
    assert doc["analysis_profile"] == "component_weighted"
    assert doc["pitch_sampling_source"] == "explicit"
    assert doc["parameters"]["register_low_midi_ps"] == 48.0
    assert doc["parameters"]["register_high_midi_ps"] == 72.0
    assert doc["parameters"]["pitch_sampling_mode"] == "event_instances"
    assert doc["parameters"]["analysis_profile"] == "component_weighted"
    assert doc["parameters"]["pitch_sampling_source"] == "explicit"

    sm = doc["score_metadata"]
    assert sm["duration_quarterlength"] == 8.0
    assert sm["n_notes_flat"] == 3
    assert sm["tie_policy"] == "merge_ties"
    assert sm["register_low_midi"] == 48.0


def test_build_registral_dispersion_export_without_analyzer() -> None:
    out = _minimal_out()
    doc = build_registral_dispersion_export("score.xml", {}, out)

    assert doc["pitch_sampling_mode"] == "event_instances"
    assert doc["analysis_profile"] == "occupied_space"
    assert doc["pitch_sampling_source"] == "analysis_profile"
    assert doc["parameters"]["pitch_sampling_mode"] == "event_instances"
    assert doc["parameters"]["analysis_profile"] == "occupied_space"
    assert "register_low_midi" not in doc
    assert "score_metadata" not in doc


# ---------------------------------------------------------------------------
# JSON export — warnings
# ---------------------------------------------------------------------------


def test_build_registral_dispersion_export_without_warnings_defaults_empty() -> None:
    out = _minimal_out()
    doc = build_registral_dispersion_export("score.xml", {}, out)
    assert doc["warnings"] == []


def test_build_registral_dispersion_export_preserves_warnings() -> None:
    out = _minimal_out(warnings=["warn one", "warn two"])
    doc = build_registral_dispersion_export("score.xml", {}, out)
    assert doc["warnings"] == ["warn one", "warn two"]
    serialized = to_json_serializable(doc)
    assert serialized["warnings"] == ["warn one", "warn two"]
