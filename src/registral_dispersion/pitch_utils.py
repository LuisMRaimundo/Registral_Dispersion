"""Note-name helpers and register-band presets."""

from __future__ import annotations

import re

import music21 as m21

# Full practical notated range (piano + orchestral extremes).
DEFAULT_REGISTER_LOW = "A0"
DEFAULT_REGISTER_HIGH = "C8"

REGISTER_PRESET_FULL = "A0 to C8 (full notated range)"

# Legacy labels — not offered in UI; resolve to the full-range preset.
_LEGACY_REGISTER_PRESET_A0_B7 = "A0 to B7 (full notated range)"
_LEGACY_REGISTER_PRESET_ORCHESTRAL = "A1 to E7 (orchestral band)"

REGISTER_PRESETS: dict[str, tuple[str, str]] = {
    REGISTER_PRESET_FULL: ("A0", "C8"),
}


def note_name_to_midi_ps(note_name: str) -> float:
    """Convert a note name (e.g. 'A0', 'A1', 'C8') to MIDI pitch space (float)."""
    p = m21.pitch.Pitch(note_name.strip())
    return float(p.ps)


_CENTS_SUFFIX = re.compile(
    r"^(?P<name>.+?)\s*(?P<cents>[+-]\d+(?:\.\d+)?)\s*c(?:ents)?$",
    re.IGNORECASE,
)


def parse_pitch_input(value: object) -> float:
    """
    Parse a pitch as MIDI ``ps`` from a number or a note name.

    Accepted forms: ``56.5``, ``"56.5"``, ``"A#3"``, ``"Bb2"``, ``"A~3"``,
    ``"A#~3"``, ``"G3+50c"``, ``"A#3 +50c"``.
    """
    if isinstance(value, bool):
        raise ValueError(
            f"Cannot parse pitch {value!r}. Use a MIDI number (e.g. 56.5) or a name "
            "(A#3, A~3, A#~3, Bb2, G3+50c)."
        )
    if isinstance(value, int | float):
        if value != value:  # NaN
            raise ValueError("Cannot parse pitch NaN.")
        return float(value)
    s = str(value).strip()
    if not s:
        raise ValueError(
            "Cannot parse an empty pitch. Use a MIDI number (e.g. 56.5) or a name "
            "(A#3, A~3, A#~3, Bb2, G3+50c)."
        )
    try:
        return float(s)
    except ValueError:
        pass
    cents_match = _CENTS_SUFFIX.fullmatch(s)
    if cents_match is not None:
        base = _name_to_ps_or_raise(cents_match.group("name"))
        return base + float(cents_match.group("cents")) / 100.0
    return _name_to_ps_or_raise(s)


def _name_to_ps_or_raise(name: str) -> float:
    token = name.strip()
    try:
        return note_name_to_midi_ps(token)
    except Exception as exc:
        raise ValueError(
            f"Cannot parse pitch {name!r}. Use a MIDI number (e.g. 56.5) or a name "
            "(A#3, A~3, A#~3, Bb2, G3+50c)."
        ) from exc


def format_pitch_name(ps: float | None) -> str:
    """Readable pitch name, including music21 quarter-tone spellings (e.g. ``A#~3``)."""
    if ps is None:
        return ""
    p = m21.pitch.Pitch()
    p.ps = float(ps)
    return str(p.nameWithOctave)


def format_ps_display(ps: float | None) -> float | None:
    """Round MIDI ``ps`` to two decimals for inventory display."""
    if ps is None:
        return None
    return round(float(ps), 2)


def resolve_register_preset(preset_label: str | None) -> tuple[str, str] | None:
    """Return ``(register_low, register_high)`` note names for a preset label, or ``None`` if unknown."""
    if preset_label is None:
        return None
    key = str(preset_label).strip()
    if key in (_LEGACY_REGISTER_PRESET_A0_B7, _LEGACY_REGISTER_PRESET_ORCHESTRAL):
        return REGISTER_PRESETS[REGISTER_PRESET_FULL]
    if key in REGISTER_PRESETS:
        return REGISTER_PRESETS[key]
    return None
