"""Sibelius glyph-only accidental repair (MusicXML <alter> vs accidental name)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from music21 import note, stream

from registral_dispersion.microtone_repair import (
    DEFAULT_MICROTONEREPAIR,
    MICROTONEREPAIR_FROM_ACCIDENTALS,
    MICROTONEREPAIR_OFF,
    MICROTONEREPAIR_WARN,
    WARN_MIDI_NO_GLYPHS,
    apply_microtone_repair,
    detect_accidental_alter_mismatch,
    normalize_microtone_repair,
    warn_glyph_alter_mismatch,
)
from registral_dispersion.json_export import JSON_EXPORT_SCHEMA_VERSION, build_registral_dispersion_export
from registral_dispersion.score_io import parse_score
from registral_dispersion.service import resolve_registral_dispersion_params, run_registral_dispersion_analysis

FIXTURES = Path(__file__).resolve().parent / "fixtures"
CLUSTER = FIXTURES / "sibelius_glyph_only_cluster.musicxml"
INHERIT = FIXTURES / "sibelius_glyph_inheritance.musicxml"

_CLUSTER_PARAMS = {
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


def test_normalize_microtone_repair_defaults() -> None:
    assert normalize_microtone_repair(None) == DEFAULT_MICROTONEREPAIR
    assert normalize_microtone_repair("") == MICROTONEREPAIR_OFF
    assert normalize_microtone_repair("FROM-ACCIDENTALS") == MICROTONEREPAIR_FROM_ACCIDENTALS


def test_normalize_microtone_repair_rejects_unknown() -> None:
    with pytest.raises(ValueError, match="Unknown microtone_repair"):
        normalize_microtone_repair("quantize")


def test_default_params_include_microtone_repair_off() -> None:
    p = resolve_registral_dispersion_params({})
    assert p["microtone_repair"] == MICROTONEREPAIR_OFF


def test_detect_cluster_finds_four_mismatches() -> None:
    sc = parse_score(str(CLUSTER))
    mismatches = detect_accidental_alter_mismatch(sc)
    assert len(mismatches) == 4
    expected_alters = sorted(m[5] for m in mismatches)
    assert expected_alters == [0.5, 0.5, 1.5, 1.5]


def test_cluster_off_collapses_to_four_integer_heights() -> None:
    out = run_registral_dispersion_analysis(str(CLUSTER), {**_CLUSTER_PARAMS, "microtone_repair": "off"})
    assert out.get("error") is None
    i = _sounding_row(out)
    r = out["results"]
    assert r["registral_span"][i] == pytest.approx(3.0)
    assert r["mean_pairwise_registral_distance"][i] == pytest.approx(1.6667, abs=5e-4)
    assert r["registral_centroid"][i] == pytest.approx(56.5)
    assert r["active_note_count"][i] == 4
    assert out["repairs"] == []
    assert not any("glyph" in w.lower() or "from_accidentals" in w for w in out["warnings"])


def test_cluster_warn_same_numbers_and_n_equals_4() -> None:
    out = run_registral_dispersion_analysis(str(CLUSTER), {**_CLUSTER_PARAMS, "microtone_repair": "warn"})
    assert out.get("error") is None
    i = _sounding_row(out)
    r = out["results"]
    assert r["registral_span"][i] == pytest.approx(3.0)
    assert r["mean_pairwise_registral_distance"][i] == pytest.approx(1.6667, abs=5e-4)
    assert r["registral_centroid"][i] == pytest.approx(56.5)
    assert r["active_note_count"][i] == 4
    assert out["repairs"] == []
    assert warn_glyph_alter_mismatch(4) in out["warnings"]


def test_cluster_from_accidentals_recovers_quarter_tones() -> None:
    out = run_registral_dispersion_analysis(
        str(CLUSTER),
        {**_CLUSTER_PARAMS, "microtone_repair": "from_accidentals"},
    )
    assert out.get("error") is None
    i = _sounding_row(out)
    r = out["results"]
    assert r["registral_span"][i] == pytest.approx(3.5)
    assert r["mean_pairwise_registral_distance"][i] == pytest.approx(1.5)
    assert r["registral_centroid"][i] == pytest.approx(56.75)
    assert r["registral_std"][i] == pytest.approx(1.1456, abs=1e-4)
    assert r["active_note_count"][i] == 8
    assert len(out["repairs"]) == 4
    assert any("from_accidentals" in w for w in out["warnings"])
    doc = build_registral_dispersion_export(str(CLUSTER), out["params"], out)
    assert doc["schema_version"] == JSON_EXPORT_SCHEMA_VERSION == "1.9"
    assert doc["microtone_repair"] == "from_accidentals"
    assert doc["parameters"]["microtone_repair"] == "from_accidentals"
    assert len(doc["repairs"]) == 4


def test_inheritance_repeated_and_tied_notes() -> None:
    sc = parse_score(str(INHERIT))
    apply_microtone_repair(sc, MICROTONEREPAIR_FROM_ACCIDENTALS, is_midi=False)
    part = sc.parts[0]
    m1, m2 = list(part.getElementsByClass(stream.Measure))
    first_g, repeated_g, tied_start = list(m1.notes)
    tied_stop = list(m2.notes)[0]
    assert first_g.pitch.ps == pytest.approx(55.5)
    assert repeated_g.pitch.ps == pytest.approx(55.5)
    assert tied_start.pitch.ps == pytest.approx(57.5)
    assert tied_stop.pitch.ps == pytest.approx(57.5)


def test_midi_never_repaired(tmp_path: Path) -> None:
    p = stream.Part()
    n = note.Note("G3")
    n.pitch.ps = 55.5
    n.quarterLength = 1.0
    p.insert(0, n)
    sc = stream.Score()
    sc.insert(0, p)
    mid = tmp_path / "qt.mid"
    sc.write("midi", fp=str(mid))
    out = run_registral_dispersion_analysis(
        str(mid),
        {**_CLUSTER_PARAMS, "microtone_repair": "from_accidentals"},
    )
    assert out.get("error") is None
    assert out["repairs"] == []
    assert WARN_MIDI_NO_GLYPHS in out["warnings"]
    i = _sounding_row(out)
    assert out["results"]["registral_span"][i] == pytest.approx(0.0)
    assert out["results"]["registral_centroid"][i] == pytest.approx(56.0)
