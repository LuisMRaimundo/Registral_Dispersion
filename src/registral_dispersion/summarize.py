"""One-number global summary API for registral dispersion."""

from __future__ import annotations

from typing import Any

from registral_dispersion.aggregation import compute_global_summary, primary_one_number_from_summary
from registral_dispersion.observation import OBSERVATION_MODE_EVENT_BOUNDARIES
from registral_dispersion.pitch_utils import DEFAULT_REGISTER_HIGH, DEFAULT_REGISTER_LOW
from registral_dispersion.profiles import DEFAULT_ANALYSIS_PROFILE
from registral_dispersion.service import run_registral_dispersion_analysis
from registral_dispersion.microtone_repair import DEFAULT_MICROTONEREPAIR
from registral_dispersion.pitch_reference import DEFAULT_PITCH_REFERENCE
from registral_dispersion.tie_policy import DEFAULT_TIE_POLICY
from registral_dispersion.warnings import collect_interpretation_warnings, merge_warnings

DEFAULT_SUMMARIZE_PARAMS: dict[str, Any] = {
    "observation_mode": OBSERVATION_MODE_EVENT_BOUNDARIES,
    "analysis_profile": DEFAULT_ANALYSIS_PROFILE,
    "register_low": DEFAULT_REGISTER_LOW,
    "register_high": DEFAULT_REGISTER_HIGH,
    "time_step": 0.25,
    "window_size": 4.0,
    "tie_policy": DEFAULT_TIE_POLICY,
    "microtone_repair": DEFAULT_MICROTONEREPAIR,
    "pitch_reference": DEFAULT_PITCH_REFERENCE,
    "pitch_overrides": [],
}


def summarize_registral_dispersion(
    score_path: str,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Run analysis and return a minimal one-number global summary.

    Defaults: ``event_boundaries``, ``occupied_space``, register A0–C8, ``tie_policy=as_imported``.
    Primary one-number metric: ``duration_weighted_registral_span`` (event boundaries) or
    ``sampled_mean_registral_span`` (fixed window).
    """
    merged = {**DEFAULT_SUMMARIZE_PARAMS, **(params or {})}
    out = run_registral_dispersion_analysis(score_path, merged)
    if out.get("error"):
        return {
            "error": out["error"],
            "primary_metric": None,
            "primary_value": None,
            "secondary_metric": None,
            "secondary_value": None,
            "global_summary": None,
            "params": out.get("params", merged),
            "warnings": merge_warnings(out.get("warnings")),
            "repairs": list(out.get("repairs") or []),
        }
    global_summary = out.get("global_summary") or compute_global_summary(
        out["results"], out["params"], analyzer=out.get("analyzer")
    )
    primary_metric, primary_value, secondary_metric, secondary_value = primary_one_number_from_summary(global_summary)
    warnings = merge_warnings(
        out.get("warnings"),
        collect_interpretation_warnings(out["params"], context="one_number_summary"),
    )
    return {
        "primary_metric": primary_metric,
        "primary_value": primary_value,
        "secondary_metric": secondary_metric,
        "secondary_value": secondary_value,
        "global_summary": global_summary,
        "params": out["params"],
        "warnings": warnings,
        "repairs": list(out.get("repairs") or []),
        "error": None,
    }
