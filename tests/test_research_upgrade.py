"""Tests for global aggregation, summarize API/CLI, tie policy, warnings, and exports."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from music21 import chord, note, stream
from music21.tie import Tie

from registral_dispersion.aggregation import (
    AGGREGATION_DURATION_WEIGHTED,
    AGGREGATION_SAMPLED_FIXED,
    compute_global_summary,
)
from registral_dispersion.analyzer import RegistralDispersionAnalyzer
from registral_dispersion.json_export import JSON_EXPORT_SCHEMA_VERSION, build_registral_dispersion_export
from registral_dispersion.observation import OBSERVATION_MODE_EVENT_BOUNDARIES, OBSERVATION_MODE_FIXED_WINDOW
from registral_dispersion.profiles import ANALYSIS_PROFILE_COMPONENT_WEIGHTED, ANALYSIS_PROFILE_OCCUPIED_SPACE
from registral_dispersion.service import resolve_registral_dispersion_params, run_registral_dispersion_analysis
from registral_dispersion.summarize import summarize_registral_dispersion
from registral_dispersion.tie_policy import TIE_POLICY_AS_IMPORTED, TIE_POLICY_MERGE_TIES, apply_tie_policy
from registral_dispersion.warnings import (
    WARN_COMPONENT_WEIGHTED,
    WARN_EXPLICIT_PITCH_SAMPLING,
    collect_interpretation_warnings,
)

REPO_ROOT = Path(__file__).resolve().parent.parent


class TestDurationWeightedAggregation(unittest.TestCase):
    def test_event_boundaries_weighted_mean(self):
        results = {
            "interval_duration": [1.0, 3.0],
            "active_note_count": [2, 2],
            "registral_span": [2.0, 10.0],
            "dispersion_degree": [2.0, 10.0],
            "mean_pairwise_registral_distance": [2.0, 10.0],
            "registral_centroid": [60.0, 72.0],
            "registral_std": [1.0, 5.0],
            "normalized_registral_span": [0.1, 0.5],
            "normalized_dispersion_degree": [0.1, 0.5],
            "normalized_mean_pairwise_registral_distance": [0.1, 0.5],
            "occupancy_entropy": [0.2, 0.8],
        }
        params = {"observation_mode": OBSERVATION_MODE_EVENT_BOUNDARIES, "analysis_profile": "occupied_space"}
        gs = compute_global_summary(results, params)
        self.assertEqual(gs["aggregation_method"], AGGREGATION_DURATION_WEIGHTED)
        self.assertAlmostEqual(gs["duration_weighted_registral_span"], (2.0 * 1 + 10.0 * 3) / 4)
        self.assertAlmostEqual(gs["duration_weighted_dispersion_degree"], gs["duration_weighted_registral_span"])
        self.assertEqual(gs["n_intervals"], 2)
        self.assertEqual(gs["n_empty_intervals"], 0)

    def test_empty_intervals_skipped_and_counted(self):
        results = {
            "interval_duration": [1.0, 2.0, 1.0],
            "active_note_count": [1, 0, 1],
            "registral_span": [4.0, float("nan"), 8.0],
            "dispersion_degree": [4.0, float("nan"), 8.0],
            "mean_pairwise_registral_distance": [0.0, float("nan"), 8.0],
            "registral_centroid": [60.0, float("nan"), 64.0],
            "registral_std": [0.0, float("nan"), 0.0],
            "normalized_registral_span": [0.2, float("nan"), 0.4],
            "normalized_dispersion_degree": [0.2, float("nan"), 0.4],
            "normalized_mean_pairwise_registral_distance": [0.0, float("nan"), 0.4],
            "occupancy_entropy": [0.0, float("nan"), 0.0],
        }
        gs = compute_global_summary(results, {"observation_mode": OBSERVATION_MODE_EVENT_BOUNDARIES})
        self.assertEqual(gs["n_empty_intervals"], 1)
        self.assertAlmostEqual(gs["duration_weighted_registral_span"], (4.0 * 1 + 8.0 * 1) / 2)
        self.assertAlmostEqual(gs["skipped_empty_interval_duration"], 2.0)

    def test_fixed_window_sampled_summary(self):
        results = {
            "interval_duration": [1.0, 1.0, 1.0],
            "active_note_count": [2, 2, 2],
            "registral_span": [2.0, 4.0, 6.0],
            "dispersion_degree": [2.0, 4.0, 6.0],
            "mean_pairwise_registral_distance": [2.0, 4.0, 6.0],
            "registral_centroid": [60.0, 60.0, 60.0],
            "registral_std": [1.0, 1.0, 1.0],
            "normalized_registral_span": [0.1, 0.2, 0.3],
            "normalized_dispersion_degree": [0.1, 0.2, 0.3],
            "normalized_mean_pairwise_registral_distance": [0.1, 0.2, 0.3],
            "occupancy_entropy": [0.1, 0.2, 0.3],
        }
        gs = compute_global_summary(results, {"observation_mode": OBSERVATION_MODE_FIXED_WINDOW})
        self.assertEqual(gs["aggregation_method"], AGGREGATION_SAMPLED_FIXED)
        self.assertAlmostEqual(gs["sampled_mean_registral_span"], 4.0)
        self.assertNotIn("duration_weighted_registral_span", gs)


class TestSummarizeAPI(unittest.TestCase):
    def _write_score(self, sc: stream.Score) -> str:
        td = tempfile.mkdtemp()
        path = Path(td) / "t.musicxml"
        sc.write("musicxml", fp=str(path))
        return str(path)

    def test_default_occupied_space_event_boundaries(self):
        p = stream.Part()
        p.insert(0, chord.Chord(["C4", "G4"], quarterLength=2.0))
        sc = stream.Score()
        sc.insert(0, p)
        path = self._write_score(sc)
        out = summarize_registral_dispersion(path, {})
        self.assertIsNone(out.get("error"))
        self.assertEqual(out["params"]["analysis_profile"], ANALYSIS_PROFILE_OCCUPIED_SPACE)
        self.assertEqual(out["params"]["observation_mode"], OBSERVATION_MODE_EVENT_BOUNDARIES)
        self.assertEqual(out["primary_metric"], "duration_weighted_registral_span")
        self.assertAlmostEqual(out["primary_value"], 7.0)
        self.assertIsNotNone(out["global_summary"])

    def test_component_weighted_includes_warning(self):
        p = stream.Part()
        p.insert(0, note.Note("C4", quarterLength=2.0))
        sc = stream.Score()
        sc.insert(0, p)
        path = self._write_score(sc)
        out = summarize_registral_dispersion(path, {"analysis_profile": ANALYSIS_PROFILE_COMPONENT_WEIGHTED})
        self.assertTrue(any(WARN_COMPONENT_WEIGHTED in w for w in out["warnings"]))

    def test_explicit_pitch_sampling_warning(self):
        p = stream.Part()
        p.insert(0, note.Note("C4", quarterLength=2.0))
        sc = stream.Score()
        sc.insert(0, p)
        path = self._write_score(sc)
        out = summarize_registral_dispersion(
            path,
            {"pitch_sampling_mode": "event_instances", "analysis_profile": ANALYSIS_PROFILE_OCCUPIED_SPACE},
        )
        self.assertTrue(any(WARN_EXPLICIT_PITCH_SAMPLING in w for w in out["warnings"]))


class TestTiePolicy(unittest.TestCase):
    def test_as_imported_unchanged(self):
        p = stream.Part()
        n1 = note.Note("C4", quarterLength=1.0)
        n2 = note.Note("C4", quarterLength=1.0)
        n1.tie = Tie("start")
        n2.tie = Tie("stop")
        p.insert(0, n1)
        p.insert(1, n2)
        sc = stream.Score()
        sc.insert(0, p)
        an_import = RegistralDispersionAnalyzer.from_stream(
            sc, 48.0, 72.0, time_step=1.0, tie_policy=TIE_POLICY_AS_IMPORTED
        )
        self.assertEqual(len(an_import.events), 2)

    def test_merge_ties_combines_simple_tie(self):
        p = stream.Part()
        n1 = note.Note("C4", quarterLength=1.0)
        n2 = note.Note("C4", quarterLength=1.0)
        n1.tie = Tie("start")
        n2.tie = Tie("stop")
        p.insert(0, n1)
        p.insert(1, n2)
        sc = stream.Score()
        sc.insert(0, p)
        merged, _ = apply_tie_policy(sc, TIE_POLICY_MERGE_TIES)
        an = RegistralDispersionAnalyzer.from_stream(
            merged, 48.0, 72.0, time_step=1.0, tie_policy=TIE_POLICY_AS_IMPORTED
        )
        self.assertEqual(len(an.events), 1)
        self.assertAlmostEqual(float(an.events[0].quarterLength), 2.0)

    def test_event_boundaries_differs_with_merge_ties(self):
        p = stream.Part()
        n1 = note.Note("C4", quarterLength=1.0)
        n2 = note.Note("C4", quarterLength=1.0)
        n1.tie = Tie("start")
        n2.tie = Tie("stop")
        p.insert(0, n1)
        p.insert(1, n2)
        sc = stream.Score()
        sc.insert(0, p)
        r_import = RegistralDispersionAnalyzer.from_stream(
            sc, 48.0, 72.0, time_step=1.0, tie_policy=TIE_POLICY_AS_IMPORTED
        ).analyze_score(4.0, observation_mode=OBSERVATION_MODE_EVENT_BOUNDARIES)
        r_merge = RegistralDispersionAnalyzer.from_stream(
            sc, 48.0, 72.0, time_step=1.0, tie_policy=TIE_POLICY_MERGE_TIES
        ).analyze_score(4.0, observation_mode=OBSERVATION_MODE_EVENT_BOUNDARIES)
        self.assertGreater(len(r_import["t"]), len(r_merge["t"]))


class TestWarnings(unittest.TestCase):
    def test_no_warning_default_occupied_space(self):
        p = resolve_registral_dispersion_params({})
        w = collect_interpretation_warnings(p)
        self.assertEqual(w, [])

    def test_export_includes_global_summary_and_schema(self):
        p = stream.Part()
        p.insert(0, note.Note("C4", quarterLength=2.0))
        sc = stream.Score()
        sc.insert(0, p)
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "n.musicxml"
            sc.write("musicxml", fp=str(path))
            out = run_registral_dispersion_analysis(str(path), {"observation_mode": "event_boundaries"})
            doc = build_registral_dispersion_export(str(path), {}, out)
            self.assertEqual(doc["schema_version"], JSON_EXPORT_SCHEMA_VERSION)
            self.assertEqual(doc["schema_version"], "1.11")
            self.assertIn("global_summary", doc)
            self.assertIn("tie_policy", doc)
            self.assertTrue(doc.get("symbolic_score_only"))


class TestSummarizeCLI(unittest.TestCase):
    def test_cli_summarize_runs(self):
        p = stream.Part()
        p.insert(0, note.Note("C4", quarterLength=2.0))
        sc = stream.Score()
        sc.insert(0, p)
        with tempfile.TemporaryDirectory() as td:
            score = Path(td) / "s.musicxml"
            out_json = Path(td) / "sum.json"
            sc.write("musicxml", fp=str(score))
            argv = [
                "__main__.py",
                "summarize",
                "--score",
                str(score),
                "--out-json",
                str(out_json),
            ]
            with mock.patch.object(sys, "argv", argv), self.assertRaises(SystemExit) as cm:
                from registral_dispersion.__main__ import main

                main()
            self.assertEqual(cm.exception.code, 0)
            doc = json.loads(out_json.read_text(encoding="utf-8"))
            self.assertIn("primary_value", doc)
            self.assertIn("global_summary", doc)


if __name__ == "__main__":
    unittest.main()
