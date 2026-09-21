"""``python -m registral_dispersion`` — Gradio UI by default; optional batch CLI."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import matplotlib.pyplot as plt

from registral_dispersion.concentration_map import DEFAULT_DISPLAY_NORMALIZATION, run_concentration_map_to_files
from registral_dispersion.json_export import (
    build_registral_dispersion_export,
    write_global_summary_csv,
    write_json_export,
    write_registral_dispersion_csv,
)
from registral_dispersion.microtone_repair import DEFAULT_MICROTONEREPAIR
from registral_dispersion.pitch_inventory import write_pitch_inventory_csv
from registral_dispersion.pitch_overrides import load_pitch_overrides
from registral_dispersion.pitch_reference import DEFAULT_PITCH_REFERENCE
from registral_dispersion.pitch_utils import DEFAULT_REGISTER_HIGH, DEFAULT_REGISTER_LOW
from registral_dispersion.plotting import make_dispersion_figure
from registral_dispersion.profiles import DEFAULT_ANALYSIS_PROFILE
from registral_dispersion.service import inspect_score_pitches, run_registral_dispersion_analysis
from registral_dispersion.summarize import DEFAULT_SUMMARIZE_PARAMS, summarize_registral_dispersion
from registral_dispersion.tie_policy import DEFAULT_TIE_POLICY


def _add_common_analysis_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--score", required=True, help="Path to MusicXML, MXL, or MIDI.")
    parser.add_argument("--register-low", default=DEFAULT_REGISTER_LOW)
    parser.add_argument("--register-high", default=DEFAULT_REGISTER_HIGH)
    parser.add_argument("--time-step", type=float, default=0.25)
    parser.add_argument("--window-size", type=float, default=4.0)
    parser.add_argument(
        "--analysis-profile",
        dest="analysis_profile",
        default=DEFAULT_ANALYSIS_PROFILE,
        choices=["occupied_space", "component_weighted"],
    )
    parser.add_argument(
        "--pitch-sampling",
        dest="pitch_sampling_mode",
        default=None,
        choices=["event_instances", "unique_pitch_heights"],
    )
    parser.add_argument(
        "--observation-mode",
        dest="observation_mode",
        default=None,
        choices=["fixed_window", "event_boundaries"],
    )
    parser.add_argument(
        "--tie-policy",
        dest="tie_policy",
        default=DEFAULT_TIE_POLICY,
        choices=["as_imported", "merge_ties"],
    )
    parser.add_argument(
        "--microtone-repair",
        dest="microtone_repair",
        default=DEFAULT_MICROTONEREPAIR,
        choices=["off", "warn", "from_accidentals"],
        help=(
            "Repair MusicXML accidental glyphs whose <alter> does not match the glyph "
            "(Sibelius-style quarter-tones). Default: off."
        ),
    )
    parser.add_argument(
        "--pitch-reference",
        dest="pitch_reference",
        default=DEFAULT_PITCH_REFERENCE,
        choices=["written", "sounding"],
        help="Use written (default) or concert/sounding pitches. Default: written.",
    )
    parser.add_argument(
        "--pitch-overrides",
        dest="pitch_overrides",
        default=None,
        help="Path to a sidecar JSON list of pitch overrides.",
    )


def _run_params_from_args(args: argparse.Namespace, *, default_observation_mode: str) -> dict:
    run_params = {
        "time_step": args.time_step,
        "window_size": args.window_size,
        "register_low": args.register_low,
        "register_high": args.register_high,
        "analysis_profile": args.analysis_profile,
        "observation_mode": args.observation_mode or default_observation_mode,
        "tie_policy": args.tie_policy,
        "microtone_repair": getattr(args, "microtone_repair", DEFAULT_MICROTONEREPAIR),
        "pitch_reference": getattr(args, "pitch_reference", DEFAULT_PITCH_REFERENCE),
    }
    if args.pitch_sampling_mode is not None:
        run_params["pitch_sampling_mode"] = args.pitch_sampling_mode
    overrides_path = getattr(args, "pitch_overrides", None)
    if overrides_path:
        run_params["pitch_overrides"] = load_pitch_overrides(overrides_path)
    return run_params


def _cli_analyze(args: argparse.Namespace) -> int:
    run_params = _run_params_from_args(args, default_observation_mode="fixed_window")
    out = run_registral_dispersion_analysis(args.score, run_params)
    if out.get("error"):
        print(out["error"], file=sys.stderr)
        return 1
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = args.prefix
    results = out["results"]
    csv_path = out_dir / f"{stem}.csv"
    json_path = out_dir / f"{stem}.json"
    png_path = out_dir / f"{stem}.png"
    summary_csv_path = out_dir / f"{stem}_global_summary.csv"
    rp = out["params"]
    an = out["analyzer"]
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
    write_json_export(json_path, build_registral_dispersion_export(args.score, rp, out))
    inventory_csv_path = out_dir / f"{stem}_pitch_inventory.csv"
    write_pitch_inventory_csv(inventory_csv_path, out.get("pitch_inventory") or [])
    if out.get("global_summary"):
        write_global_summary_csv(summary_csv_path, out["global_summary"])
    title = f"Registral dispersion — [{args.register_low}, {args.register_high}], window={args.window_size}"
    y_scale = "normalized" if args.plot_normalized else "raw"
    fig = make_dispersion_figure(
        results,
        title=title,
        show_registral_span=args.plot_span or args.plot_pairwise,
        show_occupancy_entropy=args.plot_entropy,
        y_scale=y_scale,
    )
    fig.savefig(png_path, dpi=200)
    plt.close(fig)
    print(f"Wrote {csv_path}, {json_path}, {png_path}, {inventory_csv_path}")
    if out.get("global_summary"):
        print(f"Wrote {summary_csv_path}")
    print(out.get("summary", ""))
    return 0


def _cli_summarize(args: argparse.Namespace) -> int:
    run_params = _run_params_from_args(args, default_observation_mode=DEFAULT_SUMMARIZE_PARAMS["observation_mode"])
    out = summarize_registral_dispersion(args.score, run_params)
    if out.get("error"):
        print(out["error"], file=sys.stderr)
        return 1
    doc = {
        "kind": "registral_dispersion_summary",
        "score_path": args.score,
        "primary_metric": out["primary_metric"],
        "primary_value": out["primary_value"],
        "secondary_metric": out["secondary_metric"],
        "secondary_value": out["secondary_value"],
        "global_summary": out["global_summary"],
        "params": out["params"],
        "warnings": out["warnings"],
    }
    print(f"primary_metric: {out['primary_metric']}")
    print(f"primary_value: {out['primary_value']}")
    print(f"secondary_metric: {out['secondary_metric']}")
    print(f"secondary_value: {out['secondary_value']}")
    print(f"analysis_profile: {out['params'].get('analysis_profile')}")
    print(f"pitch_sampling_mode: {out['params'].get('pitch_sampling_mode')}")
    print(f"observation_mode: {out['params'].get('observation_mode')}")
    print(f"register: {out['params'].get('register_low')}–{out['params'].get('register_high')}")
    print(f"warnings: {len(out.get('warnings') or [])}")
    for w in out.get("warnings") or []:
        print(f"  - {w}")
    if args.out_json:
        write_json_export(args.out_json, doc)
        print(f"Wrote {args.out_json}")
    if args.out_csv and out.get("global_summary"):
        write_global_summary_csv(args.out_csv, out["global_summary"])
        print(f"Wrote {args.out_csv}")
    return 0


def _cli_inventory(args: argparse.Namespace) -> int:
    run_params = {
        "register_low": args.register_low,
        "register_high": args.register_high,
        "pitch_reference": args.pitch_reference,
        "microtone_repair": getattr(args, "microtone_repair", DEFAULT_MICROTONEREPAIR),
    }
    if getattr(args, "pitch_overrides", None):
        run_params["pitch_overrides"] = load_pitch_overrides(args.pitch_overrides)
    out = inspect_score_pitches(args.score, run_params)
    if out.get("error"):
        print(out["error"], file=sys.stderr)
        return 1
    write_pitch_inventory_csv(args.out, out.get("pitch_inventory") or [])
    print(f"Wrote {args.out}")
    print(out.get("digest_line", ""))
    for w in out.get("warnings") or []:
        print(f"  - {w}")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Symbolic-score registral dispersion (MusicXML/MXL/MIDI). "
            "Batch analyze, one-number summarize, or Gradio UI."
        ),
    )
    sub = parser.add_subparsers(dest="command")

    p_ui = sub.add_parser("ui", help="Launch Gradio web UI (default if no subcommand).")
    p_ui.add_argument("--host", default=None)
    p_ui.add_argument("--port", type=int, default=None)
    p_ui.add_argument("--share", action="store_true")

    p_run = sub.add_parser("analyze", help="Batch export CSV, JSON, PNG, and global summary.")
    _add_common_analysis_args(p_run)
    p_run.set_defaults(observation_mode="fixed_window")
    p_run.add_argument("--out-dir", default=".", help="Output directory.")
    p_run.add_argument("--prefix", default="registral_dispersion", help="Basename for outputs.")
    p_run.add_argument(
        "--plot-span",
        action="store_true",
        help="Overlay mean pairwise distance on PNG (deprecated alias).",
    )
    p_run.add_argument(
        "--plot-pairwise",
        action="store_true",
        help="Overlay mean pairwise registral distance on PNG (secondary axis).",
    )
    p_run.add_argument("--plot-entropy", action="store_true", help="Include occupancy entropy panel on PNG.")
    p_run.add_argument(
        "--plot-normalized",
        action="store_true",
        help="Plot dispersion_degree and optional pairwise overlay in units of 1/R (vs raw semitones).",
    )

    p_sum = sub.add_parser("summarize", help="One-number global summary (default: event_boundaries + occupied_space).")
    _add_common_analysis_args(p_sum)
    p_sum.set_defaults(
        observation_mode=DEFAULT_SUMMARIZE_PARAMS["observation_mode"],
        analysis_profile=DEFAULT_SUMMARIZE_PARAMS["analysis_profile"],
    )
    p_sum.add_argument("--out-json", default=None, help="Optional path for summary JSON.")
    p_sum.add_argument("--out-csv", default=None, help="Optional path for global summary CSV.")

    p_heat = sub.add_parser(
        "concentration-map",
        help="Symbolic pitch–time concentration heatmap (visualization only; not dispersion metrics).",
    )
    p_heat.add_argument("--score", required=True, help="Path to MusicXML, MXL, or MIDI.")
    p_heat.add_argument(
        "--out",
        required=True,
        help="Output path (.png, .svg, or .html for interactive Plotly).",
    )
    p_heat.add_argument("--register-low", default=DEFAULT_REGISTER_LOW)
    p_heat.add_argument("--register-high", default=DEFAULT_REGISTER_HIGH)
    p_heat.add_argument(
        "--time-bin-size",
        type=float,
        default=0.25,
        help="Time bin width in quarterLength units (default 0.25).",
    )
    p_heat.add_argument(
        "--mode",
        dest="concentration_mode",
        default="event_instances",
        choices=["event_instances", "unique_pitch_heights"],
        help="How to aggregate duplicate MIDI heights within a bin (default event_instances).",
    )
    p_heat.add_argument(
        "--normalization",
        dest="display_normalization",
        default=DEFAULT_DISPLAY_NORMALIZATION,
        choices=["raw_counts", "log1p_counts", "column_normalized", "global_normalized"],
        help="Display-only color scaling (default log1p_counts accentuates populated cells).",
    )
    p_heat.add_argument(
        "--colormap",
        default="Blues",
        help="Matplotlib colormap name (sequential; default Blues).",
    )
    p_heat.add_argument("--dpi", type=int, default=300, help="Raster resolution for PNG (default 300).")
    p_heat.add_argument("--matrix-csv", default=None, help="Optional path to write raw count matrix CSV.")
    p_heat.add_argument("--matrix-npz", default=None, help="Optional path to write raw count matrix NPZ.")
    p_heat.add_argument("--title", default="Registral concentration map", help="Figure title.")

    p_inv = sub.add_parser("inventory", help="Dump the pitch inventory table without running analysis.")
    p_inv.add_argument("--score", required=True, help="Path to MusicXML, MXL, or MIDI.")
    p_inv.add_argument("--out", required=True, help="Output CSV path for the inventory table.")
    p_inv.add_argument("--register-low", default=DEFAULT_REGISTER_LOW)
    p_inv.add_argument("--register-high", default=DEFAULT_REGISTER_HIGH)
    p_inv.add_argument(
        "--pitch-reference",
        dest="pitch_reference",
        default=DEFAULT_PITCH_REFERENCE,
        choices=["written", "sounding"],
    )
    p_inv.add_argument(
        "--microtone-repair",
        dest="microtone_repair",
        default=DEFAULT_MICROTONEREPAIR,
        choices=["off", "warn", "from_accidentals"],
    )
    p_inv.add_argument(
        "--pitch-overrides",
        dest="pitch_overrides",
        default=None,
        help="Path to a sidecar JSON list of pitch overrides.",
    )

    argv = sys.argv[1:]
    if not argv:
        from registral_dispersion.app import launch

        launch()
        return
    if argv[0] not in ("ui", "analyze", "summarize", "concentration-map", "inventory"):
        argv = ["ui", *argv]
    args = parser.parse_args(argv)
    if args.command == "ui":
        from registral_dispersion.app import launch

        launch(host=args.host, port=args.port, share=args.share)
        return
    if args.command == "analyze":
        raise SystemExit(_cli_analyze(args))
    if args.command == "summarize":
        raise SystemExit(_cli_summarize(args))
    if args.command == "inventory":
        raise SystemExit(_cli_inventory(args))
    if args.command == "concentration-map":
        try:
            written = run_concentration_map_to_files(
                args.score,
                args.out,
                args.register_low,
                args.register_high,
                time_bin_size=args.time_bin_size,
                concentration_mode=args.concentration_mode,
                display_normalization=args.display_normalization,
                colormap_name=args.colormap,
                dpi=args.dpi,
                matrix_csv=args.matrix_csv,
                matrix_npz=args.matrix_npz,
                title=args.title,
            )
        except Exception as e:
            print(str(e), file=sys.stderr)
            raise SystemExit(1) from e
        for pth in written.get("outputs", []):
            print(f"Wrote {pth}")
        raise SystemExit(0)
    parser.print_help()
    raise SystemExit(2)


if __name__ == "__main__":
    main()
