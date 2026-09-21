"""
Run **registral dispersion** analysis on a symbolic score.

Canonical per-row metric: ``dispersion_degree`` (= registral span). Mean pairwise distance is
exported and optionally plotted as an overlay. Used by the Gradio app, CLI, and tests.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import numpy as np

from registral_dispersion.aggregation import compute_global_summary
from registral_dispersion.analyzer import RegisterUniformityAnalyzer, RegistralDispersionAnalyzer
from registral_dispersion.observation import normalize_observation_mode
from registral_dispersion.pitch_utils import DEFAULT_REGISTER_HIGH, DEFAULT_REGISTER_LOW, note_name_to_midi_ps
from registral_dispersion.profiles import (
    ANALYSIS_PROFILE_COMPONENT_WEIGHTED,
    ANALYSIS_PROFILE_OCCUPIED_SPACE,
    DEFAULT_ANALYSIS_PROFILE,
    resolve_profile_and_pitch_sampling,
)
from registral_dispersion.results import RegistralDispersionSeriesResult
from registral_dispersion.score_io import ScoreValidationError
from registral_dispersion.microtone_repair import DEFAULT_MICROTONEREPAIR, normalize_microtone_repair
from registral_dispersion.tie_policy import DEFAULT_TIE_POLICY, normalize_tie_policy
from registral_dispersion.warnings import collect_interpretation_warnings, merge_warnings

DEFAULT_REGISTRAL_DISPERSION_PARAMS = {
    "time_step": 0.25,
    "window_size": 4.0,
    "register_low": DEFAULT_REGISTER_LOW,
    "register_high": DEFAULT_REGISTER_HIGH,
    "analysis_profile": DEFAULT_ANALYSIS_PROFILE,
    "observation_mode": "fixed_window",
    "tie_policy": DEFAULT_TIE_POLICY,
    "microtone_repair": DEFAULT_MICROTONEREPAIR,
}

# Legacy register-uniformity / occupancy workflows: event-instance sampling (component_weighted).
DEFAULT_REGISTER_UNIFORMITY_PARAMS = {
    **DEFAULT_REGISTRAL_DISPERSION_PARAMS,
    "analysis_profile": ANALYSIS_PROFILE_COMPONENT_WEIGHTED,
}


def resolve_registral_dispersion_params(params: dict[str, Any] | None) -> dict[str, Any]:
    """
    Merge user params with defaults and resolve ``pitch_sampling_mode`` from ``analysis_profile``.

    **Precedence:** if the caller’s dict contains the key ``pitch_sampling_mode``, it is treated as an
    explicit override of the profile’s implied mode. Otherwise ``pitch_sampling_mode`` is set from
    ``analysis_profile``.
    """
    raw = dict(params or {})
    explicit_sampling = "pitch_sampling_mode" in raw
    p = {**DEFAULT_REGISTRAL_DISPERSION_PARAMS, **raw}
    prof, mode, src = resolve_profile_and_pitch_sampling(
        p.get("analysis_profile"),
        raw.get("pitch_sampling_mode") if explicit_sampling else None,
        pitch_sampling_explicit=explicit_sampling,
    )
    p["analysis_profile"] = prof
    p["pitch_sampling_mode"] = mode
    p["pitch_sampling_source"] = src
    p["observation_mode"] = normalize_observation_mode(p.get("observation_mode"))
    p["tie_policy"] = normalize_tie_policy(p.get("tie_policy"))
    p["microtone_repair"] = normalize_microtone_repair(p.get("microtone_repair"))
    return p


def _parse_register_bound(value) -> float:
    """Convert register bound from string (note name) or number (MIDI) to float MIDI ps."""
    if value is None or value == "":
        raise ValueError("Register bound is required.")
    if isinstance(value, int | float):
        return float(value)
    s = str(value).strip()
    if not s:
        raise ValueError("Register bound is required.")
    try:
        return float(s)
    except ValueError:
        pass
    return note_name_to_midi_ps(s)


def _shared_run(
    score_path: str,
    params: dict[str, Any] | None,
    progress_callback: Callable[[float, str], None] | None,
    analyzer_cls: type[RegistralDispersionAnalyzer],
) -> dict[str, Any]:
    try:
        p = resolve_registral_dispersion_params(params)
    except ValueError as e:
        return {"error": str(e), "analyzer": None, "params": dict(params or {})}
    if progress_callback:
        progress_callback(0.0, "A carregar partitura…")
    try:
        reg_low = _parse_register_bound(p.get("register_low"))
        reg_high = _parse_register_bound(p.get("register_high"))
    except ValueError as e:
        return {"error": str(e), "analyzer": None, "params": p}
    raw = dict(params or {})
    explicit_pitch_sampling = "pitch_sampling_mode" in raw
    try:
        analyzer = analyzer_cls(
            score_path=score_path,
            register_low_ps=reg_low,
            register_high_ps=reg_high,
            time_step=float(p["time_step"]),
            pitch_sampling_mode=p["pitch_sampling_mode"] if explicit_pitch_sampling else None,
            analysis_profile=p["analysis_profile"],
            tie_policy=p["tie_policy"],
            microtone_repair=p["microtone_repair"],
        )
    except ScoreValidationError as e:
        return {"error": str(e), "analyzer": None, "params": p}
    except ValueError as e:
        return {"error": str(e), "analyzer": None, "params": p}
    except Exception as e:
        msg = "Could not parse the score. Ensure the file is valid MusicXML or MIDI. Details: "
        return {"error": msg + str(e), "analyzer": None, "params": p}
    if analyzer.end_time <= 0 or len(analyzer.events) == 0:
        return {"error": "Score has no notes or no duration.", "analyzer": analyzer, "params": p}

    results_raw = analyzer.analyze_score(
        window_size=float(p["window_size"]),
        progress_callback=progress_callback,
        observation_mode=p["observation_mode"],
    )
    if progress_callback:
        progress_callback(1.0, "Concluído")
    return {"analyzer": analyzer, "params": p, "reg_low": reg_low, "reg_high": reg_high, "results_raw": results_raw}


def run_registral_dispersion_analysis(
    score_path: str,
    params: dict[str, Any] | None = None,
    progress_callback: Callable[[float, str], None] | None = None,
) -> dict[str, Any]:
    """
    Compute registral dispersion time series (``dispersion_degree``, canonical; plus supplementary
    ``mean_pairwise_registral_distance``) and optional ``occupancy_entropy`` in each window.

    Only pitches inside ``[register_low, register_high]`` (MIDI ps) are considered; register is **not**
    reduced to pitch class.

    Use ``analysis_profile`` (``occupied_space`` | ``component_weighted``) to choose the research stance;
    an explicit ``pitch_sampling_mode`` in ``params`` overrides the profile’s implied sampling mode.
    """
    base = _shared_run(score_path, params, progress_callback, RegistralDispersionAnalyzer)
    if base.get("error"):
        return {**base, "summary": None, "global_summary": None, "warnings": [], "repairs": []}
    p = base["params"]
    analyzer = base["analyzer"]
    results = RegistralDispersionSeriesResult.from_legacy(base["results_raw"]).as_legacy_dict()
    global_summary = compute_global_summary(results, p, analyzer=analyzer)
    p["register_low_midi_ps"] = float(analyzer.register_low)
    p["register_high_midi_ps"] = float(analyzer.register_high)
    p["register_width_semitones"] = float(analyzer.register_width_semitones)
    warnings = merge_warnings(
        list(getattr(analyzer, "tie_warnings", []) or []),
        list(getattr(analyzer, "microtone_warnings", []) or []),
        collect_interpretation_warnings(p, context="analysis"),
    )
    repairs = list(getattr(analyzer, "repairs", []) or [])
    dd = np.array(results["dispersion_degree"], dtype=float)
    dp = np.array(results["mean_pairwise_registral_distance"], dtype=float)
    ds = np.array(results["registral_span"], dtype=float)
    dc = np.array(results["registral_centroid"], dtype=float)
    dst = np.array(results["registral_std"], dtype=float)
    prof = p.get("analysis_profile")
    profile_hint = ""
    if prof == ANALYSIS_PROFILE_OCCUPIED_SPACE:
        profile_hint = (
            "Profile occupied_space: density-independent occupied pitch-space geometry "
            "(canonical metric: dispersion_degree).\n"
        )
    elif prof == ANALYSIS_PROFILE_COMPONENT_WEIGHTED:
        profile_hint = (
            "Profile component_weighted: notated-component multiplicity affects pairwise distance; "
            "dispersion_degree remains max-min span.\n"
        )
    obs = p.get("observation_mode", "fixed_window")
    temporal_line = (
        f"Temporal rows (event-boundary intervals): {len(dd)}\n"
        if obs == "event_boundaries"
        else f"Windows (fixed grid): {len(dd)}\n"
    )
    win_line = (
        f"Window size (fixed_window only): {p['window_size']}, Time step: {p['time_step']}\n"
        if obs == "fixed_window"
        else f"Time step (fixed_window parameter; unused for indexing in event_boundaries): {p['time_step']}\n"
    )
    agg = global_summary.get("aggregation_method", "")
    if agg == "duration_weighted_event_boundaries":
        global_line = (
            f"Global (duration-weighted): registral_span={global_summary.get('duration_weighted_registral_span'):.4f}; "
            f"mean_pairwise={global_summary.get('duration_weighted_mean_pairwise_registral_distance'):.4f}\n"
        )
    else:
        global_line = (
            "Global (sampled trajectory): "
            f"mean registral_span={global_summary.get('sampled_mean_registral_span'):.4f}; "
            f"mean pairwise={global_summary.get('sampled_mean_pairwise_registral_distance'):.4f}\n"
        )
    summary = (
        f"Registral dispersion — register band [{p.get('register_low')}, {p.get('register_high')}] "
        f"(MIDI {base['reg_low']:.0f}–{base['reg_high']:.0f}).\n"
        f"observation_mode: {obs}; tie_policy: {p.get('tie_policy')}\n"
        f"analysis_profile: {prof}; pitch_sampling_mode: {p.get('pitch_sampling_mode')} "
        f"(source: {p.get('pitch_sampling_source')}).\n"
        f"{profile_hint}"
        f"{temporal_line}"
        f"Score duration (quarterLength): {analyzer.end_time:.3f}\n"
        f"{global_line}"
        f"dispersion_degree min/mean/max: {np.nanmin(dd):.4f} / {np.nanmean(dd):.4f} / {np.nanmax(dd):.4f}\n"
        f"mean_pairwise min/mean/max: {np.nanmin(dp):.4f} / {np.nanmean(dp):.4f} / {np.nanmax(dp):.4f}\n"
        f"registral_span min/mean/max (same as dispersion_degree): "
        f"{np.nanmin(ds):.4f} / {np.nanmean(ds):.4f} / {np.nanmax(ds):.4f}\n"
        f"Centroid (MIDI) mean: {np.nanmean(dc):.2f}; std (semitones) mean: {np.nanmean(dst):.4f}\n"
        f"{win_line}"
        f"occupancy_entropy (optional) is distinct from dispersion; see README / JSON methodological_note.\n"
    )
    if warnings:
        summary += f"Warnings ({len(warnings)}): " + " | ".join(warnings) + "\n"
    return {
        "results": results,
        "analyzer": analyzer,
        "summary": summary,
        "global_summary": global_summary,
        "warnings": warnings,
        "repairs": repairs,
        "error": None,
        "params": p,
    }


def _legacy_register_uniformity_params(params: dict[str, Any] | None) -> dict[str, Any]:
    """Force legacy occupancy/U baselines unless the caller sets ``analysis_profile`` explicitly."""
    u = dict(params or {})
    if "analysis_profile" not in u:
        u["analysis_profile"] = ANALYSIS_PROFILE_COMPONENT_WEIGHTED
    return u


def run_register_uniformity_analysis(
    score_path: str,
    params: dict[str, Any] | None = None,
    progress_callback: Callable[[float, str], None] | None = None,
) -> dict[str, Any]:
    """
    **Legacy API:** returns ``results`` with only ``t`` and ``U``, where ``U`` is ``occupancy_entropy``.

    Unless ``analysis_profile`` is passed explicitly, defaults to ``component_weighted`` (``event_instances``)
    to match earlier register-uniformity / entropy workflows.

    Prefer :func:`run_registral_dispersion_analysis` for full registral-dispersion outputs.
    """
    base = _shared_run(
        score_path,
        _legacy_register_uniformity_params(params),
        progress_callback,
        RegisterUniformityAnalyzer,
    )
    if base.get("error"):
        return {**base, "summary": None, "repairs": []}
    p = base["params"]
    analyzer = base["analyzer"]
    results_raw = base["results_raw"]
    results = {"t": results_raw["t"], "U": results_raw["U"]}
    U = np.array(results["U"], dtype=float)
    summary = (
        f"occupancy_entropy U(t) (legacy register-uniformity view) — same numerical recipe as before; "
        f"not the primary registral-dispersion descriptor.\n"
        f"Register band [{p.get('register_low')}, {p.get('register_high')}] "
        f"(MIDI {base['reg_low']:.0f}–{base['reg_high']:.0f})\n"
        f"Windows: {len(U)}\n"
        f"Score duration (quarterLength): {analyzer.end_time:.3f}\n"
        f"U min: {np.nanmin(U):.4f}\n"
        f"U mean: {np.nanmean(U):.4f}\n"
        f"U max: {np.nanmax(U):.4f}\n"
        f"Window size: {p['window_size']}, Time step: {p['time_step']}\n"
        f"analysis_profile: {p.get('analysis_profile')}; pitch_sampling_mode: {p.get('pitch_sampling_mode')} "
        f"(source: {p.get('pitch_sampling_source')}).\n"
    )
    return {"results": results, "analyzer": analyzer, "summary": summary, "error": None, "params": p}
