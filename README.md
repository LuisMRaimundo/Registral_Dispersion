# Registral_Dispersion

**Canonical tool name:** **Registral_Dispersion**  
**Repository:** [github.com/LuisMRaimundo/Registral_Dispersion](https://github.com/LuisMRaimundo/Registral_Dispersion)

**What this is:** a **symbolic-score–only** research tool that measures **registral dispersion**—how spread out or compact **active notated MIDI pitches** are inside a user band—using **registral span** and **mean pairwise registral distance** (semitones), with optional **occupancy entropy** (a separate, legacy-style occupancy-evenness index, **not** the main dispersion read).

## Quick install (no Python knowledge required)

| Windows 10/11 | macOS | Linux |
|---------------|-------|-------|
| Double-click **`install/windows/INSTALL.bat`** | Double-click **`install/macos/INSTALL.command`** | Run **`install/linux/install.sh`** |

See **[install/README.md](install/README.md)** for details. **Run the installer once first** (it creates `.venv`, which is not included in the clone). Then launch with **`Launch-Registral-Dispersion.bat`** (Windows) or **`Launch-Registral-Dispersion.command`** (macOS). If you open a launcher before installing, it will tell you to run the installer.

Installable distribution name: **`registral-dispersion`** (Python package; canonical research tool name **Registral_Dispersion**; version **0.3.0** — research software; pin `package_version` and `canonical_tool_name` from JSON exports for reproducibility).

**Scope:** symbolic-score-only registral dispersion (MusicXML, MXL, MIDI via music21). **Not** audio, loudness, timbre, orchestration, harmony, pitch-class analysis, or psychoacoustic perception. For precise definitions, formulas, and interpretive limits of each metric, see **[docs/METRIC_SEMANTICS.md](docs/METRIC_SEMANTICS.md)**.

Analysis proceeds along the score using an explicit **temporal observation mode** (default: **fixed_window**, i.e. moving windows on a regular time grid).

The **default** research stance is **`analysis_profile: occupied_space`** (implies **`unique_pitch_heights`**): density-independent geometry of **occupied registral positions**. For workflows aligned with earlier register-uniformity / entropy tooling that used **event-instance** sampling, set **`analysis_profile: "component_weighted"`** or pass **`pitch_sampling_mode: "event_instances"`** explicitly (see note below).

## Analysis profiles (interpretation, not new formulas)

| Profile | Pitch sampling implied (if you do **not** override `pitch_sampling_mode`) | Interpretation | Typical primary read |
|--------|-------------------------------------------------------------------------------|----------------|----------------------|
| **`occupied_space`** (default) | `unique_pitch_heights` | Vertical opening/compression of **occupied registral positions**; multiplicity of identical heights does not inflate pairwise distance. | **registral_span**; mean pairwise secondary |
| **`component_weighted`** | `event_instances` | Dispersion among **active notated components**; duplicated unisons, doublings, and repeated noteheads are analytically meaningful. | **mean_pairwise_registral_distance**; span secondary |

**Precedence:** if your parameters dict includes the key **`pitch_sampling_mode`**, it is treated as an **explicit override** of the profile’s implied mode. If you omit `pitch_sampling_mode`, the profile alone sets it. `event_instances` is not “wrong” for registral work—it answers a **different** question than density-independent occupied space.

**Earlier entropy / uniformity workflows** used event-instance sampling (multiple identical MIDI contributions). To **reproduce** those numerical results, use `analysis_profile="component_weighted"` or pass `pitch_sampling_mode="event_instances"` (with the usual register and window settings).

## Defaults (API, CLI, UI)

| Setting | Default | Notes |
|--------|---------|--------|
| `analysis_profile` | **`occupied_space`** | Density-independent occupied pitch-space geometry. |
| `pitch_sampling_mode` (if not overridden) | **`unique_pitch_heights`** | Implied by `occupied_space` via `resolve_registral_dispersion_params`. |
| `observation_mode` | **`fixed_window`** | Moving windows: `time_step` + `window_size`. |
| `microtone_repair` | **`off`** | Leave imported `<alter>` unchanged. `warn` / `from_accidentals` for Sibelius-style glyph-only quarter-tones. |
| `pitch_reference` | **`written`** | Analyze notated pitches. Use `sounding` for concert pitch (`toSoundingPitch()`). |
| Register band | **A0 to C8 (full notated range)** preset in UI | Parsed to MIDI ps; **results depend on this band**. |
| Primary outputs | **Raw semitones** | **`dispersion_degree`** (canonical; numerically = `registral_span`), `mean_pairwise_registral_distance` (supplementary). |
| Secondary outputs | **`normalized_*`** | Raw ÷ `R = register_high_midi − register_low_midi`. |

### Plotting vs exports vs interpretation (avoid mixing these)

| Layer | Primary | Secondary / optional |
|-------|---------|----------------------|
| **UI / batch PNG curve** | **`dispersion_degree`** (= `registral_span`, max − min) | Mean pairwise distance (checkbox overlay; secondary y-axis) |
| **CSV / JSON canonical field** | **`dispersion_degree`** | `mean_pairwise_registral_distance`, centroid, std, `occupancy_entropy` |
| **Research read (`occupied_space`)** | `registral_span` / `dispersion_degree` | Mean pairwise (often coincides under `unique_pitch_heights`) |
| **Research read (`component_weighted`)** | Mean pairwise distance (multiplicity matters) | Span/degree still exported and plotted as the main curve unless you overlay pairwise |

The **plotted** primary curve always follows the code in `plotting.py` (`dispersion_degree`). Profile tables below describe **how to interpret** columns, not which line is drawn by default.

## Temporal observation modes

The **same** registral formulas (`registral_span`, `mean_pairwise_registral_distance`, optional `occupancy_entropy`, and normalized counterparts) are applied to the set of pitches that are **active** in each temporal support; only the **sampling of time** changes.

| Mode | Meaning | Typical use |
|------|---------|---------------|
| **`fixed_window`** (default, backward compatible) | Regular grid of window centers `t` with symmetric support `[t − w/2, t + w/2]`; parameters **`time_step`** and **`window_size`**. | Smoothed curves, continuity with earlier exports and moving-window studies. |
| **`event_boundaries`** | Half-open intervals **`[interval_start, interval_end)`** between sorted **onsets** and **note/chord offsets** (plus score times `0` and score duration). One row per interval where the active in-register pitch set is **constant**. **`window_size`** is ignored for indexing (still accepted for API compatibility). **`t`** is the interval **midpoint** (for plotting on a time axis). **`window_start` / `window_end`** mirror **`interval_start` / `interval_end`** as aliases. | Discrete **notational configurations** and segment-level trajectories (expansion / contraction) without arbitrary window smoothing. |

**Recommendation:** use **`event_boundaries`** when the research question targets **exact score-state segments**; use **`fixed_window`** when you want a **regularly sampled curve**.

**Empty temporal gaps** (no in-register sounding pitch on an interval, e.g. a rest between attacks): intervals are **still emitted** as rows; dispersion metrics are **NaN** and `active_note_count` is **0** (same convention as an empty moving window).

Exports record **`observation_mode`** and per-row **`interval_start`**, **`interval_end`**, and **`interval_duration`** in CSV and JSON. In **`fixed_window`** mode, interval fields **mirror** the window bounds so the schema stays consistent.

## Primary descriptors (per window or interval)

On **absolute MIDI pitch** values for notes/chord tones that are **active** in the temporal support (moving window or event interval) and lie inside the user band `[register_low, register_high]` (not pitch-class reduction):

1. **dispersion_degree** / **registral_span** — canonical metric `D_span = max(pitches) - min(pitches)` (semitones); both names refer to the same value in exports.
2. **mean_pairwise_registral_distance** — mean absolute distance over **unordered** distinct pitch pairs:  
   `D_pairwise = (2 / (n(n-1))) * sum_{i<j} |p_i - p_j|` (same as the arithmetic mean of `|p_i - p_j|` over all `i < j`; semitones).
3. **registral_centroid** — `mean(pitches)` in MIDI semitones (where the active material sits in register).
4. **registral_std** — population standard deviation of `pitches` (semitones); tight clusters vs wide spread **around the mean** (complements span and pairwise distance).

**Main curve** in the UI and batch PNG defaults to **`dispersion_degree`** (same numbers as **registral span**). **Mean pairwise registral distance** can be overlaid on a secondary axis (UI: “Overlay mean pairwise distance”; CLI: `--plot-pairwise` or deprecated `--plot-span`). **Centroid** and **std** appear in CSV/JSON exports and the text summary (not plotted by default). Span/degree and pairwise distance are **transposition-invariant**; raw centroid is **not** (it tracks absolute tessitura).

Advised parameter sets for static vs moving workflows: **[docs/PARAMETERIZATION_GUIDE.md](docs/PARAMETERIZATION_GUIDE.md)**.

### Raw vs normalized (secondary)

**Raw** `dispersion_degree`, `registral_span`, and `mean_pairwise_registral_distance` are all exported in **semitones** on every row. Only **`dispersion_degree`** is the **canonical** field and the **default plotted** series; pairwise is supplementary in exports and optional in figures.

**Normalized** columns (secondary) scale raw values by the analytical register width

`R = register_high_midi - register_low_midi`

so that `normalized_registral_span = registral_span / R`, `normalized_mean_pairwise_registral_distance = mean_pairwise_registral_distance / R`, `normalized_registral_centroid = (registral_centroid - register_low_midi) / R`, and `normalized_registral_std = registral_std / R`. They are useful for comparing runs with **different** register bounds. They are **not** perceptual dispersion, acoustic brightness, or orchestral spread—only semitone distances (or band-relative centroid position) divided by the **selected** band width (`normalization_reference: selected_register_bounds` in exports). `R` must be strictly positive (equal bounds raise a validation error).

**occupancy_entropy** (same numerical recipe as the former **register uniformity U**): normalized Shannon entropy of **semitone-bin occupancy** within the register band (natural log, base **e**; normalized by `log(n_bins)`). It measures **evenness of bin occupancy**, **not** vertical opening; it is **conceptually distinct** from `registral_span` and `mean_pairwise_registral_distance`. See **[docs/METRIC_SEMANTICS.md](docs/METRIC_SEMANTICS.md)** §5.

## Methodological note

Registral dispersion is operationalized here as the vertical opening/compression of active notated components in semitone space. The **canonical** per-row metric is **`dispersion_degree`** (= `registral_span` = max − min in semitones). **Mean pairwise registral distance** is a supplementary descriptor (especially informative under `component_weighted` / `event_instances`). Span/degree and pairwise distance are transposition-invariant in the sense that they depend only on relative MIDI distances within each temporal support; they do not measure pitch-class content, harmony, acoustic brightness, or orchestration. **Registral centroid** tracks absolute tessitura. The previous entropy-based register uniformity metric, if retained as `occupancy_entropy`, measures pitch-bin occupancy evenness and is conceptually distinct. **Full metric semantics:** [docs/METRIC_SEMANTICS.md](docs/METRIC_SEMANTICS.md).

## Edge cases

* **No active pitches** in the window: dispersion metrics, `registral_centroid`, `registral_std`, and `occupancy_entropy` are **NaN**; `active_note_count` is 0; `min_pitch` / `max_pitch` are **NaN**.
* **One active pitch**: `registral_span` = 0, `mean_pairwise_registral_distance` = 0, `registral_centroid` = that pitch, `registral_std` = 0, `occupancy_entropy` = 0; `min_pitch` = `max_pitch` = that pitch.

## Notational sampling (what is “active”?)

The engine lists candidates from **music21** `score.flatten().notes` (each `Note` and each `Chord`). **All parts are merged** before listing. A candidate is **active** in a temporal support `[t_lo, t_hi)` if its **notated** sounding overlaps that half-open span:

`onset < t_hi` and `onset + quarterLength > t_lo`.

For **`fixed_window`**, `t_lo = t − w/2` and `t_hi = t + w/2` (window center `t`). For **`event_boundaries`**, each row uses its own `[interval_start, interval_end)`.

So **sustained** notes count in every overlapped window, not only when an attack falls inside the window.

* **Chords:** each pitch in `Chord.pitches` that lies in the register band is a separate component before optional deduplication.
* **Ties:** default **`tie_policy=as_imported`** (no merge). Use **`tie_policy=merge_ties`** to run music21 `stripTies()` before listing events. Otherwise the flat stream may be one long `Note` or several tied segments depending on the file and importer; **each overlapping `Note`/`Chord` object** contributes once per object.
* **`analysis_profile`** (default **`occupied_space`**) sets the implied **`pitch_sampling_mode`** unless you pass an explicit `pitch_sampling_mode` key (see precedence above).
* **`pitch_sampling_mode`** when derived from profile:

  * **`event_instances`** (`component_weighted`) — keep every in-register MIDI value contributed by overlapping events (chord tones separately; **duplicated unisons across parts** and **repeated noteheads** count as multiple components).
  * **`unique_pitch_heights`** (`occupied_space`) — collapse to **distinct MIDI pitch numbers** within the window, then compute span, pairwise mean, and occupancy entropy. `active_note_count` is the length **after** this collapse.

Exports (CSV comment lines and JSON) record **`analysis_profile`**, **`pitch_sampling_mode`**, **`pitch_sampling_source`**, **`observation_mode`**, **`microtone_repair`**, **`pitch_reference`**, register bounds and width, **`normalization_reference`**, explicit **formula / methodological** strings, and **`package_version`** / **`tool_role`** (JSON schema **1.11**) for reproducibility.

## Install

```bash
pip install -e ".[dev]"
```

After changing the checked-out version, **reinstall** the editable package so JSON exports report the correct **`package_version`** (from `pyproject.toml`).

## Tests

**CI:** GitHub Actions (`.github/workflows/tests.yml`) on push and pull request.

```bash
pip install -e ".[dev]"
python -m pytest tests -q
python -m pytest tests -q --cov=registral_dispersion --cov-report=term-missing
```

Typical full suite: **245 passed** (2026-09-21).

## Run (Gradio UI)

```bash
registral-dispersion
# or
python -m registral_dispersion
```

The UI has two tabs:

1. **Dispersion curves** — **`dispersion_degree`** (primary), optional mean pairwise overlay and occupancy entropy (default profile: **occupied_space**). Presets: static vertical, moving fragment, global summary.
2. **Concentration heatmap** — pitch–time map where **warmer/brighter cells = more notated activity** at that register and time.

## Registral concentration map

**Complementary visualization only:** a **pitch–time heatmap** of **symbolic notational occupancy** — where active **notated** pitch components fall in register over score time (quarterLength). **Warmer / brighter color** means **more overlapping notated components** at that MIDI height in that time bin (not acoustic loudness). Default color scaling uses **`log1p_counts`** so populated regions stand out without flattening sparse passages. This is **not** a registral-dispersion metric, **not** audio energy, loudness, or orchestration. Details: **[docs/METRIC_SEMANTICS.md](docs/METRIC_SEMANTICS.md)** §7.

```bash
python -m registral_dispersion analyze --score path/to/score.musicxml --out-dir ./out
```

Defaults match the main API (**`occupied_space`**). For legacy-style **`event_instances`** analysis, run e.g.:

```bash
python -m registral_dispersion analyze --score path/to/score.musicxml --analysis-profile component_weighted --out-dir ./out
```

Explicit defaults (smoke-friendly):

```bash
python -m registral_dispersion analyze --score path/to/score.musicxml --analysis-profile occupied_space --observation-mode fixed_window --out-dir ./out
python -m registral_dispersion analyze --score path/to/score.musicxml --observation-mode event_boundaries --out-dir ./out
```

Options: `--register-low`, `--register-high`, `--time-step`, `--window-size`, `--prefix`, `--plot-pairwise` (or deprecated `--plot-span`), `--plot-entropy`, `--plot-normalized` (y-axis in 1/R units), `--tie-policy` (`as_imported` | `merge_ties`), `--analysis-profile` (`occupied_space` | `component_weighted`), optional `--pitch-sampling` (overrides profile if set), `--observation-mode` (`fixed_window` | `event_boundaries`), `--microtone-repair` (`off` | `warn` | `from_accidentals`), `--pitch-reference` (`written` | `sounding`), `--pitch-overrides path.json`. Batch `analyze` also writes `{prefix}_pitch_inventory.csv`. PNG primary curve = **`dispersion_degree`**; pairwise is overlay only.

Dump the inspectable table without running metrics:

```bash
python -m registral_dispersion inventory --score path/to/score.musicxml --pitch-reference sounding --out inventory.csv
```

## Batch export (dispersion)

**Overlap rule** matches dispersion analysis: a note/chord component is active in a half-open bin `[t, t+Δt)` iff `onset < t+Δt` and `onset + quarterLength > t`. **Chord tones** count separately. **Register** uses the same bounds parsing as the rest of the package (note names or MIDI).

**`concentration_mode`** (heatmap-specific; independent of `analysis_profile` defaults for dispersion):

| Mode | Meaning in the heatmap |
|------|-------------------------|
| **`event_instances`** (default) | Each overlapping notated component at a MIDI height increments that row (duplicated unisons across parts → higher intensity). |
| **`unique_pitch_heights`** | At most one count per distinct integer MIDI pitch per time bin (multiplicity collapsed for display). |

**Display-only normalization** (`--normalization`): `log1p_counts` (**default** — accentuates populated cells), `raw_counts`, `column_normalized` (each time column ÷ its max), or `global_normalized` (matrix ÷ global max). Color scaling only; matrix exports always store raw counts.

CLI example (high-resolution PNG, default `Δt = 0.25` qL):

```bash
python -m registral_dispersion concentration-map --score path/to/score.musicxml --out ./concentration.png --register-low A1 --register-high E7 --time-bin-size 0.25 --mode event_instances --normalization log1p_counts --colormap YlOrRd
```

Use `.svg` for vector output, or `.html` for an interactive Plotly figure (hover: time bin, MIDI, note name, intensity). Optional `--matrix-csv` / `--matrix-npz` export the **raw** count matrix (rows = MIDI pitch bins, columns = time bins) with metadata in comments / sidecar JSON inside NPZ.

Programmatic entry point: `registral_dispersion.concentration_map.build_registral_concentration_matrix`, `make_registral_concentration_map`, and `run_concentration_map_to_files`.

**Overlaying dispersion on the heatmap (Matplotlib):** pass `overlay_t` and series from `dispersion_overlay_from_results(analyze_score_output)` into `make_registral_concentration_map`. Times are quarterLength (window centers or event midpoints); the heatmap x-axis is `[time_bin_edges[0], time_bin_edges[-1]]`. For fixed-window dispersion, set `time_bin_size` equal to `time_step` so the grid matches the curve sampling.

## Python API

**Recommended entry point:** `run_registral_dispersion_analysis` — merges defaults, resolves **`analysis_profile`** and **`pitch_sampling_mode`** together, and records **`pitch_sampling_source`** in `out["params"]` for reproducibility.

**Direct construction:** `RegistralDispersionAnalyzer` (file path) and `RegistralDispersionAnalyzer.from_stream` follow the **same** profile/sampling rules as the service layer: if **`pitch_sampling_mode`** is omitted (`None`), it is **implied** from **`analysis_profile`** (`occupied_space` → `unique_pitch_heights`, `component_weighted` → `event_instances`). If you pass **`pitch_sampling_mode`** explicitly, it **overrides** that implication. The analyzer stores **`pitch_sampling_source`** on the instance (`"analysis_profile"` or `"explicit_param"`). The shared helper is `registral_dispersion.profiles.resolve_profile_and_pitch_sampling`.

```python
from registral_dispersion import run_registral_dispersion_analysis

# Default: occupied_space (implies unique_pitch_heights)
out = run_registral_dispersion_analysis("score.xml", {
    "time_step": 0.25,
    "window_size": 4.0,
    "register_low": "A0",
    "register_high": "C8",
    "observation_mode": "fixed_window",  # default; use "event_boundaries" for score-state intervals
    # "microtone_repair": "from_accidentals",  # Sibelius glyph-only quarter-tones
    # "pitch_reference": "sounding",          # concert pitch (default: written)
    # "pitch_overrides": [...],               # see pitch inventory / sidecar JSON
})
print(out["params"]["analysis_profile"], out["params"]["pitch_sampling_mode"])

# Legacy-style component / event-instance sampling:
# out = run_registral_dispersion_analysis("score.xml", {..., "analysis_profile": "component_weighted"})
```

Legacy API (only `t` and `U` = occupancy entropy): `run_register_uniformity_analysis` — defaults to **`component_weighted`** unless you pass **`analysis_profile`** explicitly, so older **U** baselines stay reproducible.

## Global summary (whole-score aggregate)

Every successful `run_registral_dispersion_analysis` call now includes `out["global_summary"]`:

| `observation_mode` | Aggregation | Primary global fields |
|--------------------|-------------|------------------------|
| **`event_boundaries`** | Duration-weighted over intervals (skips NaN / empty rows) | `duration_weighted_registral_span`, `duration_weighted_mean_pairwise_registral_distance`, … |
| **`fixed_window`** | Sampled trajectory summary (windows overlap; **not** duration states) | `sampled_mean_registral_span`, `sampled_max_registral_span`, … |

JSON exports (schema **1.11**) include `global_summary`, `warnings`, `tie_policy`, `microtone_repair`, `pitch_reference`, `transposing_parts`, `pitch_overrides`, `pitch_inventory_digest`, `repairs`, and `symbolic_score_only: true`.  
Batch `analyze` also writes `{prefix}_global_summary.csv` (key/value, separate from per-row CSV) and `{prefix}_pitch_inventory.csv`.

## One-number API and CLI (recommended for a single score metric)

**Python:**

```python
from registral_dispersion import summarize_registral_dispersion

summary = summarize_registral_dispersion("score.xml")  # defaults: event_boundaries + occupied_space + A0–C8
print(summary["primary_metric"], summary["primary_value"])
print(summary["warnings"])
```

**CLI:**

```bash
python -m registral_dispersion summarize --score score.xml --out-json summary.json --out-csv summary.csv
```

Defaults: `event_boundaries`, `occupied_space`, register A0–C8, `tie_policy=as_imported`.  
Primary one-number: **`duration_weighted_registral_span`** (semitones). Secondary: **`duration_weighted_mean_pairwise_registral_distance`**.

Interpretation warnings are emitted when `component_weighted` is selected, when `pitch_sampling_mode` explicitly overrides the profile, or when a one-number summary uses `fixed_window`.

## Tie policy

| Value | Behavior |
|-------|----------|
| **`as_imported`** (default) | Preserve music21 import structure (backward compatible). |
| **`merge_ties`** | Apply `stripTies()` before analysis; collapse tied continuations where music21 allows. |

Set via `tie_policy` in API params, `--tie-policy` on CLI, recorded in JSON/CSV metadata. Ambiguous ties may produce warnings.

## Benchmarks (synthetic regression fixtures)

Controlled synthetic MusicXML fixtures and frozen summarize outputs live under `benchmarks/` ( **not** empirical validation corpora).

```bash
python benchmarks/scripts/generate_frozen_outputs.py
python benchmarks/scripts/compare_frozen_outputs.py
```

## Supported files

MusicXML (`.xml`, `.musicxml`), MXL, MIDI (`.mid`, `.midi`); MXL zip safety checks before parsing.

## Export cache

`REGISTRAL_DISPERSION_CACHE_DIR` (also accepts `REGISTER_UNIFORMITY_CACHE_DIR`, `HOMOGENEITY_CACHE_DIR` — **legacy env names only**, not separate tools).

## Microtonal files exported from Sibelius

Some MusicXML exporters (notably **Sibelius 8**) write quarter-tone accidentals as **glyphs only**: `<accidental>quarter-sharp</accidental>` with `<alter>0</alter>`, and `<accidental>three-quarters-sharp</accidental>` with `<alter>1</alter>`. music21 then keeps the glyph name (`half-sharp` / `one-and-a-half-sharp`) but an **integer** `accidental.alter`, so `pitch.ps` is chromatic and the quarter-tone is lost.

`microtone_repair` (default **`off`**) controls an import-time step that runs **before** tie stripping:

| Mode | Behaviour |
|------|-----------|
| **`off`** | Current / historical behaviour: use the imported `<alter>`. Frozen benchmarks stay identical. |
| **`warn`** | Detect glyph/`<alter>` mismatches; do not change pitches; emit one warning with the mismatch count. |
| **`from_accidentals`** | Rewrite each mismatched accidental from its glyph name (`music21.pitch.Accidental(name)`), then propagate the repaired alter through the measure (same part/staff/step/octave until a new accidental or barline) and along ties. |

MIDI has no accidental glyphs; `microtone_repair` never rewrites MIDI and warns that pitch-bend is ignored. API: `microtone_repair` in `resolve_registral_dispersion_params`. CLI: `--microtone-repair`. Recorded in JSON/CSV as `microtone_repair`; applied repairs are listed in `repairs`.

## Checking what the tool actually read

Before trusting a span or centroid, inspect the **pitch inventory**: every Note and chord tone after microtone repair and optional sounding conversion, including unpitched/percussion rows that never enter the metrics (`used_in_metrics=False`).

Each row has a stable `note_id` (`part_index:measure:offset:voice:chord_index`) plus written and sounding names/`ps` (two decimals; quarter-tones as music21 names such as `A#~3` or `A#3 +50c`). Flags mark `microtone_repaired`, `transposed`, `unpitched`, `tied_continuation`, and `out_of_band`.

Below the table a one-line **digest** reports note count, unique sounding pitches, min, max, and the sorted unique list — the check against the score.

**Gradio** is two steps: **Load & inspect** fills an editable table (`sounding_ps` / `sounding_name`, `used_in_metrics`) and a per-part extra transposition (semitones, may be fractional); **Run analysis** uses that edited state. **CLI:** `inventory --out inventory.csv`. **API:** `run_registral_dispersion_analysis(..., params={"pitch_overrides": [...]})`. Overrides are saved/loaded as `<score>.pitch_overrides.json` (`--pitch-overrides path.json`). The written sidecar is `{"pitch_overrides_schema": "1", "pitch_overrides": [...]}`; the loader still accepts a bare list or `{"pitch_overrides": [...]}`.

`note_id`s and the inventory are computed **before** tie handling. A note-level override applies to the whole music21 tie chain and logs `propagated_to` (the other `note_id`s).

Order of operations: parse → microtone repair → sounding conversion → part-level overrides → note-level overrides → tie policy → event listing → metrics. Default `pitch_reference='written'` and empty overrides keep frozen benchmarks identical.

## Limitations

* **Symbolic notation only** (MusicXML, MXL, MIDI via **music21**): **no audio analysis**, no performance timing beyond notated durations.
* **MIDI** stores integer key numbers only; pitch-bend is ignored. Use MusicXML/MXL for quarter-tones, and `microtone_repair='from_accidentals'` when the file is a Sibelius-style glyph-only export.
* **No dynamics**, **no orchestration weighting**, **no automatic layer or staff detection**, **no psychoacoustic models**.
* **Tie behavior:** default **`tie_policy=as_imported`**. Use **`merge_ties`** to collapse tied segments via music21 `stripTies()` before analysis; record `tie_policy` in exports.
* **Numerical results depend on** the chosen **register band**, **`analysis_profile` / `pitch_sampling_mode`**, and **`observation_mode`** (fixed-window grid vs event-boundary segmentation).
* **Normalized** columns are **secondary**: they scale raw semitone metrics by the selected register width `R`; they are **not** perceptual “brightness”, orchestral spread, or acoustic density.
* **occupancy_entropy** is **not** registral dispersion; it is an optional **bin-occupancy evenness** index (historically related to register-uniformity / **U** workflows) kept for comparison.
* **No scalar named `registral_density`** is exported; informal “density” usually refers to the concentration heatmap or multiplicity-aware sampling—not a separate dispersion formula.
* **Pitch-class set, harmony, and global tessitura** as musical conclusions are **out of scope**: the tool only aggregates **absolute MIDI pitch** heights in-band for the configured temporal slices.

Extended discussion: **[docs/METRIC_SEMANTICS.md](docs/METRIC_SEMANTICS.md)** (§12).

## Copyright and use

Copyright © 2026 Luís Raimundo. All rights reserved.

This repository and its contents are proprietary research material. **No open-source licence is granted.** See **[COPYRIGHT.md](COPYRIGHT.md)**.

**Contact:** [lmr.2020@outlook.pt](mailto:lmr.2020@outlook.pt)

## Acknowledgements

Developed with support from FCT and Universidade NOVA de Lisboa (DOI: [10.54499/2020.08817.BD](https://doi.org/10.54499/2020.08817.BD)). The author thanks Isabel Pires for her support. See **[ACKNOWLEDGEMENTS.md](ACKNOWLEDGEMENTS.md)**.
