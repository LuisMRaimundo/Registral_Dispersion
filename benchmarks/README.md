# Registral_Dispersion benchmarks

Controlled **synthetic fixtures** for regression and frozen-output comparison.

These are **not** empirical validation corpora, analyst-labelled datasets, or perceptual benchmarks. Metric semantics: [../docs/METRIC_SEMANTICS.md](../docs/METRIC_SEMANTICS.md).

## Layout

- `manifest.json` — fixture catalogue and metadata
- `fixtures/` — minimal MusicXML scores (legal to redistribute)
- `frozen_outputs/` — JSON summaries generated with pinned default summarize parameters (`schema_version` 1.8)
- `scripts/generate_frozen_outputs.py` — regenerate frozen outputs after intentional changes
- `scripts/compare_frozen_outputs.py` — compare current summarize output to frozen baselines

## Default summarize parameters for frozen outputs

- `observation_mode`: `event_boundaries`
- `analysis_profile`: `occupied_space`
- `register`: A0–C8
- `tie_policy`: `as_imported`

## Regenerate

```bash
python benchmarks/scripts/generate_frozen_outputs.py
python benchmarks/scripts/compare_frozen_outputs.py
```
