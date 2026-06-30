"""Focused pytest coverage for tie_policy normalization and application."""

from __future__ import annotations

from typing import ClassVar

import pytest
from music21 import note, stream
from music21.tie import Tie

from registral_dispersion.tie_policy import (
    DEFAULT_TIE_POLICY,
    TIE_POLICY_AS_IMPORTED,
    TIE_POLICY_MERGE_TIES,
    apply_tie_policy,
    normalize_tie_policy,
)

# ---------------------------------------------------------------------------
# normalize_tie_policy — defaults
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "value",
    [None, "", "   ", "\t\n"],
)
def test_normalize_tie_policy_defaults(value) -> None:
    assert normalize_tie_policy(value) == DEFAULT_TIE_POLICY
    assert normalize_tie_policy(value) == TIE_POLICY_AS_IMPORTED


# ---------------------------------------------------------------------------
# normalize_tie_policy — accepted aliases
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("as_imported", TIE_POLICY_AS_IMPORTED),
        ("as imported", TIE_POLICY_AS_IMPORTED),
        ("as-imported", TIE_POLICY_AS_IMPORTED),
        ("MERGE-TIES", TIE_POLICY_MERGE_TIES),
        ("merge ties", TIE_POLICY_MERGE_TIES),
    ],
)
def test_normalize_tie_policy_accepted_aliases(value: str, expected: str) -> None:
    assert normalize_tie_policy(value) == expected


# ---------------------------------------------------------------------------
# normalize_tie_policy — invalid
# ---------------------------------------------------------------------------


def test_normalize_tie_policy_rejects_unknown_value() -> None:
    with pytest.raises(ValueError) as exc_info:
        normalize_tie_policy("bogus_policy")
    msg = str(exc_info.value)
    assert "Unknown tie_policy" in msg
    assert "bogus_policy" in msg
    assert TIE_POLICY_AS_IMPORTED in msg
    assert TIE_POLICY_MERGE_TIES in msg


# ---------------------------------------------------------------------------
# apply_tie_policy — as_imported
# ---------------------------------------------------------------------------


def test_apply_tie_policy_as_imported_returns_same_stream() -> None:
    sc = stream.Score()
    sc.insert(0, stream.Part())
    result, warnings = apply_tie_policy(sc, TIE_POLICY_AS_IMPORTED)
    assert result is sc
    assert warnings == []


# ---------------------------------------------------------------------------
# apply_tie_policy — merge_ties success
# ---------------------------------------------------------------------------


def _score_with_simple_tie() -> stream.Score:
    p = stream.Part()
    n1 = note.Note("C4", quarterLength=1.0)
    n2 = note.Note("C4", quarterLength=1.0)
    n1.tie = Tie("start")
    n2.tie = Tie("stop")
    p.insert(0, n1)
    p.insert(1, n2)
    sc = stream.Score()
    sc.insert(0, p)
    return sc


def test_apply_tie_policy_merge_ties_collapses_tied_notes() -> None:
    sc = _score_with_simple_tie()
    merged, warnings = apply_tie_policy(sc, TIE_POLICY_MERGE_TIES)
    assert merged is not None
    assert isinstance(warnings, list)
    notes = list(merged.flatten().notes)
    assert len(notes) == 1
    assert float(notes[0].quarterLength) == pytest.approx(2.0)


# ---------------------------------------------------------------------------
# apply_tie_policy — stripTies exception fallback
# ---------------------------------------------------------------------------


class _StripTiesFailingScore:
    def stripTies(self, inPlace: bool = False):
        raise RuntimeError("simulated stripTies failure")


def test_apply_tie_policy_merge_ties_strip_ties_failure_fallback() -> None:
    fake = _StripTiesFailingScore()
    result, warnings = apply_tie_policy(fake, TIE_POLICY_MERGE_TIES)
    assert result is fake
    assert len(warnings) == 1
    assert "stripTies failed" in warnings[0]
    assert "falling back to as_imported" in warnings[0]


# ---------------------------------------------------------------------------
# apply_tie_policy — residual tie metadata warning
# ---------------------------------------------------------------------------


class _NoteWithResidualTie:
    tie = object()


class _RecurseWithTiedNotes:
    notes: ClassVar[list[_NoteWithResidualTie]] = [_NoteWithResidualTie()]


class _MergedStreamWithResidualTies:
    def recurse(self):
        return _RecurseWithTiedNotes()


class _StripTiesScoreWithResidualTies:
    def stripTies(self, inPlace: bool = False):
        return _MergedStreamWithResidualTies()


def test_apply_tie_policy_merge_ties_warns_on_residual_tie_metadata() -> None:
    fake = _StripTiesScoreWithResidualTies()
    merged, warnings = apply_tie_policy(fake, TIE_POLICY_MERGE_TIES)
    assert merged is not None
    assert isinstance(merged, _MergedStreamWithResidualTies)
    assert len(warnings) == 1
    assert "still carry tie metadata" in warnings[0]
    assert "interpret sustained durations with caution" in warnings[0]
