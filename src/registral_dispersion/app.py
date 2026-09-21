"""Gradio UI: registral dispersion (primary) with optional occupancy entropy panel."""

from __future__ import annotations

import logging
import warnings

import gradio as gr
import matplotlib.pyplot as plt
import numpy as np

from registral_dispersion.analysis_presets import (
    ANALYSIS_PRESETS,
    PRESET_MOVING_FRAGMENT,
    apply_analysis_preset,
    preset_guidance_text,
)
from registral_dispersion.concentration_map import (
    DEFAULT_COLORMAP,
    DEFAULT_CONCENTRATION_MODE,
    DEFAULT_DISPLAY_NORMALIZATION,
    DEFAULT_TIME_BIN_SIZE,
    DISPLAY_NORMALIZATION_COLUMN,
    DISPLAY_NORMALIZATION_GLOBAL,
    DISPLAY_NORMALIZATION_LOG1P,
    DISPLAY_NORMALIZATION_RAW,
    build_registral_concentration_matrix,
    make_registral_concentration_map,
    make_registral_concentration_map_plotly,
    normalize_display_normalization,
    save_registral_concentration_figure,
    write_concentration_matrix_csv,
)
from registral_dispersion.json_export import (
    build_registral_dispersion_export,
    write_json_export,
    write_registral_dispersion_csv,
)
from registral_dispersion.metric_documentation import CANONICAL_TOOL_NAME
from registral_dispersion.observation import (
    OBSERVATION_MODE_EVENT_BOUNDARIES,
    OBSERVATION_MODE_FIXED_WINDOW,
)
from registral_dispersion.output_paths import cleanup_stale_exports, new_export_path
from registral_dispersion.pitch_utils import (
    REGISTER_PRESET_FULL,
    REGISTER_PRESETS,
    note_name_to_midi_ps,
    resolve_register_preset,
)
from registral_dispersion.plotting import make_dispersion_figure, make_dispersion_figure_plotly
from registral_dispersion.profiles import (
    ANALYSIS_PROFILE_COMPONENT_WEIGHTED,
    ANALYSIS_PROFILE_OCCUPIED_SPACE,
    DEFAULT_ANALYSIS_PROFILE,
    normalize_analysis_profile,
)
from registral_dispersion.sampling import PITCH_SAMPLING_MODES
from registral_dispersion.microtone_repair import DEFAULT_MICROTONEREPAIR
from registral_dispersion.pitch_inventory import INVENTORY_COLUMNS, write_pitch_inventory_csv
from registral_dispersion.pitch_overrides import (
    overrides_from_inventory_edits,
    save_pitch_overrides,
    sidecar_path_for_score,
)
from registral_dispersion.pitch_reference import DEFAULT_PITCH_REFERENCE
from registral_dispersion.service import inspect_score_pitches, run_registral_dispersion_analysis
from registral_dispersion.ui_validation import coerce_float, validate_uploaded_score
from registral_dispersion.visual_theme import GRADIO_THEME_CSS

_LOG = logging.getLogger(__name__)

_PITCH_OVERRIDE_FOLLOW_PROFILE = "(from profile)"


def _export_plotly_figure_static(fig, stem: str) -> str:
    png_path = new_export_path(stem, ".png")
    try:
        fig.write_image(str(png_path))
        return str(png_path)
    except Exception as exc:  # pragma: no cover - environment-dependent
        _LOG.warning("Plotly write_image failed (%s); falling back to HTML export.", exc)
        warnings.warn(
            "Plot static PNG export failed (install compatible plotly+kaleido, see pyproject.toml). "
            "Saved interactive HTML instead.",
            UserWarning,
            stacklevel=2,
        )
        html_path = new_export_path(stem, ".html")
        fig.write_html(str(html_path), include_plotlyjs="cdn", full_html=True)
        return str(html_path)


def _render_concentration_figure(
    score_path: str,
    register_low: str,
    register_high: str,
    *,
    time_bin_size: float,
    concentration_mode: str = DEFAULT_CONCENTRATION_MODE,
    display_normalization: str = DEFAULT_DISPLAY_NORMALIZATION,
    colormap_name: str = DEFAULT_COLORMAP,
    interactive_plot: bool = True,
    microtone_repair: str = DEFAULT_MICROTONEREPAIR,
):
    """Build concentration matrix + figure; return (fig, bundle, plot_export_path)."""
    rlo = _parse_register_limit(register_low)
    rhi = _parse_register_limit(register_high)
    dt = float(time_bin_size)
    if dt <= 0:
        raise gr.Error("Time bin size must be > 0.")
    disp_norm = normalize_display_normalization(display_normalization)
    cmap = str(colormap_name or DEFAULT_COLORMAP).strip() or DEFAULT_COLORMAP
    mode = str(concentration_mode or DEFAULT_CONCENTRATION_MODE).strip()
    try:
        bundle = build_registral_concentration_matrix(
            score_path,
            rlo,
            rhi,
            time_bin_size=dt,
            concentration_mode=mode,
            microtone_repair=microtone_repair,
        )
    except ValueError as exc:
        raise gr.Error(str(exc)) from exc
    bundle["metadata"]["score_path"] = str(score_path)
    bundle["metadata"]["display_normalization"] = disp_norm
    title = f"Registral concentration · [{register_low}, {register_high}]"
    if interactive_plot:
        fig = make_registral_concentration_map_plotly(
            bundle,
            title=title,
            display_normalization=disp_norm,
            colorscale_name=cmap,
        )
        plot_path = _export_plotly_figure_static(fig, "concentration_plot_")
    else:
        fig = make_registral_concentration_map(
            bundle,
            title=title,
            display_normalization=disp_norm,
            colormap_name=cmap,
        )
        plot_path = new_export_path("concentration_plot_", ".png")
        save_registral_concentration_figure(fig, plot_path)
        plt.close(fig)
    return fig, bundle, plot_path


def _records_from_df(df) -> list[dict]:
    if df is None:
        return []
    if hasattr(df, "to_dict"):
        return list(df.to_dict(orient="records"))
    if isinstance(df, list):
        return [dict(r) for r in df if isinstance(r, dict)]
    return []


def _parts_table_from_inventory(rows: list[dict]) -> list[dict]:
    seen: dict[object, dict] = {}
    for row in rows:
        nid = str(row.get("note_id") or "")
        try:
            part_index = int(str(row.get("_part_index", nid.split(":")[0] if nid else 0)))
        except (TypeError, ValueError):
            part_index = 0
        key = (part_index, row.get("part"), row.get("instrument"))
        if key in seen:
            continue
        seen[key] = {
            "part_index": part_index,
            "part": row.get("part") or "",
            "instrument": row.get("instrument") or "",
            "extra_semitones": 0.0,
        }
    return list(seen.values())


def load_inspect_ui(
    file_obj=None,
    register_low=None,
    register_high=None,
    pitch_reference=None,
    microtone_repair=None,
):
    """Step 1: parse the score and show the editable pitch inventory."""
    score_path = validate_uploaded_score(file_obj)
    if not register_low or not str(register_low).strip():
        raise gr.Error("Enter a lower register limit (e.g. A1 or MIDI number).")
    if not register_high or not str(register_high).strip():
        raise gr.Error("Enter an upper register limit (e.g. E7 or MIDI number).")
    params = {
        "register_low": str(register_low).strip(),
        "register_high": str(register_high).strip(),
        "pitch_reference": (
            str(pitch_reference).strip()
            if pitch_reference not in (None, "")
            else DEFAULT_PITCH_REFERENCE
        ),
        "microtone_repair": (
            str(microtone_repair).strip()
            if microtone_repair not in (None, "")
            else DEFAULT_MICROTONEREPAIR
        ),
    }
    out = inspect_score_pitches(score_path, params)
    if out.get("error"):
        raise gr.Error(out["error"])
    table = out.get("pitch_inventory") or []
    parts = _parts_table_from_inventory(out.get("pitch_inventory_raw") or table)
    warnings = "\n".join(out.get("warnings") or []) or "No warnings."
    digest = out.get("digest_line") or ""
    return table, digest, parts, warnings, table


def run_dispersion_ui(
    progress=gr.Progress(),
    file_obj=None,
    register_low=None,
    register_high=None,
    time_step=None,
    window_size=None,
    analysis_profile=None,
    observation_mode=None,
    pitch_sampling_override=None,
    microtone_repair=None,
    pitch_reference=None,
    inventory_df=None,
    part_transpose_df=None,
    inventory_original=None,
    interactive_plot=None,
    show_registral_span=None,
    show_occupancy_entropy=None,
    plot_normalized_y=None,
    show_heatmap=None,
    heatmap_mode=None,
    heatmap_normalization=None,
    heatmap_colormap=None,
):
    """Compute registral dispersion + concentration heatmap; export CSV/JSON."""
    progress_callback = lambda frac, desc: progress(frac, desc=desc) if progress else None
    score_path = validate_uploaded_score(file_obj)
    if not register_low or not str(register_low).strip():
        raise gr.Error("Enter a lower register limit (e.g. A1 or MIDI number).")
    if not register_high or not str(register_high).strip():
        raise gr.Error("Enter an upper register limit (e.g. E7 or MIDI number).")
    time_step = coerce_float(time_step, 0.25)
    window_size = coerce_float(window_size, 4.0)
    if time_step <= 0 or window_size <= 0:
        raise gr.Error("Time step and window size must be > 0.")
    ap = normalize_analysis_profile(
        analysis_profile if analysis_profile not in (None, "") else DEFAULT_ANALYSIS_PROFILE
    )
    obs = str(observation_mode).strip() if observation_mode not in (None, "") else OBSERVATION_MODE_FIXED_WINDOW
    params: dict = {
        "time_step": time_step,
        "window_size": window_size,
        "register_low": str(register_low).strip(),
        "register_high": str(register_high).strip(),
        "analysis_profile": ap,
        "observation_mode": obs,
        "microtone_repair": (
            str(microtone_repair).strip()
            if microtone_repair not in (None, "")
            else DEFAULT_MICROTONEREPAIR
        ),
        "pitch_reference": (
            str(pitch_reference).strip()
            if pitch_reference not in (None, "")
            else DEFAULT_PITCH_REFERENCE
        ),
    }
    original_rows = _records_from_df(inventory_original)
    edited_rows = _records_from_df(inventory_df)
    part_rows = _records_from_df(part_transpose_df)
    if original_rows and edited_rows:
        try:
            params["pitch_overrides"] = overrides_from_inventory_edits(
                original_rows, edited_rows, part_rows
            )
        except ValueError as exc:
            raise gr.Error(str(exc)) from exc
    ovr = pitch_sampling_override if pitch_sampling_override is not None else _PITCH_OVERRIDE_FOLLOW_PROFILE
    ovr_s = str(ovr).strip()
    if ovr_s and ovr_s != _PITCH_OVERRIDE_FOLLOW_PROFILE and ovr_s in PITCH_SAMPLING_MODES:
        params["pitch_sampling_mode"] = ovr_s
    out = run_registral_dispersion_analysis(score_path, params, progress_callback=progress_callback)
    if out.get("error"):
        raise gr.Error(out["error"])
    results = out["results"]
    summary = out["summary"]
    rp = out["params"]
    interactive_plot = True if interactive_plot is None else bool(interactive_plot)
    show_span = bool(show_registral_span)
    show_ent = bool(show_occupancy_entropy)
    y_scale = "normalized" if bool(plot_normalized_y) else "raw"
    an = out["analyzer"]
    obs_l = str(rp.get("observation_mode") or OBSERVATION_MODE_FIXED_WINDOW)
    if obs_l == OBSERVATION_MODE_EVENT_BOUNDARIES:
        title = f"Registral dispersion — [{register_low}, {register_high}], event_boundaries"
    else:
        title = f"Registral dispersion — [{register_low}, {register_high}], window={window_size}"
    if interactive_plot:
        fig = make_dispersion_figure_plotly(
            results,
            title=title,
            show_registral_span=show_span,
            show_occupancy_entropy=show_ent,
            y_scale=y_scale,
        )
        plot_path = _export_plotly_figure_static(fig, "dispersion_plot_")
    else:
        fig = make_dispersion_figure(
            results,
            title=title,
            show_registral_span=show_span,
            show_occupancy_entropy=show_ent,
            y_scale=y_scale,
        )
        plot_path = new_export_path("dispersion_plot_", ".png")
        fig.savefig(plot_path, dpi=200)
        plt.close(fig)
    csv_path = new_export_path("dispersion_", ".csv")
    write_registral_dispersion_csv(
        csv_path,
        results,
        pitch_sampling_mode=rp.get("pitch_sampling_mode"),
        analysis_profile=rp.get("analysis_profile"),
        pitch_sampling_source=rp.get("pitch_sampling_source"),
        observation_mode=rp.get("observation_mode"),
        register_low_midi=float(an.register_low),
        register_high_midi=float(an.register_high),
        register_width_semitones=float(an.register_width_semitones),
        microtone_repair=rp.get("microtone_repair"),
        pitch_reference=rp.get("pitch_reference"),
    )
    json_path = new_export_path("dispersion_data_", ".json")
    write_json_export(json_path, build_registral_dispersion_export(score_path, rp, out))
    inventory_csv_path = new_export_path("pitch_inventory_", ".csv")
    write_pitch_inventory_csv(inventory_csv_path, out.get("pitch_inventory") or [])
    overrides_json_path = None
    applied = out.get("pitch_overrides") or []
    if applied:
        overrides_json_path = new_export_path("pitch_overrides_", ".json")
        save_pitch_overrides(overrides_json_path, applied)
        try:
            save_pitch_overrides(sidecar_path_for_score(score_path), applied)
        except OSError:
            pass

    heatmap_fig = None
    heatmap_plot_path = None
    heat_matrix_path = None
    heat_summary = ""
    if show_heatmap is None or bool(show_heatmap):
        if progress_callback:
            progress_callback(0.85, "Building concentration heatmap")
        heatmap_fig, heat_bundle, heatmap_plot_path = _render_concentration_figure(
            score_path,
            str(register_low).strip(),
            str(register_high).strip(),
            time_bin_size=time_step,
            concentration_mode=str(heatmap_mode or DEFAULT_CONCENTRATION_MODE),
            display_normalization=str(heatmap_normalization or DEFAULT_DISPLAY_NORMALIZATION),
            colormap_name=str(heatmap_colormap or DEFAULT_COLORMAP),
            interactive_plot=interactive_plot,
            microtone_repair=str(rp.get("microtone_repair") or DEFAULT_MICROTONEREPAIR),
        )
        heat_matrix_path = new_export_path("concentration_matrix_", ".csv")
        write_concentration_matrix_csv(heat_matrix_path, heat_bundle)
        mat = np.asarray(heat_bundle["matrix"], dtype=float)
        heat_summary = (
            f"\n\n--- Concentration heatmap ---\n"
            f"Pitch rows: {mat.shape[0]}, time bins: {mat.shape[1]} (Δt = {time_step} qL). "
            f"Peak cell count: {float(np.max(mat)) if mat.size else 0:.0f}. "
            "Warmer/brighter = more notated activity at that pitch and time."
        )

    if progress_callback:
        progress_callback(1.0, "Done")
    return (
        fig,
        heatmap_fig,
        summary + heat_summary,
        csv_path,
        plot_path,
        json_path,
        heatmap_plot_path,
        heat_matrix_path,
        inventory_csv_path,
        overrides_json_path,
    )


def apply_register_preset(preset_label: str | None):
    """Update low/high textboxes when the user picks a named register band."""
    pair = resolve_register_preset(preset_label)
    if pair is None:
        return gr.update(), gr.update()
    lo, hi = pair
    return lo, hi


def _parse_register_limit(value: str | None) -> float:
    if value is None or not str(value).strip():
        raise gr.Error("Enter a register limit (e.g. A1 or MIDI number).")
    s = str(value).strip()
    try:
        return float(s)
    except ValueError:
        return float(note_name_to_midi_ps(s))


def run_concentration_ui(
    progress=gr.Progress(),
    file_obj=None,
    register_low=None,
    register_high=None,
    time_bin_size=None,
    concentration_mode=None,
    display_normalization=None,
    colormap_name=None,
    interactive_plot=None,
):
    """Heatmap-only run (advanced options)."""
    progress_callback = lambda frac, desc: progress(frac, desc=desc) if progress else None
    if progress_callback:
        progress_callback(0.05, "Loading score")
    score_path = validate_uploaded_score(file_obj)
    dt = coerce_float(time_bin_size, DEFAULT_TIME_BIN_SIZE)
    mode = str(concentration_mode or DEFAULT_CONCENTRATION_MODE).strip()
    disp_norm = normalize_display_normalization(display_normalization or DEFAULT_DISPLAY_NORMALIZATION)
    cmap = str(colormap_name or DEFAULT_COLORMAP).strip() or DEFAULT_COLORMAP
    interactive_plot = True if interactive_plot is None else bool(interactive_plot)

    if progress_callback:
        progress_callback(0.35, "Building concentration matrix")
    fig, bundle, plot_path = _render_concentration_figure(
        score_path,
        str(register_low).strip(),
        str(register_high).strip(),
        time_bin_size=dt,
        concentration_mode=mode,
        display_normalization=disp_norm,
        colormap_name=cmap,
        interactive_plot=interactive_plot,
    )

    matrix_csv_path = new_export_path("concentration_matrix_", ".csv")
    write_concentration_matrix_csv(matrix_csv_path, bundle)

    mat = np.asarray(bundle["matrix"], dtype=float)
    rlo = _parse_register_limit(register_low)
    rhi = _parse_register_limit(register_high)
    peak = float(np.max(mat)) if mat.size else 0.0
    nz = int(np.count_nonzero(mat))
    n_pitch, n_bins = mat.shape
    summary = (
        f"Registral concentration map — register band [{register_low}, {register_high}] "
        f"(MIDI {rlo:.0f}–{rhi:.0f}).\n"
        f"Pitch rows: {n_pitch}, time bins: {n_bins} (Δt = {dt} quarterLength).\n"
        f"concentration_mode: {mode}; display_normalization: {disp_norm}; colormap: {cmap}.\n"
        f"Peak cell count: {peak:.0f}; non-empty cells: {nz} / {mat.size}.\n"
        "Brighter / warmer color = more overlapping notated components at that pitch and time.\n"
        "This is symbolic occupancy only — not audio, dynamics, or dispersion metrics."
    )
    if progress_callback:
        progress_callback(1.0, "Done")
    return fig, summary, plot_path, matrix_csv_path


def build_demo() -> gr.Blocks:
    theme = gr.themes.Soft(
        primary_hue="amber",
        neutral_hue="stone",
        font=[gr.themes.GoogleFont("Source Sans 3"), "Segoe UI", "sans-serif"],
    ).set(
        body_background_fill="#f5f4f1",
        block_background_fill="#ffffff",
        block_border_width="1px",
        block_title_text_weight="500",
        button_primary_background_fill="#b45309",
        button_primary_background_fill_hover="#92400e",
    )
    demo = gr.Blocks(title=CANONICAL_TOOL_NAME, theme=theme, css=GRADIO_THEME_CSS)
    with demo:
        gr.HTML(
            f"<div class='hero-title'>{CANONICAL_TOOL_NAME}</div>"
            "<div class='hero-sub'>Symbolic analysis of vertical register structure — "
            "dispersion metrics and a pitch–time density map. "
            "<em>Dispersão no registo.</em></div>"
        )
        file_in = gr.File(label="Score file (MusicXML or MIDI)")

        analysis_preset_u = gr.Radio(
            choices=list(ANALYSIS_PRESETS),
            value=PRESET_MOVING_FRAGMENT,
            label="Analysis preset (advised parameterization)",
            info="Applies recommended settings from the parameterization guide. Choose Custom to tune manually.",
        )
        preset_guidance_u = gr.Markdown(preset_guidance_text(PRESET_MOVING_FRAGMENT))

        register_preset_u = gr.Radio(
            choices=list(REGISTER_PRESETS.keys()),
            value=REGISTER_PRESET_FULL,
            label="Register band",
        )
        with gr.Row():
            register_low_in = gr.Textbox(
                value="A0",
                label="Lower register limit (MIDI / note name)",
                placeholder="e.g. A0 or 21",
            )
            register_high_in = gr.Textbox(
                value="C8",
                label="Upper register limit (MIDI / note name)",
                placeholder="e.g. C8 or 108",
            )
        register_preset_u.change(
            fn=apply_register_preset,
            inputs=[register_preset_u],
            outputs=[register_low_in, register_high_in],
        )

        with gr.Row():
            with gr.Column(scale=1):
                time_step_u = gr.Number(value=0.25, label="Time step / heatmap bin size (quarterLength)")
                window_size_u = gr.Number(value=4.0, label="Window size (quarterLength)")
                analysis_profile_u = gr.Radio(
                    choices=[
                        (
                            "occupied_space — recommended for density-independent registral dispersion",
                            ANALYSIS_PROFILE_OCCUPIED_SPACE,
                        ),
                        (
                            "component_weighted — notated-component multiplicity (legacy-style)",
                            ANALYSIS_PROFILE_COMPONENT_WEIGHTED,
                        ),
                    ],
                    value=ANALYSIS_PROFILE_OCCUPIED_SPACE,
                    label="Analysis profile",
                )
                observation_mode_u = gr.Radio(
                    choices=[
                        (
                            "fixed_window — smoothed curve (moving windows on a time grid)",
                            OBSERVATION_MODE_FIXED_WINDOW,
                        ),
                        (
                            "event_boundaries — exact score-state intervals (constant active pitch set)",
                            OBSERVATION_MODE_EVENT_BOUNDARIES,
                        ),
                    ],
                    value=OBSERVATION_MODE_FIXED_WINDOW,
                    label="Temporal observation mode",
                )
                pitch_override_u = gr.Radio(
                    choices=[
                        (_PITCH_OVERRIDE_FOLLOW_PROFILE, _PITCH_OVERRIDE_FOLLOW_PROFILE),
                        ("event_instances (override profile)", "event_instances"),
                        ("unique_pitch_heights (override profile)", "unique_pitch_heights"),
                    ],
                    value=_PITCH_OVERRIDE_FOLLOW_PROFILE,
                    label="Pitch sampling override (optional)",
                )
                microtone_repair_u = gr.Radio(
                    choices=[
                        ("off — keep imported <alter> (default)", "off"),
                        ("warn — detect Sibelius-style glyph/<alter> mismatches", "warn"),
                        ("from_accidentals — repair quarter-tones from the accidental glyph", "from_accidentals"),
                    ],
                    value=DEFAULT_MICROTONEREPAIR,
                    label="Microtone repair (MusicXML accidental glyphs)",
                )
                pitch_reference_u = gr.Radio(
                    choices=[
                        ("written — as notated (default)", "written"),
                        ("sounding — concert pitch via music21 toSoundingPitch()", "sounding"),
                    ],
                    value=DEFAULT_PITCH_REFERENCE,
                    label="Pitch reference",
                )
                show_span_in = gr.Checkbox(
                    value=False,
                    label="Overlay mean pairwise distance (secondary axis)",
                )
                show_entropy_in = gr.Checkbox(value=False, label="Show occupancy entropy panel")
                plot_norm_y_in = gr.Checkbox(
                    value=False,
                    label="Plot y-axis in normalized units (÷ register width R)",
                )
                show_heatmap_in = gr.Checkbox(value=True, label="Include concentration heatmap (pitch × time)")
                interactive_u = gr.Checkbox(value=True, label="Interactive plots (Plotly)")
                load_btn = gr.Button("Load & inspect", variant="secondary")
                run_btn = gr.Button("Run analysis", variant="primary")

                with gr.Accordion("Advanced heatmap options", open=False):
                    heat_mode_u = gr.Radio(
                        choices=[
                            ("event_instances — doublings increase intensity", "event_instances"),
                            ("unique_pitch_heights — at most one per pitch per bin", "unique_pitch_heights"),
                        ],
                        value=DEFAULT_CONCENTRATION_MODE,
                        label="Heatmap counting mode",
                    )
                    heat_norm_u = gr.Radio(
                        choices=[
                            ("log1p_counts — accent populated regions (recommended)", DISPLAY_NORMALIZATION_LOG1P),
                            ("raw_counts — literal component counts", DISPLAY_NORMALIZATION_RAW),
                            ("column_normalized — vertical shape per time slice", DISPLAY_NORMALIZATION_COLUMN),
                            ("global_normalized — scale to global peak", DISPLAY_NORMALIZATION_GLOBAL),
                        ],
                        value=DEFAULT_DISPLAY_NORMALIZATION,
                        label="Heatmap color scaling",
                    )
                    heat_cmap_u = gr.Dropdown(
                        choices=[
                            "registral_ember",
                            "inferno",
                            "magma",
                            "YlOrRd",
                            "viridis",
                            "Blues",
                        ],
                        value=DEFAULT_COLORMAP,
                        label="Heatmap palette",
                    )

                analysis_preset_u.change(
                    fn=apply_analysis_preset,
                    inputs=[analysis_preset_u],
                    outputs=[
                        preset_guidance_u,
                        register_preset_u,
                        register_low_in,
                        register_high_in,
                        time_step_u,
                        window_size_u,
                        analysis_profile_u,
                        observation_mode_u,
                        pitch_override_u,
                        show_span_in,
                        show_entropy_in,
                        plot_norm_y_in,
                        show_heatmap_in,
                        heat_mode_u,
                        heat_norm_u,
                        heat_cmap_u,
                    ],
                )

            with gr.Column(scale=2):
                gr.Markdown("### Step 1 — Load & inspect")
                inventory_out = gr.Dataframe(
                    headers=INVENTORY_COLUMNS,
                    label="Pitch inventory (edit sounding_ps / sounding_name and used_in_metrics)",
                    interactive=True,
                    wrap=True,
                )
                digest_out = gr.Markdown()
                part_transpose_out = gr.Dataframe(
                    headers=["part_index", "part", "instrument", "extra_semitones"],
                    label="Extra transposition per part (semitones, may be fractional)",
                    interactive=True,
                )
                inspect_warnings_out = gr.Textbox(label="Inspect warnings", lines=3)
                inventory_state = gr.State([])
                gr.Markdown("### Step 2 — Run analysis")
                dispersion_plot_out = gr.Plot(label="Dispersion trajectory")
                heatmap_plot_out = gr.Plot(label="Register density map")
                summary_out = gr.Textbox(label="Summary", lines=16)
                with gr.Row():
                    dispersion_csv_out = gr.File(label="Dispersion CSV")
                    dispersion_json_out = gr.File(label="Dispersion JSON")
                    dispersion_plot_file_out = gr.File(label="Dispersion plot PNG")
                    heatmap_plot_file_out = gr.File(label="Heatmap PNG")
                    heat_matrix_out = gr.File(label="Heatmap matrix CSV")
                    inventory_csv_out = gr.File(label="Pitch inventory CSV")
                    overrides_json_out = gr.File(label="Pitch overrides JSON")

        load_btn.click(
            fn=load_inspect_ui,
            inputs=[
                file_in,
                register_low_in,
                register_high_in,
                pitch_reference_u,
                microtone_repair_u,
            ],
            outputs=[
                inventory_out,
                digest_out,
                part_transpose_out,
                inspect_warnings_out,
                inventory_state,
            ],
        )
        run_btn.click(
            fn=run_dispersion_ui,
            inputs=[
                file_in,
                register_low_in,
                register_high_in,
                time_step_u,
                window_size_u,
                analysis_profile_u,
                observation_mode_u,
                pitch_override_u,
                microtone_repair_u,
                pitch_reference_u,
                inventory_out,
                part_transpose_out,
                inventory_state,
                interactive_u,
                show_span_in,
                show_entropy_in,
                plot_norm_y_in,
                show_heatmap_in,
                heat_mode_u,
                heat_norm_u,
                heat_cmap_u,
            ],
            outputs=[
                dispersion_plot_out,
                heatmap_plot_out,
                summary_out,
                dispersion_csv_out,
                dispersion_plot_file_out,
                dispersion_json_out,
                heatmap_plot_file_out,
                heat_matrix_out,
                inventory_csv_out,
                overrides_json_out,
            ],
        )
    return demo


def launch(host: str | None = None, port: int | None = None, share: bool = False) -> None:
    cleanup_stale_exports()
    demo = build_demo()
    demo.launch(server_name=host, server_port=port, share=share)


def main() -> None:
    """Entry point for ``registral-dispersion`` console script (Gradio UI)."""
    launch()
