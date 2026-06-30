"""Interpretation warnings for profile, sampling, aggregation, and normalization."""

from __future__ import annotations

from typing import Any

from registral_dispersion.observation import OBSERVATION_MODE_EVENT_BOUNDARIES, OBSERVATION_MODE_FIXED_WINDOW
from registral_dispersion.profiles import ANALYSIS_PROFILE_COMPONENT_WEIGHTED

WARN_EXPLICIT_PITCH_SAMPLING = (
    "Explicit pitch_sampling_mode overrides analysis_profile; interpretation follows sampling mode."
)
WARN_COMPONENT_WEIGHTED = (
    "Component-weighted profile counts duplicated unisons/event instances; interpret as "
    "component-weighted registral spread, not density-independent occupied-space geometry."
)
WARN_NORMALIZED_PRIMARY = "Normalized values are register-band-relative, not perceptual brightness."
WARN_FIXED_WINDOW_ONE_NUMBER = (
    "One-number summary uses fixed_window observation: global values are sampled trajectory "
    "summaries, not duration-weighted event-state aggregates."
)


def collect_interpretation_warnings(
    params: dict[str, Any],
    *,
    context: str = "analysis",
    normalized_primary: bool = False,
) -> list[str]:
    """
    Build deterministic interpretation warnings from resolved parameters.

    ``context`` may be ``analysis`` or ``one_number_summary`` (adds component_weighted reminder).
    """
    warnings: list[str] = []
    src = str(params.get("pitch_sampling_source") or "")
    if src == "explicit_param":
        warnings.append(WARN_EXPLICIT_PITCH_SAMPLING)
    if params.get("analysis_profile") == ANALYSIS_PROFILE_COMPONENT_WEIGHTED:
        warnings.append(WARN_COMPONENT_WEIGHTED)
    if normalized_primary:
        warnings.append(WARN_NORMALIZED_PRIMARY)
    obs = params.get("observation_mode", OBSERVATION_MODE_FIXED_WINDOW)
    if context == "one_number_summary" and obs != OBSERVATION_MODE_EVENT_BOUNDARIES:
        warnings.append(WARN_FIXED_WINDOW_ONE_NUMBER)
    return _dedupe(warnings)


def merge_warnings(*groups: list[str] | None) -> list[str]:
    """Merge warning lists preserving order."""
    out: list[str] = []
    for g in groups:
        if not g:
            continue
        for w in g:
            if w not in out:
                out.append(w)
    return out


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out
