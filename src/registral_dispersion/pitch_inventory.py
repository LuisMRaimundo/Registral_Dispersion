"""Inspectable pitch inventory: one row per notated pitch after repair/conversion."""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from music21 import chord as m21_chord
from music21 import note as m21_note
from music21 import stream

from registral_dispersion.pitch_overrides import (
    OVERRIDE_KIND_MANUAL_EXCLUDE,
    OVERRIDE_KIND_MANUAL_PITCH,
    OVERRIDE_KIND_PART_TRANSPOSITION,
    coerce_used_in_metrics,
    normalize_pitch_overrides,
    warn_manual_overrides,
    warn_out_of_band_edit,
)
from registral_dispersion.pitch_reference import (
    PITCH_REFERENCE_SOUNDING,
    PITCH_REFERENCE_WRITTEN,
    convert_score_to_sounding,
    detect_transposing_parts,
    normalize_pitch_reference,
    warn_written_with_transposing_parts,
)
from registral_dispersion.pitch_utils import format_pitch_name, format_ps_display, parse_pitch_input

MISC_NOTE_IDS = "rd_note_ids"
MISC_EXCLUDE_INDICES = "rd_exclude_indices"

INVENTORY_COLUMNS = [
    "note_id",
    "part",
    "instrument",
    "measure",
    "offset_qL",
    "duration_qL",
    "written_name",
    "written_ps",
    "sounding_name",
    "sounding_ps",
    "accidental_glyph",
    "flags",
    "used_in_metrics",
]

_PS_EPS = 1e-9


@dataclass
class PitchItem:
    el: Any
    pitch: Any | None
    part_index: int
    part: str
    instrument: str
    measure: int | str
    offset_qL: float
    duration_qL: float
    voice: str
    chord_index: int
    note_id: str
    unpitched: bool
    tied_continuation: bool
    accidental_glyph: str
    ps: float | None
    name: str


@dataclass
class PreparedScore:
    score: stream.Stream
    pitch_reference: str
    inventory: list[dict[str, Any]]
    digest: dict[str, Any]
    transposing_parts: list[dict[str, Any]]
    pitch_overrides: list[dict[str, Any]]
    warnings: list[str] = field(default_factory=list)


def _editorial_misc(el) -> dict[str, Any]:
    editorial = getattr(el, "editorial", None)
    if editorial is None:
        return {}
    misc = getattr(editorial, "misc", None)
    if misc is None:
        editorial.misc = {}
        return editorial.misc
    return misc


def excluded_indices(el) -> set[int]:
    misc = _editorial_misc(el)
    raw = misc.get(MISC_EXCLUDE_INDICES) or []
    out: set[int] = set()
    for item in raw:
        try:
            out.add(int(item))
        except (TypeError, ValueError):
            continue
    return out


def _fmt_offset(offset: object) -> str:
    f = float(offset)
    if abs(f - round(f)) < 1e-9:
        return str(int(round(f)))
    return f"{f:.6g}"


def make_note_id(part_index: int, measure: object, offset: object, voice: object, chord_index: int) -> str:
    """Stable ``part_index:measure:offset:voice:chord_index``."""
    mn = 0 if measure in (None, "") else measure
    return f"{int(part_index)}:{mn}:{_fmt_offset(offset)}:{voice}:{int(chord_index)}"


def _voice_id(el) -> str:
    v = getattr(el, "voice", None)
    if v not in (None, ""):
        return str(v)
    site = getattr(el, "activeSite", None)
    if site is not None and type(site).__name__ == "Voice":
        vid = getattr(site, "id", None)
        return "1" if vid in (None, "") else str(vid)
    return "1"


def _measure_number(measure) -> int | str:
    if measure is None:
        return 0
    num = getattr(measure, "number", None)
    if num in (None, ""):
        return 0
    return num


def _part_label(part) -> str:
    if part is None:
        return ""
    for attr in ("partName", "id"):
        val = getattr(part, attr, None)
        if val not in (None, ""):
            return str(val)
    return ""


def _instrument_name(part) -> str:
    if part is None or not hasattr(part, "getInstrument"):
        return ""
    try:
        inst = part.getInstrument(returnDefault=True)
    except Exception:
        return ""
    if inst is None:
        return ""
    for attr in ("instrumentName", "bestName"):
        val = getattr(inst, attr, None)
        if val not in (None, ""):
            return str(val)
    return str(inst)


def _is_tied_continuation(el) -> bool:
    tie = getattr(el, "tie", None)
    if tie is None:
        return False
    return getattr(tie, "type", None) in ("stop", "continue")


def _accidental_glyph(pitch) -> str:
    if pitch is None:
        return ""
    acc = getattr(pitch, "accidental", None)
    if acc is None:
        return ""
    name = getattr(acc, "name", None)
    return "" if name in (None, "") else str(name)


def _iter_parts(score: stream.Stream):
    parts = list(getattr(score, "parts", []) or [])
    if parts:
        for i, part in enumerate(parts):
            yield i, part
        return
    yield 0, score


def _iter_note_elements(part):
    measures = list(part.getElementsByClass(stream.Measure))
    if measures:
        for measure in measures:
            for el in measure.recurse().notes:
                yield measure, el
        return
    for el in part.recurse().notes:
        yield el.getContextByClass(stream.Measure), el


def _component_pitches(el) -> list[tuple[int, Any | None, bool]]:
    if isinstance(el, m21_note.Unpitched):
        return [(0, None, True)]
    if isinstance(el, m21_note.Note):
        return [(0, el.pitch, False)]
    if isinstance(el, m21_chord.Chord):
        return [(i, p, False) for i, p in enumerate(el.pitches)]
    return []


def iter_score_pitch_items(score: stream.Stream) -> list[PitchItem]:
    """Walk every Note / Chord tone / Unpitched in document order."""
    items: list[PitchItem] = []
    for part_index, part in _iter_parts(score):
        part_name = _part_label(part)
        inst_name = _instrument_name(part)
        for measure, el in _iter_note_elements(part):
            mn = _measure_number(measure)
            offset = float(el.offset)
            dur = float(el.quarterLength) if hasattr(el, "quarterLength") else 0.0
            voice = _voice_id(el)
            tied = _is_tied_continuation(el)
            for chord_index, pitch, unpitched in _component_pitches(el):
                nid = make_note_id(part_index, mn, offset, voice, chord_index)
                ps = None if (unpitched or pitch is None) else float(pitch.ps)
                name = "" if ps is None else format_pitch_name(ps)
                items.append(
                    PitchItem(
                        el=el,
                        pitch=pitch,
                        part_index=part_index,
                        part=part_name,
                        instrument=inst_name,
                        measure=mn,
                        offset_qL=offset,
                        duration_qL=dur,
                        voice=voice,
                        chord_index=chord_index,
                        note_id=nid,
                        unpitched=unpitched,
                        tied_continuation=tied,
                        accidental_glyph=_accidental_glyph(pitch),
                        ps=ps,
                        name=name,
                    )
                )
    return items


def stamp_note_ids(score: stream.Stream) -> dict[str, tuple[Any, int]]:
    """Write ``rd_note_ids`` onto each element; return ``note_id → (el, chord_index)``."""
    index: dict[str, tuple[Any, int]] = {}
    for item in iter_score_pitch_items(score):
        misc = _editorial_misc(item.el)
        ids = list(misc.get(MISC_NOTE_IDS) or [])
        while len(ids) <= item.chord_index:
            ids.append(None)
        ids[item.chord_index] = item.note_id
        misc[MISC_NOTE_IDS] = ids
        index[item.note_id] = (item.el, item.chord_index)
    return index


def _repair_keys(repairs: list[dict[str, Any]] | None) -> set[tuple]:
    keys: set[tuple] = set()
    for rec in repairs or []:
        keys.add(
            (
                str(rec.get("part") or ""),
                rec.get("measure"),
                float(rec.get("offset") or 0.0),
                str(rec.get("nameWithOctave") or ""),
            )
        )
    return keys


def _flags_for(
    *,
    unpitched: bool,
    tied_continuation: bool,
    transposed: bool,
    repaired: bool,
    out_of_band: bool,
) -> list[str]:
    flags: list[str] = []
    if repaired:
        flags.append("microtone_repaired")
    if transposed:
        flags.append("transposed")
    if unpitched:
        flags.append("unpitched")
    if tied_continuation:
        flags.append("tied_continuation")
    if out_of_band:
        flags.append("out_of_band")
    return flags


def _in_band(ps: float | None, low: float | None, high: float | None) -> bool:
    if ps is None:
        return False
    if low is None or high is None:
        return True
    lo, hi = (low, high) if low <= high else (high, low)
    return lo <= float(ps) <= hi


def _analysis_ps(row: dict[str, Any], pitch_reference: str) -> float | None:
    if pitch_reference == PITCH_REFERENCE_SOUNDING:
        return row.get("sounding_ps")
    return row.get("written_ps")


def _row_from_pair(
    written: PitchItem,
    sounding: PitchItem,
    *,
    pitch_reference: str,
    register_low: float | None,
    register_high: float | None,
    repaired: bool,
) -> dict[str, Any]:
    written_ps = None if written.unpitched else written.ps
    sounding_ps = None if sounding.unpitched else sounding.ps
    transposed = (
        written_ps is not None
        and sounding_ps is not None
        and abs(float(written_ps) - float(sounding_ps)) > _PS_EPS
    )
    analysis = sounding_ps if pitch_reference == PITCH_REFERENCE_SOUNDING else written_ps
    out_of_band = (not written.unpitched) and (not _in_band(analysis, register_low, register_high))
    used = (not written.unpitched) and (not out_of_band)
    return {
        "note_id": written.note_id,
        "part": written.part,
        "instrument": written.instrument,
        "measure": written.measure,
        "offset_qL": float(written.offset_qL),
        "duration_qL": float(written.duration_qL),
        "written_name": "" if written.unpitched else (written.name or format_pitch_name(written_ps)),
        "written_ps": format_ps_display(written_ps),
        "sounding_name": "" if sounding.unpitched else (sounding.name or format_pitch_name(sounding_ps)),
        "sounding_ps": format_ps_display(sounding_ps),
        "accidental_glyph": written.accidental_glyph,
        "flags": _flags_for(
            unpitched=written.unpitched,
            tied_continuation=written.tied_continuation,
            transposed=transposed,
            repaired=repaired,
            out_of_band=out_of_band,
        ),
        "used_in_metrics": used,
        "_written_ps": written_ps,
        "_sounding_ps": sounding_ps,
        "_part_index": written.part_index,
        "_chord_index": written.chord_index,
        "_unpitched": written.unpitched,
        "_excluded": False,
    }


def pitch_inventory_digest(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """``n_notes``, ``n_unique``, ``min``, ``max``, sorted unique sounding ``ps``."""
    sounding: list[float] = []
    for row in rows:
        ps = row.get("_sounding_ps", row.get("sounding_ps"))
        if row.get("_unpitched") or ps in (None, ""):
            continue
        sounding.append(float(ps))
    unique = sorted({round(p, 6) if abs(p - round(p, 6)) < 1e-9 else p for p in sounding})
    # keep original floats but unique by rounded-6; re-derive from sounding
    uniq_map: dict[float, float] = {}
    for p in sounding:
        uniq_map[round(p, 6)] = p
    unique_ps = [uniq_map[k] for k in sorted(uniq_map)]
    return {
        "n_notes": len(rows),
        "n_unique": len(unique_ps),
        "min": None if not unique_ps else float(min(unique_ps)),
        "max": None if not unique_ps else float(max(unique_ps)),
        "unique_ps": unique_ps,
    }


def inventory_digest_line(digest: dict[str, Any]) -> str:
    unique = digest.get("unique_ps") or []
    unique_s = ", ".join(f"{format_ps_display(p)}" for p in unique)
    mn = digest.get("min")
    mx = digest.get("max")
    mn_s = "—" if mn is None else f"{format_ps_display(mn)}"
    mx_s = "—" if mx is None else f"{format_ps_display(mx)}"
    return (
        f"{digest.get('n_notes', 0)} notes, {digest.get('n_unique', 0)} unique sounding pitches, "
        f"min {mn_s}, max {mx_s}, [{unique_s}]"
    )


def _is_repaired(item: PitchItem, repair_keys: set[tuple]) -> bool:
    if not repair_keys:
        return False
    return (str(item.part or ""), item.measure, float(item.offset_qL), item.name) in repair_keys


def build_pitch_inventory(score: stream.Stream, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """
    One row per pitch (chord tones separately) **after** microtone repair, pairing
    written and sounding copies. ``params`` may include ``pitch_reference``,
    ``register_low`` / ``register_high`` (note names or MIDI), ``register_low_ps`` /
    ``register_high_ps``, and ``repairs``.
    """
    params = dict(params or {})
    ref = normalize_pitch_reference(params.get("pitch_reference"))
    register_low = params.get("register_low_ps")
    register_high = params.get("register_high_ps")
    if register_low is None and params.get("register_low") not in (None, ""):
        register_low = parse_pitch_input(params["register_low"])
    if register_high is None and params.get("register_high") not in (None, ""):
        register_high = parse_pitch_input(params["register_high"])
    written_items = iter_score_pitch_items(score)
    sounding_score = convert_score_to_sounding(score)
    sounding_items = iter_score_pitch_items(sounding_score)
    if len(sounding_items) != len(written_items):
        sounding_items = written_items
    repair_keys = _repair_keys(params.get("repairs"))
    rows: list[dict[str, Any]] = []
    for w, s in zip(written_items, sounding_items, strict=False):
        rows.append(
            _row_from_pair(
                w,
                s,
                pitch_reference=ref,
                register_low=None if register_low is None else float(register_low),
                register_high=None if register_high is None else float(register_high),
                repaired=_is_repaired(w, repair_keys),
            )
        )
    return rows


def _refresh_row_derived(
    row: dict[str, Any],
    *,
    pitch_reference: str,
    register_low: float | None,
    register_high: float | None,
) -> None:
    written_ps = row.get("_written_ps")
    sounding_ps = row.get("_sounding_ps")
    row["written_ps"] = format_ps_display(written_ps)
    row["sounding_ps"] = format_ps_display(sounding_ps)
    row["written_name"] = "" if row.get("_unpitched") else format_pitch_name(written_ps)
    row["sounding_name"] = "" if row.get("_unpitched") else format_pitch_name(sounding_ps)
    analysis = _analysis_ps(row, pitch_reference)
    if analysis is None and pitch_reference == PITCH_REFERENCE_SOUNDING:
        analysis = sounding_ps
    elif analysis is None:
        analysis = written_ps
    # After overrides the analysis pitch is the working (sounding display) value
    # when the user edited sounding_ps; use _sounding_ps if reference is sounding,
    # otherwise the working pitch is stored in both after a note-level edit.
    working = sounding_ps if pitch_reference == PITCH_REFERENCE_SOUNDING else written_ps
    if row.get("_pitch_overridden"):
        working = sounding_ps if sounding_ps is not None else written_ps
    out_of_band = (not row.get("_unpitched")) and (not _in_band(working, register_low, register_high))
    transposed = (
        written_ps is not None
        and sounding_ps is not None
        and abs(float(written_ps) - float(sounding_ps)) > _PS_EPS
    )
    flags = [f for f in (row.get("flags") or []) if f not in {"out_of_band", "transposed"}]
    if transposed and "transposed" not in flags:
        flags.append("transposed")
    if out_of_band and "out_of_band" not in flags:
        flags.append("out_of_band")
    row["flags"] = flags
    excluded = bool(row.get("_excluded"))
    row["used_in_metrics"] = (not row.get("_unpitched")) and (not excluded) and (not out_of_band)


def _set_component_ps(el, chord_index: int, ps: float) -> None:
    if isinstance(el, m21_note.Note):
        el.pitch.ps = float(ps)
        return
    if isinstance(el, m21_chord.Chord):
        pitches = list(el.pitches)
        if 0 <= chord_index < len(pitches):
            pitches[chord_index].ps = float(ps)


def _mark_excluded(el, chord_index: int) -> None:
    misc = _editorial_misc(el)
    current = {int(i) for i in (misc.get(MISC_EXCLUDE_INDICES) or []) if str(i).lstrip("-").isdigit()}
    current.add(int(chord_index))
    misc[MISC_EXCLUDE_INDICES] = sorted(current)


def _mark_included(el, chord_index: int) -> None:
    misc = _editorial_misc(el)
    current = {int(i) for i in (misc.get(MISC_EXCLUDE_INDICES) or []) if str(i).lstrip("-").isdigit()}
    current.discard(int(chord_index))
    misc[MISC_EXCLUDE_INDICES] = sorted(current)


def _part_spec_matches(row: dict[str, Any], spec: Any) -> bool:
    if spec is None or spec == "":
        return False
    if isinstance(spec, int | float) and not isinstance(spec, bool):
        return int(row.get("_part_index", -1)) == int(spec)
    s = str(spec).strip()
    if s.isdigit() or (s.startswith("-") and s[1:].isdigit()):
        return int(row.get("_part_index", -1)) == int(s)
    return s in {str(row.get("part") or ""), str(row.get("instrument") or "")}


def apply_pitch_overrides(
    working: stream.Stream,
    rows: list[dict[str, Any]],
    overrides: list[dict[str, Any]],
    *,
    pitch_reference: str,
    register_low: float | None,
    register_high: float | None,
) -> tuple[list[dict[str, Any]], list[str]]:
    """
    Apply part-level then note-level overrides to ``working`` and update inventory rows.

    Returns ``(rows, warnings)``.
    """
    normalized = normalize_pitch_overrides(overrides)
    if not normalized:
        return rows, []
    index = stamp_note_ids(working)
    by_id = {str(r["note_id"]): r for r in rows}
    warnings: list[str] = []

    part_level = [o for o in normalized if o["kind"] == OVERRIDE_KIND_PART_TRANSPOSITION]
    note_level = [o for o in normalized if o["kind"] != OVERRIDE_KIND_PART_TRANSPOSITION]

    for ov in part_level:
        delta = float(ov["new"])
        for row in rows:
            if row.get("_unpitched"):
                continue
            if not _part_spec_matches(row, ov.get("part")):
                continue
            nid = str(row["note_id"])
            target = index.get(nid)
            if target is None:
                continue
            el, chord_index = target
            current = row.get("_sounding_ps") if pitch_reference == PITCH_REFERENCE_SOUNDING else row.get("_written_ps")
            if current is None:
                continue
            new_ps = float(current) + delta
            _set_component_ps(el, chord_index, new_ps)
            if pitch_reference == PITCH_REFERENCE_SOUNDING:
                row["_sounding_ps"] = new_ps
            else:
                row["_written_ps"] = new_ps
                row["_sounding_ps"] = (
                    None if row.get("_sounding_ps") is None else float(row["_sounding_ps"]) + delta
                )
            row["_pitch_overridden"] = True
            _refresh_row_derived(row, pitch_reference=pitch_reference, register_low=register_low, register_high=register_high)

    for ov in note_level:
        nid = str(ov.get("note_id") or "")
        row = by_id.get(nid)
        target = index.get(nid)
        if row is None or target is None:
            continue
        el, chord_index = target
        if ov["kind"] == OVERRIDE_KIND_MANUAL_PITCH:
            new_ps = float(ov["new"])
            _set_component_ps(el, chord_index, new_ps)
            if pitch_reference == PITCH_REFERENCE_SOUNDING:
                row["_sounding_ps"] = new_ps
            else:
                row["_written_ps"] = new_ps
            row["_sounding_ps"] = new_ps
            row["_pitch_overridden"] = True
            if register_low is not None and register_high is not None and not _in_band(
                new_ps, register_low, register_high
            ):
                warnings.append(warn_out_of_band_edit(nid, new_ps, float(register_low), float(register_high)))
        elif ov["kind"] == OVERRIDE_KIND_MANUAL_EXCLUDE:
            used = coerce_used_in_metrics(ov["new"])
            row["_excluded"] = not used
            if used:
                _mark_included(el, chord_index)
            else:
                _mark_excluded(el, chord_index)
        _refresh_row_derived(row, pitch_reference=pitch_reference, register_low=register_low, register_high=register_high)

    warnings.insert(0, warn_manual_overrides(len(normalized)))
    return rows, warnings


def prepare_score_for_analysis(
    score: stream.Stream,
    *,
    pitch_reference: str | None = None,
    pitch_overrides: list[dict[str, Any]] | None = None,
    register_low_ps: float | None = None,
    register_high_ps: float | None = None,
    repairs: list[dict[str, Any]] | None = None,
) -> PreparedScore:
    """
    After microtone repair: detect transposing parts, optional sounding conversion,
    then part- and note-level overrides. Tie policy is applied by the analyzer afterwards.
    """
    ref = normalize_pitch_reference(pitch_reference)
    transposing = detect_transposing_parts(score)
    warnings: list[str] = []
    if ref == PITCH_REFERENCE_WRITTEN and transposing:
        warnings.append(warn_written_with_transposing_parts(transposing))

    inventory_params = {
        "pitch_reference": ref,
        "register_low_ps": register_low_ps,
        "register_high_ps": register_high_ps,
        "repairs": repairs or [],
    }
    rows = build_pitch_inventory(score, inventory_params)
    working = convert_score_to_sounding(score) if ref == PITCH_REFERENCE_SOUNDING else score
    stamp_note_ids(working)
    applied = normalize_pitch_overrides(pitch_overrides)
    if applied:
        rows, ov_warnings = apply_pitch_overrides(
            working,
            rows,
            applied,
            pitch_reference=ref,
            register_low=register_low_ps,
            register_high=register_high_ps,
        )
        warnings.extend(ov_warnings)
    digest = pitch_inventory_digest(rows)
    return PreparedScore(
        score=working,
        pitch_reference=ref,
        inventory=rows,
        digest=digest,
        transposing_parts=transposing,
        pitch_overrides=applied,
        warnings=warnings,
    )


def public_inventory_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Drop private ``_`` keys for export / UI."""
    out: list[dict[str, Any]] = []
    for row in rows:
        pub = {k: v for k, v in row.items() if not str(k).startswith("_")}
        flags = pub.get("flags") or []
        if isinstance(flags, list):
            pub["flags"] = ",".join(flags)
        out.append(pub)
    return out


def write_pitch_inventory_csv(path: str | Path, rows: list[dict[str, Any]]) -> str:
    """Write the inspectable inventory table (public columns only)."""
    p = Path(path)
    public = public_inventory_rows(rows)
    with p.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=INVENTORY_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        for row in public:
            writer.writerow({k: row.get(k, "") for k in INVENTORY_COLUMNS})
    return str(p)
