"""Tests for registral dispersion, legacy occupancy entropy, and exports."""

from __future__ import annotations

import math
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import matplotlib.pyplot as plt
import numpy as np
from music21 import chord, note, stream

from registral_dispersion.analysis_presets import (
    PRESET_CUSTOM,
    PRESET_MOVING_FRAGMENT,
    PRESET_SPECS,
    PRESET_STATIC_VERTICAL,
    apply_analysis_preset,
    preset_guidance_text,
)
from registral_dispersion.analyzer import RegisterUniformityAnalyzer, RegistralDispersionAnalyzer
from registral_dispersion.app import build_demo
from registral_dispersion.json_export import (
    build_register_export,
    build_registral_dispersion_export,
    write_register_uniformity_csv,
    write_registral_dispersion_csv,
)
from registral_dispersion.metric_documentation import NORMALIZATION_REFERENCE
from registral_dispersion.observation import (
    OBSERVATION_MODE_EVENT_BOUNDARIES,
    OBSERVATION_MODE_FIXED_WINDOW,
)
from registral_dispersion.output_paths import new_export_path
from registral_dispersion.pitch_utils import (
    DEFAULT_REGISTER_HIGH,
    DEFAULT_REGISTER_LOW,
    REGISTER_PRESET_FULL,
    REGISTER_PRESETS,
    note_name_to_midi_ps,
    resolve_register_preset,
)
from registral_dispersion.plotting import make_dispersion_figure
from registral_dispersion.profiles import (
    ANALYSIS_PROFILE_COMPONENT_WEIGHTED,
    ANALYSIS_PROFILE_OCCUPIED_SPACE,
    DEFAULT_ANALYSIS_PROFILE,
    implied_pitch_sampling_mode,
    normalize_analysis_profile,
    resolve_profile_and_pitch_sampling,
)
from registral_dispersion.sampling import normalize_pitch_sampling_mode
from registral_dispersion.score_io import ScoreValidationError, validate_score_path
from registral_dispersion.service import (
    resolve_registral_dispersion_params,
    run_register_uniformity_analysis,
    run_registral_dispersion_analysis,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURE_XML = REPO_ROOT / "tests" / "fixtures" / "step_density.xml"
EMPTY_NO_NOTES_XML = REPO_ROOT / "tests" / "fixtures" / "empty_no_notes.xml"
SINGLE_NOTE_XML = REPO_ROOT / "tests" / "fixtures" / "single_note.xml"

# occupancy_entropy baseline (legacy U), step_density.xml, time_step=0.5, window=4, A1–E7
_BASELINE_OCCUPANCY = np.array(
    [
        0.16427204996205022,
        0.2603650391064418,
        0.2603650391064418,
        0.32854409992410044,
        0.32854409992410044,
        0.42463708906849196,
        0.46116994801745426,
        0.44772027822975025,
        0.41428229800403493,
        0.40396926948997125,
        0.36754185908485143,
        0.36242339151596975,
        0.32854409992410044,
        0.32611749554868635,
        0.32854409992410044,
        0.3237720945249899,
        0.32854409992410044,
    ],
    dtype=float,
)


class TestPitchSamplingNormalize(unittest.TestCase):
    def test_unknown_mode_defaults_to_event_instances(self):
        self.assertEqual(normalize_pitch_sampling_mode("not_a_mode"), "event_instances")

    def test_aliases(self):
        self.assertEqual(normalize_pitch_sampling_mode("UNIQUE_PITCH_HEIGHTS"), "unique_pitch_heights")


class TestAnalysisProfileResolution(unittest.TestCase):
    def test_occupied_space_implies_unique_pitch_heights(self):
        p = resolve_registral_dispersion_params({"analysis_profile": "occupied_space"})
        self.assertEqual(p["analysis_profile"], ANALYSIS_PROFILE_OCCUPIED_SPACE)
        self.assertEqual(p["pitch_sampling_mode"], "unique_pitch_heights")
        self.assertEqual(p["pitch_sampling_source"], "analysis_profile")

    def test_component_weighted_implies_event_instances(self):
        p = resolve_registral_dispersion_params({"analysis_profile": "component_weighted"})
        self.assertEqual(p["pitch_sampling_mode"], "event_instances")
        self.assertEqual(p["pitch_sampling_source"], "analysis_profile")

    def test_explicit_pitch_sampling_overrides_profile(self):
        p = resolve_registral_dispersion_params(
            {"analysis_profile": "occupied_space", "pitch_sampling_mode": "event_instances"}
        )
        self.assertEqual(p["pitch_sampling_mode"], "event_instances")
        self.assertEqual(p["pitch_sampling_source"], "explicit_param")

    def test_implied_pitch_sampling_mode_helpers(self):
        self.assertEqual(implied_pitch_sampling_mode("occupied_space"), "unique_pitch_heights")
        self.assertEqual(implied_pitch_sampling_mode("component_weighted"), "event_instances")

    def test_unknown_profile_defaults_to_occupied_space(self):
        self.assertEqual(normalize_analysis_profile("unknown"), DEFAULT_ANALYSIS_PROFILE)

    def test_empty_params_resolve_to_occupied_space(self):
        p = resolve_registral_dispersion_params({})
        self.assertEqual(p["analysis_profile"], ANALYSIS_PROFILE_OCCUPIED_SPACE)
        self.assertEqual(p["pitch_sampling_mode"], "unique_pitch_heights")
        self.assertEqual(p["pitch_sampling_source"], "analysis_profile")
        self.assertEqual(p["register_low"], "A0")
        self.assertEqual(p["register_high"], "C8")

    def test_observation_mode_defaults_to_fixed_window(self):
        p = resolve_registral_dispersion_params({})
        self.assertEqual(p["observation_mode"], "fixed_window")

    def test_observation_mode_event_boundaries_normalized(self):
        p = resolve_registral_dispersion_params({"observation_mode": "event_boundaries"})
        self.assertEqual(p["observation_mode"], "event_boundaries")


class TestNormalizationScale(unittest.TestCase):
    def test_nan_and_zero(self):
        self.assertTrue(np.isnan(RegistralDispersionAnalyzer.scale_dispersion_by_register_width(float("nan"), 24.0)))
        self.assertEqual(RegistralDispersionAnalyzer.scale_dispersion_by_register_width(0.0, 24.0), 0.0)

    def test_one_octave_in_two_octave_register(self):
        R = 24.0
        self.assertAlmostEqual(RegistralDispersionAnalyzer.scale_dispersion_by_register_width(12.0, R), 0.5)


class TestAnalyzerProfilePitchSamplingAPI(unittest.TestCase):
    """Direct RegistralDispersionAnalyzer must match service profile/sampling resolution."""

    def _minimal_score(self):
        p = stream.Part()
        p.insert(0, note.Note("C4", quarterLength=1.0))
        sc = stream.Score()
        sc.insert(0, p)
        return sc

    def test_direct_occupied_space_implies_unique_pitch_heights(self):
        an = RegistralDispersionAnalyzer.from_stream(
            self._minimal_score(),
            48.0,
            72.0,
            time_step=1.0,
            analysis_profile=ANALYSIS_PROFILE_OCCUPIED_SPACE,
        )
        self.assertEqual(an.analysis_profile, ANALYSIS_PROFILE_OCCUPIED_SPACE)
        self.assertEqual(an.pitch_sampling_mode, "unique_pitch_heights")
        self.assertEqual(an.pitch_sampling_source, "analysis_profile")

    def test_direct_component_weighted_implies_event_instances(self):
        an = RegistralDispersionAnalyzer.from_stream(
            self._minimal_score(),
            48.0,
            72.0,
            time_step=1.0,
            analysis_profile=ANALYSIS_PROFILE_COMPONENT_WEIGHTED,
        )
        self.assertEqual(an.analysis_profile, ANALYSIS_PROFILE_COMPONENT_WEIGHTED)
        self.assertEqual(an.pitch_sampling_mode, "event_instances")
        self.assertEqual(an.pitch_sampling_source, "analysis_profile")

    def test_explicit_pitch_sampling_overrides_profile(self):
        an = RegistralDispersionAnalyzer.from_stream(
            self._minimal_score(),
            48.0,
            72.0,
            time_step=1.0,
            pitch_sampling_mode="event_instances",
            analysis_profile=ANALYSIS_PROFILE_OCCUPIED_SPACE,
        )
        self.assertEqual(an.pitch_sampling_mode, "event_instances")
        self.assertEqual(an.pitch_sampling_source, "explicit_param")

    def test_service_and_direct_analyzer_agree(self):
        sc = self._minimal_score()
        an = RegistralDispersionAnalyzer.from_stream(sc, 48.0, 72.0, time_step=1.0, analysis_profile="occupied_space")
        resolved = resolve_registral_dispersion_params({"analysis_profile": "occupied_space", "time_step": 1.0})
        self.assertEqual(an.analysis_profile, resolved["analysis_profile"])
        self.assertEqual(an.pitch_sampling_mode, resolved["pitch_sampling_mode"])
        self.assertEqual(an.pitch_sampling_source, resolved["pitch_sampling_source"])

    def test_resolve_profile_and_pitch_sampling_matches_service_explicit_rule(self):
        prof, mode, src = resolve_profile_and_pitch_sampling(
            "occupied_space",
            "event_instances",
            pitch_sampling_explicit=True,
        )
        self.assertEqual(prof, ANALYSIS_PROFILE_OCCUPIED_SPACE)
        self.assertEqual(mode, "event_instances")
        self.assertEqual(src, "explicit_param")


class TestDispersionFormulas(unittest.TestCase):
    """Exact expectations for D_span and D_pairwise (static methods)."""

    def test_dispersion_degree_equals_registral_span(self):
        cases = (
            np.array([60.0]),
            np.array([60.0, 72.0]),
            np.array([60.0, 61.0, 62.0]),
        )
        for p in cases:
            self.assertEqual(
                RegistralDispersionAnalyzer.compute_dispersion_degree(p),
                RegistralDispersionAnalyzer.compute_registral_span(p),
            )
        empty = np.array([], dtype=float)
        self.assertTrue(np.isnan(RegistralDispersionAnalyzer.compute_dispersion_degree(empty)))
        self.assertTrue(np.isnan(RegistralDispersionAnalyzer.compute_registral_span(empty)))

    def test_empty_window(self):
        p = np.array([], dtype=float)
        self.assertTrue(np.isnan(RegistralDispersionAnalyzer.compute_registral_span(p)))
        self.assertTrue(np.isnan(RegistralDispersionAnalyzer.compute_mean_pairwise_registral_distance(p)))

    def test_single_pitch(self):
        p = np.array([60.0])
        self.assertEqual(RegistralDispersionAnalyzer.compute_registral_span(p), 0.0)
        self.assertEqual(RegistralDispersionAnalyzer.compute_mean_pairwise_registral_distance(p), 0.0)

    def test_two_pitches_one_octave(self):
        p = np.array([60.0, 72.0])
        self.assertEqual(RegistralDispersionAnalyzer.compute_registral_span(p), 12.0)
        self.assertAlmostEqual(RegistralDispersionAnalyzer.compute_mean_pairwise_registral_distance(p), 12.0)

    def test_compact_cluster_three_semitones(self):
        p = np.array([60.0, 61.0, 62.0])
        self.assertEqual(RegistralDispersionAnalyzer.compute_registral_span(p), 2.0)
        self.assertAlmostEqual(RegistralDispersionAnalyzer.compute_mean_pairwise_registral_distance(p), 4.0 / 3.0)

    def test_widely_dispersed_three(self):
        p = np.array([60.0, 72.0, 84.0])
        self.assertEqual(RegistralDispersionAnalyzer.compute_registral_span(p), 24.0)
        # Pairs: 12+24+12 = 48; 2/(3*2) * 48 = 16
        self.assertAlmostEqual(RegistralDispersionAnalyzer.compute_mean_pairwise_registral_distance(p), 16.0)

    def test_centroid_and_std(self):
        p = np.array([60.0, 72.0, 84.0])
        self.assertAlmostEqual(RegistralDispersionAnalyzer.compute_registral_centroid(p), 72.0)
        self.assertAlmostEqual(RegistralDispersionAnalyzer.compute_registral_std(p), math.sqrt(96.0))

    def test_centroid_empty_and_single(self):
        empty = np.array([], dtype=float)
        self.assertTrue(np.isnan(RegistralDispersionAnalyzer.compute_registral_centroid(empty)))
        self.assertTrue(np.isnan(RegistralDispersionAnalyzer.compute_registral_std(empty)))
        one = np.array([60.0])
        self.assertAlmostEqual(RegistralDispersionAnalyzer.compute_registral_centroid(one), 60.0)
        self.assertEqual(RegistralDispersionAnalyzer.compute_registral_std(one), 0.0)

    def test_normalized_centroid_in_band(self):
        self.assertAlmostEqual(
            RegistralDispersionAnalyzer.normalize_centroid_to_band(72.0, 60.0, 24.0),
            0.5,
        )
        self.assertTrue(np.isnan(RegistralDispersionAnalyzer.normalize_centroid_to_band(float("nan"), 60.0, 24.0)))

    def test_occupancy_entropy_single_bin_not_negative_zero(self):
        sc = stream.Score()
        sc.insert(0, stream.Part())
        sc.parts[0].insert(0, note.Note("C4", quarterLength=1.0))
        an = RegistralDispersionAnalyzer.from_stream(sc, 60.0, 71.0, pitch_sampling_mode="event_instances")
        for pitches in (
            np.array([60.0]),
            np.array([60.0, 60.0]),
            np.array([60.0, 60.1]),
        ):
            u = an.compute_occupancy_entropy(pitches)
            self.assertEqual(u, 0.0)
            self.assertEqual(math.copysign(1.0, u), 1.0)


class TestNotationalSamplingSynthetic(unittest.TestCase):
    """music21 streams: overlap windows, chords, unisons, repeats, empty register band."""

    def test_sustained_note_counts_in_overlapping_windows(self):
        p = stream.Part()
        p.insert(0, note.Note("C4", quarterLength=8.0))
        sc = stream.Score()
        sc.insert(0, p)
        an = RegistralDispersionAnalyzer.from_stream(sc, 48.0, 72.0, time_step=1.0)
        r = an.analyze_score(window_size=2.0)
        counts = np.asarray(r["active_note_count"], dtype=int)
        self.assertGreater(len(counts), 4)
        self.assertTrue(np.all(counts == 1))

    def test_chord_members_separate(self):
        p = stream.Part()
        p.insert(0, chord.Chord(["C4", "E4", "G4"], quarterLength=1.0))
        sc = stream.Score()
        sc.insert(0, p)
        an = RegistralDispersionAnalyzer.from_stream(sc, 48.0, 88.0, time_step=1.0)
        r = an.analyze_score(4.0)
        i = int(np.argmin(np.abs(np.asarray(r["t"], dtype=float) - 0.0)))
        self.assertEqual(r["active_note_count"][i], 3)
        self.assertAlmostEqual(r["registral_span"][i], 7.0)
        self.assertAlmostEqual(r["mean_pairwise_registral_distance"][i], 14.0 / 3.0)

    def test_duplicate_unison_two_parts_event_vs_unique(self):
        p1 = stream.Part()
        p1.insert(0, note.Note("C4", quarterLength=2.0))
        p2 = stream.Part()
        p2.insert(0, note.Note("C4", quarterLength=2.0))
        sc = stream.Score()
        sc.append(p1)
        sc.append(p2)
        ev = RegistralDispersionAnalyzer.from_stream(
            sc,
            48.0,
            72.0,
            time_step=1.0,
            pitch_sampling_mode="event_instances",
            analysis_profile=ANALYSIS_PROFILE_COMPONENT_WEIGHTED,
        )
        un = RegistralDispersionAnalyzer.from_stream(
            sc,
            48.0,
            72.0,
            time_step=1.0,
            pitch_sampling_mode="unique_pitch_heights",
            analysis_profile=ANALYSIS_PROFILE_OCCUPIED_SPACE,
        )
        r_ev = ev.analyze_score(4.0)
        r_un = un.analyze_score(4.0)
        i = int(np.argmin(np.abs(np.asarray(r_ev["t"], dtype=float) - 1.0)))
        self.assertEqual(r_ev["active_note_count"][i], 2)
        self.assertEqual(r_un["active_note_count"][i], 1)
        self.assertAlmostEqual(r_ev["mean_pairwise_registral_distance"][i], 0.0)
        self.assertAlmostEqual(r_un["mean_pairwise_registral_distance"][i], 0.0)
        self.assertAlmostEqual(r_ev["registral_span"][i], r_un["registral_span"][i])

    def test_duplicated_two_note_aggregate_pairwise_differs_span_matches(self):
        p1 = stream.Part()
        p1.insert(0, chord.Chord(["C4", "G4"], quarterLength=2.0))
        p2 = stream.Part()
        p2.insert(0, chord.Chord(["C4", "G4"], quarterLength=2.0))
        sc = stream.Score()
        sc.append(p1)
        sc.append(p2)
        ev = RegistralDispersionAnalyzer.from_stream(
            sc,
            48.0,
            88.0,
            time_step=1.0,
            pitch_sampling_mode="event_instances",
            analysis_profile=ANALYSIS_PROFILE_COMPONENT_WEIGHTED,
        )
        oc = RegistralDispersionAnalyzer.from_stream(
            sc,
            48.0,
            88.0,
            time_step=1.0,
            pitch_sampling_mode="unique_pitch_heights",
            analysis_profile=ANALYSIS_PROFILE_OCCUPIED_SPACE,
        )
        r_ev = ev.analyze_score(4.0)
        r_oc = oc.analyze_score(4.0)
        i = int(np.argmin(np.abs(np.asarray(r_ev["t"], dtype=float) - 1.0)))
        self.assertAlmostEqual(r_ev["registral_span"][i], r_oc["registral_span"][i])
        dp_ev = r_ev["mean_pairwise_registral_distance"][i]
        dp_oc = r_oc["mean_pairwise_registral_distance"][i]
        self.assertNotAlmostEqual(dp_ev, dp_oc)

    def test_repeated_same_pitch_two_noteheads(self):
        p = stream.Part()
        p.insert(0, note.Note("C4", quarterLength=0.5))
        p.insert(0.5, note.Note("C4", quarterLength=0.5))
        sc = stream.Score()
        sc.insert(0, p)
        ev = RegistralDispersionAnalyzer.from_stream(
            sc,
            48.0,
            72.0,
            time_step=0.25,
            pitch_sampling_mode="event_instances",
            analysis_profile=ANALYSIS_PROFILE_COMPONENT_WEIGHTED,
        )
        un = RegistralDispersionAnalyzer.from_stream(
            sc,
            48.0,
            72.0,
            time_step=0.25,
            pitch_sampling_mode="unique_pitch_heights",
            analysis_profile=ANALYSIS_PROFILE_OCCUPIED_SPACE,
        )
        r_ev = ev.analyze_score(2.0)
        r_un = un.analyze_score(2.0)
        i = int(np.argmin(np.abs(np.asarray(r_ev["t"], dtype=float) - 0.5)))
        self.assertEqual(r_ev["active_note_count"][i], 2)
        self.assertEqual(r_un["active_note_count"][i], 1)

    def test_chord_centroid_and_std(self):
        p = stream.Part()
        p.insert(0, chord.Chord(["C4", "E4", "G4"], quarterLength=1.0))
        sc = stream.Score()
        sc.insert(0, p)
        an = RegistralDispersionAnalyzer.from_stream(sc, 48.0, 88.0, time_step=1.0)
        r = an.analyze_score(4.0)
        i = int(np.argmin(np.abs(np.asarray(r["t"], dtype=float) - 0.0)))
        self.assertAlmostEqual(r["registral_centroid"][i], (60.0 + 64.0 + 67.0) / 3.0)
        self.assertAlmostEqual(r["registral_std"][i], 2.8674417556808756)

    def test_empty_window_register_excludes_all(self):
        p = stream.Part()
        p.insert(0, note.Note("C4", quarterLength=4.0))
        sc = stream.Score()
        sc.insert(0, p)
        an = RegistralDispersionAnalyzer.from_stream(sc, 20.0, 23.0, time_step=1.0)
        r = an.analyze_score(4.0)
        self.assertTrue(np.all(np.asarray(r["active_note_count"], dtype=int) == 0))
        self.assertTrue(np.all(np.isnan(np.asarray(r["registral_span"], dtype=float))))

    def test_wide_spaced_aggregate(self):
        p = stream.Part()
        p.insert(0, chord.Chord(["C4", "C5", "C6"], quarterLength=2.0))
        sc = stream.Score()
        sc.insert(0, p)
        an = RegistralDispersionAnalyzer.from_stream(sc, 48.0, 100.0, time_step=1.0)
        r = an.analyze_score(4.0)
        i = int(np.argmin(np.abs(np.asarray(r["t"], dtype=float) - 0.0)))
        self.assertAlmostEqual(r["registral_span"][i], 24.0)
        self.assertAlmostEqual(r["mean_pairwise_registral_distance"][i], 16.0)

    def test_normalized_octave_span_and_pairwise_in_two_octave_band(self):
        """R = 24 (e.g. MIDI 60–84); C4–C5 span and pairwise raw 12 → normalized 0.5."""
        p = stream.Part()
        p.insert(0, chord.Chord(["C4", "C5"], quarterLength=2.0))
        sc = stream.Score()
        sc.insert(0, p)
        an = RegistralDispersionAnalyzer.from_stream(sc, 60.0, 84.0, time_step=1.0)
        self.assertAlmostEqual(an.register_width_semitones, 24.0)
        r = an.analyze_score(4.0)
        i = int(np.argmin(np.abs(np.asarray(r["t"], dtype=float) - 0.0)))
        self.assertAlmostEqual(r["normalized_registral_span"][i], 0.5)
        self.assertAlmostEqual(r["normalized_mean_pairwise_registral_distance"][i], 0.5)

    def test_empty_window_normalized_nan(self):
        p = stream.Part()
        p.insert(0, note.Note("C4", quarterLength=4.0))
        sc = stream.Score()
        sc.insert(0, p)
        an = RegistralDispersionAnalyzer.from_stream(sc, 20.0, 23.0, time_step=1.0)
        r = an.analyze_score(4.0)
        self.assertTrue(np.all(np.isnan(np.asarray(r["normalized_registral_span"], dtype=float))))

    def test_single_pitch_normalized_zeros(self):
        p = stream.Part()
        p.insert(0, note.Note("C4", quarterLength=4.0))
        sc = stream.Score()
        sc.insert(0, p)
        an = RegistralDispersionAnalyzer.from_stream(sc, 48.0, 72.0, time_step=1.0)
        r = an.analyze_score(4.0)
        i = int(np.argmin(np.abs(np.asarray(r["t"], dtype=float) - 0.0)))
        self.assertEqual(r["active_note_count"][i], 1)
        self.assertAlmostEqual(r["normalized_registral_span"][i], 0.0)
        self.assertAlmostEqual(r["normalized_mean_pairwise_registral_distance"][i], 0.0)


class TestRegisterWidthValidation(unittest.TestCase):
    def test_equal_bounds_raise(self):
        sc = stream.Score()
        sc.insert(0, stream.Part([note.Note("C4", quarterLength=1.0)]))
        with self.assertRaises(ValueError) as ctx:
            RegistralDispersionAnalyzer.from_stream(sc, 60.0, 60.0, time_step=1.0)
        self.assertIn("width", str(ctx.exception).lower())


class TestEventBoundariesObservation(unittest.TestCase):
    """Synthetic streams: event_boundaries temporal mode."""

    def test_one_sustained_note_single_interval_span_zero(self):
        p = stream.Part()
        p.insert(0, note.Note("C4", quarterLength=4.0))
        sc = stream.Score()
        sc.insert(0, p)
        an = RegistralDispersionAnalyzer.from_stream(sc, 48.0, 72.0, time_step=1.0)
        r = an.analyze_score(4.0, observation_mode=OBSERVATION_MODE_EVENT_BOUNDARIES)
        self.assertEqual(len(r["t"]), 1)
        self.assertAlmostEqual(r["interval_start"][0], 0.0)
        self.assertAlmostEqual(r["interval_end"][0], 4.0)
        self.assertAlmostEqual(r["interval_duration"][0], 4.0)
        self.assertEqual(r["active_note_count"][0], 1)
        self.assertAlmostEqual(r["registral_span"][0], 0.0)
        self.assertAlmostEqual(r["mean_pairwise_registral_distance"][0], 0.0)

    def test_overlapping_two_notes_three_intervals(self):
        p = stream.Part()
        p.insert(0, note.Note("C4", quarterLength=2.0))
        p.insert(1, note.Note("C5", quarterLength=2.0))
        sc = stream.Score()
        sc.insert(0, p)
        an = RegistralDispersionAnalyzer.from_stream(sc, 48.0, 88.0, time_step=1.0)
        r = an.analyze_score(4.0, observation_mode=OBSERVATION_MODE_EVENT_BOUNDARIES)
        self.assertEqual(len(r["t"]), 3)
        self.assertAlmostEqual(r["interval_start"][0], 0.0)
        self.assertAlmostEqual(r["interval_end"][0], 1.0)
        self.assertEqual(r["active_note_count"][0], 1)
        self.assertAlmostEqual(r["registral_span"][0], 0.0)
        self.assertAlmostEqual(r["interval_start"][1], 1.0)
        self.assertAlmostEqual(r["interval_end"][1], 2.0)
        self.assertEqual(r["active_note_count"][1], 2)
        self.assertAlmostEqual(r["registral_span"][1], 12.0)
        self.assertAlmostEqual(r["mean_pairwise_registral_distance"][1], 12.0)
        self.assertAlmostEqual(r["interval_start"][2], 2.0)
        self.assertAlmostEqual(r["interval_end"][2], 3.0)
        self.assertEqual(r["active_note_count"][2], 1)
        self.assertAlmostEqual(r["registral_span"][2], 0.0)

    def test_chord_one_interval_expected_dispersion(self):
        p = stream.Part()
        p.insert(0, chord.Chord(["C4", "E4", "G4"], quarterLength=1.0))
        sc = stream.Score()
        sc.insert(0, p)
        an = RegistralDispersionAnalyzer.from_stream(sc, 48.0, 88.0, time_step=1.0)
        r = an.analyze_score(4.0, observation_mode=OBSERVATION_MODE_EVENT_BOUNDARIES)
        self.assertEqual(len(r["t"]), 1)
        self.assertEqual(r["active_note_count"][0], 3)
        self.assertAlmostEqual(r["registral_span"][0], 7.0)
        self.assertAlmostEqual(r["mean_pairwise_registral_distance"][0], 14.0 / 3.0)

    def test_rest_gap_row_included_with_nan_metrics(self):
        p = stream.Part()
        p.insert(0, note.Note("C4", quarterLength=1.0))
        p.insert(2, note.Note("D4", quarterLength=1.0))
        sc = stream.Score()
        sc.insert(0, p)
        an = RegistralDispersionAnalyzer.from_stream(sc, 48.0, 72.0, time_step=1.0)
        r = an.analyze_score(4.0, observation_mode=OBSERVATION_MODE_EVENT_BOUNDARIES)
        gap_idx = next(
            i
            for i in range(len(r["interval_start"]))
            if r["interval_start"][i] >= 1.0 - 1e-9 and r["interval_end"][i] <= 2.0 + 1e-9
        )
        self.assertEqual(r["active_note_count"][gap_idx], 0)
        self.assertTrue(np.isnan(r["registral_span"][gap_idx]))

    def test_event_occupied_space_collapses_duplicate_unisons(self):
        # Same written height twice in one chord → two raw components; unique_pitch_heights collapses.
        p = stream.Part()
        p.insert(0, chord.Chord(["C4", "C4"], quarterLength=2.0))
        sc = stream.Score()
        sc.insert(0, p)
        an = RegistralDispersionAnalyzer.from_stream(
            sc,
            48.0,
            72.0,
            time_step=1.0,
            analysis_profile=ANALYSIS_PROFILE_OCCUPIED_SPACE,
        )
        self.assertEqual(an.pitch_sampling_mode, "unique_pitch_heights")
        r = an.analyze_score(4.0, observation_mode=OBSERVATION_MODE_EVENT_BOUNDARIES)
        idx = next(i for i in range(len(r["t"])) if r["active_note_count"][i] > 0)
        self.assertAlmostEqual(r["interval_start"][idx], 0.0)
        self.assertAlmostEqual(r["interval_end"][idx], 2.0)
        self.assertEqual(r["active_note_count"][idx], 1)

    def test_event_component_weighted_preserves_duplicate_unisons(self):
        p = stream.Part()
        p.insert(0, chord.Chord(["C4", "C4"], quarterLength=2.0))
        sc = stream.Score()
        sc.insert(0, p)
        an = RegistralDispersionAnalyzer.from_stream(
            sc,
            48.0,
            72.0,
            time_step=1.0,
            analysis_profile=ANALYSIS_PROFILE_COMPONENT_WEIGHTED,
        )
        self.assertEqual(an.pitch_sampling_mode, "event_instances")
        r = an.analyze_score(4.0, observation_mode=OBSERVATION_MODE_EVENT_BOUNDARIES)
        idx = next(i for i in range(len(r["t"])) if r["active_note_count"][i] > 0)
        self.assertAlmostEqual(r["interval_start"][idx], 0.0)
        self.assertAlmostEqual(r["interval_end"][idx], 2.0)
        self.assertEqual(r["active_note_count"][idx], 2)

    def test_event_csv_and_json_include_mode_and_interval_fields(self):
        p = stream.Part()
        p.insert(0, note.Note("C4", quarterLength=1.0))
        sc = stream.Score()
        sc.insert(0, p)
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            path = root / "ev.musicxml"
            sc.write("musicxml", fp=str(path))
            out = run_registral_dispersion_analysis(
                str(path),
                {
                    "observation_mode": "event_boundaries",
                    "register_low": "A1",
                    "register_high": "E7",
                    "window_size": 4.0,
                },
            )
            self.assertIsNone(out.get("error"))
            doc = build_registral_dispersion_export(str(path), {}, out)
            self.assertEqual(doc.get("observation_mode"), "event_boundaries")
            self.assertIn("interval_start", doc["results"])
            self.assertIn("interval_duration", doc["results"])
            csv_p = root / "o.csv"
            rp = out["params"]
            an = out["analyzer"]
            write_registral_dispersion_csv(
                csv_p,
                out["results"],
                pitch_sampling_mode=rp.get("pitch_sampling_mode"),
                analysis_profile=rp.get("analysis_profile"),
                pitch_sampling_source=rp.get("pitch_sampling_source"),
                observation_mode=rp.get("observation_mode"),
                register_low_midi=float(an.register_low),
                register_high_midi=float(an.register_high),
                register_width_semitones=float(an.register_width_semitones),
            )
            text = csv_p.read_text(encoding="utf-8")
        self.assertIn("# observation_mode: event_boundaries", text)
        hdr = next(ln for ln in text.splitlines() if ln.strip() and not ln.startswith("#"))
        self.assertIn("interval_start", hdr)
        self.assertIn("interval_duration", hdr)


class TestNoteNameToMidiPs(unittest.TestCase):
    def test_a0(self):
        self.assertAlmostEqual(note_name_to_midi_ps("A0"), 21.0)

    def test_a1(self):
        self.assertAlmostEqual(note_name_to_midi_ps("A1"), 33.0)

    def test_c8(self):
        self.assertAlmostEqual(note_name_to_midi_ps("C8"), 108.0)

    def test_c4(self):
        self.assertAlmostEqual(note_name_to_midi_ps("C4"), 60.0)


class TestRegisterPresets(unittest.TestCase):
    def test_default_register_constants(self):
        self.assertEqual(DEFAULT_REGISTER_LOW, "A0")
        self.assertEqual(DEFAULT_REGISTER_HIGH, "C8")

    def test_full_preset_resolves_a0_c8(self):
        self.assertEqual(resolve_register_preset(REGISTER_PRESET_FULL), ("A0", "C8"))

    def test_full_preset_only_in_ui(self):
        self.assertEqual(REGISTER_PRESETS[REGISTER_PRESET_FULL], ("A0", "C8"))
        self.assertEqual(len(REGISTER_PRESETS), 1)
        self.assertNotIn("A1 to E7 (orchestral band)", REGISTER_PRESETS)

    def test_legacy_a0_b7_label_maps_to_a0_c8(self):
        self.assertEqual(
            resolve_register_preset("A0 to B7 (full notated range)"),
            ("A0", "C8"),
        )
        self.assertNotIn("A0 to B7 (full notated range)", REGISTER_PRESETS)

    def test_legacy_orchestral_label_maps_to_a0_c8(self):
        self.assertEqual(
            resolve_register_preset("A1 to E7 (orchestral band)"),
            ("A0", "C8"),
        )


class TestAnalysisPresets(unittest.TestCase):
    def test_guidance_text_for_advised_presets(self):
        self.assertIn("Static vertical aggregate", preset_guidance_text(PRESET_STATIC_VERTICAL))
        self.assertIn("Moving fragment", preset_guidance_text(PRESET_MOVING_FRAGMENT))
        self.assertIn("Custom", preset_guidance_text(PRESET_CUSTOM))

    def test_static_preset_spec(self):
        spec = PRESET_SPECS[PRESET_STATIC_VERTICAL]
        self.assertEqual(spec.observation_mode, OBSERVATION_MODE_EVENT_BOUNDARIES)
        self.assertEqual(spec.primary_metric, "dispersion_degree")
        self.assertFalse(spec.show_registral_span)

    def test_moving_preset_spec(self):
        spec = PRESET_SPECS[PRESET_MOVING_FRAGMENT]
        self.assertEqual(spec.observation_mode, OBSERVATION_MODE_FIXED_WINDOW)
        self.assertEqual(spec.primary_metric, "dispersion_degree")
        self.assertFalse(spec.show_registral_span)

    def test_apply_preset_updates_values(self):
        updates = apply_analysis_preset(PRESET_STATIC_VERTICAL)
        self.assertEqual(len(updates), 16)
        (
            guidance,
            reg_preset,
            reg_lo,
            reg_hi,
            dt,
            _win,
            _profile,
            obs,
            _pitch,
            _span,
            _ent,
            _norm_y,
            _heat,
            _hmode,
            _hnorm,
            _hcmap,
        ) = updates
        self.assertIn("Static vertical aggregate", guidance)
        self.assertEqual(reg_preset["value"], PRESET_SPECS[PRESET_STATIC_VERTICAL].register_preset)
        self.assertEqual(reg_lo["value"], "A0")
        self.assertEqual(reg_hi["value"], "C8")
        self.assertEqual(dt["value"], 0.25)
        self.assertEqual(obs["value"], OBSERVATION_MODE_EVENT_BOUNDARIES)

    def test_apply_custom_is_noop(self):
        updates = apply_analysis_preset(PRESET_CUSTOM)
        self.assertIn("Custom", updates[0])
        for item in updates[1:]:
            self.assertNotIn("value", item)


class TestRegisterUniformityAnalyzerLegacy(unittest.TestCase):
    """Legacy class returns only t and U (occupancy_entropy)."""

    @classmethod
    def setUpClass(cls):
        if not FIXTURE_XML.is_file():
            raise unittest.SkipTest(f"Fixture not found: {FIXTURE_XML}")
        cls.analyzer = RegisterUniformityAnalyzer(
            score_path=str(FIXTURE_XML),
            register_low_ps=21.0,
            register_high_ps=88.0,
            time_step=0.5,
        )

    def test_compute_uniformity_empty(self):
        U = self.analyzer.compute_uniformity(np.array([]))
        self.assertTrue(np.isnan(U))

    def test_compute_uniformity_single_pitch(self):
        U = self.analyzer.compute_uniformity(np.array([60.0]))
        self.assertEqual(U, 0.0)

    def test_analyze_score_legacy_shape(self):
        results = self.analyzer.analyze_score(window_size=4.0)
        self.assertEqual(set(results.keys()), {"t", "U"})
        self.assertEqual(len(results["t"]), len(results["U"]))

    def test_legacy_defaults_component_weighted_and_event_instances(self):
        self.assertEqual(self.analyzer.analysis_profile, ANALYSIS_PROFILE_COMPONENT_WEIGHTED)
        self.assertEqual(self.analyzer.pitch_sampling_mode, "event_instances")
        self.assertEqual(self.analyzer.pitch_sampling_source, "analysis_profile")


class TestRunRegisterUniformityAnalysis(unittest.TestCase):
    def test_occupancy_baseline_unchanged(self):
        if not FIXTURE_XML.is_file():
            self.skipTest("Fixture not found")
        out = run_register_uniformity_analysis(
            str(FIXTURE_XML),
            {"time_step": 0.5, "window_size": 4.0, "register_low": "A1", "register_high": "E7"},
        )
        self.assertIsNone(out.get("error"))
        got = np.array(out["results"]["U"], dtype=float)
        np.testing.assert_allclose(got, _BASELINE_OCCUPANCY, rtol=0, atol=0, equal_nan=True)


class TestRunRegistralDispersionAnalysis(unittest.TestCase):
    def test_invalid_observation_mode_returns_error(self):
        if not FIXTURE_XML.is_file():
            self.skipTest("Fixture not found")
        out = run_registral_dispersion_analysis(
            str(FIXTURE_XML),
            {"observation_mode": "not_a_mode", "window_size": 4.0, "register_low": "A1", "register_high": "E7"},
        )
        self.assertIsNotNone(out.get("error"))
        self.assertIn("observation_mode", (out.get("error") or "").lower())

    def test_full_result_keys_default_profile(self):
        if not FIXTURE_XML.is_file():
            self.skipTest("Fixture not found")
        out = run_registral_dispersion_analysis(
            str(FIXTURE_XML),
            {"time_step": 0.5, "window_size": 4.0, "register_low": "A1", "register_high": "E7"},
        )
        self.assertIsNone(out.get("error"))
        self.assertEqual(out["params"]["analysis_profile"], ANALYSIS_PROFILE_OCCUPIED_SPACE)
        self.assertEqual(out["params"]["pitch_sampling_mode"], "unique_pitch_heights")
        self.assertEqual(out["params"]["pitch_sampling_source"], "analysis_profile")
        r = out["results"]
        for k in (
            "t",
            "interval_start",
            "interval_end",
            "interval_duration",
            "window_start",
            "window_end",
            "active_note_count",
            "min_pitch",
            "max_pitch",
            "dispersion_degree",
            "normalized_dispersion_degree",
            "registral_span",
            "mean_pairwise_registral_distance",
            "registral_centroid",
            "registral_std",
            "normalized_registral_span",
            "normalized_mean_pairwise_registral_distance",
            "normalized_registral_centroid",
            "normalized_registral_std",
            "occupancy_entropy",
        ):
            self.assertIn(k, r)
        self.assertEqual(len(r["t"]), len(r["dispersion_degree"]))
        np.testing.assert_allclose(
            np.asarray(r["dispersion_degree"], dtype=float),
            np.asarray(r["registral_span"], dtype=float),
            equal_nan=True,
        )
        np.testing.assert_allclose(
            np.asarray(r["normalized_dispersion_degree"], dtype=float),
            np.asarray(r["normalized_registral_span"], dtype=float),
            equal_nan=True,
        )
        self.assertEqual(out["params"].get("observation_mode"), "fixed_window")
        for i in range(len(r["t"])):
            self.assertAlmostEqual(r["interval_start"][i], r["window_start"][i])
            self.assertAlmostEqual(r["interval_end"][i], r["window_end"][i])
        occ = np.asarray(r["occupancy_entropy"], dtype=float)
        with self.assertRaises(AssertionError):
            np.testing.assert_allclose(occ, _BASELINE_OCCUPANCY, rtol=0, atol=0, equal_nan=True)

    def test_fixture_occupancy_baseline_requires_component_weighted(self):
        if not FIXTURE_XML.is_file():
            self.skipTest("Fixture not found")
        out = run_registral_dispersion_analysis(
            str(FIXTURE_XML),
            {
                "time_step": 0.5,
                "window_size": 4.0,
                "register_low": "A1",
                "register_high": "E7",
                "analysis_profile": ANALYSIS_PROFILE_COMPONENT_WEIGHTED,
            },
        )
        self.assertIsNone(out.get("error"))
        self.assertEqual(out["params"]["analysis_profile"], ANALYSIS_PROFILE_COMPONENT_WEIGHTED)
        self.assertEqual(out["params"]["pitch_sampling_mode"], "event_instances")
        np.testing.assert_allclose(
            np.asarray(out["results"]["occupancy_entropy"], dtype=float),
            _BASELINE_OCCUPANCY,
            rtol=0,
            atol=0,
            equal_nan=True,
        )

    def test_duplicate_unison_collapsed_under_default_file_run(self):
        p1 = stream.Part()
        p1.insert(0, note.Note("C4", quarterLength=4.0))
        p2 = stream.Part()
        p2.insert(0, note.Note("C4", quarterLength=4.0))
        sc = stream.Score()
        sc.append(p1)
        sc.append(p2)
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "unison.musicxml"
            sc.write("musicxml", fp=str(path))
            out = run_registral_dispersion_analysis(
                str(path),
                {
                    "time_step": 1.0,
                    "window_size": 4.0,
                    "register_low": "A1",
                    "register_high": "C6",
                },
            )
        self.assertIsNone(out.get("error"))
        self.assertEqual(out["params"]["analysis_profile"], ANALYSIS_PROFILE_OCCUPIED_SPACE)
        r = out["results"]
        i = int(np.argmin(np.abs(np.asarray(r["t"], dtype=float) - 1.0)))
        self.assertEqual(r["active_note_count"][i], 1)

    def test_empty_score_returns_error(self):
        if not EMPTY_NO_NOTES_XML.is_file():
            self.skipTest("Fixture not found")
        out = run_registral_dispersion_analysis(
            str(EMPTY_NO_NOTES_XML),
            {"window_size": 4.0, "register_low": "A1", "register_high": "E7"},
        )
        self.assertIsNotNone(out.get("error"))


class TestScoreValidation(unittest.TestCase):
    def test_rejects_wrong_extension(self):
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            path = f.name
        try:
            with self.assertRaises(ScoreValidationError):
                validate_score_path(path)
        finally:
            os.unlink(path)


class TestPlottingSmoke(unittest.TestCase):
    def test_make_dispersion_figure(self):
        if not FIXTURE_XML.is_file():
            self.skipTest("Fixture not found")
        out = run_registral_dispersion_analysis(
            str(FIXTURE_XML),
            {"time_step": 1.0, "window_size": 4.0, "register_low": "C4", "register_high": "G4"},
        )
        self.assertIsNone(out.get("error"))
        fig = make_dispersion_figure(out["results"], show_registral_span=True, show_occupancy_entropy=True)
        try:
            self.assertGreater(len(fig.axes), 0)
        finally:
            plt.close(fig)

    def test_make_dispersion_figure_normalized_y(self):
        if not FIXTURE_XML.is_file():
            self.skipTest("Fixture not found")
        out = run_registral_dispersion_analysis(
            str(FIXTURE_XML),
            {"time_step": 1.0, "window_size": 4.0, "register_low": "C4", "register_high": "G4"},
        )
        self.assertIsNone(out.get("error"))
        fig = make_dispersion_figure(
            out["results"],
            show_registral_span=True,
            show_occupancy_entropy=False,
            y_scale="normalized",
        )
        try:
            self.assertGreater(len(fig.axes), 0)
        finally:
            plt.close(fig)


class TestOutputPaths(unittest.TestCase):
    def test_new_export_path_under_tmp(self):
        with (
            tempfile.TemporaryDirectory() as td,
            mock.patch.dict(os.environ, {"REGISTRAL_DISPERSION_CACHE_DIR": td}, clear=False),
        ):
            p = new_export_path("test_", ".csv")
            Path(p).write_text("x", encoding="utf-8")
            self.assertTrue(str(p).startswith(td))


class TestGradioBuild(unittest.TestCase):
    def test_build_demo(self):
        demo = build_demo()
        self.assertIsNotNone(demo)


class TestJsonExport(unittest.TestCase):
    def test_registral_export_includes_normalization_metadata(self):
        if not FIXTURE_XML.is_file():
            self.skipTest("Fixture not found")
        out = run_registral_dispersion_analysis(
            str(FIXTURE_XML),
            {"time_step": 0.5, "window_size": 4.0, "register_low": "A1", "register_high": "E7"},
        )
        doc = build_registral_dispersion_export(str(FIXTURE_XML), {}, out)
        self.assertEqual(doc.get("normalization_reference"), NORMALIZATION_REFERENCE)
        self.assertIn("register_width_semitones", doc)
        self.assertEqual(doc.get("schema_version"), "1.10")
        self.assertEqual(doc.get("observation_mode"), "fixed_window")
        self.assertIn("metric_formulas", doc)
        self.assertIn("package_version", doc)
        self.assertEqual(doc.get("tool_role"), "research_software")
        self.assertEqual(doc.get("canonical_tool_name"), "Registral_Dispersion")
        sm = doc.get("score_metadata") or {}
        self.assertEqual(sm.get("normalization_reference"), NORMALIZATION_REFERENCE)
        self.assertIn("register_low_midi", sm)
        self.assertEqual(sm.get("observation_mode"), "fixed_window")

    def test_registral_export_default_profile_metadata(self):
        if not FIXTURE_XML.is_file():
            self.skipTest("Fixture not found")
        out = run_registral_dispersion_analysis(
            str(FIXTURE_XML),
            {"time_step": 0.5, "window_size": 4.0, "register_low": "A1", "register_high": "E7"},
        )
        doc = build_registral_dispersion_export(str(FIXTURE_XML), {"register_low": "A1"}, out)
        self.assertEqual(doc.get("kind"), "registral_dispersion")
        self.assertEqual(doc.get("schema_version"), "1.10")
        self.assertEqual(doc.get("pitch_sampling_mode"), "unique_pitch_heights")
        self.assertEqual(doc.get("analysis_profile"), "occupied_space")
        self.assertEqual(doc.get("pitch_sampling_source"), "analysis_profile")
        self.assertIn("methodological_note", doc)
        self.assertIn("methodological_note_analysis_profiles", doc)
        self.assertIn("dispersion_degree_definition", doc)
        self.assertIn("dispersion_degree", doc["results"])
        self.assertIn("registral_centroid", doc["results"])
        self.assertIn("normalized_registral_span", doc["results"])
        self.assertEqual(doc.get("score_metadata", {}).get("pitch_sampling_mode"), "unique_pitch_heights")
        self.assertEqual(doc.get("score_metadata", {}).get("analysis_profile"), "occupied_space")

    def test_registral_export_component_weighted_explicit(self):
        if not FIXTURE_XML.is_file():
            self.skipTest("Fixture not found")
        out = run_registral_dispersion_analysis(
            str(FIXTURE_XML),
            {
                "time_step": 0.5,
                "window_size": 4.0,
                "register_low": "A1",
                "register_high": "E7",
                "analysis_profile": ANALYSIS_PROFILE_COMPONENT_WEIGHTED,
            },
        )
        doc = build_registral_dispersion_export(str(FIXTURE_XML), {}, out)
        self.assertEqual(doc.get("analysis_profile"), "component_weighted")
        self.assertEqual(doc.get("pitch_sampling_mode"), "event_instances")

    def test_legacy_register_export_kind(self):
        if not FIXTURE_XML.is_file():
            self.skipTest("Fixture not found")
        out = run_register_uniformity_analysis(
            str(FIXTURE_XML),
            {"time_step": 0.5, "window_size": 4.0, "register_low": "A1", "register_high": "E7"},
        )
        doc = build_register_export(str(FIXTURE_XML), {}, out)
        self.assertEqual(doc.get("kind"), "register_uniformity_legacy")
        self.assertIn("U", doc["results"])


class TestCsvExport(unittest.TestCase):
    def test_equal_register_service_error(self):
        if not FIXTURE_XML.is_file():
            self.skipTest("Fixture not found")
        out = run_registral_dispersion_analysis(
            str(FIXTURE_XML),
            {"register_low": "C4", "register_high": "C4", "window_size": 4.0},
        )
        self.assertIsNotNone(out.get("error"))
        self.assertIn("width", (out.get("error") or "").lower())

    def test_full_csv_reflects_default_occupied_space(self):
        if not FIXTURE_XML.is_file():
            self.skipTest("Fixture not found")
        out = run_registral_dispersion_analysis(
            str(FIXTURE_XML),
            {"time_step": 0.5, "window_size": 4.0, "register_low": "A1", "register_high": "E7"},
        )
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "curve.csv"
            rp = out["params"]
            an = out["analyzer"]
            write_registral_dispersion_csv(
                p,
                out["results"],
                pitch_sampling_mode=rp.get("pitch_sampling_mode"),
                analysis_profile=rp.get("analysis_profile"),
                pitch_sampling_source=rp.get("pitch_sampling_source"),
                observation_mode=rp.get("observation_mode"),
                register_low_midi=float(an.register_low),
                register_high_midi=float(an.register_high),
                register_width_semitones=float(an.register_width_semitones),
            )
            text = p.read_text(encoding="utf-8")
            self.assertIn(f"# normalization_reference: {NORMALIZATION_REFERENCE}", text)
            self.assertIn("# register_width_semitones:", text)
            self.assertIn("# analysis_profile: occupied_space", text)
            self.assertIn("# pitch_sampling_mode: unique_pitch_heights", text)
            self.assertIn("# pitch_sampling_source: analysis_profile", text)
            self.assertIn("# observation_mode: fixed_window", text)
            self.assertIn("Formulas: dispersion_degree", text)
            self.assertIn("mean_pairwise_registral_distance", text)
            hdr = next(ln for ln in text.splitlines() if ln.strip() and not ln.startswith("#"))
            self.assertIn("dispersion_degree", hdr)
            self.assertIn("normalized_dispersion_degree", hdr)
            self.assertIn("registral_centroid", hdr)
            self.assertIn("normalized_registral_centroid", hdr)
            self.assertIn("normalized_registral_span", hdr)
            self.assertIn("interval_start", hdr)

    def test_full_csv_legacy_baseline_with_component_weighted(self):
        if not FIXTURE_XML.is_file():
            self.skipTest("Fixture not found")
        out = run_registral_dispersion_analysis(
            str(FIXTURE_XML),
            {
                "time_step": 0.5,
                "window_size": 4.0,
                "register_low": "A1",
                "register_high": "E7",
                "analysis_profile": ANALYSIS_PROFILE_COMPONENT_WEIGHTED,
            },
        )
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "curve.csv"
            rp = out["params"]
            an = out["analyzer"]
            write_registral_dispersion_csv(
                p,
                out["results"],
                pitch_sampling_mode=rp.get("pitch_sampling_mode"),
                analysis_profile=rp.get("analysis_profile"),
                pitch_sampling_source=rp.get("pitch_sampling_source"),
                observation_mode=rp.get("observation_mode"),
                register_low_midi=float(an.register_low),
                register_high_midi=float(an.register_high),
                register_width_semitones=float(an.register_width_semitones),
            )
            text = p.read_text(encoding="utf-8")
            self.assertIn("# analysis_profile: component_weighted", text)
            self.assertIn("# pitch_sampling_mode: event_instances", text)
            lines = [ln for ln in text.splitlines() if ln.strip() and not ln.startswith("#")]
            header = lines[0]
            self.assertIn("occupancy_entropy", header)
            data = np.genfromtxt(lines[1:], delimiter=",", dtype=float)
            occ_col = data[:, -1]
            np.testing.assert_allclose(occ_col, _BASELINE_OCCUPANCY, rtol=0, atol=0, equal_nan=True)

    def test_legacy_two_column_csv(self):
        if not FIXTURE_XML.is_file():
            self.skipTest("Fixture not found")
        out = run_register_uniformity_analysis(
            str(FIXTURE_XML),
            {"time_step": 0.5, "window_size": 4.0, "register_low": "A1", "register_high": "E7"},
        )
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "legacy.csv"
            write_register_uniformity_csv(
                p,
                np.array(out["results"]["t"]),
                np.array(out["results"]["U"]),
            )
            lines = [ln for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()]
            body = [ln for ln in lines if not ln.startswith("#")]
            data = np.genfromtxt(body[1:], delimiter=",", dtype=float)
            np.testing.assert_allclose(data[:, 1], _BASELINE_OCCUPANCY, rtol=0, atol=0, equal_nan=True)


if __name__ == "__main__":
    unittest.main()
