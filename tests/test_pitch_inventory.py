"""Written/sounding conversion, pitch inventory, and manual overrides."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from registral_dispersion.json_export import JSON_EXPORT_SCHEMA_VERSION, build_registral_dispersion_export
from registral_dispersion.pitch_inventory import build_pitch_inventory, public_inventory_rows
from registral_dispersion.pitch_overrides import (
    load_pitch_overrides,
    save_pitch_overrides,
    sidecar_path_for_score,
)
from registral_dispersion.pitch_reference import (
    DEFAULT_PITCH_REFERENCE,
    PITCH_PIPELINE_ORDER,
    normalize_pitch_reference,
)
from registral_dispersion.pitch_utils import parse_pitch_input
from registral_dispersion.score_io import parse_score
from registral_dispersion.service import (
    inspect_score_pitches,
    resolve_registral_dispersion_params,
    run_registral_dispersion_analysis,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures"
HORN = FIXTURES / "horn_brass_unpitched.musicxml"
BASS = FIXTURES / "double_bass_octave_change.musicxml"
CLUSTER = FIXTURES / "sibelius_glyph_only_cluster.musicxml"

_PARAMS = {
    "observation_mode": "event_boundaries",
    "analysis_profile": "occupied_space",
    "register_low": "A0",
    "register_high": "C8",
}


def _sounding_row(out: dict) -> int:
    counts = np.asarray(out["results"]["active_note_count"], dtype=int)
    idx = np.flatnonzero(counts > 0)
    assert idx.size >= 1
    return int(idx[0])


def test_pipeline_order_is_documented() -> None:
    assert PITCH_PIPELINE_ORDER == (
        "parse",
        "microtone_repair",
        "sounding_conversion",
        "part_level_overrides",
        "note_level_overrides",
        "tie_policy",
        "event_listing",
        "metrics",
    )


def test_default_pitch_reference_is_written() -> None:
    assert normalize_pitch_reference(None) == DEFAULT_PITCH_REFERENCE == "written"
    p = resolve_registral_dispersion_params({})
    assert p["pitch_reference"] == "written"
    assert p["pitch_overrides"] == []


def test_parse_pitch_input_names_and_cents() -> None:
    assert parse_pitch_input(56.5) == pytest.approx(56.5)
    assert parse_pitch_input("A#3") == pytest.approx(58.0)
    assert parse_pitch_input("Bb2") == pytest.approx(46.0)
    assert parse_pitch_input("G3+50c") == pytest.approx(55.5)
    assert parse_pitch_input("A#3 +50c") == pytest.approx(58.5)
    assert parse_pitch_input("A~3") == pytest.approx(57.5)


def test_parse_pitch_input_rejects_invalid() -> None:
    with pytest.raises(ValueError, match="Cannot parse pitch"):
        parse_pitch_input("not-a-pitch")


def test_horn_written_span_and_warning() -> None:
    out = run_registral_dispersion_analysis(str(HORN), {**_PARAMS, "pitch_reference": "written"})
    assert out.get("error") is None
    i = _sounding_row(out)
    assert out["results"]["registral_span"][i] == pytest.approx(35.0)
    assert any("NOT in sounding pitch" in w for w in out["warnings"])
    assert out["transposing_parts"]
    horn_rows = [p for p in out["transposing_parts"] if "Horn" in str(p.get("instrument") or p.get("part"))]
    assert horn_rows
    assert horn_rows[0]["interval_semitones"] == pytest.approx(-7.0)


def test_horn_sounding_metrics_and_inventory() -> None:
    out = run_registral_dispersion_analysis(str(HORN), {**_PARAMS, "pitch_reference": "sounding"})
    assert out.get("error") is None
    i = _sounding_row(out)
    r = out["results"]
    assert r["registral_span"][i] == pytest.approx(28.0)
    assert r["registral_centroid"][i] == pytest.approx(45.8889, abs=1e-4)
    assert r["mean_pairwise_registral_distance"][i] == pytest.approx(11.6667, abs=1e-4)
    assert r["registral_std"][i] == pytest.approx(9.1219, abs=1e-4)
    digest = out["pitch_inventory_digest"]
    assert digest["n_unique"] == 9
    inv = out["pitch_inventory"]
    assert len(inv) == 10
    drum = [row for row in inv if "unpitched" in str(row.get("flags"))]
    assert len(drum) == 1
    assert drum[0]["used_in_metrics"] is False
    assert any("transposed" in str(row.get("flags")) for row in inv)


def test_double_bass_octave_change_sounding_ps() -> None:
    sc = parse_score(str(BASS))
    rows = build_pitch_inventory(sc, {"pitch_reference": "sounding", "register_low": "A0", "register_high": "C8"})
    assert len(rows) == 1
    assert rows[0]["_sounding_ps"] == pytest.approx(31.0)
    assert rows[0]["sounding_ps"] == pytest.approx(31.0)
    out = run_registral_dispersion_analysis(str(BASS), {**_PARAMS, "pitch_reference": "sounding"})
    i = _sounding_row(out)
    assert out["results"]["min_pitch"][i] == pytest.approx(31.0)


def test_override_change_sounding_ps_changes_metrics() -> None:
    baseline = run_registral_dispersion_analysis(str(HORN), {**_PARAMS, "pitch_reference": "sounding"})
    tuba = next(row for row in baseline["pitch_inventory"] if row.get("written_ps") == 33.0)
    ov = [
        {
            "note_id": tuba["note_id"],
            "part": tuba["part"],
            "measure": tuba["measure"],
            "field": "sounding_ps",
            "original": 33.0,
            "new": 21.0,
            "kind": "manual_pitch",
        }
    ]
    out = run_registral_dispersion_analysis(
        str(HORN),
        {**_PARAMS, "pitch_reference": "sounding", "pitch_overrides": ov},
    )
    assert out.get("error") is None
    i0 = _sounding_row(baseline)
    i1 = _sounding_row(out)
    assert out["results"]["registral_span"][i1] != baseline["results"]["registral_span"][i0]
    assert out["results"]["min_pitch"][i1] == pytest.approx(21.0)
    logged = [e for e in out["pitch_overrides"] if e["kind"] == "manual_pitch"]
    assert len(logged) == 1
    assert logged[0]["original"] == pytest.approx(33.0)
    assert logged[0]["new"] == pytest.approx(21.0)
    assert any("1 manual pitch override" in w for w in out["warnings"])


def test_override_exclude_note() -> None:
    baseline = run_registral_dispersion_analysis(str(HORN), {**_PARAMS, "pitch_reference": "sounding"})
    top = max(
        (row for row in baseline["pitch_inventory"] if row.get("used_in_metrics")),
        key=lambda r: float(r["sounding_ps"]),
    )
    ov = [
        {
            "note_id": top["note_id"],
            "part": top["part"],
            "measure": top["measure"],
            "field": "used_in_metrics",
            "original": True,
            "new": False,
            "kind": "manual_exclude",
        }
    ]
    out = run_registral_dispersion_analysis(
        str(HORN),
        {**_PARAMS, "pitch_reference": "sounding", "pitch_overrides": ov},
    )
    i0 = _sounding_row(baseline)
    i1 = _sounding_row(out)
    assert out["results"]["registral_span"][i1] < baseline["results"]["registral_span"][i0]
    assert out["results"]["max_pitch"][i1] < baseline["results"]["max_pitch"][i0]


def test_override_part_transposition_half_semitone() -> None:
    baseline = run_registral_dispersion_analysis(str(HORN), {**_PARAMS, "pitch_reference": "sounding"})
    horn_part = next(
        row for row in baseline["pitch_inventory"] if "Horn" in str(row.get("instrument") or row.get("part"))
    )
    ov = [
        {
            "part": horn_part["part"],
            "field": "part_transposition",
            "original": 0.0,
            "new": 0.5,
            "kind": "part_transposition",
        }
    ]
    out = run_registral_dispersion_analysis(
        str(HORN),
        {**_PARAMS, "pitch_reference": "sounding", "pitch_overrides": ov},
    )
    i0 = _sounding_row(baseline)
    i1 = _sounding_row(out)
    assert out["results"]["max_pitch"][i1] == pytest.approx(baseline["results"]["max_pitch"][i0] + 0.5)
    assert out["results"]["registral_span"][i1] == pytest.approx(baseline["results"]["registral_span"][i0] + 0.5)


def test_override_sidecar_round_trip(tmp_path: Path) -> None:
    baseline = run_registral_dispersion_analysis(str(HORN), {**_PARAMS, "pitch_reference": "sounding"})
    tuba = next(row for row in baseline["pitch_inventory"] if row.get("written_ps") == 33.0)
    ov = [
        {
            "note_id": tuba["note_id"],
            "part": tuba["part"],
            "measure": tuba["measure"],
            "field": "sounding_ps",
            "original": 33.0,
            "new": 24.0,
            "kind": "manual_pitch",
        }
    ]
    first = run_registral_dispersion_analysis(
        str(HORN),
        {**_PARAMS, "pitch_reference": "sounding", "pitch_overrides": ov},
    )
    sidecar = tmp_path / "horn.musicxml.pitch_overrides.json"
    save_pitch_overrides(sidecar, first["pitch_overrides"])
    assert sidecar_path_for_score(tmp_path / "horn.musicxml") == sidecar
    reloaded = load_pitch_overrides(sidecar)
    second = run_registral_dispersion_analysis(
        str(HORN),
        {**_PARAMS, "pitch_reference": "sounding", "pitch_overrides": reloaded},
    )
    i1 = _sounding_row(first)
    i2 = _sounding_row(second)
    assert first["results"]["registral_span"][i1] == pytest.approx(second["results"]["registral_span"][i2])
    assert first["results"]["registral_centroid"][i1] == pytest.approx(second["results"]["registral_centroid"][i2])


def test_invalid_override_name_rejected() -> None:
    out = run_registral_dispersion_analysis(
        str(HORN),
        {
            **_PARAMS,
            "pitch_overrides": [{"note_id": "0:1:0:1:0", "new": "not-a-pitch", "kind": "manual_pitch"}],
        },
    )
    assert out.get("error")
    assert "Cannot parse pitch" in str(out["error"])


def test_written_no_overrides_matches_historical_cluster() -> None:
    historical = run_registral_dispersion_analysis(
        str(CLUSTER),
        {**_PARAMS, "microtone_repair": "off"},
    )
    explicit = run_registral_dispersion_analysis(
        str(CLUSTER),
        {**_PARAMS, "microtone_repair": "off", "pitch_reference": "written", "pitch_overrides": []},
    )
    assert historical.get("error") is None
    i0 = _sounding_row(historical)
    i1 = _sounding_row(explicit)
    for key in (
        "registral_span",
        "mean_pairwise_registral_distance",
        "registral_centroid",
        "registral_std",
        "dispersion_degree",
        "occupancy_entropy",
    ):
        assert historical["results"][key][i0] == pytest.approx(explicit["results"][key][i1])


def test_json_export_includes_inventory_fields() -> None:
    out = run_registral_dispersion_analysis(str(HORN), {**_PARAMS, "pitch_reference": "sounding"})
    doc = build_registral_dispersion_export(str(HORN), out["params"], out)
    assert doc["schema_version"] == JSON_EXPORT_SCHEMA_VERSION == "1.10"
    assert doc["pitch_reference"] == "sounding"
    assert doc["transposing_parts"]
    assert doc["pitch_inventory_digest"]["n_unique"] == 9
    assert "pitch_overrides" in doc


def test_inspect_inventory_lists_unpitched() -> None:
    out = inspect_score_pitches(str(HORN), {**_PARAMS, "pitch_reference": "sounding"})
    assert out.get("error") is None
    assert len(out["pitch_inventory"]) == 10
    public = public_inventory_rows(out["pitch_inventory_raw"])
    assert all("note_id" in row for row in public)
    assert "unique sounding" in out["digest_line"]
