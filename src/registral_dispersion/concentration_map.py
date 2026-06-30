"""
Symbolic **registral concentration map**: pitch–time heatmap of notational occupancy.

This module is **visualization-only**. It does not define or alter registral-dispersion metrics
(``registral_span``, ``mean_pairwise_registral_distance``, ``occupancy_entropy``).
Intensity is a **count of active notated pitch components** per time bin and semitone row
(MIDI pitch space), not audio energy, dynamics, or perceptual salience.
"""

from __future__ import annotations

import json
import math
from collections import Counter
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any, cast

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.axes import Axes
from matplotlib.figure import Figure
from music21 import chord as m21_chord
from music21 import note as m21_note
from music21 import stream

from registral_dispersion.sampling import (
    PITCH_SAMPLING_EVENT_INSTANCES,
    PITCH_SAMPLING_UNIQUE_PITCH_HEIGHTS,
    normalize_pitch_sampling_mode,
)
from registral_dispersion.score_io import parse_score
from registral_dispersion.visual_theme import (
    ACCENT_GOLD,
    CANVAS_BG,
    PANEL_BG,
    TEXT_MUTED,
    TEXT_PRIMARY,
    add_octave_guides_mpl,
    apply_plotly_heatmap_layout,
    crop_display_matrix,
    resolve_mpl_cmap,
    resolve_plotly_colorscale,
    style_mpl_colorbar,
    style_mpl_heatmap,
)

DISPLAY_NORMALIZATION_RAW = "raw_counts"
DISPLAY_NORMALIZATION_COLUMN = "column_normalized"
DISPLAY_NORMALIZATION_GLOBAL = "global_normalized"
DISPLAY_NORMALIZATION_LOG1P = "log1p_counts"

DISPLAY_NORMALIZATIONS = (
    DISPLAY_NORMALIZATION_RAW,
    DISPLAY_NORMALIZATION_LOG1P,
    DISPLAY_NORMALIZATION_COLUMN,
    DISPLAY_NORMALIZATION_GLOBAL,
)

DEFAULT_TIME_BIN_SIZE = 0.25
DEFAULT_CONCENTRATION_MODE = PITCH_SAMPLING_EVENT_INSTANCES
DEFAULT_DISPLAY_NORMALIZATION = DISPLAY_NORMALIZATION_LOG1P
DEFAULT_COLORMAP = "registral_ember"
DEFAULT_DPI = 300


def _package_version() -> str:
    try:
        return version("registral-dispersion")
    except PackageNotFoundError:
        return "unknown"


def _event_active_in_half_open_bin(e, t0: float, t1: float) -> bool:
    """Same overlap rule as registral analysis: onset < t_hi and offset > t_lo."""
    onset = float(e.offset)
    dur = float(e.quarterLength) if hasattr(e, "quarterLength") else 0.0
    return (onset < t1) and ((onset + dur) > t0)


def _raw_midi_components_in_bin(
    events: list,
    t0: float,
    t1: float,
    register_low: float,
    register_high: float,
) -> list[float]:
    """List MIDI ``ps`` values for in-register note/chord components active on ``[t0, t1)``."""
    out: list[float] = []
    for e in events:
        if not _event_active_in_half_open_bin(e, t0, t1):
            continue
        if isinstance(e, m21_note.Note):
            ps = float(e.pitch.ps)
            if register_low <= ps <= register_high:
                out.append(ps)
        elif isinstance(e, m21_chord.Chord):
            for p in e.pitches:
                ps = float(p.ps)
                if register_low <= ps <= register_high:
                    out.append(ps)
    return out


def _pitch_row_indices(register_low_ps: float, register_high_ps: float) -> tuple[np.ndarray, int, int]:
    """
    Integer MIDI rows from ``m_min`` to ``m_max`` inclusive, covering all semitones that can lie in
    ``[register_low, register_high]`` (inclusive on pitch class integers).
    """
    lo = float(min(register_low_ps, register_high_ps))
    hi = float(max(register_low_ps, register_high_ps))
    m_min = math.ceil(lo - 1e-9)
    m_max = math.floor(hi + 1e-9)
    if m_max < m_min:
        m_max = m_min
    mids = np.arange(m_min, m_max + 1, dtype=int)
    return mids, m_min, m_max


def _counts_per_integer_midi(
    raw: list[float],
    concentration_mode: str,
    m_min: int,
    m_max: int,
) -> np.ndarray:
    """Vector of length ``(m_max - m_min + 1)`` with counts per integer MIDI row."""
    n = m_max - m_min + 1
    counts = np.zeros(n, dtype=float)
    if not raw:
        return counts
    mode = normalize_pitch_sampling_mode(concentration_mode)
    if mode == PITCH_SAMPLING_UNIQUE_PITCH_HEIGHTS:
        seen = {round(ps) for ps in raw if m_min <= round(ps) <= m_max}
        for m in seen:
            counts[m - m_min] = 1.0
        return counts
    c: Counter[int] = Counter()
    for ps in raw:
        m = round(ps)
        if m_min <= m <= m_max:
            c[m] += 1
    for m, v in c.items():
        counts[m - m_min] = float(v)
    return counts


def normalize_display_normalization(value: str | None) -> str:
    """Return a supported display-normalization mode (default ``log1p_counts``)."""
    if value is None or str(value).strip() == "":
        return DEFAULT_DISPLAY_NORMALIZATION
    s = str(value).strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "log": DISPLAY_NORMALIZATION_LOG1P,
        "log1p": DISPLAY_NORMALIZATION_LOG1P,
        "raw": DISPLAY_NORMALIZATION_RAW,
        "column": DISPLAY_NORMALIZATION_COLUMN,
        "global": DISPLAY_NORMALIZATION_GLOBAL,
    }
    if s in aliases:
        return aliases[s]
    if s in DISPLAY_NORMALIZATIONS:
        return s
    return DEFAULT_DISPLAY_NORMALIZATION


def dispersion_overlay_from_results(
    results: dict[str, Any],
    *,
    use_normalized: bool = False,
) -> tuple[np.ndarray, np.ndarray | None, np.ndarray | None]:
    """
    Build ``(overlay_t, mean_pairwise, registral_span)`` from :meth:`RegistralDispersionAnalyzer.analyze_score`
    output for :func:`make_registral_concentration_map`.

    **Temporal alignment:** ``overlay_t`` is ``results['t']`` in quarterLength — window centers for
    ``fixed_window``, interval midpoints for ``event_boundaries``. The heatmap x-axis spans
    ``time_bin_edges[0]`` … ``time_bin_edges[-1]`` (half-open bin grid). Use the same score duration
    and prefer ``time_bin_size == time_step`` when overlaying fixed-window dispersion on a heatmap.
    """
    t = np.asarray(results["t"], dtype=float)
    if use_normalized:
        mp_key, sp_key = (
            "normalized_mean_pairwise_registral_distance",
            "normalized_registral_span",
        )
    else:
        mp_key, sp_key = "mean_pairwise_registral_distance", "registral_span"
    mp = results.get(mp_key)
    sp = results.get(sp_key)
    mean_pairwise = None if mp is None else np.asarray(mp, dtype=float)
    registral_span = None if sp is None else np.asarray(sp, dtype=float)
    return t, mean_pairwise, registral_span


def _apply_display_normalization(matrix: np.ndarray, how: str) -> tuple[np.ndarray, str]:
    """Return ``(display_matrix, colorbar_label_suffix)`` for visualization only."""
    m = np.asarray(matrix, dtype=float)
    h = normalize_display_normalization(how)
    if h == DISPLAY_NORMALIZATION_LOG1P:
        return np.log1p(m), " (log(1+count); accentuates populated cells)"
    if h == DISPLAY_NORMALIZATION_COLUMN:
        col_max = np.max(m, axis=0, keepdims=True)
        col_max = np.where(col_max > 0, col_max, 1.0)
        out = m / col_max
        return out, " (column max = 1; display only)"
    if h == DISPLAY_NORMALIZATION_GLOBAL:
        g = float(np.max(m)) if m.size else 0.0
        denom = g if g > 0 else 1.0
        return m / denom, " (global max = 1; display only)"
    return m.copy(), " (symbolic component counts)"


def build_registral_concentration_matrix(
    score: str | stream.Stream,
    register_low_ps: float,
    register_high_ps: float,
    *,
    time_bin_size: float = DEFAULT_TIME_BIN_SIZE,
    concentration_mode: str = DEFAULT_CONCENTRATION_MODE,
) -> dict[str, Any]:
    """
    Build ``pitch_rows × time_bins`` matrix of symbolic occupancy counts.

    * **Rows:** integer MIDI pitches from ``ceil(register_low)`` to ``floor(register_high)`` (inclusive).
    * **Columns:** half-open time bins ``[k·Δt, (k+1)·Δt)`` from score start to ``ceil(duration/Δt)·Δt``.
    * **Cell value:** number of active **notated** components at that MIDI height in that bin
      (``event_instances``: separate counts per notehead/chord tone; ``unique_pitch_heights``: at most 1
      per distinct MIDI integer per bin).

    Overlap rule matches dispersion analysis: ``onset < bin_end`` and ``onset + quarterLength > bin_start``.
    """
    if time_bin_size <= 0:
        raise ValueError("time_bin_size must be positive.")
    sc = parse_score(score) if isinstance(score, str) else score
    flat = sc.flatten()
    events = list(flat.notes)
    end_time = float(max(sc.highestTime, flat.highestTime))
    reg_lo = float(min(register_low_ps, register_high_ps))
    reg_hi = float(max(register_low_ps, register_high_ps))
    if reg_hi <= reg_lo:
        raise ValueError("Register band must have strictly positive width.")

    mids, m_min, m_max = _pitch_row_indices(reg_lo, reg_hi)
    n_pitch = len(mids)
    n_bins = max(1, math.ceil(end_time / time_bin_size))
    edges = (np.arange(n_bins + 1, dtype=float)) * float(time_bin_size)
    mat = np.zeros((n_pitch, n_bins), dtype=float)
    mode = normalize_pitch_sampling_mode(concentration_mode)

    for j in range(n_bins):
        t0 = float(edges[j])
        t1 = float(edges[j + 1])
        raw = _raw_midi_components_in_bin(events, t0, t1, reg_lo, reg_hi)
        mat[:, j] = _counts_per_integer_midi(raw, mode, m_min, m_max)

    meta = {
        "score_path": str(score) if isinstance(score, str) else None,
        "register_low_midi_ps": reg_lo,
        "register_high_midi_ps": reg_hi,
        "time_bin_size": float(time_bin_size),
        "concentration_mode": mode,
        "display_normalization": None,
        "package_version": _package_version(),
        "overlap_rule": "onset < bin_end and onset + quarterLength > bin_start (half-open bins)",
        "description": (
            "Symbolic notational occupancy counts per semitone row and time bin; "
            "not audio, dynamics, or registral-dispersion metrics."
        ),
    }
    return {
        "matrix": mat,
        "pitch_midi": mids.astype(int),
        "time_bin_edges": edges,
        "time_bin_centers": 0.5 * (edges[:-1] + edges[1:]),
        "register_low_midi_ps": reg_lo,
        "register_high_midi_ps": reg_hi,
        "metadata": meta,
    }


def write_concentration_matrix_csv(path: str | Path, bundle: dict[str, Any]) -> str:
    """Write matrix CSV: rows = MIDI pitch, columns = time bin start (quarterLength); leading ``#`` metadata."""
    p = Path(path)
    mat = np.asarray(bundle["matrix"], dtype=float)
    mids = np.asarray(bundle["pitch_midi"], dtype=int)
    edges = np.asarray(bundle["time_bin_edges"], dtype=float)
    meta = dict(bundle.get("metadata") or {})
    lines = [
        "# registral_dispersion: symbolic registral concentration matrix (not dispersion metrics).",
        f"# score_path: {meta.get('score_path', '')}",
        f"# register_low_midi_ps: {meta.get('register_low_midi_ps')}",
        f"# register_high_midi_ps: {meta.get('register_high_midi_ps')}",
        f"# time_bin_size: {meta.get('time_bin_size')}",
        f"# concentration_mode: {meta.get('concentration_mode')}",
        f"# package_version: {meta.get('package_version')}",
    ]
    header = "pitch_midi," + ",".join(f"t_{edges[j]:.12g}" for j in range(mat.shape[1]))
    lines.append(header)
    for i, m in enumerate(mids):
        row = [str(int(m))] + [f"{mat[i, j]:.12g}" for j in range(mat.shape[1])]
        lines.append(",".join(row))
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(p)


def write_concentration_matrix_npz(path: str | Path, bundle: dict[str, Any]) -> str:
    """Save ``matrix``, ``pitch_midi``, ``time_bin_edges``, and ``metadata_json`` compressed."""
    p = Path(path)
    meta = json.dumps(bundle.get("metadata") or {}, indent=2, ensure_ascii=False)
    np.savez_compressed(
        p,
        matrix=np.asarray(bundle["matrix"], dtype=float),
        pitch_midi=np.asarray(bundle["pitch_midi"], dtype=int),
        time_bin_edges=np.asarray(bundle["time_bin_edges"], dtype=float),
        metadata_json=np.asarray(meta),
    )
    return str(p)


def make_registral_concentration_map(
    bundle: dict[str, Any],
    *,
    title: str | None = "Registral concentration",
    display_normalization: str = DEFAULT_DISPLAY_NORMALIZATION,
    colormap_name: str = DEFAULT_COLORMAP,
    dpi: int = DEFAULT_DPI,
    show_note_names_y: bool | None = None,
    crop_to_active_band: bool = True,
    overlay_t: np.ndarray | None = None,
    overlay_mean_pairwise: np.ndarray | None = None,
    overlay_registral_span: np.ndarray | None = None,
    figsize: tuple[float, float] | None = None,
) -> Figure:
    """
    Publication-style Matplotlib heatmap: dark gallery canvas, ember palette, octave guides.

    **Dispersion overlay (optional):** pass ``overlay_t`` in quarterLength together with semitone (or
    normalized) series of equal length. Time is **not** resampled: points plot at ``overlay_t`` on the
    heatmap x-axis ``[time_bin_edges[0], time_bin_edges[-1]]``. Use
    :func:`dispersion_overlay_from_results` to extract arrays from analysis output. Mismatched lengths
    skip the affected series; the shared x-axis is clipped to the heatmap extent after plotting.
    """
    mat = np.asarray(bundle["matrix"], dtype=float)
    mids = np.asarray(bundle["pitch_midi"], dtype=int)
    edges = np.asarray(bundle["time_bin_edges"], dtype=float)
    if crop_to_active_band:
        mat, mids = crop_display_matrix(mat, mids)
    disp, cbar_suffix = _apply_display_normalization(mat, display_normalization)
    if show_note_names_y is None:
        show_note_names_y = len(mids) <= 48

    n_rows = max(4, len(mids))
    if figsize is None:
        h = float(np.clip(0.14 * n_rows + 2.8, 5.0, 14.0))
        figsize = (13.5, h)

    fig, ax = plt.subplots(figsize=figsize, facecolor=CANVAS_BG)
    assert isinstance(ax, Axes)
    m_min, m_max = int(mids[0]), int(mids[-1])
    add_octave_guides_mpl(ax, m_min, m_max, dark=True)

    extent = (float(edges[0]), float(edges[-1]), float(mids[0]) - 0.5, float(mids[-1]) + 0.5)
    cmap = resolve_mpl_cmap(colormap_name)
    im = ax.imshow(
        disp,
        origin="lower",
        aspect="auto",
        extent=extent,
        interpolation="bilinear",
        cmap=cmap,
        vmin=0.0,
        vmax=None,
    )
    style_mpl_heatmap(
        fig,
        ax,
        title=str(title or "Registral concentration"),
        xlabel="Time (quarterLength)",
        ylabel="Register",
        dark=True,
    )
    cbar = fig.colorbar(im, ax=ax, fraction=0.025, pad=0.02)
    style_mpl_colorbar(
        cbar,
        dark=True,
        label="Notational density" + cbar_suffix,
    )

    if show_note_names_y and len(mids) > 0:
        try:
            from music21.pitch import Pitch

            tick_step = max(1, len(mids) // 20)
            ticks = mids[::tick_step]
            labels = [Pitch(midi=int(m)).nameWithOctave for m in ticks]
            ax.set_yticks(ticks.astype(float))
            ax.set_yticklabels(labels, fontsize=8, color=TEXT_MUTED)
        except Exception:
            ax.set_yticks(mids[:: max(1, len(mids) // 20)])

    has_overlay = (
        overlay_t is not None
        and overlay_t.size > 0
        and (
            (overlay_mean_pairwise is not None and overlay_mean_pairwise.size > 0)
            or (overlay_registral_span is not None and overlay_registral_span.size > 0)
        )
    )
    if has_overlay:
        assert overlay_t is not None
        ot = np.asarray(overlay_t, dtype=float)
        x_lo, x_hi = float(edges[0]), float(edges[-1])
        ax2 = cast(Axes, ax.twinx())
        plotted = False

        def _plot_overlay(y: np.ndarray, *, color: str, linestyle: str, label: str, lw: float) -> None:
            nonlocal plotted
            if y.size != ot.size:
                return
            mask = np.isfinite(y) & np.isfinite(ot)
            if not np.any(mask):
                return
            ax2.plot(
                ot[mask],
                y[mask],
                color=color,
                linestyle=linestyle,
                linewidth=lw,
                alpha=0.9 if linestyle == "-" else 0.85,
                label=label,
            )
            plotted = True

        if overlay_mean_pairwise is not None:
            _plot_overlay(
                np.asarray(overlay_mean_pairwise, dtype=float),
                color=ACCENT_GOLD,
                linestyle="-",
                label="Mean pairwise distance",
                lw=1.6,
            )
        if overlay_registral_span is not None:
            _plot_overlay(
                np.asarray(overlay_registral_span, dtype=float),
                color="#6eb5d9",
                linestyle="--",
                label="Registral span",
                lw=1.4,
            )
        if plotted:
            ax.set_xlim(x_lo, x_hi)
            ax2.set_xlim(x_lo, x_hi)
            ax2.set_ylabel("Dispersion (semitones)", fontsize=9, color=TEXT_MUTED)
            ax2.tick_params(axis="y", labelsize=8, colors=TEXT_MUTED)
            ax2.spines[:].set_visible(False)
            ax2.legend(loc="upper right", fontsize=7, framealpha=0.15, facecolor=PANEL_BG, edgecolor="none")

    fig.tight_layout(pad=1.2)
    return fig


def make_registral_concentration_map_plotly(
    bundle: dict[str, Any],
    *,
    title: str | None = "Registral concentration",
    display_normalization: str = DEFAULT_DISPLAY_NORMALIZATION,
    colorscale_name: str = DEFAULT_COLORMAP,
    crop_to_active_band: bool = True,
) -> Any:
    """Interactive Plotly heatmap with gallery-style dark theme and custom ember palette."""
    import plotly.graph_objects as go

    mat = np.asarray(bundle["matrix"], dtype=float)
    mids = np.asarray(bundle["pitch_midi"], dtype=int)
    edges = np.asarray(bundle["time_bin_edges"], dtype=float)
    if crop_to_active_band:
        mat, mids = crop_display_matrix(mat, mids)
    centers = 0.5 * (edges[:-1] + edges[1:])
    disp, cbar_suffix = _apply_display_normalization(mat, display_normalization)
    colorscale = resolve_plotly_colorscale(colorscale_name)
    hover_midi = np.repeat(mids[:, None], disp.shape[1], axis=1)
    try:
        from music21.pitch import Pitch

        hover_names = np.vectorize(lambda m: Pitch(midi=int(m)).nameWithOctave)(hover_midi)
    except Exception:
        hover_names = hover_midi.astype(str)

    def _hover_cell(i: int, j: int) -> str:
        lo_b, hi_b = float(edges[j]), float(edges[j + 1])
        midi = int(hover_midi[i, j])
        nm = str(hover_names[i, j])
        raw = float(mat[i, j])
        return f"<b>{nm}</b><br>t ∈ [{lo_b:.2f}, {hi_b:.2f}) qL<br>MIDI {midi}<br>Activity: {raw:.0f} component(s)"

    z_text = np.array(
        [[_hover_cell(i, j) for j in range(disp.shape[1])] for i in range(disp.shape[0])],
        dtype=object,
    )

    y_labels: list[str] | None = None
    try:
        from music21.pitch import Pitch

        y_labels = [Pitch(midi=int(m)).nameWithOctave for m in mids]
    except Exception:
        pass

    n_rows = max(4, len(mids))
    height = int(np.clip(80 * n_rows + 180, 420, 900))

    fig = go.Figure(
        data=go.Heatmap(
            z=disp,
            x=centers,
            y=mids.astype(float),
            colorscale=colorscale,
            hovertext=z_text,
            hoverinfo="text",
            zmin=0.0,
            xgap=0,
            ygap=0,
            colorbar=dict(
                title=dict(text="Density" + cbar_suffix, side="right"),
                thickness=14,
                len=0.75,
            ),
        )
    )
    if y_labels is not None and len(y_labels) == len(mids):
        fig.update_yaxes(tickmode="array", tickvals=mids.astype(float), ticktext=y_labels)

    # Octave guides (C-naturals)
    m_min, m_max = int(mids[0]), int(mids[-1])
    shapes = []
    start = m_min - (m_min % 12)
    for m in range(start, m_max + 1, 12):
        if m_min <= m <= m_max:
            shapes.append(
                dict(
                    type="line",
                    xref="paper",
                    x0=0,
                    x1=1,
                    yref="y",
                    y0=m - 0.5,
                    y1=m - 0.5,
                    line=dict(color="rgba(255,255,255,0.06)", width=1),
                    layer="below",
                )
            )
    fig.update_layout(shapes=shapes)
    fig.update_traces(
        colorbar=dict(
            title=dict(text="Density" + cbar_suffix, side="right", font=dict(color=TEXT_PRIMARY, size=11)),
            tickfont=dict(color=TEXT_MUTED, size=9),
            outlinewidth=0,
            thickness=14,
            len=0.75,
        )
    )

    apply_plotly_heatmap_layout(
        fig,
        title=str(title or "Registral concentration"),
        xlabel="Time (quarterLength)",
        ylabel="Register",
        colorbar_title="Density" + cbar_suffix,
        height=height,
    )
    return fig


def save_registral_concentration_figure(
    fig: Figure,
    out_path: str | Path,
    *,
    dpi: int = DEFAULT_DPI,
) -> str:
    """Save Matplotlib figure to ``.png`` or ``.svg`` (by extension)."""
    p = Path(out_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    suf = p.suffix.lower()
    if suf == ".svg":
        fig.savefig(p, dpi=dpi, bbox_inches="tight", facecolor=CANVAS_BG, edgecolor="none")
    else:
        fig.savefig(p, dpi=dpi, bbox_inches="tight", facecolor=CANVAS_BG, edgecolor="none")
    return str(p)


def write_registral_concentration_plotly_html(fig: Any, out_path: str | Path) -> str:
    p = Path(out_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    fig.write_html(str(p), include_plotlyjs="cdn")
    return str(p)


def run_concentration_map_to_files(
    score_path: str,
    out_image: str | Path,
    register_low: str | float,
    register_high: str | float,
    *,
    time_bin_size: float = DEFAULT_TIME_BIN_SIZE,
    concentration_mode: str = DEFAULT_CONCENTRATION_MODE,
    display_normalization: str = DEFAULT_DISPLAY_NORMALIZATION,
    colormap_name: str = DEFAULT_COLORMAP,
    dpi: int = DEFAULT_DPI,
    matrix_csv: str | Path | None = None,
    matrix_npz: str | Path | None = None,
    title: str | None = "Registral concentration map",
) -> dict[str, Any]:
    """
    High-level entry: parse score (with package validation), build matrix, write image/HTML and optional matrix exports.

    ``register_low`` / ``register_high`` accept note names or numeric MIDI ``ps`` (same convention as analysis).
    """
    from registral_dispersion.pitch_utils import note_name_to_midi_ps

    def _reg(v: str | float) -> float:
        if isinstance(v, int | float):
            return float(v)
        return float(note_name_to_midi_ps(str(v).strip()))

    rlo = _reg(register_low)
    rhi = _reg(register_high)
    bundle = build_registral_concentration_matrix(
        score_path,
        rlo,
        rhi,
        time_bin_size=time_bin_size,
        concentration_mode=concentration_mode,
    )
    bundle["metadata"]["score_path"] = str(score_path)
    bundle["metadata"]["display_normalization"] = normalize_display_normalization(display_normalization)

    out_p = Path(out_image)
    written: dict[str, Any] = {"bundle": bundle, "outputs": []}
    if out_p.suffix.lower() == ".html":
        pfig = make_registral_concentration_map_plotly(
            bundle,
            title=title,
            display_normalization=display_normalization,
            colorscale_name=colormap_name,
        )
        write_registral_concentration_plotly_html(pfig, out_p)
        written["outputs"].append(str(out_p))
    else:
        fig = make_registral_concentration_map(
            bundle,
            title=title,
            display_normalization=display_normalization,
            colormap_name=colormap_name,
            dpi=dpi,
        )
        save_registral_concentration_figure(fig, out_p, dpi=dpi)
        plt.close(fig)
        written["outputs"].append(str(out_p))

    if matrix_csv:
        written["outputs"].append(write_concentration_matrix_csv(matrix_csv, bundle))
    if matrix_npz:
        written["outputs"].append(write_concentration_matrix_npz(matrix_npz, bundle))
    return written
