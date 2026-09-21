"""Focused pytest coverage for registral_dispersion CLI (__main__)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from registral_dispersion.__main__ import (
    _cli_analyze,
    _cli_summarize,
    _run_params_from_args,
    main,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
SINGLE_NOTE_XML = REPO_ROOT / "tests" / "fixtures" / "single_note.xml"


def _argv(*parts: str) -> list[str]:
    return ["registral_dispersion", *parts]


def _run_main(monkeypatch: pytest.MonkeyPatch, argv: list[str]) -> None:
    monkeypatch.setattr(sys, "argv", argv)
    main()


# ---------------------------------------------------------------------------
# Help / usage
# ---------------------------------------------------------------------------


def test_analyze_help_exits_cleanly(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc_info:
        _run_main(monkeypatch, _argv("analyze", "--help"))
    assert exc_info.value.code == 0
    out = capsys.readouterr().out
    assert "--score" in out
    assert "--microtone-repair" in out
    assert "--pitch-reference" in out
    assert "analyze" in out.lower()


def test_inventory_help_exits_cleanly(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc_info:
        _run_main(monkeypatch, _argv("inventory", "--help"))
    assert exc_info.value.code == 0
    out = capsys.readouterr().out
    assert "--score" in out
    assert "--pitch-reference" in out
    assert "--out" in out


def test_summarize_help_exits_cleanly(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc_info:
        _run_main(monkeypatch, _argv("summarize", "--help"))
    assert exc_info.value.code == 0
    out = capsys.readouterr().out
    assert "--score" in out
    assert "summarize" in out.lower()


def test_bare_help_routes_to_ui_subcommand_help(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as exc_info:
        _run_main(monkeypatch, _argv("--help"))
    assert exc_info.value.code == 0
    out = capsys.readouterr().out
    assert "ui" in out.lower() or "Gradio" in out


# ---------------------------------------------------------------------------
# Missing required arguments
# ---------------------------------------------------------------------------


def test_analyze_missing_required_score(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc_info:
        _run_main(monkeypatch, _argv("analyze"))
    assert exc_info.value.code == 2
    err = capsys.readouterr().err
    assert "score" in err.lower() or "required" in err.lower()


def test_concentration_map_missing_required_out(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as exc_info:
        _run_main(
            monkeypatch,
            _argv("concentration-map", "--score", "score.xml"),
        )
    assert exc_info.value.code == 2
    err = capsys.readouterr().err
    assert "out" in err.lower() or "required" in err.lower()


# ---------------------------------------------------------------------------
# Invalid input file / validation errors
# ---------------------------------------------------------------------------


def test_analyze_missing_score_path_exits_with_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    missing = tmp_path / "missing.xml"
    with pytest.raises(SystemExit) as exc_info:
        _run_main(
            monkeypatch,
            _argv(
                "analyze",
                "--score",
                str(missing),
                "--out-dir",
                str(tmp_path / "out"),
            ),
        )
    assert exc_info.value.code == 1
    assert "not found" in capsys.readouterr().err.lower()


def test_analyze_unsupported_extension_exits_with_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    bad = tmp_path / "notes.txt"
    bad.write_text("not a score", encoding="utf-8")
    with pytest.raises(SystemExit) as exc_info:
        _run_main(
            monkeypatch,
            _argv("analyze", "--score", str(bad), "--out-dir", str(tmp_path)),
        )
    assert exc_info.value.code == 1
    assert "unsupported extension" in capsys.readouterr().err.lower()


def test_analyze_empty_file_exits_with_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    empty = tmp_path / "empty.xml"
    empty.write_bytes(b"")
    with pytest.raises(SystemExit) as exc_info:
        _run_main(
            monkeypatch,
            _argv("analyze", "--score", str(empty), "--out-dir", str(tmp_path)),
        )
    assert exc_info.value.code == 1
    assert "empty" in capsys.readouterr().err.lower()


def test_summarize_missing_score_path_exits_with_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    missing = tmp_path / "ghost.xml"
    with pytest.raises(SystemExit) as exc_info:
        _run_main(monkeypatch, _argv("summarize", "--score", str(missing)))
    assert exc_info.value.code == 1
    assert "not found" in capsys.readouterr().err.lower()


# ---------------------------------------------------------------------------
# argparse invalid choices
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("flag", "value"),
    [
        ("--tie-policy", "invalid_policy"),
        ("--analysis-profile", "invalid_profile"),
        ("--pitch-sampling", "invalid_sampling"),
        ("--observation-mode", "invalid_mode"),
    ],
)
def test_analyze_rejects_invalid_choice(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    flag: str,
    value: str,
) -> None:
    score = tmp_path / "score.xml"
    score.write_text("<score-partwise/>", encoding="utf-8")
    with pytest.raises(SystemExit) as exc_info:
        _run_main(
            monkeypatch,
            _argv("analyze", "--score", str(score), flag, value),
        )
    assert exc_info.value.code == 2


# ---------------------------------------------------------------------------
# _run_params_from_args
# ---------------------------------------------------------------------------


def test_run_params_from_args_applies_defaults_and_optional_pitch_sampling() -> None:
    args = argparse.Namespace(
        time_step=0.5,
        window_size=2.0,
        register_low="A1",
        register_high="E7",
        analysis_profile="component_weighted",
        observation_mode=None,
        tie_policy="merge_ties",
        pitch_sampling_mode="unique_pitch_heights",
    )
    params = _run_params_from_args(args, default_observation_mode="fixed_window")
    assert params["observation_mode"] == "fixed_window"
    assert params["tie_policy"] == "merge_ties"
    assert params["pitch_sampling_mode"] == "unique_pitch_heights"
    assert params["analysis_profile"] == "component_weighted"


def test_run_params_from_args_omits_pitch_sampling_when_none() -> None:
    args = argparse.Namespace(
        time_step=0.25,
        window_size=4.0,
        register_low="A0",
        register_high="C8",
        analysis_profile="occupied_space",
        observation_mode="event_boundaries",
        tie_policy="as_imported",
        pitch_sampling_mode=None,
    )
    params = _run_params_from_args(args, default_observation_mode="fixed_window")
    assert "pitch_sampling_mode" not in params
    assert params["observation_mode"] == "event_boundaries"


# ---------------------------------------------------------------------------
# analyze — mocked fast path
# ---------------------------------------------------------------------------


def _fake_analyze_out() -> dict:
    analyzer = MagicMock()
    analyzer.register_low = 48.0
    analyzer.register_high = 72.0
    analyzer.register_width_semitones = 24.0
    return {
        "error": None,
        "params": {
            "pitch_sampling_mode": "event_instances",
            "analysis_profile": "component_weighted",
            "pitch_sampling_source": "explicit",
            "observation_mode": "fixed_window",
            "tie_policy": "merge_ties",
        },
        "analyzer": analyzer,
        "results": {
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
        },
        "global_summary": {"aggregation_method": "duration_weighted", "mean": 0.1},
        "summary": "ok",
    }


def test_cli_analyze_writes_outputs_with_explicit_dir_and_prefix(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    score = tmp_path / "score.xml"
    score.write_text("<score-partwise/>", encoding="utf-8")
    out_dir = tmp_path / "exports"
    monkeypatch.setattr(
        "registral_dispersion.__main__.run_registral_dispersion_analysis",
        lambda _score, _params: _fake_analyze_out(),
    )

    args = argparse.Namespace(
        score=str(score),
        out_dir=str(out_dir),
        prefix="cli_run",
        register_low="C3",
        register_high="C5",
        window_size=4.0,
        plot_span=False,
        plot_pairwise=True,
        plot_entropy=True,
        plot_normalized=True,
        time_step=0.25,
        analysis_profile="component_weighted",
        observation_mode="fixed_window",
        tie_policy="merge_ties",
        pitch_sampling_mode="event_instances",
    )
    assert _cli_analyze(args) == 0

    assert (out_dir / "cli_run.csv").is_file()
    assert (out_dir / "cli_run.json").is_file()
    assert (out_dir / "cli_run.png").is_file()
    assert (out_dir / "cli_run_global_summary.csv").is_file()
    assert (out_dir / "cli_run_pitch_inventory.csv").is_file()
    out = capsys.readouterr().out
    assert "Wrote" in out
    assert str(out_dir / "cli_run.csv") in out


def test_cli_analyze_returns_error_code_when_analysis_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    score = tmp_path / "score.xml"
    score.write_text("<score-partwise/>", encoding="utf-8")
    monkeypatch.setattr(
        "registral_dispersion.__main__.run_registral_dispersion_analysis",
        lambda _score, _params: {"error": "analysis failed", "params": {}},
    )
    args = argparse.Namespace(
        score=str(score),
        out_dir=str(tmp_path),
        prefix="x",
        register_low="C3",
        register_high="C5",
        window_size=4.0,
        plot_span=False,
        plot_pairwise=False,
        plot_entropy=False,
        plot_normalized=False,
        time_step=0.25,
        analysis_profile="occupied_space",
        observation_mode="fixed_window",
        tie_policy="as_imported",
        pitch_sampling_mode=None,
    )
    assert _cli_analyze(args) == 1
    assert "analysis failed" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# summarize — mocked and direct paths
# ---------------------------------------------------------------------------


def test_cli_summarize_writes_optional_outputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    score = tmp_path / "score.xml"
    score.write_text("<score-partwise/>", encoding="utf-8")
    out_json = tmp_path / "summary.json"
    out_csv = tmp_path / "summary.csv"
    monkeypatch.setattr(
        "registral_dispersion.__main__.summarize_registral_dispersion",
        lambda _score, _params: {
            "error": None,
            "primary_metric": "dispersion_degree",
            "primary_value": 0.42,
            "secondary_metric": "occupancy_entropy",
            "secondary_value": 0.1,
            "global_summary": {"aggregation_method": "duration_weighted", "mean": 0.42},
            "params": {
                "analysis_profile": "occupied_space",
                "pitch_sampling_mode": "unique_pitch_heights",
                "observation_mode": "event_boundaries",
                "register_low": "A0",
                "register_high": "C8",
            },
            "warnings": ["caution"],
        },
    )
    args = argparse.Namespace(
        score=str(score),
        out_json=str(out_json),
        out_csv=str(out_csv),
        time_step=0.25,
        window_size=4.0,
        register_low="A0",
        register_high="C8",
        analysis_profile="occupied_space",
        observation_mode="event_boundaries",
        tie_policy="as_imported",
        pitch_sampling_mode=None,
    )
    assert _cli_summarize(args) == 0
    assert out_json.is_file()
    assert out_csv.is_file()
    doc = json.loads(out_json.read_text(encoding="utf-8"))
    assert doc["primary_value"] == 0.42
    out = capsys.readouterr().out
    assert "primary_metric:" in out
    assert "caution" in out


def test_cli_summarize_returns_error_code(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    score = tmp_path / "score.xml"
    score.write_text("<score-partwise/>", encoding="utf-8")
    monkeypatch.setattr(
        "registral_dispersion.__main__.summarize_registral_dispersion",
        lambda _score, _params: {"error": "summarize failed", "params": {}},
    )
    args = argparse.Namespace(
        score=str(score),
        out_json=None,
        out_csv=None,
        time_step=0.25,
        window_size=4.0,
        register_low="A0",
        register_high="C8",
        analysis_profile="occupied_space",
        observation_mode="event_boundaries",
        tie_policy="as_imported",
        pitch_sampling_mode=None,
    )
    assert _cli_summarize(args) == 1
    assert "summarize failed" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# UI launch paths
# ---------------------------------------------------------------------------


def test_default_no_argv_launches_ui(monkeypatch: pytest.MonkeyPatch) -> None:
    called: dict[str, object] = {}

    def _launch() -> None:
        called["ui"] = True

    monkeypatch.setattr("registral_dispersion.app.launch", _launch)
    monkeypatch.setattr(sys, "argv", ["registral_dispersion"])
    main()
    assert called.get("ui") is True


def test_ui_subcommand_forwards_host_and_port(monkeypatch: pytest.MonkeyPatch) -> None:
    called: dict[str, object] = {}

    def _launch(*, host=None, port=None, share=False) -> None:
        called["host"] = host
        called["port"] = port
        called["share"] = share

    monkeypatch.setattr("registral_dispersion.app.launch", _launch)
    monkeypatch.setattr(
        sys,
        "argv",
        _argv("ui", "--host", "127.0.0.1", "--port", "7860", "--share"),
    )
    main()
    assert called["host"] == "127.0.0.1"
    assert called["port"] == 7860
    assert called["share"] is True


def test_unknown_first_token_routes_to_ui_subcommand(monkeypatch: pytest.MonkeyPatch) -> None:
    called: dict[str, object] = {}

    def _launch(*, host=None, port=None, share=False) -> None:
        called["host"] = host

    monkeypatch.setattr("registral_dispersion.app.launch", _launch)
    monkeypatch.setattr(sys, "argv", _argv("--host", "0.0.0.0"))
    main()
    assert called["host"] == "0.0.0.0"


# ---------------------------------------------------------------------------
# concentration-map CLI
# ---------------------------------------------------------------------------


def test_cli_analyze_skips_global_summary_when_absent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    score = tmp_path / "score.xml"
    score.write_text("<score-partwise/>", encoding="utf-8")
    out = _fake_analyze_out()
    out.pop("global_summary")
    monkeypatch.setattr(
        "registral_dispersion.__main__.run_registral_dispersion_analysis",
        lambda _score, _params: out,
    )
    args = argparse.Namespace(
        score=str(score),
        out_dir=str(tmp_path),
        prefix="no_summary",
        register_low="C3",
        register_high="C5",
        window_size=4.0,
        plot_span=False,
        plot_pairwise=False,
        plot_entropy=False,
        plot_normalized=False,
        time_step=0.25,
        analysis_profile="occupied_space",
        observation_mode="fixed_window",
        tie_policy="as_imported",
        pitch_sampling_mode=None,
    )
    assert _cli_analyze(args) == 0
    assert not (tmp_path / "no_summary_global_summary.csv").exists()
    printed = capsys.readouterr().out
    assert "global_summary.csv" not in printed


def test_concentration_map_success_exits_zero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    out = tmp_path / "map.png"
    monkeypatch.setattr(
        "registral_dispersion.__main__.run_concentration_map_to_files",
        lambda *_args, **_kwargs: {"outputs": [str(out)]},
    )
    with pytest.raises(SystemExit) as exc_info:
        _run_main(
            monkeypatch,
            _argv(
                "concentration-map",
                "--score",
                str(tmp_path / "score.xml"),
                "--out",
                str(out),
            ),
        )
    assert exc_info.value.code == 0
    assert "Wrote" in capsys.readouterr().out


def test_concentration_map_failure_exits_nonzero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    out = tmp_path / "map.png"

    def _boom(*_args, **_kwargs):
        raise RuntimeError("map failed")

    monkeypatch.setattr("registral_dispersion.__main__.run_concentration_map_to_files", _boom)
    with pytest.raises(SystemExit) as exc_info:
        _run_main(
            monkeypatch,
            _argv(
                "concentration-map",
                "--score",
                str(tmp_path / "score.xml"),
                "--out",
                str(out),
            ),
        )
    assert exc_info.value.code == 1
    assert "map failed" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# Integration — real fixture through main()
# ---------------------------------------------------------------------------


def test_analyze_integration_with_fixture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    if not SINGLE_NOTE_XML.is_file():
        pytest.skip("Fixture not found")
    out_dir = tmp_path / "cli_out"
    with pytest.raises(SystemExit) as exc_info:
        _run_main(
            monkeypatch,
            _argv(
                "analyze",
                "--score",
                str(SINGLE_NOTE_XML),
                "--out-dir",
                str(out_dir),
                "--prefix",
                "fixture_run",
                "--register-low",
                "C3",
                "--register-high",
                "C5",
                "--window-size",
                "4",
                "--time-step",
                "1",
                "--tie-policy",
                "as_imported",
                "--analysis-profile",
                "occupied_space",
            ),
        )
    assert exc_info.value.code == 0
    assert (out_dir / "fixture_run.csv").is_file()
    assert (out_dir / "fixture_run.json").is_file()
    assert (out_dir / "fixture_run.png").is_file()
    assert "Wrote" in capsys.readouterr().out


def test_summarize_integration_with_fixture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    if not SINGLE_NOTE_XML.is_file():
        pytest.skip("Fixture not found")
    out_json = tmp_path / "sum.json"
    with pytest.raises(SystemExit) as exc_info:
        _run_main(
            monkeypatch,
            _argv(
                "summarize",
                "--score",
                str(SINGLE_NOTE_XML),
                "--out-json",
                str(out_json),
                "--tie-policy",
                "merge_ties",
            ),
        )
    assert exc_info.value.code == 0
    doc = json.loads(out_json.read_text(encoding="utf-8"))
    assert "primary_value" in doc
    assert "global_summary" in doc
    assert "primary_metric:" in capsys.readouterr().out
