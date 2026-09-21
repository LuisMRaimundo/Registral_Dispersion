"""Repair MusicXML accidental glyphs whose ``<alter>`` does not match the glyph name.

Sibelius 8 (and similar exporters) write microtonal accidentals as glyphs only, e.g.
``<accidental>quarter-sharp</accidental>`` with ``<alter>0</alter>``. music21 then stores
``accidental.name == "half-sharp"`` but ``accidental.alter == 0.0``, so ``pitch.ps`` is an
integer and the quarter-tone is lost.

This module detects that mismatch and, optionally, rewrites the accidental from the glyph
name **before** tie stripping and event listing.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from music21 import chord as m21_chord
from music21 import note as m21_note
from music21 import pitch as m21_pitch
from music21 import stream

MICROTONEREPAIR_OFF = "off"
MICROTONEREPAIR_WARN = "warn"
MICROTONEREPAIR_FROM_ACCIDENTALS = "from_accidentals"

MICROTONEREPAIR_MODES = frozenset(
    {MICROTONEREPAIR_OFF, MICROTONEREPAIR_WARN, MICROTONEREPAIR_FROM_ACCIDENTALS}
)

DEFAULT_MICROTONEREPAIR = MICROTONEREPAIR_OFF

MIDI_EXTENSIONS = frozenset({".mid", ".midi"})

_ALTER_EPS = 1e-6

WARN_MIDI_NO_GLYPHS = (
    "MIDI input has no accidental-glyph information; microtones cannot be recovered "
    "(pitch-bend is ignored). microtone_repair has no effect."
)


def warn_glyph_alter_mismatch(n: int) -> str:
    """Warning text for ``microtone_repair='warn'`` (N mismatched pitches)."""
    return (
        f"{n} pitches carry a microtonal accidental glyph but an integer <alter>; "
        "results ignore these inflections. Re-run with microtone_repair='from_accidentals' "
        "or fix the file."
    )


def warn_repaired_from_accidentals(n: int) -> str:
    """Summary warning after applying ``from_accidentals``."""
    return (
        f"Repaired {n} pitch(es) whose accidental glyph did not match <alter> "
        "(microtone_repair='from_accidentals')."
    )


def normalize_microtone_repair(value: Any) -> str:
    """Return a supported mode; default ``off`` if missing. Unknown values raise ``ValueError``."""
    if value is None or str(value).strip() == "":
        return DEFAULT_MICROTONEREPAIR
    s = str(value).strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "from_accidental": MICROTONEREPAIR_FROM_ACCIDENTALS,
        "fromaccidentals": MICROTONEREPAIR_FROM_ACCIDENTALS,
        "glyphs": MICROTONEREPAIR_FROM_ACCIDENTALS,
    }
    s = aliases.get(s, s)
    if s in MICROTONEREPAIR_MODES:
        return s
    raise ValueError(
        f"Unknown microtone_repair {value!r}; expected "
        f"{MICROTONEREPAIR_OFF!r}, {MICROTONEREPAIR_WARN!r}, or {MICROTONEREPAIR_FROM_ACCIDENTALS!r}."
    )


def is_midi_score_path(path: str | None) -> bool:
    """True when ``path`` is a MIDI file (no accidental glyphs)."""
    if not path:
        return False
    return Path(path).suffix.lower() in MIDI_EXTENSIONS


def _canonical_alter(accidental_name: str) -> float | None:
    try:
        return float(m21_pitch.Accidental(accidental_name).alter)
    except Exception:
        return None


def _pitches_of(el) -> tuple[m21_pitch.Pitch, ...]:
    if isinstance(el, m21_note.Note):
        return (el.pitch,)
    if isinstance(el, m21_chord.Chord):
        return tuple(el.pitches)
    return ()


def _part_label(part) -> str | None:
    if part is None:
        return None
    for attr in ("id", "partName"):
        val = getattr(part, attr, None)
        if val not in (None, ""):
            return str(val)
    return None


def _measure_number(measure) -> int | str | None:
    if measure is None:
        return None
    num = getattr(measure, "number", None)
    return num


def _staff_id(el) -> int:
    s = getattr(el, "staff", None)
    if s in (None, ""):
        return 1
    try:
        return int(s)
    except (TypeError, ValueError):
        return 1


def _has_displayed_accidental(p: m21_pitch.Pitch) -> bool:
    acc = p.accidental
    if acc is None:
        return False
    if acc.displayStatus is False:
        return False
    return True


def _clone_accidental(acc: m21_pitch.Accidental, *, display_status: bool | None) -> m21_pitch.Accidental:
    new = m21_pitch.Accidental(acc.name)
    new.displayStatus = display_status
    return new


def _tie_type(el) -> str | None:
    tie = getattr(el, "tie", None)
    if tie is None:
        return None
    return getattr(tie, "type", None)


def _iter_note_contexts(score: stream.Stream):
    """Yield ``(part, measure, element)`` for every Note/Chord in document order."""
    parts = list(score.parts) if getattr(score, "parts", None) else []
    if not parts:
        measures = list(score.getElementsByClass(stream.Measure))
        if measures:
            for measure in measures:
                for el in measure.notes:
                    yield score, measure, el
        else:
            for el in score.recurse().notes:
                yield score, el.getContextByClass(stream.Measure), el
        return
    for part in parts:
        measures = list(part.getElementsByClass(stream.Measure))
        if measures:
            for measure in measures:
                for el in measure.notes:
                    yield part, measure, el
        else:
            for el in part.recurse().notes:
                yield part, el.getContextByClass(stream.Measure), el


def detect_accidental_alter_mismatch(score: stream.Stream) -> list[tuple]:
    """
    Compare each pitch's stored ``accidental.alter`` with music21's canonical alter for
    ``accidental.name``.

    Returns a list of
    ``(part, measure, offset, nameWithOctave, found_alter, expected_alter)``.
    """
    mismatches: list[tuple] = []
    for part, measure, el in _iter_note_contexts(score):
        offset = float(el.offset)
        for p in _pitches_of(el):
            acc = p.accidental
            if acc is None or not getattr(acc, "name", None):
                continue
            expected = _canonical_alter(acc.name)
            if expected is None:
                continue
            found = float(acc.alter)
            if abs(found - expected) <= _ALTER_EPS:
                continue
            mismatches.append(
                (
                    _part_label(part),
                    _measure_number(measure),
                    offset,
                    str(p.nameWithOctave),
                    found,
                    expected,
                )
            )
    return mismatches


def _apply_named_accidental(p: m21_pitch.Pitch, name: str, *, display_status: bool | None) -> None:
    new = m21_pitch.Accidental(name)
    new.displayStatus = display_status
    p.accidental = new


def _repair_mismatches_in_place(score: stream.Stream) -> list[dict[str, Any]]:
    """Rewrite mismatched accidentals from their glyph name. Returns repair records."""
    repairs: list[dict[str, Any]] = []
    for part, measure, el in _iter_note_contexts(score):
        offset = float(el.offset)
        for p in _pitches_of(el):
            acc = p.accidental
            if acc is None or not getattr(acc, "name", None):
                continue
            expected = _canonical_alter(acc.name)
            if expected is None:
                continue
            found = float(acc.alter)
            if abs(found - expected) <= _ALTER_EPS:
                continue
            display = acc.displayStatus
            name = acc.name
            _apply_named_accidental(p, name, display_status=display)
            repairs.append(
                {
                    "part": _part_label(part),
                    "measure": _measure_number(measure),
                    "offset": offset,
                    "nameWithOctave": str(p.nameWithOctave),
                    "found_alter": found,
                    "expected_alter": expected,
                    "accidental_name": name,
                    "kind": "glyph_alter",
                }
            )
    return repairs


def _propagate_repaired_alters(score: stream.Stream) -> None:
    """
    After glyph repairs, copy the repaired alter onto later notes that would inherit it
    in MusicXML: same part/staff/step/octave until a new displayed accidental or barline;
    tied continuations inherit from the tie start across barlines.
    """
    measure_state: dict[tuple, m21_pitch.Accidental] = {}
    tie_state: dict[tuple, m21_pitch.Accidental] = {}
    current_measure_id: object = object()

    for part, measure, el in _iter_note_contexts(score):
        measure_id = id(measure) if measure is not None else ("bare", _part_label(part))
        if measure_id != current_measure_id:
            measure_state = {}
            current_measure_id = measure_id

        tie = _tie_type(el)
        for p in _pitches_of(el):
            key = (_part_label(part), _staff_id(el), p.step, p.octave)
            if _has_displayed_accidental(p):
                acc = p.accidental
                expected = _canonical_alter(acc.name) if acc is not None else None
                is_repaired_glyph = (
                    acc is not None
                    and expected is not None
                    and abs(float(acc.alter) - expected) <= _ALTER_EPS
                    and abs(expected - round(expected)) > _ALTER_EPS
                )
                if is_repaired_glyph:
                    cloned = _clone_accidental(acc, display_status=False)
                    measure_state[key] = cloned
                    if tie in ("start", "continue"):
                        tie_state[key] = cloned
                else:
                    measure_state.pop(key, None)
                    if tie in ("start", "continue"):
                        tie_state.pop(key, None)
                if tie == "stop":
                    tie_state.pop(key, None)
                continue

            inherited = None
            if tie in ("stop", "continue") and key in tie_state:
                inherited = tie_state[key]
            elif key in measure_state:
                inherited = measure_state[key]
            if inherited is not None:
                _apply_named_accidental(p, inherited.name, display_status=False)
            if tie in ("start", "continue") and inherited is not None:
                tie_state[key] = _clone_accidental(inherited, display_status=False)
            if tie == "stop":
                tie_state.pop(key, None)


def apply_microtone_repair(
    score: stream.Stream,
    mode: str | None,
    *,
    is_midi: bool = False,
) -> tuple[stream.Stream, list[str], list[dict[str, Any]]]:
    """
    Apply ``microtone_repair`` to ``score``.

    Returns ``(score, warnings, repairs)``. MIDI input is never modified.
    """
    resolved = normalize_microtone_repair(mode)
    if resolved == MICROTONEREPAIR_OFF:
        return score, [], []
    if is_midi:
        return score, [WARN_MIDI_NO_GLYPHS], []

    mismatches = detect_accidental_alter_mismatch(score)
    if resolved == MICROTONEREPAIR_WARN:
        if not mismatches:
            return score, [], []
        return score, [warn_glyph_alter_mismatch(len(mismatches))], []

    repairs = _repair_mismatches_in_place(score)
    if repairs:
        _propagate_repaired_alters(score)
        return score, [warn_repaired_from_accidentals(len(repairs))], repairs
    return score, [], []
