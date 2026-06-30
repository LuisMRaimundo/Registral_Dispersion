"""Shared visual theme for publication-style registral figures."""

from __future__ import annotations

from typing import Any

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.axes import Axes
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.figure import Figure

# Gallery-style dark canvas
CANVAS_BG = "#0c0c10"
PANEL_BG = "#14141c"
PANEL_BG_LIGHT = "#faf9f7"
TEXT_PRIMARY = "#ece8e1"
TEXT_MUTED = "#9a9590"
TEXT_DARK = "#1c1917"
GRID_COLOR = "#2a2a36"
GRID_COLOR_LIGHT = "#d6d3d1"
ACCENT_GOLD = "#d4a853"
ACCENT_AMBER = "#e8b84a"
ACCENT_COPPER = "#b87333"
ACCENT_TEAL = "#3d8b8b"
ACCENT_VIOLET = "#9b7edc"
LINE_PAIRWISE = "#e8b84a"
LINE_SPAN = "#6eb5d9"
LINE_ENTROPY = "#9b7edc"

COLORMAP_REGISTRAL_EMBER = "registral_ember"
COLORMAP_INFERNO = "inferno"
COLORMAP_MAGMA = "magma"

_EMBER_STOPS: list[tuple[float, str]] = [
    (0.0, "#060608"),
    (0.06, "#0f1218"),
    (0.18, "#152238"),
    (0.32, "#1e4a52"),
    (0.48, "#3d6b5a"),
    (0.62, "#a06832"),
    (0.78, "#d4a853"),
    (0.90, "#f0dfa8"),
    (1.0, "#fff8eb"),
]

PLOTLY_EMBER_SCALE: list[list[float | str]] = [[pos, col] for pos, col in _EMBER_STOPS]

FONT_SERIF = "Georgia, 'Palatino Linotype', 'Times New Roman', serif"
FONT_SANS = "'Segoe UI', 'Helvetica Neue', Arial, sans-serif"


def register_matplotlib_colormaps() -> None:
    """Register custom colormaps once (safe to call repeatedly)."""
    if COLORMAP_REGISTRAL_EMBER not in plt.colormaps():
        plt.colormaps.register(
            LinearSegmentedColormap.from_list(COLORMAP_REGISTRAL_EMBER, _EMBER_STOPS),
            name=COLORMAP_REGISTRAL_EMBER,
        )


def resolve_plotly_colorscale(name: str) -> str | list[list[float | str]]:
    register_matplotlib_colormaps()
    key = str(name or COLORMAP_REGISTRAL_EMBER).strip().lower().replace("-", "_")
    if key in (COLORMAP_REGISTRAL_EMBER, "registral_ember", "ember"):
        return PLOTLY_EMBER_SCALE
    return name


def resolve_mpl_cmap(name: str):
    register_matplotlib_colormaps()
    key = str(name or COLORMAP_REGISTRAL_EMBER).strip().lower().replace("-", "_")
    if key in (COLORMAP_REGISTRAL_EMBER, "registral_ember", "ember"):
        return COLORMAP_REGISTRAL_EMBER
    return name


def crop_display_matrix(
    matrix: np.ndarray,
    pitch_midi: np.ndarray,
    *,
    padding_semitones: int = 4,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Crop rows to the active pitch band (plus padding) for clearer, more focused heatmaps.

    Display-only; does not alter exported raw matrices.
    """
    mat = np.asarray(matrix, dtype=float)
    mids = np.asarray(pitch_midi, dtype=int)
    if mat.size == 0 or mids.size == 0:
        return mat, mids
    active = np.any(mat > 0, axis=1)
    if not np.any(active):
        return mat, mids
    idx = np.flatnonzero(active)
    lo = max(0, int(idx[0]) - padding_semitones)
    hi = min(len(mids) - 1, int(idx[-1]) + padding_semitones)
    return mat[lo : hi + 1], mids[lo : hi + 1]


def _octave_c_pitches(m_min: int, m_max: int) -> list[int]:
    start = m_min - (m_min % 12)
    return [m for m in range(start, m_max + 1, 12) if m_min <= m <= m_max]


def style_mpl_heatmap(
    fig: Figure,
    ax: Axes,
    *,
    title: str,
    xlabel: str,
    ylabel: str,
    dark: bool = True,
) -> None:
    bg = CANVAS_BG if dark else PANEL_BG_LIGHT
    fg = TEXT_PRIMARY if dark else TEXT_DARK
    fig.patch.set_facecolor(bg)
    ax.set_facecolor(PANEL_BG if dark else "#ffffff")
    ax.set_title(title, fontsize=15, fontweight="500", color=fg, pad=14, fontfamily="serif")
    ax.set_xlabel(xlabel, fontsize=11, color=fg, labelpad=8)
    ax.set_ylabel(ylabel, fontsize=11, color=fg, labelpad=8)
    ax.tick_params(axis="both", colors=TEXT_MUTED if dark else "#57534e", labelsize=9)
    for spine in ax.spines.values():
        spine.set_visible(False)


def add_octave_guides_mpl(ax: Axes, m_min: int, m_max: int, *, dark: bool = True) -> None:
    color = "#ffffff" if dark else "#78716c"
    for m in _octave_c_pitches(m_min, m_max):
        ax.axhline(m - 0.5, color=color, alpha=0.07 if dark else 0.12, linewidth=0.6, zorder=0)


def style_mpl_colorbar(cbar, *, dark: bool = True, label: str = "") -> None:
    fg = TEXT_PRIMARY if dark else TEXT_DARK
    cbar.ax.yaxis.set_tick_params(color=TEXT_MUTED if dark else "#57534e", labelsize=8)
    cbar.outline.set_visible(False)
    if label:
        cbar.set_label(label, fontsize=9, color=fg, labelpad=10)
    plt.setp(plt.getp(cbar.ax.axes, "yticklabels"), color=TEXT_MUTED if dark else "#57534e")


def apply_plotly_heatmap_layout(
    fig: Any,
    *,
    title: str,
    xlabel: str,
    ylabel: str,
    colorbar_title: str,
    height: int = 520,
) -> Any:
    fig.update_layout(
        title=dict(
            text=f"<span style='font-family:{FONT_SERIF}'>{title}</span>",
            x=0.5,
            xanchor="center",
            font=dict(size=18, color=TEXT_PRIMARY),
        ),
        paper_bgcolor=CANVAS_BG,
        plot_bgcolor=PANEL_BG,
        font=dict(family=FONT_SANS, size=11, color=TEXT_MUTED),
        margin=dict(l=72, r=24, t=72, b=56),
        height=height,
        hoverlabel=dict(
            bgcolor="#1e1e28",
            bordercolor=ACCENT_GOLD,
            font=dict(family=FONT_SANS, size=11, color=TEXT_PRIMARY),
        ),
    )
    fig.update_xaxes(
        title_text=xlabel,
        gridcolor=GRID_COLOR,
        zeroline=False,
        linecolor=GRID_COLOR,
        tickfont=dict(color=TEXT_MUTED),
        title_font=dict(color=TEXT_PRIMARY, size=12),
    )
    fig.update_yaxes(
        title_text=ylabel,
        gridcolor=GRID_COLOR,
        zeroline=False,
        linecolor=GRID_COLOR,
        tickfont=dict(color=TEXT_MUTED),
        title_font=dict(color=TEXT_PRIMARY, size=12),
    )
    return fig


def apply_plotly_dispersion_layout(
    fig: Any,
    *,
    title: str,
    height: int = 420,
    secondary_y: bool = False,
) -> Any:
    fig.update_layout(
        title=dict(
            text=f"<span style='font-family:{FONT_SERIF}'>{title}</span>",
            x=0.5,
            xanchor="center",
            font=dict(size=17, color=TEXT_DARK),
        ),
        paper_bgcolor=PANEL_BG_LIGHT,
        plot_bgcolor="#ffffff",
        font=dict(family=FONT_SANS, size=11, color="#44403c"),
        hovermode="x unified",
        height=height,
        margin=dict(l=64, r=88 if secondary_y else 56, t=68, b=52),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.03,
            xanchor="right",
            x=1,
            bgcolor="rgba(255,255,255,0.85)",
            bordercolor="#e7e5e4",
            borderwidth=1,
            font=dict(size=10),
        ),
        hoverlabel=dict(bgcolor="#fff", bordercolor=ACCENT_GOLD, font=dict(size=11)),
    )
    fig.update_xaxes(
        showgrid=True,
        gridcolor="#ece9e4",
        zeroline=False,
        linecolor="#d6d3d1",
        title_font=dict(size=12),
    )
    fig.update_yaxes(
        showgrid=True,
        gridcolor="#ece9e4",
        zeroline=False,
        linecolor="#d6d3d1",
        title_font=dict(size=12),
    )
    return fig


GRADIO_THEME_CSS = """
.gradio-container {
    font-family: 'Segoe UI', 'Helvetica Neue', Arial, sans-serif !important;
    max-width: 1280px !important;
}
.hero-title {
    font-family: Georgia, 'Palatino Linotype', serif;
    font-size: 1.85rem;
    font-weight: 500;
    letter-spacing: 0.02em;
    color: #1c1917;
    margin-bottom: 0.25rem;
}
.hero-sub {
    color: #57534e;
    font-size: 0.95rem;
    line-height: 1.55;
    margin-bottom: 1rem;
}
"""
