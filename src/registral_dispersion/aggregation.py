"""Global / whole-score aggregation of registral dispersion time series."""

from __future__ import annotations

import math
from importlib.metadata import PackageNotFoundError, version
from typing import Any

import numpy as np

from registral_dispersion.metric_documentation import NORMALIZATION_REFERENCE
from registral_dispersion.observation import OBSERVATION_MODE_EVENT_BOUNDARIES, OBSERVATION_MODE_FIXED_WINDOW
from registral_dispersion.tie_policy import DEFAULT_TIE_POLICY

AGGREGATION_DURATION_WEIGHTED = "duration_weighted_event_boundaries"
AGGREGATION_SAMPLED_FIXED = "sampled_fixed_window_summary"
SUMMARY_SCHEMA_VERSION = "1.9"


def _package_version() -> str:
    try:
        return version("registral-dispersion")
    except PackageNotFoundError:
        return "unknown"


def _as_f64(values) -> np.ndarray:
    return np.asarray(values, dtype=float)


def _duration_weighted_mean(values: np.ndarray, durations: np.ndarray) -> float:
    mask = ~np.isnan(values) & (durations > 0)
    if not np.any(mask):
        return float("nan")
    w = durations[mask]
    return float(np.sum(values[mask] * w) / np.sum(w))


def _duration_weighted_median(values: np.ndarray, durations: np.ndarray) -> float:
    mask = ~np.isnan(values) & (durations > 0)
    if not np.any(mask):
        return float("nan")
    v = values[mask]
    w = durations[mask]
    order = np.argsort(v)
    v_sorted = v[order]
    w_sorted = w[order]
    cum = np.cumsum(w_sorted)
    half = 0.5 * float(np.sum(w_sorted))
    idx = int(np.searchsorted(cum, half, side="left"))
    idx = min(idx, len(v_sorted) - 1)
    return float(v_sorted[idx])


def _nan_min(values: np.ndarray) -> float:
    if values.size == 0 or np.all(np.isnan(values)):
        return float("nan")
    return float(np.nanmin(values))


def _nan_max(values: np.ndarray) -> float:
    if values.size == 0 or np.all(np.isnan(values)):
        return float("nan")
    return float(np.nanmax(values))


def _nan_mean(values: np.ndarray) -> float:
    if values.size == 0 or np.all(np.isnan(values)):
        return float("nan")
    return float(np.nanmean(values))


def _nan_median(values: np.ndarray) -> float:
    if values.size == 0 or np.all(np.isnan(values)):
        return float("nan")
    return float(np.nanmedian(values))


def compute_global_summary(
    results: dict[str, Any],
    params: dict[str, Any] | None = None,
    *,
    analyzer: Any | None = None,
) -> dict[str, Any]:
    """
    Aggregate per-row registral dispersion results into a whole-score summary.

    Event-boundary rows use duration-weighted statistics. Fixed-window rows use sampled
    trajectory summaries (overlapping windows are not independent duration states).
    """
    p = dict(params or {})
    obs = str(p.get("observation_mode") or OBSERVATION_MODE_FIXED_WINDOW)
    durations = _as_f64(results.get("interval_duration", results.get("t", [])))
    active = np.asarray(results.get("active_note_count", []), dtype=int)
    n_intervals = len(durations)
    empty_mask = active == 0 if active.size else np.zeros(n_intervals, dtype=bool)
    n_empty = int(np.sum(empty_mask)) if n_intervals else 0

    span = _as_f64(results.get("registral_span", []))
    pairwise = _as_f64(results.get("mean_pairwise_registral_distance", []))
    centroid = _as_f64(results.get("registral_centroid", []))
    std = _as_f64(results.get("registral_std", []))
    norm_span = _as_f64(results.get("normalized_registral_span", []))
    norm_pairwise = _as_f64(results.get("normalized_mean_pairwise_registral_distance", []))
    entropy = _as_f64(results.get("occupancy_entropy", []))
    dispersion_degree = _as_f64(results.get("dispersion_degree", span))
    norm_degree = _as_f64(results.get("normalized_dispersion_degree", norm_span))

    sound_mask = ~empty_mask
    sound_duration = float(np.sum(durations[sound_mask])) if n_intervals and np.any(sound_mask) else 0.0
    skipped_empty_duration = float(np.sum(durations[empty_mask])) if n_intervals and np.any(empty_mask) else 0.0

    summary: dict[str, Any] = {
        "n_intervals": n_intervals,
        "n_empty_intervals": n_empty,
        "skipped_empty_interval_duration": skipped_empty_duration,
        "total_observed_duration": sound_duration,
        "mean_active_note_count": _nan_mean(_as_f64(active.astype(float))),
        "max_active_note_count": int(np.max(active)) if active.size else 0,
        "analysis_profile": p.get("analysis_profile"),
        "pitch_sampling_mode": p.get("pitch_sampling_mode"),
        "pitch_sampling_source": p.get("pitch_sampling_source"),
        "observation_mode": obs,
        "tie_policy": p.get("tie_policy", DEFAULT_TIE_POLICY),
        "microtone_repair": p.get("microtone_repair", "off"),
        "register_low": p.get("register_low"),
        "register_high": p.get("register_high"),
        "normalization_reference": NORMALIZATION_REFERENCE,
        "package_version": _package_version(),
        "schema_version": SUMMARY_SCHEMA_VERSION,
        "symbolic_score_only": True,
    }

    if analyzer is not None:
        summary["register_low_midi"] = float(getattr(analyzer, "register_low", float("nan")))
        summary["register_high_midi"] = float(getattr(analyzer, "register_high", float("nan")))
        summary["register_width_semitones"] = float(getattr(analyzer, "register_width_semitones", float("nan")))
    elif p.get("register_low_midi_ps") is not None:
        summary["register_low_midi"] = float(p["register_low_midi_ps"])
        summary["register_high_midi"] = float(p["register_high_midi_ps"])
        summary["register_width_semitones"] = float(p.get("register_width_semitones", float("nan")))

    if obs == OBSERVATION_MODE_EVENT_BOUNDARIES:
        summary["aggregation_method"] = AGGREGATION_DURATION_WEIGHTED
        summary["duration_weighted_registral_span"] = _duration_weighted_mean(span, durations)
        summary["duration_weighted_dispersion_degree"] = _duration_weighted_mean(dispersion_degree, durations)
        summary["duration_weighted_mean_pairwise_registral_distance"] = _duration_weighted_mean(pairwise, durations)
        summary["duration_weighted_registral_centroid"] = _duration_weighted_mean(centroid, durations)
        summary["duration_weighted_registral_std"] = _duration_weighted_mean(std, durations)
        summary["duration_weighted_normalized_registral_span"] = _duration_weighted_mean(norm_span, durations)
        summary["duration_weighted_normalized_dispersion_degree"] = _duration_weighted_mean(norm_degree, durations)
        summary["duration_weighted_normalized_mean_pairwise_registral_distance"] = _duration_weighted_mean(
            norm_pairwise, durations
        )
        summary["duration_weighted_occupancy_entropy"] = _duration_weighted_mean(entropy, durations)
        summary["duration_weighted_occupancy_entropy_note"] = "occupancy evenness index; not registral dispersion"
        summary["median_registral_span"] = _duration_weighted_median(span, durations)
        summary["median_mean_pairwise_registral_distance"] = _duration_weighted_median(pairwise, durations)
        summary["max_registral_span"] = _nan_max(span)
        summary["max_dispersion_degree"] = _nan_max(dispersion_degree)
        summary["max_mean_pairwise_registral_distance"] = _nan_max(pairwise)
        summary["min_registral_span"] = _nan_min(span)
        summary["min_mean_pairwise_registral_distance"] = _nan_min(pairwise)
    else:
        summary["aggregation_method"] = AGGREGATION_SAMPLED_FIXED
        summary["n_windows"] = n_intervals
        summary["sampled_mean_registral_span"] = _nan_mean(span)
        summary["sampled_mean_dispersion_degree"] = _nan_mean(dispersion_degree)
        summary["sampled_mean_pairwise_registral_distance"] = _nan_mean(pairwise)
        summary["sampled_mean_registral_centroid"] = _nan_mean(centroid)
        summary["sampled_mean_registral_std"] = _nan_mean(std)
        summary["sampled_mean_normalized_registral_span"] = _nan_mean(norm_span)
        summary["sampled_mean_normalized_dispersion_degree"] = _nan_mean(norm_degree)
        summary["sampled_mean_normalized_mean_pairwise_registral_distance"] = _nan_mean(norm_pairwise)
        summary["sampled_mean_occupancy_entropy"] = _nan_mean(entropy)
        summary["sampled_mean_occupancy_entropy_note"] = "occupancy evenness index; not registral dispersion"
        summary["sampled_median_registral_span"] = _nan_median(span)
        summary["sampled_median_mean_pairwise_registral_distance"] = _nan_median(pairwise)
        summary["sampled_max_registral_span"] = _nan_max(span)
        summary["sampled_max_dispersion_degree"] = _nan_max(dispersion_degree)
        summary["sampled_max_mean_pairwise_registral_distance"] = _nan_max(pairwise)
        summary["sampled_min_registral_span"] = _nan_min(span)
        summary["sampled_min_mean_pairwise_registral_distance"] = _nan_min(pairwise)

    return summary


def primary_one_number_from_summary(global_summary: dict[str, Any]) -> tuple[str, float, str, float]:
    """
    Return ``(primary_metric, primary_value, secondary_metric, secondary_value)`` for one-number API.

    Uses duration-weighted fields for event-boundary aggregation; sampled means for fixed-window.
    """
    method = global_summary.get("aggregation_method")
    if method == AGGREGATION_DURATION_WEIGHTED:
        primary_metric = "duration_weighted_registral_span"
        secondary_metric = "duration_weighted_mean_pairwise_registral_distance"
        primary_value = float(global_summary.get(primary_metric, float("nan")))
        secondary_value = float(global_summary.get(secondary_metric, float("nan")))
    else:
        primary_metric = "sampled_mean_registral_span"
        secondary_metric = "sampled_mean_pairwise_registral_distance"
        primary_value = float(global_summary.get(primary_metric, float("nan")))
        secondary_value = float(global_summary.get(secondary_metric, float("nan")))
    if math.isnan(primary_value):
        primary_value = float("nan")
    if math.isnan(secondary_value):
        secondary_value = float("nan")
    return primary_metric, primary_value, secondary_metric, secondary_value
