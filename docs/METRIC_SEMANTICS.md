# Metric semantics and interpretive limits

**Tool:** **Registral_Dispersion** (`registral-dispersion` v0.3.0)  
**Status:** methodological reference (aligned with `src/registral_dispersion/analyzer.py`, `concentration_map.py`, and export metadata)

This document defines what the exported numbers **mean**, what they **do not** mean, and how to use them in musicological interpretation. For advised parameter sets, see [PARAMETERIZATION_GUIDE.md](PARAMETERIZATION_GUIDE.md).

---

## 1. Scope and methodological status

The metrics in this repository are **symbolic, score-derived descriptors** of **registral distribution**. They are computed from **parsed notated pitch events** (MusicXML, MXL, or MIDI via **music21**), not from audio waveforms.

They are **not**:

- direct **acoustic**, **spectral**, **timbral**, or **dynamic** measurements;
- **perceptual**, **psychoacoustic**, or **orchestration-density** models;
- measures of **harmony**, **pitch-class set structure**, or **textural rhythm** unless you derive those separately from the exported tables.

The tool measures **how notated or parsed pitch events occupy and distribute themselves across register** within user-defined temporal supports (moving windows or event-boundary intervals) and within a user-defined registral band `[register_low, register_high]`.

Every export should record **`analysis_profile`**, **`pitch_sampling_mode`**, **`observation_mode`**, **`tie_policy`**, **`microtone_repair`**, **`pitch_reference`**, register bounds, and **`symbolic_score_only: true`** (JSON schema 1.11) so results remain reproducible and interpretable.

---

## 2. Core vocabulary

| Term | Meaning in this tool |
|------|----------------------|
| **Pitch event** | A **notated** `Note` or each pitch in a `Chord` listed from `score.flatten().notes`. Rests, clefs, and non-note objects are excluded. |
| **Active pitch event** | A pitch event whose **notated sounding** overlaps the current temporal support: `onset < t_end` and `onset + quarterLength > t_start`. Sustained notes remain active across their full notated duration, not only at attack. |
| **Register** | Absolute **MIDI pitch space** (semitones, `pitch.ps`), restricted to the analytical band between **`register_low`** and **`register_high`** (inclusive). This is **not** pitch-class reduction. |
| **Registral span** | Extremal vertical spread: `max(pitches) − min(pitches)` in semitones. Identical to **`dispersion_degree`**. |
| **Registral space** | The selected semitone band `R = register_high_midi − register_low_midi` used as the analytical frame; normalized columns scale raw distances by `R`. |
| **Registral occupancy** | Which semitone heights (or bins) have at least one active sampled pitch in a temporal support. Used implicitly by **`occupancy_entropy`** and the concentration map. |
| **Registral concentration** | **Local clustering** of activity in register (many components in a narrow band). Described by low span, low pairwise distance, low entropy, or high heatmap intensity in a few rows—not by a single scalar named “concentration” in dispersion exports. |
| **Registral dispersion** | **Vertical opening / compression** of the active pitch set: operationalized primarily by **registral span** (`dispersion_degree`) and secondarily by **mean pairwise registral distance**. |
| **Sampling point / window** | The temporal support on which pitches are aggregated: either a **symmetric moving window** (`fixed_window`) or a **half-open event interval** `[interval_start, interval_end)` (`event_boundaries`). |
| **Observation** | How time is segmented before metrics are computed (`observation_mode`). Same formulas apply to the active pitch set in each segment; only the **time indexing** changes. |
| **Profile (`analysis_profile`)** | Research stance linking interpretation to implied **`pitch_sampling_mode`**: `occupied_space` (geometry of occupied heights) vs `component_weighted` (multiplicity of notated components). |
| **`pitch_sampling_mode`** | How the list of MIDI heights is built **before** span, pairwise, centroid, std, and entropy: **`unique_pitch_heights`** (distinct MIDI values) vs **`event_instances`** (every in-register contribution kept). |

**Chords:** each member of `Chord.pitches` that lies in the register band is a **separate pitch event** before optional deduplication. A three-note chord contributes three heights under `event_instances`; under `unique_pitch_heights`, duplicates at the same MIDI value collapse to one.

**Simultaneities:** all parts are merged via `flatten()`; cross-part unisons count as separate instances when using `event_instances`.

---

## 3. `registral_span` / `dispersion_degree`

### Implementation (exact)

For active sampled pitches `p = (p_1, …, p_n)` in a temporal support:

```
registral_span = dispersion_degree = max(p) − min(p)    (semitones)
```

Source: `RegistralDispersionAnalyzer.compute_registral_span` → `numpy.ptp(pitches)`.

| Case | Value |
|------|--------|
| `n = 0` (no active in-register pitches) | **NaN** |
| `n = 1` | **0** |
| `n ≥ 2` | `max − min` |

**Normalized:** `normalized_registral_span = normalized_dispersion_degree = registral_span / R`, where `R = register_high_midi − register_low_midi`.

### Interpretation

- Measures **extremal registral spread** only (lowest and highest active pitch).
- **Insensitive to internal distribution**: a sparse two-note octave and a dense chord filling that octave share the same span.
- **Transposition-invariant** within each row (depends only on relative pitch distances, not note names).
- **Does not measure** how many distinct registral zones are used, how evenly they are filled, or how many parts contribute.

---

## 4. `mean_pairwise_registral_distance`

### Implementation (exact)

For `n` sampled pitches (after `pitch_sampling_mode`):

```
D_pairwise = (2 / (n(n−1))) × Σ_{i<j} |p_i − p_j|
           = mean of |p_i − p_j| over all unordered distinct pairs i < j
```

Source: `compute_mean_pairwise_registral_distance` (upper-triangle sum × `2/(n(n−1))`).

| Case | Value |
|------|--------|
| `n = 0` | **NaN** |
| `n = 1` | **0** |
| `n ≥ 2` | as above |

**Normalized:** `normalized_mean_pairwise_registral_distance = D_pairwise / R`.

### Interpretation

- Measures **average internal separation** among active pitches.
- **More sensitive to distribution** than span alone: clustered inner voices with extreme outer notes can yield high span but moderate pairwise distance; polarized low/high duos can yield high pairwise distance relative to span.
- Under **`unique_pitch_heights`**, duplicate MIDI values do not inflate `n`; under **`event_instances`**, repeated unisons **do** increase `n` and can change pairwise distance while span stays unchanged.
- **Does not measure** temporal rearticulation rate, rhythmic density, or orchestration timbre.

---

## 5. `occupancy_entropy`

### Implementation (exact)

1. Build semitone **histogram bins** over the analytical register:  
   `bin_edges = linspace(register_low − 0.5, register_high + 0.5, n_bins + 1)` with  
   `n_bins = max(1, round(register_high − register_low) + 1)`.
2. Count sampled pitches into bins (`numpy.histogram`).
3. Let `p_k = count_k / total` for bins with `count_k > 0`.
4. Shannon entropy ( **natural logarithm**, base **e** ):  
   `H = − Σ_k p_k log(p_k)`.
5. Normalize by maximum entropy for uniform occupancy over `n_bins`:  
   `occupancy_entropy = clip(H / log(n_bins), 0, 1)`.

| Case | Value |
|------|--------|
| `n = 0` | **NaN** |
| `n = 1` | **0** (single occupied bin) |
| all mass in one bin | **0** |
| uniform over all occupied bins (max spread) | approaches **1** |

### Interpretation

- Measures **evenness of semitone-bin occupancy** within the selected register band for the active pitch sample—not vertical **opening** (span) or **pairwise separation**.
- **Higher entropy** → more **evenly distributed** occupancy across bins (given the current pitch sample).
- **Lower entropy** → **concentration** in fewer registral zones.
- **Not automatically “better” or “more dispersed”** without context: high entropy can coexist with low span (many pitches in a narrow band spread across adjacent bins).
- Historically related to legacy **register-uniformity / U** workflows; retained for comparison, **not** as the canonical dispersion read.

---

## 6. `registral_density` / occupancy density

**There is no exported scalar named `registral_density` in the current codebase.**

Related quantities you may use—each with distinct semantics:

| Quantity | What it reflects | Formula / source |
|----------|------------------|------------------|
| **`active_note_count`** | Length of the pitch array **after** `pitch_sampling_mode` | Integer per row; not normalized by register width |
| **Occupied-bin fraction** (derived) | Share of semitone bins with count > 0 in a window | Not exported; can be computed from histogram logic used by entropy |
| **`occupancy_entropy`** | **Evenness** of bin counts, not “how many bins are filled” | See §5 |
| **Concentration map cell values** | **Count** of active notated components per integer MIDI row × time bin | See §7; visualization-only module |

**Clarifications:**

- The tool does **not** divide occupied positions by available range as a primary dispersion metric.
- **`event_instances`** counts repeated pitches; **`unique_pitch_heights`** counts distinct MIDI values only.
- **Normalized span/pairwise** scale by full band width `R` but describe **distance**, not **occupancy fraction**.
- **Event density** (attacks per time) and **textural/orchestral density** (acoustic mass, doubling policy) are **out of scope** unless you derive them from raw event lists outside this package.

When documentation or UI uses informal “density,” it usually refers to the **concentration heatmap** (notational activity per register-time cell) or to **multiplicity-aware** (`component_weighted`) sampling—not to a separate registral-density formula.

---

## 7. Concentration map

### What it represents

A **symbolic pitch–time heatmap** of **notational occupancy** (`concentration_map.py`). It is **visualization-only** and does **not** alter dispersion metrics.

### Matrix structure

- **Rows:** integer MIDI pitches from `ceil(register_low)` to `floor(register_high)` (inclusive).
- **Columns:** half-open time bins `[k·Δt, (k+1)·Δt)` from score start through score duration (`time_bin_size = Δt`).
- **Cell value (raw):** count of active **notated** components at that MIDI height in that bin.

**Overlap rule** (same as dispersion): `onset < bin_end` and `onset + quarterLength > bin_start`.

**`concentration_mode`:**

| Mode | Cell count |
|------|------------|
| **`event_instances`** (default) | Each overlapping component increments its MIDI row (cross-part unisons add). |
| **`unique_pitch_heights`** | At most **1** per distinct integer MIDI pitch per bin. |

### Colour / intensity

Display normalization is **cosmetic only** (`--normalization` / `display_normalization`):

| Mode | Effect |
|------|--------|
| **`log1p_counts`** (default) | `log(1 + count)` — accentuates populated cells |
| **`raw_counts`** | Raw component counts |
| **`column_normalized`** | Each time column ÷ its max |
| **`global_normalized`** | Entire matrix ÷ global max |

Exported matrix CSV/NPZ stores **raw counts**, not normalized display values.

### What to infer — and what not to

**May support:** where registral activity **clusters** over time; visual comparison with dispersion curves overlaid via `dispersion_overlay_from_results`.

**Do not infer:** audio energy, loudness, timbral salience, orchestration weight, or perceptual “brightness.” Warmer colour means **more notated components** in that register-time cell, not louder sound.

---

## 8. Sampling and observation semantics

### Active events over time

- Candidates come from **`flatten().notes`** (`Note`, `Chord` only).
- **Sustained notes** contribute across the **whole notated duration** wherever overlap holds—not only at onset.
- **Register filter:** pitches outside `[register_low, register_high]` are excluded before sampling.

### Ties (`tie_policy`)

| Policy | Behaviour |
|--------|-----------|
| **`as_imported`** (default) | Preserve music21 import structure; tied chains may appear as one long `Note` or several tied segments. |
| **`merge_ties`** | Run `stripTies(inPlace=False)` before listing; collapse continuations where music21 allows. |

Tie choice changes **which objects** exist in the flat stream and therefore sustained vs fragmented contributions.

### `pitch_sampling_mode`

| Mode | Effect on pitch list |
|------|----------------------|
| **`unique_pitch_heights`** | `numpy.unique` on in-register MIDI values in the support |
| **`event_instances`** | Keep every in-register contribution (chord tones, doublings, cross-part unisons) |

Implied by **`analysis_profile`** unless an explicit `pitch_sampling_mode` key overrides (`pitch_sampling_source` recorded in exports).

### `microtone_repair`

Import-time handling of MusicXML accidental glyphs whose stored `<alter>` does not match the glyph name (Sibelius 8: `quarter-sharp` + `<alter>0</alter>`, `three-quarters-sharp` + `<alter>1</alter>`).

| Mode | Effect |
|------|--------|
| **`off`** (default) | Use music21's imported `pitch.ps` (integer when `<alter>` is integer). |
| **`warn`** | Detect mismatches; do not rewrite; one warning with the count `N`. |
| **`from_accidentals`** | Set `pitch.accidental = Accidental(name)` (keep `displayStatus`) for each mismatch, then propagate the repaired alter in-measure and across ties. |

MIDI is never rewritten. Applied edits are listed in export field `repairs`. Values are not comparable across modes for the same glyph-only file.

### Order of operations

Pitches that enter the metrics are produced in this order (do not compare results across skipped steps):

1. **parse** (MusicXML / MXL / MIDI via music21)
2. **microtone repair** (`microtone_repair`)
3. **sounding conversion** (copy + `toSoundingPitch()` when `pitch_reference='sounding'`)
4. **part-level overrides** (extra transposition in semitones, may be fractional)
5. **note-level overrides** (manual `sounding_ps` / exclude; applied to the whole pre-tie chain and logged as `propagated_to`)
6. **tie policy**
7. **event listing**
8. **metrics**

### `pitch_reference`

| Mode | Effect |
|------|--------|
| **`written`** (default) | Analyze notated MIDI `pitch.ps`. Frozen benchmarks stay identical. If transposing parts exist (`Instrument.transposition` or MusicXML `<transpose>`), a warning lists them and states that metrics are **not** in sounding pitch. |
| **`sounding`** | After repair, convert a **copy** of the score with music21 `toSoundingPitch()` (chromatic transpositions such as Horn in F / Bb clarinet, and octave-change instruments such as double bass). |

The pitch inventory always shows both written and sounding columns. Transposing parts are recorded in `transposing_parts` (`part`, `instrument`, `interval_semitones`). Manual edits are listed in `pitch_overrides` (`manual_pitch` | `manual_exclude` | `part_transposition`).

### `register_low` / `register_high`

- Parsed to MIDI **`pitch.ps`** (note names or numeric).
- Define the **analytical registral frame**: pitches outside the band are ignored; **`R`** sets normalized denominators and entropy bin layout.
- **Results depend strongly on this band**—narrow bands cap span and change entropy bin count.

### `observation_mode`

| Mode | Temporal support |
|------|------------------|
| **`fixed_window`** | Window center `t`, support `[t − window_size/2, t + window_size/2]` on grid `time_step` |
| **`event_boundaries`** | Maximal intervals where the active in-register pitch set is constant; `[interval_start, interval_end)` |

Same metric formulas on each support; empty intervals still emit rows with **NaN** dispersion fields and `active_note_count = 0`.

---

## 9. Interpretation table

| Metric / setting | Measures | Does not measure | Main interpretive risk |
|------------------|----------|------------------|-------------------------|
| **`registral_span` / `dispersion_degree`** | Extremal vertical spread (semitones) | Internal spacing, bin evenness, multiplicity | Equating span with “richness” or orchestration width |
| **`mean_pairwise_registral_distance`** | Mean pair separation among sampled pitches | Absolute tessitura, harmonic tension | Ignoring `pitch_sampling_mode` when comparing scores with doublings |
| **`occupancy_entropy`** | Evenness of semitone-bin occupancy | Vertical opening, loudness, perceptual uniformity | Treating entropy as dispersion or as inherently “better” when high |
| **Registral / occupancy density (informal)** | *(no single export)* — see §6 | Acoustic or orchestral density | Using heatmap colour or colloquial “density” as a dispersion substitute |
| **Concentration map** | Notational activity per MIDI row × time | Audio energy, dynamics, timbre | Reading colour as loudness or psychoacoustic salience |
| **`register_low` / `register_high`** | Analytical band and normalization frame | Composer-intended “correct” register labels | Narrow bands artificially compress span and entropy |
| **`pitch_sampling_mode`** | Whether duplicates count in `n` | Changing span formula | Mixing `event_instances` and `unique_pitch_heights` across a corpus |
| **`analysis_profile`** | Recommended primary read (geometry vs multiplicity) | New formulas | Switching profiles mid-study without recording exports |
| **`observation_mode`** | Time segmentation | Onset density or rhythmic complexity | Comparing duration-weighted globals from `event_boundaries` with sampled means from `fixed_window` without comment |

---

## 10. Examples of interpretive distinctions

1. **High span, low occupancy density (informal):** Two notes at registral extremes yield a large span but only two occupied heights (low bin occupancy; entropy depends on band width).

2. **Low span, high local concentration:** A dense cluster in the middle register yields small span and small pairwise distance; the concentration map may show bright bands in few rows.

3. **Same span, different pairwise distance:** `{C3, G3}` and `{C3, C4, G3}` can share span 19 semitones but differ in mean pairwise distance (especially under `event_instances` if doublings are present).

4. **Entropy vs span:** Pitches spread across many bins with similar counts yield **high entropy**; pitches confined to a cluster yield **low entropy**—even when span is identical between cases with different bin filling patterns.

5. **Sustained field vs rearticulation:** A long held chord and a rapid rearticulation pattern may produce similar **registral dispersion** in overlapping windows but very different **temporal/event behaviour**, which this tool does **not** primarily quantify (use event lists, separate onset metrics, or `event_boundaries` segmentation for state-level reading).

---

## 11. Relation to musicological use

Used **together**, the metrics can support discussion of:

| Phenomenon | Useful metrics / views |
|------------|-------------------------|
| **Registral expansion / contraction** | `registral_span` trajectory; `event_boundaries` intervals |
| **Polarization** (low vs high registral anchors) | High span with moderate pairwise distance vs compact clusters |
| **Concentration / saturation** | Low span + low entropy + bright heatmap bands |
| **Stratification** | Heatmap rows; entropy; multiple stable centroid levels over time |
| **Register migration** | `registral_centroid`, heatmap drift (centroid is absolute tessitura) |
| **Registral stability** | Low variance of span/centroid across adjacent intervals |

**Do not** treat any single scalar (especially one global summary number) as complete evidence. Combine **span**, **pairwise**, optional **entropy**, **centroid/std**, temporal segmentation, and the **concentration map** with explicit **`analysis_profile`** and register bounds.

---

## 12. Limitations

- **No audio analysis** — no waveform, spectrum, or performance timing beyond notated `quarterLength`.
- **No spectral density** or timbral density.
- **No perceptual validation** — normalized values are **not** psychoacoustic units.
- **No orchestration-weighted acoustic model** unless you implement one externally.
- **Symbolic parsing quality** depends on MusicXML/MXL/MIDI encoding and **music21** import (transposition, ties, divisi, percussion spelling). Some exporters (Sibelius 8) write microtonal **glyphs** with an integer `<alter>`; default `microtone_repair='off'` then yields integer `pitch.ps`. Use `from_accidentals` to restore the glyph inflection, or `warn` to detect the mismatch without changing numbers.
- **MIDI** cannot recover quarter-tones (pitch-bend is ignored); `microtone_repair` does not rewrite MIDI.
- **Transposition, tie, sampling, and register assumptions** must be documented per analysis from export metadata (`tie_policy`, `pitch_reference`, `pitch_sampling_source`, `observation_mode`, `microtone_repair`, bounds, `package_version`). Default written-pitch analysis does **not** apply concert-pitch conversion; use `pitch_reference='sounding'` and check the pitch inventory digest against the score.

---

## 13. Quick formula reference

```
dispersion_degree = registral_span = max(p) − min(p)

mean_pairwise_registral_distance = (2/(n(n−1))) Σ_{i<j} |p_i − p_j|

occupancy_entropy = H / log(n_bins)
  H = − Σ_k p_k log(p_k)     (natural log, base e)
  p_k = bin_count_k / Σ bin_counts

normalized_* = raw_* / R     (for span, pairwise, std)
normalized_registral_centroid = (centroid − register_low) / R

R = register_high_midi − register_low_midi
```

**Canonical per-row dispersion read:** **`dispersion_degree`** (= `registral_span`).  
**Supplementary:** `mean_pairwise_registral_distance`, `registral_centroid`, `registral_std`, optional `occupancy_entropy`.  
**Complementary visualization:** registral concentration map (raw notational counts).

---

## 14. See also

- [README.md](../README.md) — install, CLI, defaults
- [PARAMETERIZATION_GUIDE.md](PARAMETERIZATION_GUIDE.md) — advised presets for static, moving, and summarize workflows
- [REGISTRAL_REGRESSION_FIXTURES.md](REGISTRAL_REGRESSION_FIXTURES.md) — controlled MusicXML fixtures for qualitative metric invariants (Phase 1)
- Export strings in `src/registral_dispersion/metric_documentation.py` (mirrored in CSV `#` comments and JSON)
