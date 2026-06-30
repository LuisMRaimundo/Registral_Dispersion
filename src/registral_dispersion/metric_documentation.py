"""
Documentation strings for exports and UI (not used in numerical computation).

**Notational sampling (active pitches):**

Events come from ``music21`` ``flatten().notes`` (``Note`` and ``Chord`` only). A component is **active**
in a window if its **notated** span overlaps the window: ``onset < window_end`` and
``onset + quarterLength > window_start`` (sustained soundings count without an attack inside the window).
Chord members contribute as separate MIDI heights before optional collapse. All parts are merged via
``flatten()`` into one aggregate list.

**pitch_sampling_mode**

* ``event_instances`` — every in-register MIDI contribution is kept (cross-part unisons and repeated
  noteheads count separately).
* ``unique_pitch_heights`` — collapse to distinct MIDI pitch numbers inside the window before span,
  pairwise distance, and occupancy entropy.

**Ties:** ``tie_policy=as_imported`` (default) preserves importer structure; ``merge_ties`` runs
``stripTies()`` before listing. Each overlapping ``Note``/``Chord`` object contributes according to the
rules above.

**Edge-case convention (all window metrics):**

* **No active pitches** in the window: ``dispersion_degree``, ``registral_span``,
  ``mean_pairwise_registral_distance``, ``registral_centroid``, ``registral_std``, and ``occupancy_entropy`` are
  **NaN**; ``active_note_count`` is 0; ``min_pitch`` / ``max_pitch`` are **NaN**. The secondary
  ``normalized_dispersion_degree`` and other ``normalized_*`` fields are **NaN** in the same windows.
* **Exactly one active pitch**: ``dispersion_degree`` = 0, ``registral_span`` = 0,
  ``mean_pairwise_registral_distance`` = 0 (no pairs),
  ``registral_centroid`` = that pitch, ``registral_std`` = 0, ``occupancy_entropy`` = 0 (single-bin occupancy);
  ``min_pitch`` = ``max_pitch`` = that pitch. Normalized dispersion fields are 0; ``normalized_registral_centroid``
  is ``(pitch - register_low) / R``.

**Terminology:** ``dispersion_degree`` is the **canonical** registral dispersion metric
(``max(pitches) - min(pitches)`` in semitones; numerically identical to ``registral_span``).
``mean_pairwise_registral_distance`` is a **supplementary** descriptor when clustering is uneven.
``registral_centroid`` and ``registral_std`` summarize **tessitura location** and **cluster tightness** (complementary
to span/pairwise; raw centroid is **not** transposition-invariant). ``occupancy_entropy`` is **not** registral dispersion;
it is a legacy **register-uniformity / occupancy-evenness** recipe retained for comparison. This tool does **not** infer density, harmony, pitch-class set structure,
tessitura labels, acoustic brightness, or orchestration.
"""

CANONICAL_TOOL_NAME = "Registral_Dispersion"

METHODOLOGICAL_NOTE_REGISTRAL = (
    "Registral dispersion is operationalized here as the vertical opening/compression of active notated "
    "components in semitone space. The canonical metric is dispersion_degree "
    "(= registral_span = max(pitches) - min(pitches), semitones). "
    "mean_pairwise_registral_distance "
    "(D_pairwise = (2/(n(n-1))) * sum_{i<j} |p_i - p_j|) is supplementary. These descriptors are transposition-invariant "
    "in the sense that they depend only on relative MIDI pitch distances within each temporal support, "
    "not on absolute tessitura labels; they do not measure pitch-class set content, harmony, density, acoustic "
    "brightness, or orchestration. Complementary summaries registral_centroid (mean MIDI pitch) and registral_std "
    "(population std dev in semitones) describe tessitura location and cluster tightness; raw centroid depends on "
    "absolute pitch while normalized_registral_centroid = (centroid - register_low) / R locates the mean within the "
    "selected band. The previous entropy-based register uniformity metric, retained as "
    "occupancy_entropy, measures pitch-bin occupancy evenness within the user-selected register band and "
    "is conceptually distinct from registral span and pairwise distance."
)

METRIC_PRIMARY_NAME = "Registral dispersion (dispersion_degree)"

METRIC_DEFINITION_PRIMARY = (
    "Canonical metric dispersion_degree = max(pitches) - min(pitches) (semitones) per temporal row "
    "(fixed window or event interval); numerically identical to registral_span. "
    "normalized_dispersion_degree = dispersion_degree / R. "
    "Supplementary: mean_pairwise_registral_distance; registral_centroid (mean pitch); "
    "registral_std (population std dev). Optional: occupancy_entropy = normalized Shannon "
    "entropy of semitone-bin occupancy in the selected register (not a substitute for dispersion)."
)

DISPERSION_DEGREE_DEFINITION = (
    "dispersion_degree = max(active MIDI pitches) - min(active MIDI pitches) in semitones "
    "(alias: registral_span)."
)

# Single-line export blurb (CSV comments + JSON); must match implementation in analyzer.py.
METRIC_FORMULAS_INLINE = (
    "Formulas: dispersion_degree = registral_span = max(pitches)-min(pitches) (semitones); "
    "normalized_dispersion_degree = dispersion_degree/R; "
    "mean_pairwise_registral_distance = (2/(n(n-1)))*sum_{i<j}|p_i-p_j| (mean over unordered distinct pairs); "
    "registral_centroid = mean(pitches); registral_std = population std dev of pitches (semitones); "
    "normalized_registral_span = registral_span/R; normalized_mean_pairwise_registral_distance = "
    "mean_pairwise_registral_distance/R; normalized_registral_centroid = (registral_centroid - register_low)/R; "
    "normalized_registral_std = registral_std/R with R = register_high_midi - register_low_midi."
)

PLOT_YAXIS_PRIMARY = "Dispersion degree (semitones)"
PLOT_YAXIS_PAIRWISE = "Mean pairwise distance (semitones)"
PLOT_YAXIS_SPAN = "Registral span (semitones)"
PLOT_YAXIS_ENTROPY = "Occupancy entropy [0–1]"
PLOT_YAXIS_PRIMARY_NORMALIZED = "Dispersion degree / register width (0–1 scale)"
PLOT_YAXIS_PAIRWISE_NORMALIZED = "Mean pairwise distance / register width (0–1 scale)"
PLOT_YAXIS_SPAN_NORMALIZED = "Registral span / register width (0–1 scale)"

NORMALIZATION_REFERENCE = "selected_register_bounds"

METHODOLOGICAL_NOTE_NORMALIZATION = (
    "Secondary normalized_* columns divide raw semitone span and mean pairwise distance by "
    "R = register_high_midi - register_low_midi for the selected analytical register bounds "
    f"(normalization_reference={NORMALIZATION_REFERENCE!r}). "
    "They support comparison across analyses with different register bands; they are not perceptual "
    "dispersion, acoustic brightness, or orchestral spread."
)

CSV_COLUMN_HEADER = (
    "interval_start,interval_end,interval_duration,window_start,window_end,t_window_center,"
    "active_note_count,min_pitch,max_pitch,"
    "dispersion_degree,normalized_dispersion_degree,"
    "registral_span,mean_pairwise_registral_distance,registral_centroid,registral_std,"
    "normalized_registral_span,normalized_mean_pairwise_registral_distance,"
    "normalized_registral_centroid,normalized_registral_std,occupancy_entropy"
)

OBSERVATION_MODES_CSV_BLURB = (
    "observation_mode fixed_window: symmetric moving windows on a regular time grid (time_step, window_size). "
    "observation_mode event_boundaries: half-open intervals [t0,t1) between sorted note/chord onsets and "
    "releases where the active in-register pitch set is constant; gaps with no sounding pitches are "
    "included as rows with NaN dispersion metrics (same convention as empty fixed windows)."
)

NOTATIONAL_SAMPLING_CSV_BLURB = (
    "Notational sampling: overlap rule on flatten().notes; chord members separate; "
    "see README pitch_sampling_mode (event_instances vs unique_pitch_heights)."
)

METHODOLOGICAL_NOTE_ANALYSIS_PROFILES = (
    "analysis_profile 'occupied_space' targets density-independent geometry of occupied registral positions "
    "(implies unique_pitch_heights); read dispersion_degree as the canonical metric. "
    "analysis_profile 'component_weighted' targets dispersion among active notated components "
    "(implies event_instances); duplicated unisons and repeated heights are legitimate multiplicity—"
    "not wrong, but a different analytical question—dispersion_degree still uses max-min span while "
    "mean_pairwise_registral_distance may diverge when doublings are present. "
    "If both analysis_profile and pitch_sampling_mode appear in the request, an explicit "
    "pitch_sampling_mode parameter overrides the profile’s implied sampling mode; otherwise the profile "
    "determines pitch_sampling_mode."
)
