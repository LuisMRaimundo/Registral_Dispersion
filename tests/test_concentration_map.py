"""Tests for symbolic registral concentration map (visualization only)."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.figure import Figure
from music21 import chord, note, stream

from registral_dispersion.__main__ import main
from registral_dispersion.analyzer import RegistralDispersionAnalyzer
from registral_dispersion.concentration_map import (
    DISPLAY_NORMALIZATION_LOG1P,
    _apply_display_normalization,
    build_registral_concentration_matrix,
    dispersion_overlay_from_results,
    make_registral_concentration_map,
    make_registral_concentration_map_plotly,
    run_concentration_map_to_files,
    write_concentration_matrix_csv,
    write_concentration_matrix_npz,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
SINGLE_NOTE_XML = REPO_ROOT / "tests" / "fixtures" / "single_note.xml"


def _score_c4_sustain(ql: float = 4.0) -> stream.Score:
    p = stream.Part()
    p.insert(0, note.Note("C4", quarterLength=ql))
    sc = stream.Score()
    sc.insert(0, p)
    return sc


class TestConcentrationMatrix(unittest.TestCase):
    def test_sustained_c4_row_active_across_bins(self):
        sc = _score_c4_sustain(4.0)
        b = build_registral_concentration_matrix(
            sc, 48.0, 72.0, time_bin_size=1.0, concentration_mode="event_instances"
        )
        mat = b["matrix"]
        mids = b["pitch_midi"]
        self.assertIn(60, mids)
        i = int(np.where(mids == 60)[0][0])
        self.assertTrue(np.all(mat[i, :] >= 1.0))
        self.assertEqual(mat.shape[1], 4)

    def test_chord_c4_g4_both_rows(self):
        p = stream.Part()
        p.insert(0, chord.Chord(["C4", "G4"], quarterLength=1.0))
        sc = stream.Score()
        sc.insert(0, p)
        b = build_registral_concentration_matrix(
            sc, 48.0, 72.0, time_bin_size=1.0, concentration_mode="event_instances"
        )
        mat = b["matrix"]
        mids = b["pitch_midi"]
        i_c = int(np.where(mids == 60)[0][0])
        i_g = int(np.where(mids == 67)[0][0])
        self.assertGreaterEqual(mat[i_c, 0], 1.0)
        self.assertGreaterEqual(mat[i_g, 0], 1.0)

    def test_duplicate_unison_event_instances_count_two(self):
        p1 = stream.Part()
        p2 = stream.Part()
        p1.insert(0, note.Note("C4", quarterLength=2.0))
        p2.insert(0, note.Note("C4", quarterLength=2.0))
        sc = stream.Score()
        sc.insert(0, p1)
        sc.insert(0, p2)
        b = build_registral_concentration_matrix(
            sc, 48.0, 72.0, time_bin_size=1.0, concentration_mode="event_instances"
        )
        mat = b["matrix"]
        mids = b["pitch_midi"]
        i = int(np.where(mids == 60)[0][0])
        self.assertEqual(mat[i, 0], 2.0)

    def test_duplicate_unison_unique_pitch_heights_count_one(self):
        p1 = stream.Part()
        p2 = stream.Part()
        p1.insert(0, note.Note("C4", quarterLength=2.0))
        p2.insert(0, note.Note("C4", quarterLength=2.0))
        sc = stream.Score()
        sc.insert(0, p1)
        sc.insert(0, p2)
        b = build_registral_concentration_matrix(
            sc, 48.0, 72.0, time_bin_size=1.0, concentration_mode="unique_pitch_heights"
        )
        mat = b["matrix"]
        mids = b["pitch_midi"]
        i = int(np.where(mids == 60)[0][0])
        self.assertEqual(mat[i, 0], 1.0)

    def test_empty_bin_zero(self):
        p = stream.Part()
        p.insert(0, note.Note("C4", quarterLength=0.5))
        p.insert(4.0, note.Note("D4", quarterLength=0.5))
        sc = stream.Score()
        sc.insert(0, p)
        b = build_registral_concentration_matrix(
            sc, 48.0, 72.0, time_bin_size=0.25, concentration_mode="event_instances"
        )
        mat = b["matrix"]
        mids = b["pitch_midi"]
        i = int(np.where(mids == 60)[0][0])
        # Gap between C4 ending at 0.5 and D4 at 4.0 — e.g. bin [1.0, 1.25) has no activity.
        j = int(np.searchsorted(b["time_bin_edges"], 1.0, side="right") - 1)
        self.assertEqual(mat[i, j], 0.0)

    def test_matrix_shape_matches_register_and_time_bin(self):
        sc = _score_c4_sustain(1.0)
        b = build_registral_concentration_matrix(
            sc, 59.0, 61.0, time_bin_size=0.25, concentration_mode="event_instances"
        )
        mat = b["matrix"]
        self.assertEqual(mat.shape[0], 3)
        self.assertEqual(mat.shape[1], 4)

    def test_matplotlib_figure_returned(self):
        sc = _score_c4_sustain(1.0)
        b = build_registral_concentration_matrix(
            sc, 48.0, 72.0, time_bin_size=0.5, concentration_mode="event_instances"
        )
        fig = make_registral_concentration_map(b, title="Test map")
        self.assertIsInstance(fig, Figure)

    def test_dispersion_overlay_xlim_matches_heatmap(self):
        p = stream.Part()
        p.insert(0, chord.Chord(["C4", "E4", "G4"], quarterLength=2.0))
        sc = stream.Score()
        sc.insert(0, p)
        dt = 0.5
        b = build_registral_concentration_matrix(sc, 48.0, 72.0, time_bin_size=dt, concentration_mode="event_instances")
        edges = np.asarray(b["time_bin_edges"], dtype=float)
        an = RegistralDispersionAnalyzer.from_stream(sc, 48.0, 72.0, time_step=dt)
        results = an.analyze_score(window_size=1.0)
        ot, mp, sp = dispersion_overlay_from_results(results)
        self.assertEqual(ot.size, mp.size)
        fig = make_registral_concentration_map(
            b,
            overlay_t=ot,
            overlay_mean_pairwise=mp,
            overlay_registral_span=sp,
        )
        try:
            ax = fig.axes[0]
            self.assertAlmostEqual(ax.get_xlim()[0], float(edges[0]))
            self.assertAlmostEqual(ax.get_xlim()[1], float(edges[-1]))
            overlay_axes = [a for a in fig.axes if a.get_lines()]
            self.assertGreaterEqual(len(overlay_axes), 1)
            for oax in overlay_axes:
                self.assertAlmostEqual(oax.get_xlim()[0], float(edges[0]))
                self.assertAlmostEqual(oax.get_xlim()[1], float(edges[-1]))
        finally:
            plt.close(fig)

    def test_dispersion_overlay_from_results_keys(self):
        results = {
            "t": [0.0, 1.0],
            "mean_pairwise_registral_distance": [1.0, 2.0],
            "registral_span": [3.0, 4.0],
        }
        t, mp, sp = dispersion_overlay_from_results(results)
        np.testing.assert_array_equal(t, [0.0, 1.0])
        np.testing.assert_array_equal(mp, [1.0, 2.0])
        np.testing.assert_array_equal(sp, [3.0, 4.0])

    def test_log1p_display_normalization(self):
        m = np.array([[0.0, 1.0, 10.0]], dtype=float)
        disp, suffix = _apply_display_normalization(m, DISPLAY_NORMALIZATION_LOG1P)
        np.testing.assert_allclose(disp, np.log1p(m))
        self.assertIn("log", suffix.lower())

    def test_plotly_figure_builds(self):
        sc = _score_c4_sustain(1.0)
        b = build_registral_concentration_matrix(
            sc, 48.0, 72.0, time_bin_size=0.5, concentration_mode="event_instances"
        )
        fig = make_registral_concentration_map_plotly(b, title="Interactive test")
        self.assertTrue(hasattr(fig, "to_dict"))

    def test_csv_npz_export_roundtrip_npz(self):
        sc = _score_c4_sustain(1.0)
        b = build_registral_concentration_matrix(
            sc, 59.0, 61.0, time_bin_size=0.5, concentration_mode="event_instances"
        )
        with tempfile.TemporaryDirectory() as td:
            npz = Path(td) / "m.npz"
            csv = Path(td) / "m.csv"
            write_concentration_matrix_npz(npz, b)
            write_concentration_matrix_csv(csv, b)
            self.assertTrue(npz.is_file())
            self.assertTrue(csv.is_file())
            with np.load(npz, allow_pickle=False) as z:
                self.assertIn("matrix", z.files)
                self.assertEqual(z["matrix"].shape, b["matrix"].shape)


class TestConcentrationMapCLI(unittest.TestCase):
    def test_cli_writes_png(self):
        if not SINGLE_NOTE_XML.is_file():
            self.skipTest("Fixture not found")
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "map.png"
            argv = [
                "__main__.py",
                "concentration-map",
                "--score",
                str(SINGLE_NOTE_XML),
                "--out",
                str(out),
                "--register-low",
                "C3",
                "--register-high",
                "C5",
                "--time-bin-size",
                "1.0",
            ]
            with patch.object(sys, "argv", argv), self.assertRaises(SystemExit) as cm:
                main()
            self.assertEqual(cm.exception.code, 0)
            self.assertTrue(out.is_file())
            self.assertGreater(out.stat().st_size, 100)

    def test_run_concentration_map_to_files_svg(self):
        if not SINGLE_NOTE_XML.is_file():
            self.skipTest("Fixture not found")
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "m.svg"
            run_concentration_map_to_files(
                str(SINGLE_NOTE_XML),
                out,
                "C3",
                "C5",
                time_bin_size=1.0,
                matrix_csv=Path(td) / "m.csv",
            )
            self.assertTrue(out.is_file())
            self.assertTrue((Path(td) / "m.csv").is_file())
