# Registral regression fixtures (Phase 1)

**Tool:** **Registral_Dispersion**

**Location:** `corpus/fixtures/registral_regression/`  
**Generator:** `corpus/scripts/create_registral_regression_fixtures.py`  
**Inspection report:** `corpus/reports/registral_regression_inspection.md` (exploratory, not golden)  
**Tests:** `tests/test_registral_regression_fixtures.py`  
**Metric semantics:** [METRIC_SEMANTICS.md](METRIC_SEMANTICS.md)

---

## Purpose

This suite provides **controlled, deterministic MusicXML fixtures** for **qualitative regression** of registral-dispersion behaviour. Each fixture encodes a musically interpretable registral situation (concentration, polarization, expansion, transposition invariance, same-span / different internal spacing).

These fixtures are:

- **symbolic-score-only** (parsed via **music21**);
- **not** acoustic, perceptual, or orchestration validation corpora;
- **Phase 1:** structural invariant tests only — **not** strict golden numeric baselines.

Regenerate fixtures after intentional design changes:

```bash
python corpus/scripts/create_registral_regression_fixtures.py
python corpus/scripts/inspect_registral_regression.py
python -m pytest tests/test_registral_regression_fixtures.py -q
```

---

## Standard analysis parameters (tests & inspection)

| Parameter | Value |
|-----------|--------|
| `observation_mode` | `event_boundaries` |
| `analysis_profile` | `occupied_space` |
| `pitch_sampling_mode` (implied) | `unique_pitch_heights` |
| `register_low` / `register_high` | `A0` / `C8` |
| `tie_policy` | `as_imported` |

Event-boundary mode gives one row per **constant active pitch set**, which suits directional fixtures (expansion / contraction).

---

## Fixture catalogue

| Fixture | Musical design | Expected metric behaviour (qualitative) |
|---------|----------------|----------------------------------------|
| **`unison_register`** | Four parts, all **C4** | Span **0**; pairwise **0**; entropy **minimal** (single occupied bin). Total registral concentration. |
| **`cluster_middle_register`** | Sustained **C4–F4** chromatic cluster | **Low** span; **low–moderate** pairwise; entropy **moderate** (several adjacent bins). Compact middle-register saturation. |
| **`wide_bipolar_register`** | **C2 + C6** (no middle fill) | **High** span and pairwise; entropy **moderate/low** (polarized extremes). **Largest span** in this suite. Concentration map: two separated bands. |
| **`registral_expansion`** | Sequential states C4 → … → C3–C5 | Span **increases** over time (monotonic in Phase 1 inspection). Pairwise generally increases. Map shows **widening** occupation. |
| **`registral_contraction`** | Reverse of expansion | Span **decreases** over time. Pairwise generally decreases. Map shows **narrowing** occupation. |
| **`high_register_concentration`** | **C6–E6–G6** cluster | Small–moderate span; activity in **high** MIDI rows (mean active MIDI ≫ middle C). |
| **`low_register_concentration`** | **C2–E2–G2** (parallel structure) | **Same** span, pairwise, and entropy as high fixture; **lower** absolute MIDI location on concentration map. Tests transposition invariance of dispersion vs location. |
| **`same_span_sparse_extremes`** | **C3 + C5** only | Span = **24** semitones; **high** pairwise (only extreme pair); **lower** entropy. |
| **`same_span_filled_middle`** | **C3, G3, C4, E4, G4, C5** | **Same** span as sparse; **lower** pairwise (internal fill); **higher** entropy and `active_note_count`. Demonstrates span alone is insufficient. |

---

## What each metric family should show

| Measure | These fixtures test |
|---------|---------------------|
| **`registral_span` / `dispersion_degree`** | Zero (unison); ordering cluster < wide; monotonic expansion/contraction; equality sparse vs filled. |
| **`mean_pairwise_registral_distance`** | Zero (unison); cluster < wide; filled < sparse at equal span; tracks expansion/contraction. |
| **`occupancy_entropy`** | Minimal (unison); filled > sparse at equal span; **not** interchangeable with span. |
| **Concentration map** | High vs low register location; bipolar two-band pattern (visual / row inspection). |

**Warning:** span, pairwise distance, entropy, and concentration-map intensity measure **different** aspects of registral structure. Do not rank scores using a single column.

---

## Golden regression vs qualitative only

| Suitable for future **golden** numeric regression | **Qualitative only** (Phase 1) |
|---------------------------------------------------|--------------------------------|
| `unison_register` span/pairwise/entropy = 0 | Exact entropy values across full A0–C8 band (bin count dependent) |
| `same_span_*` span equality | Concentration-map display normalization |
| `high_register_concentration` vs `low_register_concentration` dispersion equality | Perceptual “brightness” of heatmap colours |
| Monotonic span sequences in expansion/contraction | Global summary aggregates |

Promote numbers to frozen JSON only after explicit Phase 2 review and pinned `package_version`.

---

## Related documentation

- [METRIC_SEMANTICS.md](METRIC_SEMANTICS.md) — formulas and interpretive limits
- [PARAMETERIZATION_GUIDE.md](PARAMETERIZATION_GUIDE.md) — advised analysis presets
- [benchmarks/README.md](../benchmarks/README.md) — separate synthetic summarize regression suite
