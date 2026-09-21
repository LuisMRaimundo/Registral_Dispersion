# Changelog

## Unreleased

- **`microtone_repair`** (`off` default | `warn` | `from_accidentals`): detect and optionally repair MusicXML accidental glyphs whose `<alter>` does not match the glyph (Sibelius 8 quarter-sharp / three-quarters-sharp). Repair runs before tie stripping; measure- and tie-inheritance of the repaired alter is applied. MIDI is never rewritten. CLI `--microtone-repair`, Gradio control, `repairs` in the analysis result. Default `off` leaves all frozen benchmark numbers unchanged.
- **JSON schema 1.9:** `microtone_repair` in parameters / score metadata / CSV comments; `repairs` array on successful exports.
- GitHub repository renamed to **Registral_Dispersion** (`LuisMRaimundo/Registral_Dispersion`); documentation and installer URLs updated.
- Canonical research tool name **Registral_Dispersion** applied across documentation, UI, exports (`canonical_tool_name`), and launchers. Legacy aliases (`register_uniformity`, homogeneity cache env vars) retained for backward compatibility only.

## 0.3.0 (2026-05-20)

- Built-in **global summary** (`global_summary`) on every analysis run.
- **One-number API:** `summarize_registral_dispersion`.
- **One-number CLI:** `python -m registral_dispersion summarize`.
- **`tie_policy`:** `as_imported` (default) and `merge_ties` via music21 `stripTies()`.
- **Interpretation warnings** for profile/sampling overrides and fixed-window one-number use.
- **JSON schema 1.8:** `global_summary`, `warnings`, `tie_policy`, `symbolic_score_only`.
- Separate **global summary CSV** export on batch `analyze`.
- **Benchmarks/** synthetic fixtures with frozen summarize outputs (regression only).
- No change to per-row dispersion **formulas**; defaults preserved (`occupied_space`, `fixed_window` for full analysis).
- Documentation aligned with implementation: primary plotted/exported canonical metric **`dispersion_degree`**; JSON schema **1.8**; `tie_policy` in README and parameterization guide.

## 0.2.1

- Canonical **`dispersion_degree`** field (alias of `registral_span`).

## 0.2.0

- Initial registral-dispersion release with profiles, event boundaries, concentration map.
