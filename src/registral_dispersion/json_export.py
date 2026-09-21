"""Structured JSON and CSV export for registral dispersion results."""

from __future__ import annotations

import io
import json
import math
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

import numpy as np

from registral_dispersion.metric_documentation import (
    CANONICAL_TOOL_NAME,
    CSV_COLUMN_HEADER,
    DISPERSION_DEGREE_DEFINITION,
    METHODOLOGICAL_NOTE_ANALYSIS_PROFILES,
    METHODOLOGICAL_NOTE_NORMALIZATION,
    METHODOLOGICAL_NOTE_REGISTRAL,
    METRIC_DEFINITION_PRIMARY,
    METRIC_FORMULAS_INLINE,
    METRIC_PRIMARY_NAME,
    NORMALIZATION_REFERENCE,
    NOTATIONAL_SAMPLING_CSV_BLURB,
    OBSERVATION_MODES_CSV_BLURB,
)
from registral_dispersion.profiles import normalize_analysis_profile
from registral_dispersion.sampling import normalize_pitch_sampling_mode
from registral_dispersion.service import resolve_registral_dispersion_params
from registral_dispersion.tie_policy import DEFAULT_TIE_POLICY

JSON_EXPORT_SCHEMA_VERSION = "1.10"

TOOL_SCOPE_STATEMENT = (
    "Symbolic-score-only registral dispersion tool. Analyzes MusicXML, MXL, and MIDI via music21. "
    "Does not analyze audio, loudness, timbre, orchestration, harmony, pitch-class content, or "
    "psychoacoustic perception."
)


def _package_version() -> str:
    try:
        return version("registral-dispersion")
    except PackageNotFoundError:
        return "unknown"


def _export_provenance() -> dict[str, str | bool]:
    """Software identity for reproducible exports (JSON; mirrored in CSV comments where applicable)."""
    return {
        "canonical_tool_name": CANONICAL_TOOL_NAME,
        "package_name": "registral-dispersion",
        "package_version": _package_version(),
        "tool_role": "research_software",
        "symbolic_score_only": True,
        "tool_scope_statement": TOOL_SCOPE_STATEMENT,
    }


def to_json_serializable(obj: Any) -> Any:
    """Recursively convert numpy scalars/arrays and non-JSON floats to JSON-safe values."""
    if obj is None:
        return None
    if isinstance(obj, str | bool | int):
        return obj
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    if isinstance(obj, np.ndarray):
        return to_json_serializable(obj.tolist())
    if isinstance(obj, np.generic):
        return to_json_serializable(obj.item())
    if isinstance(obj, dict):
        return {str(k): to_json_serializable(v) for k, v in obj.items()}
    if isinstance(obj, list | tuple):
        return [to_json_serializable(v) for v in obj]
    return str(obj)


def write_json_export(path: str | Path, document: dict[str, Any]) -> str:
    """Write ``document`` as UTF-8 JSON with indentation; return path as str."""
    p = Path(path)
    payload = to_json_serializable(document)
    p.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return str(p)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _metric_export_fields() -> dict[str, str]:
    return {
        "metric_primary_name": METRIC_PRIMARY_NAME,
        "metric_definition_primary": METRIC_DEFINITION_PRIMARY,
        "dispersion_degree_definition": DISPERSION_DEGREE_DEFINITION,
        "metric_formulas": METRIC_FORMULAS_INLINE,
        "methodological_note": METHODOLOGICAL_NOTE_REGISTRAL,
        "methodological_note_analysis_profiles": METHODOLOGICAL_NOTE_ANALYSIS_PROFILES,
        "methodological_note_normalization": METHODOLOGICAL_NOTE_NORMALIZATION,
    }


def write_registral_dispersion_csv(
    path: str | Path,
    results: dict[str, Any],
    *,
    pitch_sampling_mode: str | None = None,
    analysis_profile: str | None = None,
    pitch_sampling_source: str | None = None,
    observation_mode: str | None = None,
    register_low_midi: float | None = None,
    register_high_midi: float | None = None,
    register_width_semitones: float | None = None,
    microtone_repair: str | None = None,
    pitch_reference: str | None = None,
) -> str:
    """
    Write one CSV row per window with leading ``#`` comment lines (metric definitions).

    Numeric body uses ``fmt='%.18e'`` like prior exports.
    """
    p = Path(path)
    t = np.asarray(results["t"], dtype=float)
    ist = np.asarray(results["interval_start"], dtype=float)
    ien = np.asarray(results["interval_end"], dtype=float)
    idur = np.asarray(results["interval_duration"], dtype=float)
    cols = [
        ist,
        ien,
        idur,
        np.asarray(results["window_start"], dtype=float),
        np.asarray(results["window_end"], dtype=float),
        t,
        np.asarray(results["active_note_count"], dtype=float),
        np.asarray(results["min_pitch"], dtype=float),
        np.asarray(results["max_pitch"], dtype=float),
        np.asarray(results["dispersion_degree"], dtype=float),
        np.asarray(results["normalized_dispersion_degree"], dtype=float),
        np.asarray(results["registral_span"], dtype=float),
        np.asarray(results["mean_pairwise_registral_distance"], dtype=float),
        np.asarray(results["registral_centroid"], dtype=float),
        np.asarray(results["registral_std"], dtype=float),
        np.asarray(results["normalized_registral_span"], dtype=float),
        np.asarray(results["normalized_mean_pairwise_registral_distance"], dtype=float),
        np.asarray(results["normalized_registral_centroid"], dtype=float),
        np.asarray(results["normalized_registral_std"], dtype=float),
        np.asarray(results["occupancy_entropy"], dtype=float),
    ]
    mat = np.column_stack(cols)
    buf = io.StringIO()
    np.savetxt(buf, mat, delimiter=",", fmt="%.18e")
    body = buf.getvalue()
    m = _metric_export_fields()
    mode = normalize_pitch_sampling_mode(pitch_sampling_mode)
    prof = normalize_analysis_profile(analysis_profile)
    src = pitch_sampling_source or "unknown"
    obs_line = str(observation_mode).strip() if observation_mode is not None else "fixed_window"
    lines = [
        f"# {m['metric_primary_name']}",
        f"# {m['metric_definition_primary']}",
        f"# {m['metric_formulas']}",
        f"# {m['methodological_note']}",
        f"# {m['methodological_note_normalization']}",
        f"# analysis_profile: {prof}",
        f"# pitch_sampling_mode: {mode}",
        f"# pitch_sampling_source: {src}",
        f"# {m['methodological_note_analysis_profiles']}",
        f"# {NOTATIONAL_SAMPLING_CSV_BLURB}",
        f"# {OBSERVATION_MODES_CSV_BLURB}",
        f"# observation_mode: {obs_line}",
        f"# microtone_repair: {microtone_repair if microtone_repair is not None else 'off'}",
        f"# pitch_reference: {pitch_reference if pitch_reference is not None else 'written'}",
    ]
    if register_low_midi is not None and register_high_midi is not None and register_width_semitones is not None:
        lines.extend(
            [
                f"# normalization_reference: {NORMALIZATION_REFERENCE}",
                f"# register_low_midi: {register_low_midi}",
                f"# register_high_midi: {register_high_midi}",
                f"# register_width_semitones: {register_width_semitones}",
            ]
        )
    lines.append(CSV_COLUMN_HEADER)
    lines.append(body.rstrip("\n"))
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(p)


def write_global_summary_csv(path: str | Path, global_summary: dict[str, Any]) -> str:
    """
    Write a two-column key,value CSV for :func:`registral_dispersion.aggregation.compute_global_summary` output.

    Separate from per-row dispersion CSV; does not mix global and row-level data.
    """
    p = Path(path)
    lines = [
        f"# {CANONICAL_TOOL_NAME} global summary (whole-score aggregate)",
        f"# aggregation_method: {global_summary.get('aggregation_method')}",
        "key,value",
    ]
    for key in sorted(global_summary.keys()):
        val = global_summary[key]
        if val is None or (isinstance(val, float) and (math.isnan(val) or math.isinf(val))):
            cell = ""
        elif isinstance(val, float):
            cell = repr(val)
        else:
            cell = str(val).replace(",", ";")
        lines.append(f"{key},{cell}")
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(p)


def build_registral_dispersion_export(
    score_path: str | None,
    params: dict[str, Any],
    out: dict[str, Any],
) -> dict[str, Any]:
    """Full export document for :func:`run_registral_dispersion_analysis` output."""
    resolved = dict(out.get("params") or resolve_registral_dispersion_params(params))
    mode = normalize_pitch_sampling_mode(resolved.get("pitch_sampling_mode"))
    prof = normalize_analysis_profile(resolved.get("analysis_profile"))
    src = str(resolved.get("pitch_sampling_source") or "")
    obs_mode = str(resolved.get("observation_mode") or "fixed_window")
    tie_pol = str(resolved.get("tie_policy") or DEFAULT_TIE_POLICY)
    base: dict[str, Any] = {
        "schema_version": JSON_EXPORT_SCHEMA_VERSION,
        "kind": "registral_dispersion",
        "exported_at_utc": _utc_now_iso(),
        "score_path": score_path,
        "parameters": to_json_serializable(params),
        "analysis_profile": prof,
        "pitch_sampling_mode": mode,
        "pitch_sampling_source": src or None,
        "observation_mode": obs_mode,
        "tie_policy": tie_pol,
        "microtone_repair": str(resolved.get("microtone_repair") or "off"),
        "pitch_reference": str(resolved.get("pitch_reference") or "written"),
        "transposing_parts": to_json_serializable(out.get("transposing_parts") or []),
        "pitch_overrides": to_json_serializable(out.get("pitch_overrides") or []),
        "pitch_inventory_digest": to_json_serializable(out.get("pitch_inventory_digest")),
        "symbolic_score_only": True,
        "tool_scope_statement": TOOL_SCOPE_STATEMENT,
        "error": out.get("error"),
        **_export_provenance(),
        **_metric_export_fields(),
    }
    if out.get("error"):
        base["parameters"] = to_json_serializable(resolved)
        base["pitch_sampling_mode"] = mode
        base["analysis_profile"] = prof
        base["pitch_sampling_source"] = src or None
        return base
    an = out.get("analyzer")
    base["summary"] = out.get("summary")
    base["results"] = to_json_serializable(out.get("results", {}))
    base["global_summary"] = to_json_serializable(out.get("global_summary"))
    base["warnings"] = to_json_serializable(out.get("warnings") or [])
    base["repairs"] = to_json_serializable(out.get("repairs") or [])
    params_out = dict(resolved)
    if an is not None:
        params_out["register_low_midi_ps"] = float(getattr(an, "register_low", 0.0))
        params_out["register_high_midi_ps"] = float(getattr(an, "register_high", 0.0))
        params_out["pitch_sampling_mode"] = str(getattr(an, "pitch_sampling_mode", mode))
        params_out["analysis_profile"] = str(getattr(an, "analysis_profile", prof))
        psrc = str(getattr(an, "pitch_sampling_source", src))
        params_out["pitch_sampling_source"] = psrc
        base["pitch_sampling_mode"] = str(getattr(an, "pitch_sampling_mode", mode))
        base["analysis_profile"] = str(getattr(an, "analysis_profile", prof))
        base["pitch_sampling_source"] = psrc or None
    else:
        params_out["pitch_sampling_mode"] = str(mode)
        params_out["analysis_profile"] = prof
        base["analysis_profile"] = prof
    base["parameters"] = to_json_serializable(params_out)
    if an is not None:
        rlo = float(getattr(an, "register_low", 0.0))
        rhi = float(getattr(an, "register_high", 0.0))
        rw = float(getattr(an, "register_width_semitones", 0.0))
        base["normalization_reference"] = NORMALIZATION_REFERENCE
        base["register_low_midi"] = rlo
        base["register_high_midi"] = rhi
        base["register_width_semitones"] = rw
        base["score_metadata"] = {
            "duration_quarterlength": float(getattr(an, "end_time", 0.0) or 0.0),
            "register_low_midi_ps": rlo,
            "register_high_midi_ps": rhi,
            "n_notes_flat": len(getattr(an, "events", []) or []),
            "analysis_profile": str(getattr(an, "analysis_profile", prof)),
            "pitch_sampling_mode": str(getattr(an, "pitch_sampling_mode", mode)),
            "pitch_sampling_source": str(getattr(an, "pitch_sampling_source", src)),
            "observation_mode": obs_mode,
            "tie_policy": str(getattr(an, "tie_policy", tie_pol)),
            "microtone_repair": str(getattr(an, "microtone_repair", resolved.get("microtone_repair") or "off")),
            "pitch_reference": str(getattr(an, "pitch_reference", resolved.get("pitch_reference") or "written")),
            "normalization_reference": NORMALIZATION_REFERENCE,
            "register_low_midi": rlo,
            "register_high_midi": rhi,
            "register_width_semitones": rw,
        }
    return base


def write_register_uniformity_csv(path: str | Path, t_arr: np.ndarray, u_arr: np.ndarray) -> str:
    """
    Deprecated: write only ``t_quarterLength`` and ``U`` (occupancy entropy).

    For registral dispersion, use :func:`write_registral_dispersion_csv` with the full results dict.
    """
    p = Path(path)
    buf = io.StringIO()
    np.savetxt(buf, np.column_stack([t_arr, u_arr]), delimiter=",", fmt="%.18e")
    body = buf.getvalue()
    m = _metric_export_fields()
    lines = [
        "# Legacy export: t and U (occupancy_entropy / register uniformity) only.",
        f"# {m['methodological_note']}",
        "t_quarterLength,U",
        body.rstrip("\n"),
    ]
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(p)


def build_register_export(
    score_path: str | None,
    params: dict[str, Any],
    out: dict[str, Any],
) -> dict[str, Any]:
    """
    Deprecated: use :func:`build_registral_dispersion_export`.

    If ``out`` contains full dispersion results, forwards to that builder; otherwise emits a small
    legacy document for ``t`` / ``U`` (occupancy entropy) only.
    """
    r = out.get("results") or {}
    if r and "mean_pairwise_registral_distance" in r:
        return build_registral_dispersion_export(score_path, params, out)
    base: dict[str, Any] = {
        "schema_version": JSON_EXPORT_SCHEMA_VERSION,
        "kind": "register_uniformity_legacy",
        "exported_at_utc": _utc_now_iso(),
        "score_path": score_path,
        "parameters": to_json_serializable(params),
        "error": out.get("error"),
        "deprecated": "Prefer run_registral_dispersion_analysis + build_registral_dispersion_export",
        **_export_provenance(),
        **_metric_export_fields(),
    }
    if out.get("error"):
        return base
    base["summary"] = out.get("summary")
    base["results"] = to_json_serializable(r)
    an = out.get("analyzer")
    if an is not None:
        base["score_metadata"] = {
            "duration_quarterlength": float(getattr(an, "end_time", 0.0) or 0.0),
            "register_low_midi_ps": float(getattr(an, "register_low", 0.0)),
            "register_high_midi_ps": float(getattr(an, "register_high", 0.0)),
            "n_notes_flat": len(getattr(an, "events", []) or []),
        }
    return base
