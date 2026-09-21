"""
**Registral dispersion** from symbolic scores (MusicXML, MXL, MIDI).

**Canonical metric per temporal row:** ``dispersion_degree`` = ``max(p) - min(p)`` (semitones) over
active MIDI pitches in the user register band (not pitch-class reduction). Numerically identical to
``registral_span``; ``normalized_dispersion_degree`` scales by register width ``R``.

Supplementary descriptors: ``mean_pairwise_registral_distance``, ``registral_centroid``, ``registral_std``.

**occupancy_entropy** (optional / secondary) is the previous normalized Shannon entropy of semitone-bin
occupancy; it is **not** the main operationalization of registral dispersion.

The default ``analysis_profile`` is ``occupied_space`` (density-independent occupied registral geometry);
use ``component_weighted`` or ``run_register_uniformity_analysis`` for legacy event-instance workflows.

One-number global summary: :func:`summarize_registral_dispersion`.

See :mod:`registral_dispersion.metric_documentation` for edge-case conventions.

Distribution **0.3.0** is **research software**: pin ``package_version`` from JSON exports for reproducibility.
"""

from registral_dispersion.aggregation import compute_global_summary
from registral_dispersion.analyzer import RegisterUniformityAnalyzer, RegistralDispersionAnalyzer
from registral_dispersion.profiles import (
    ANALYSIS_PROFILE_COMPONENT_WEIGHTED,
    ANALYSIS_PROFILE_OCCUPIED_SPACE,
    DEFAULT_ANALYSIS_PROFILE,
    implied_pitch_sampling_mode,
    normalize_analysis_profile,
)
from registral_dispersion.sampling import (
    DEFAULT_PITCH_SAMPLING_MODE,
    PITCH_SAMPLING_EVENT_INSTANCES,
    PITCH_SAMPLING_UNIQUE_PITCH_HEIGHTS,
    normalize_pitch_sampling_mode,
)
from registral_dispersion.service import (
    DEFAULT_REGISTER_UNIFORMITY_PARAMS,
    DEFAULT_REGISTRAL_DISPERSION_PARAMS,
    resolve_registral_dispersion_params,
    run_register_uniformity_analysis,
    run_registral_dispersion_analysis,
)
from registral_dispersion.summarize import DEFAULT_SUMMARIZE_PARAMS, summarize_registral_dispersion
from registral_dispersion.microtone_repair import (
    DEFAULT_MICROTONEREPAIR,
    MICROTONEREPAIR_FROM_ACCIDENTALS,
    MICROTONEREPAIR_OFF,
    MICROTONEREPAIR_WARN,
    detect_accidental_alter_mismatch,
    normalize_microtone_repair,
)
from registral_dispersion.pitch_inventory import build_pitch_inventory
from registral_dispersion.pitch_reference import (
    DEFAULT_PITCH_REFERENCE,
    PITCH_REFERENCE_SOUNDING,
    PITCH_REFERENCE_WRITTEN,
    normalize_pitch_reference,
)
from registral_dispersion.pitch_utils import parse_pitch_input
from registral_dispersion.tie_policy import DEFAULT_TIE_POLICY, TIE_POLICY_AS_IMPORTED, TIE_POLICY_MERGE_TIES

__all__ = [
    "ANALYSIS_PROFILE_COMPONENT_WEIGHTED",
    "ANALYSIS_PROFILE_OCCUPIED_SPACE",
    "DEFAULT_ANALYSIS_PROFILE",
    "DEFAULT_PITCH_SAMPLING_MODE",
    "DEFAULT_REGISTER_UNIFORMITY_PARAMS",
    "DEFAULT_REGISTRAL_DISPERSION_PARAMS",
    "DEFAULT_SUMMARIZE_PARAMS",
    "DEFAULT_MICROTONEREPAIR",
    "DEFAULT_PITCH_REFERENCE",
    "DEFAULT_TIE_POLICY",
    "PITCH_REFERENCE_SOUNDING",
    "PITCH_REFERENCE_WRITTEN",
    "MICROTONEREPAIR_FROM_ACCIDENTALS",
    "MICROTONEREPAIR_OFF",
    "MICROTONEREPAIR_WARN",
    "PITCH_SAMPLING_EVENT_INSTANCES",
    "PITCH_SAMPLING_UNIQUE_PITCH_HEIGHTS",
    "TIE_POLICY_AS_IMPORTED",
    "TIE_POLICY_MERGE_TIES",
    "RegisterUniformityAnalyzer",
    "RegistralDispersionAnalyzer",
    "compute_global_summary",
    "detect_accidental_alter_mismatch",
    "implied_pitch_sampling_mode",
    "normalize_analysis_profile",
    "build_pitch_inventory",
    "normalize_microtone_repair",
    "normalize_pitch_reference",
    "normalize_pitch_sampling_mode",
    "parse_pitch_input",
    "resolve_registral_dispersion_params",
    "run_register_uniformity_analysis",
    "run_registral_dispersion_analysis",
    "summarize_registral_dispersion",
]
