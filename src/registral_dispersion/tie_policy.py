"""Explicit tie handling for reproducible symbolic-score parsing."""

from __future__ import annotations

from typing import Any

TIE_POLICY_AS_IMPORTED = "as_imported"
TIE_POLICY_MERGE_TIES = "merge_ties"

TIE_POLICIES = frozenset({TIE_POLICY_AS_IMPORTED, TIE_POLICY_MERGE_TIES})

DEFAULT_TIE_POLICY = TIE_POLICY_AS_IMPORTED


def normalize_tie_policy(value: Any) -> str:
    """Return a supported tie policy; default ``as_imported`` if missing or unknown."""
    if value is None or str(value).strip() == "":
        return DEFAULT_TIE_POLICY
    s = str(value).strip().lower().replace("-", "_").replace(" ", "_")
    if s in TIE_POLICIES:
        return s
    raise ValueError(f"Unknown tie_policy {value!r}; expected {TIE_POLICY_AS_IMPORTED!r} or {TIE_POLICY_MERGE_TIES!r}.")


def apply_tie_policy(score_stream, tie_policy: Any = DEFAULT_TIE_POLICY) -> tuple[Any, list[str]]:
    """
    Apply ``tie_policy`` to a parsed music21 stream.

    Returns ``(processed_stream, warnings)``. ``as_imported`` returns the input unchanged.
    ``merge_ties`` uses music21 ``stripTies(inPlace=False)`` to collapse tied continuations.
    """
    policy = normalize_tie_policy(tie_policy)
    if policy == TIE_POLICY_AS_IMPORTED:
        return score_stream, []

    warnings: list[str] = []
    try:
        merged = score_stream.stripTies(inPlace=False)
    except Exception as exc:
        warnings.append(f"tie_policy merge_ties: stripTies failed ({exc}); falling back to as_imported stream.")
        return score_stream, warnings

    remaining = 0
    for el in merged.recurse().notes:
        if getattr(el, "tie", None) is not None:
            remaining += 1
    if remaining:
        warnings.append(
            f"tie_policy merge_ties: {remaining} note/chord object(s) still carry tie metadata after "
            "stripTies; interpret sustained durations with caution."
        )
    return merged, warnings
