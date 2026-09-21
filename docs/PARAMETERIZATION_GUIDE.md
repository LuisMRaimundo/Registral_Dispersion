# Registral dispersion — recommended parameterization

**Tool:** **Registral_Dispersion** (`registral-dispersion` v0.3.0)  
**Purpose:** advised settings for common research setups in symbolic-score registral dispersion analysis:

**Metric definitions and interpretive limits:** [METRIC_SEMANTICS.md](METRIC_SEMANTICS.md)

1. **Static vertical aggregate** — the vertical registral “state” at each moment (or over the whole score), without arbitrary temporal smoothing.
2. **Moving fragment** — how registral dispersion **evolves** along the score via sliding temporal windows.
3. **One-number global summary** — duration-weighted whole-score aggregate via `summarize` CLI/API.

All values below assume **MusicXML / MXL / MIDI** input parsed by **music21**. Results are **symbolic** (not acoustic).

---

## Shared concepts (both setups)

| Concept | Recommended default | Notes |
|--------|---------------------|--------|
| **Register preset** | **A0–C8 (full notated range)** | Results depend on the band. Normalized columns scale by `R = register_high − register_low`. |
| **Raw vs normalized** | **Raw semitones** for primary publication; **normalized_*** for cross-score comparison with different register bounds | Normalized values are **not** perceptual brightness. |
| **Heatmap (complement)** | Always include when exploring register **notational occupancy** (informal “density”) | Independent of dispersion formulas; use **registral_ember** + **log1p_counts**. See [METRIC_SEMANTICS.md](METRIC_SEMANTICS.md) §7. |
| **Exports** | Always keep **CSV + JSON** | JSON records `analysis_profile`, `pitch_sampling_mode`, `observation_mode`, `microtone_repair`, `pitch_reference`, formulas, and `package_version`. Also keep `{prefix}_pitch_inventory.csv` from batch `analyze`. |
| **`microtone_repair`** | **`off`** | Leave imported `<alter>` unchanged (reproducible default). Use **`warn`** to detect Sibelius-style glyph/`<alter>` mismatches, or **`from_accidentals`** to restore quarter-tones from the accidental glyph before analysis. MIDI is never rewritten. |
| **`pitch_reference`** | **`written`** | Analyze notated pitches (reproducible default; frozen benchmarks stay identical). Use **`sounding`** for concert pitch (`toSoundingPitch()` after repair). Inspect the **pitch inventory** digest before publishing. |

### Analysis profile (choose one stance)

| Profile | Implied sampling | Use when |
|---------|------------------|----------|
| **`occupied_space`** *(advised default)* | `unique_pitch_heights` | You care about **geometry of occupied pitch heights** (opening/compression of registral space). Doublings at the same pitch do **not** inflate dispersion. **Primary read:** `registral_span`. |
| **`component_weighted`** | `event_instances` | Doublings, divisi unisons, and repeated noteheads **should** count (orchestral **mass** in register). **Primary read:** `mean_pairwise_registral_distance`. |

**Do not mix interpretations** across corpora: pick one profile and keep it fixed.

---

# 1. Static vertical aggregate

## Research question

*What is the vertical registral configuration while a given score state holds?*  
Each row describes a **fixed set of sounding pitches** — no moving-window blur.

## Recommended observation mode

**`event_boundaries`**

- One row per maximal interval `[interval_start, interval_end)` where the active in-register pitch set is **constant**.
- `window_size` is **ignored** for segmentation (still accepted by the API).
- `time_step` is **unused** for indexing (still stored in exports).

## Advised parameter set

| Parameter | UI / API value | Rationale |
|-----------|----------------|-----------|
| `observation_mode` | **`event_boundaries`** | Exact notational vertical states |
| `analysis_profile` | **`occupied_space`** | Density-independent vertical geometry |
| `pitch_sampling_mode` | *(omit — implied)* → `unique_pitch_heights` | Do not override unless you deliberately want event instances |
| `register_low` | **`A0`** | Full notated range (low) |
| `register_high` | **`C8`** | Full notated range (high) |
| `time_step` | **`0.25`** | Inert for segmentation; keep default for export compatibility |
| `window_size` | **`4.0`** | Inert for segmentation; keep default for export compatibility |
| `microtone_repair` | **`off`** | Keep unless the MusicXML is a Sibelius-style glyph-only quarter-tone export |
| `pitch_reference` | **`written`** | Keep unless the research question is concert-pitch register (transposing scores) |

### Primary metrics to read (per interval)

| Metric | Role in static vertical reading |
|--------|----------------------------------|
| **`dispersion_degree`** / **`registral_span`** | **Primary** — canonical vertical opening (semitones); identical values |
| **`mean_pairwise_registral_distance`** | Secondary — mean pair separation (can diverge from span/degree if clustering is uneven) |
| **`registral_centroid`** | Where the vertical mass sits (absolute tessitura) |
| **`registral_std`** | Tight vs loose clustering around the centroid |
| **`normalized_registral_span`** | Compare segments when register band is fixed |
| **`occupancy_entropy`** | Optional — bin evenness; **not** dispersion (use only comparatively) | See [METRIC_SEMANTICS.md](METRIC_SEMANTICS.md) §5 |

### Post-processing: whole-score static summary

The tool outputs **one row per constant state**, not a single global number. For a **single aggregate** over the entire piece:

**Option A — duration-weighted mean (recommended):**

```
For each interval i with duration d_i:
  weight w_i = d_i / sum(d_i)
  aggregate_span = sum(w_i * registral_span_i)   # skip NaN rows (rests)
```

Use the same weighting for `mean_pairwise_registral_distance`, `registral_centroid`, etc.

**Option B — one full-score window (single row):**

Use only if you need one CSV row for the entire work:

| Parameter | Value |
|-----------|--------|
| `observation_mode` | **`fixed_window`** |
| `window_size` | **`≥ 2 × score_duration`** (quarterLength) |
| `time_step` | **`≥ score_duration`** |
| Other settings | Same as table above |

This yields essentially **one window** covering the full sounding span. Less precise than `event_boundaries` for internal registral change, but valid as a **global vertical summary**.

### Heatmap (static vertical complement)

| Parameter | Advised value |
|-----------|---------------|
| Include heatmap | **Yes** |
| Time bin size | **`0.25`** qL (finer: `0.125` for short gestures) |
| Counting mode | **`event_instances`** (shows doublings / orchestral mass) |
| Color scaling | **`log1p_counts`** |
| Palette | **`registral_ember`** |

**Read:** horizontal bands = sustained register occupation; vertical extent of bright regions ≈ registral footprint over time.

### UI checklist (static vertical aggregate)

- [ ] Register preset: **A0 to C8 (full notated range)**
- [ ] Temporal observation: **event_boundaries**
- [ ] Analysis profile: **occupied_space**
- [ ] Pitch sampling override: **(from profile)**
- [ ] Include concentration heatmap: **checked**
- [ ] Overlay mean pairwise distance: optional (secondary axis; primary curve is `dispersion_degree`)
- [ ] Plot normalized y-axis: **off** (prefer raw semitones for publication)

### CLI (static vertical aggregate)

```bash
python -m registral_dispersion analyze ^
  --score "path/to/score.musicxml" ^
  --out-dir "./out_static_vertical" ^
  --prefix "static_vertical" ^
  --register-low A0 ^
  --register-high C8 ^
  --observation-mode event_boundaries ^
  --analysis-profile occupied_space ^
  --microtone-repair off ^
  --plot-pairwise
```

Heatmap (separate export):

```bash
python -m registral_dispersion concentration-map ^
  --score "path/to/score.musicxml" ^
  --out "./out_static_vertical/concentration.png" ^
  --register-low A0 ^
  --register-high C8 ^
  --time-bin-size 0.25 ^
  --mode event_instances ^
  --normalization log1p_counts ^
  --colormap registral_ember
```

### Python API (static vertical aggregate)

```python
from registral_dispersion import run_registral_dispersion_analysis

params_static = {
    "observation_mode": "event_boundaries",
    "analysis_profile": "occupied_space",
    "register_low": "A0",
    "register_high": "C8",
    "time_step": 0.25,
    "window_size": 4.0,
}

out = run_registral_dispersion_analysis("score.musicxml", params_static)
# Primary columns: out["results"]["registral_span"], interval_start, interval_end, interval_duration
```

---

# 2. Moving fragment

## Research question

*How does registral dispersion **change over time** along the score?*  
Sliding windows produce a **continuous (sampled) trajectory** of vertical opening/compression.

## Recommended observation mode

**`fixed_window`**

- Symmetric window `[t − w/2, t + w/2]` at each grid point `t`.
- **`time_step`** = grid spacing; **`window_size`** = window length (both in quarterLength).

## Advised parameter set

| Parameter | UI / API value | Rationale |
|-----------|----------------|-----------|
| `observation_mode` | **`fixed_window`** | Moving temporal support |
| `analysis_profile` | **`occupied_space`** | Registral geometry (default) |
| `pitch_sampling_mode` | *(omit)* → `unique_pitch_heights` | — |
| `register_low` | **`A0`** | Full notated range (low) |
| `register_high` | **`C8`** | Full notated range (high) |
| **`time_step`** | **`0.25`** qL | Standard grid: sixteenth-note at ♩=60; good balance detail / stability |
| **`window_size`** | **`4.0`** qL | ~one bar at 4/4 ♩=60; smooths local texture without hiding bar-level change |
| `microtone_repair` | **`off`** | Keep unless the MusicXML is a Sibelius-style glyph-only quarter-tone export |
| `pitch_reference` | **`written`** | Keep unless the research question is concert-pitch register (transposing scores) |

### Alternative window sizes (same time_step)

| Goal | `window_size` | `time_step` | Comment |
|------|---------------|-------------|---------|
| **Fine gesture / local fragmentation** | **1.0–2.0** qL | **0.125–0.25** | More reactive; noisier curves |
| **Standard (advised)** | **4.0** qL | **0.25** | Default research balance |
| **Section / phrase level** | **8.0–16.0** qL | **0.5–1.0** | Smoother; use for long orchestral spans |
| **Very long works (operas, Mahler)** | **8.0** qL | **0.5** | Reduces row count and high-frequency jitter |

**Rule of thumb:** keep `window_size / time_step` between **8 and 32** (enough overlap for smooth curves without excessive redundancy).

### Primary metrics to read (moving fragment)

| Metric | Role in temporal reading |
|--------|---------------------------|
| **`dispersion_degree`** / **`registral_span`** | **Primary curve** (UI and PNG default) — smoothed vertical opening trajectory |
| **`mean_pairwise_registral_distance`** | Optional overlay — mean pair separation (enable when doublings matter or under `component_weighted`) |
| **`registral_centroid`** | Tessitura drift over time (export from CSV) |
| **`registral_std`** | Cluster tightness evolution |
| **`normalized_dispersion_degree`** | Compare scores with same band |

### Plot options (moving fragment)

| UI option | Advised |
|-----------|---------|
| Overlay mean pairwise distance | **On** when comparing span vs mean separation; **off** for minimal occupied-space curves |
| Show occupancy entropy | **Off** by default — enable only for bin-evenness comparison |
| Plot normalized y-axis | **Off** for single-score study; **On** for cross-score corpus |
| Interactive plots | **On** (Plotly) |
| Include heatmap | **On** — align heatmap bin size with **`time_step`** |

### Heatmap (moving fragment complement)

| Parameter | Advised value |
|-----------|---------------|
| Time bin size | **Same as `time_step`** → **`0.25`** qL |
| Counting mode | **`event_instances`** |
| Color scaling | **`log1p_counts`** |
| Palette | **`registral_ember`** |

Aligning heatmap bins with dispersion grid makes visual comparison straightforward.

### UI checklist (moving fragment)

- [ ] Register preset: **A0 to C8 (full notated range)**
- [ ] Temporal observation: **fixed_window**
- [ ] Time step / heatmap bin: **0.25**
- [ ] Window size: **4.0**
- [ ] Analysis profile: **occupied_space**
- [ ] Include concentration heatmap: **checked**
- [ ] Overlay mean pairwise distance: optional (primary = `dispersion_degree`)
- [ ] Show occupancy entropy: **unchecked** (unless studying uniformity)

### CLI (moving fragment)

```bash
python -m registral_dispersion analyze ^
  --score "path/to/score.musicxml" ^
  --out-dir "./out_moving_fragment" ^
  --prefix "moving_fragment" ^
  --register-low A0 ^
  --register-high C8 ^
  --observation-mode fixed_window ^
  --time-step 0.25 ^
  --window-size 4.0 ^
  --analysis-profile occupied_space ^
  --microtone-repair off ^
  --plot-pairwise
```

Combined workflow (dispersion + heatmap via UI): click **Run analysis** once with the settings above.

### Python API (moving fragment)

```python
from registral_dispersion import run_registral_dispersion_analysis

params_moving = {
    "observation_mode": "fixed_window",
    "analysis_profile": "occupied_space",
    "register_low": "A0",
    "register_high": "C8",
    "time_step": 0.25,
    "window_size": 4.0,
}

out = run_registral_dispersion_analysis("score.musicxml", params_moving)
# Primary curve: out["results"]["dispersion_degree"] vs out["results"]["t"]
```

---

# Quick comparison

| | **Static vertical aggregate** | **Moving fragment** |
|---|------------------------------|---------------------|
| **Observation** | `event_boundaries` | `fixed_window` |
| **Time logic** | One row per **constant pitch set** | One row per **sliding window** |
| **Primary metric** | `dispersion_degree` / `registral_span` | `dispersion_degree` (curve); pairwise optional overlay |
| **Profile** | `occupied_space` | `occupied_space` |
| **Register** | A0–C8 | A0–C8 |
| **time_step** | 0.25 (inert) | **0.25** (active grid) |
| **window_size** | 4.0 (inert) | **4.0** (active) |
| **Heatmap Δt** | 0.25 | **0.25** (= time_step) |
| **Best for** | Segment taxonomy, vertical states, orchestration snapshots | Trajectories, climaxes, registral expansion/contraction over time |

---

# 3. One-number global summary

## Research question

*What is a single whole-score registral dispersion value for this symbolic score?*

## Recommended path

`summarize_registral_dispersion` (API) or `python -m registral_dispersion summarize` (CLI).

| Parameter | Advised value |
|-----------|---------------|
| `observation_mode` | **`event_boundaries`** |
| `analysis_profile` | **`occupied_space`** |
| `register_low` / `register_high` | **A0 / C8** |
| `tie_policy` | **`as_imported`** (or **`merge_ties`** for tied scores) |
| `microtone_repair` | **`off`** (or **`from_accidentals`** for Sibelius glyph-only quarter-tone MusicXML) |
| `pitch_reference` | **`written`** (or **`sounding`** for concert-pitch register on transposing scores) |

Primary: **`duration_weighted_registral_span`**. Secondary: **`duration_weighted_mean_pairwise_registral_distance`**.

```bash
python -m registral_dispersion summarize --score "path/to/score.musicxml" --out-json summary.json
```

```python
from registral_dispersion import summarize_registral_dispersion
out = summarize_registral_dispersion("score.musicxml")
print(out["primary_metric"], out["primary_value"], out["warnings"])
```

Do not use `fixed_window` for a duration-weighted one-number unless you accept a sampled trajectory summary (warning emitted).

---

# When to switch to `component_weighted`

Use **`analysis_profile: component_weighted`** (implies `event_instances`) if the research question explicitly includes:

- double octaves and massed unisons;
- divisi doubling at the same pitch;
- orchestrational **weight** rather than pure registral geometry.

Then treat **`mean_pairwise_registral_distance`** as primary in both setups.

---

# Reproducibility checklist (publication)

1. Record **`package_version`** from JSON export.  
2. Archive **exact parameter dict** (this document + your score path).  
3. State **register band** and **profile** in the paper methods section.  
4. Distinguish **dispersion metrics** from **occupancy_entropy** and from **concentration-map notational occupancy** (not acoustic density). See [METRIC_SEMANTICS.md](METRIC_SEMANTICS.md).  
5. Record **`tie_policy`**, **`microtone_repair`**, **`pitch_reference`**, **`global_summary`**, the pitch-inventory digest, and any **`warnings`** / **`repairs`** / **`pitch_overrides`** from JSON export (sidecar envelope `pitch_overrides_schema: "1"`; note-level `propagated_to` across ties).  
6. Run **`benchmarks/scripts/compare_frozen_outputs.py`** after intentional code changes (synthetic fixtures only).

---

*Document version: 2026-09-21 — matches Registral_Dispersion / registral-dispersion 0.3.0 (plotting: primary `dispersion_degree`; JSON schema 1.11; `microtone_repair`; `pitch_reference`).*
