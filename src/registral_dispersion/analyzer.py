"""Registral dispersion and optional occupancy entropy from symbolic scores."""

from __future__ import annotations

import math

import numpy as np
from music21 import chord as m21_chord
from music21 import note as m21_note
from music21 import stream

from registral_dispersion.observation import (
    OBSERVATION_MODE_EVENT_BOUNDARIES,
    OBSERVATION_MODE_FIXED_WINDOW,
    collect_sorted_event_boundaries,
    iter_positive_duration_intervals,
    normalize_observation_mode,
)
from registral_dispersion.profiles import (
    ANALYSIS_PROFILE_COMPONENT_WEIGHTED,
    resolve_profile_and_pitch_sampling,
)
from registral_dispersion.sampling import normalize_pitch_sampling_mode
from registral_dispersion.score_io import parse_score
from registral_dispersion.tie_policy import DEFAULT_TIE_POLICY, apply_tie_policy, normalize_tie_policy


class RegistralDispersionAnalyzer:
    """
    **Registral dispersion** over time: vertical structure of active **MIDI pitch** (not pitch-class)
    in a user-defined register band ``[register_low, register_high]``.

    **D_span** = ``max(p) - min(p)`` over active pitches in each temporal row (semitones).

    **D_pairwise** = ``(2 / (n (n-1))) * sum_{i < j} |p_i - p_j|`` (mean absolute pairwise distance).

    **occupancy_entropy** (optional secondary): normalized Shannon entropy of semitone-bin counts in the
    register band (same numerical recipe as the former register-uniformity ``U``); conceptually distinct
    from span and pairwise distance.

    Analysis uses **notated symbolic pitches** only (no audio).

    **Secondary normalized outputs:** ``normalized_registral_span`` and
    ``normalized_mean_pairwise_registral_distance`` divide the raw semitone metrics by
    ``R = register_high - register_low`` (strictly positive; see README). Raw columns remain primary.

    **Temporal observation:** ``observation_mode='fixed_window'`` (default) uses a regular time grid and
    symmetric moving windows; ``observation_mode='event_boundaries'`` uses half-open intervals
    ``[start, end)`` between sorted note/chord onset and release times where the active pitch set is
    constant (see README).

    **Profile and pitch sampling:** if ``pitch_sampling_mode`` is omitted (``None``), it is implied from
    ``analysis_profile`` (same rule as :func:`registral_dispersion.service.resolve_registral_dispersion_params`).
    An explicit ``pitch_sampling_mode`` overrides that implication. ``pitch_sampling_source`` records whether
    the mode came from the profile or from an explicit parameter.

    **What counts as active (notational sampling)**

    * **Source events:** ``music21.stream.Stream.flatten().notes`` on the parsed score. Each ``Note`` and
      each ``Chord`` is a candidate; other event types are ignored.
    * **Window rule (sustained / overlap):** an event is active in ``[t - w/2, t + w/2]`` if its **notated**
      onset is strictly before the window end and ``onset + quarterLength`` is strictly after the window
      start. Sustained notes therefore count in every overlapped window, not only windows containing an
      attack.
    * **Chords:** every pitch in ``Chord.pitches`` that lies in the register band is a separate component
      before sampling (unless ``unique_pitch_heights`` collapses duplicates).
    * **Parts:** ``flatten()`` merges all parts; cross-part aggregates are joint.
    * **``pitch_sampling_mode``:** ``event_instances`` keeps every in-register MIDI contribution as listed
      (repeated heights, duplicated unisons across parts, repeated noteheads all count separately).
      ``unique_pitch_heights`` collapses to distinct MIDI pitch numbers within the window before metrics.
    * **Ties:** controlled by ``tie_policy`` (default ``as_imported``: no merge). ``merge_ties`` runs
      music21 ``stripTies()`` before event listing. Otherwise the flat stream may contain one long ``Note``
      or several tied segments depending on the file and import; each overlapping object contributes
      according to the rules above.
    """

    def __init__(
        self,
        score_path: str,
        register_low_ps: float,
        register_high_ps: float,
        time_step: float = 0.25,
        pitch_sampling_mode: str | None = None,
        analysis_profile: str | None = None,
        tie_policy: str = DEFAULT_TIE_POLICY,
    ):
        self._score_path: str | None = score_path
        raw = parse_score(score_path)
        processed, tie_warnings = apply_tie_policy(raw, tie_policy)
        self.tie_policy = normalize_tie_policy(tie_policy)
        self.tie_warnings = list(tie_warnings)
        self._init_from_parsed_stream(
            processed,
            register_low_ps,
            register_high_ps,
            time_step,
            pitch_sampling_mode,
            analysis_profile,
        )

    @classmethod
    def from_stream(
        cls,
        score_stream: stream.Stream,
        register_low_ps: float,
        register_high_ps: float,
        time_step: float = 0.25,
        pitch_sampling_mode: str | None = None,
        analysis_profile: str | None = None,
        tie_policy: str = DEFAULT_TIE_POLICY,
    ) -> RegistralDispersionAnalyzer:
        """Build an analyzer from an in-memory music21 stream (e.g. for tests)."""
        self = cls.__new__(cls)
        self._score_path = None
        processed, tie_warnings = apply_tie_policy(score_stream, tie_policy)
        self.tie_policy = normalize_tie_policy(tie_policy)
        self.tie_warnings = list(tie_warnings)
        self._init_from_parsed_stream(
            processed,
            register_low_ps,
            register_high_ps,
            time_step,
            pitch_sampling_mode,
            analysis_profile,
        )
        return self

    def _init_from_parsed_stream(
        self,
        score_stream: stream.Stream,
        register_low_ps: float,
        register_high_ps: float,
        time_step: float,
        pitch_sampling_mode: str | None,
        analysis_profile: str | None = None,
    ) -> None:
        self.score = score_stream
        self.flat = self.score.flatten()
        self.events = list(self.flat.notes)
        self.end_time = float(max(self.score.highestTime, self.flat.highestTime))
        self.time_axis = np.arange(0.0, self.end_time + 1e-9, time_step)
        self.register_low = float(min(register_low_ps, register_high_ps))
        self.register_high = float(max(register_low_ps, register_high_ps))
        self.register_width_semitones = float(self.register_high - self.register_low)
        if self.register_width_semitones <= 0.0:
            raise ValueError(
                "Register band must have strictly positive width in MIDI pitch space "
                f"(register_high_midi > register_low_midi). Got register_low={self.register_low}, "
                f"register_high={self.register_high} (width {self.register_width_semitones} semitones)."
            )
        explicit_pitch = pitch_sampling_mode is not None
        prof, mode, src = resolve_profile_and_pitch_sampling(
            analysis_profile,
            pitch_sampling_mode,
            pitch_sampling_explicit=explicit_pitch,
        )
        self.analysis_profile = prof
        self.pitch_sampling_mode = normalize_pitch_sampling_mode(mode)
        self.pitch_sampling_source = src
        n_semitones = max(1, int(round(self.register_high - self.register_low)) + 1)  # noqa: RUF046
        self._bin_edges = np.linspace(self.register_low - 0.5, self.register_high + 0.5, n_semitones + 1)
        self._n_bins = len(self._bin_edges) - 1
        self._max_entropy = float(np.log(max(1, self._n_bins)))

    def _active_in_window(self, e, t_start: float, t_end: float) -> bool:
        onset = float(e.offset)
        dur = float(e.quarterLength) if hasattr(e, "quarterLength") else 0.0
        return (onset < t_end) and ((onset + dur) > t_start)

    def _raw_pitches_in_time_span(self, t_start: float, t_end: float) -> list[float]:
        active = [e for e in self.events if self._active_in_window(e, t_start, t_end)]
        pitches: list[float] = []
        for e in active:
            if isinstance(e, m21_note.Note):
                ps = float(e.pitch.ps)
                if self.register_low <= ps <= self.register_high:
                    pitches.append(ps)
            elif isinstance(e, m21_chord.Chord):
                for p in e.pitches:
                    ps = float(p.ps)
                    if self.register_low <= ps <= self.register_high:
                        pitches.append(ps)
        return pitches

    def _raw_pitches_in_register(self, window_center: float, window_size: float) -> list[float]:
        t_start = window_center - window_size / 2.0
        t_end = window_center + window_size / 2.0
        return self._raw_pitches_in_time_span(t_start, t_end)

    def _apply_pitch_sampling(self, raw: list[float]) -> np.ndarray:
        if not raw:
            return np.array([], dtype=float)
        arr = np.array(raw, dtype=float)
        if self.pitch_sampling_mode == "unique_pitch_heights":
            return np.unique(arr)
        return arr

    def _pitches_in_register(self, window_center: float, window_size: float) -> np.ndarray:
        return self._apply_pitch_sampling(self._raw_pitches_in_register(window_center, window_size))

    @staticmethod
    def scale_dispersion_by_register_width(raw: float, register_width_semitones: float) -> float:
        """
        Secondary descriptor: raw semitone distance divided by the selected analytical register width ``R``.

        ``R`` must be strictly positive (validated at analyzer construction). If ``raw`` is NaN, returns NaN;
        if ``raw`` is 0, returns 0.
        """
        r = float(raw)
        if math.isnan(r):
            return float("nan")
        if r == 0.0:
            return 0.0
        return r / float(register_width_semitones)

    @staticmethod
    def compute_registral_span(pitches: np.ndarray) -> float:
        """D_span = max(p) - min(p); NaN if empty; 0 if one pitch."""
        if pitches.size == 0:
            return float("nan")
        if pitches.size == 1:
            return 0.0
        return float(np.ptp(pitches))

    @staticmethod
    def compute_dispersion_degree(pitches: np.ndarray) -> float:
        """Canonical dispersion metric: max(p) - min(p) in semitones (identical to registral_span)."""
        return RegistralDispersionAnalyzer.compute_registral_span(pitches)

    @staticmethod
    def compute_mean_pairwise_registral_distance(pitches: np.ndarray) -> float:
        """D_pairwise = (2/(n(n-1))) sum_{i<j} |p_i - p_j|; NaN if empty; 0 if one pitch."""
        if pitches.size == 0:
            return float("nan")
        if pitches.size == 1:
            return 0.0
        n = int(pitches.size)
        diff = np.abs(pitches[:, None] - pitches[None, :])
        iu = np.triu_indices(n, k=1)
        return float(2.0 / (n * (n - 1)) * diff[iu].sum())

    @staticmethod
    def compute_registral_centroid(pitches: np.ndarray) -> float:
        """Arithmetic mean of active MIDI pitches (semitones); NaN if empty."""
        if pitches.size == 0:
            return float("nan")
        return float(np.mean(pitches))

    @staticmethod
    def compute_registral_std(pitches: np.ndarray) -> float:
        """Population std dev of active MIDI pitches (semitones); NaN if empty; 0 if one pitch."""
        if pitches.size == 0:
            return float("nan")
        if pitches.size == 1:
            return 0.0
        return float(np.std(pitches, ddof=0))

    @staticmethod
    def normalize_centroid_to_band(centroid: float, register_low: float, register_width_semitones: float) -> float:
        """
        Secondary descriptor: ``(centroid - register_low) / R`` → position in the analytical band ``[0, 1]``.

        Unlike span and pairwise distance, the raw centroid depends on absolute tessitura; this normalized
        form supports comparison across register bands.
        """
        c = float(centroid)
        if math.isnan(c):
            return float("nan")
        return (c - float(register_low)) / float(register_width_semitones)

    def compute_occupancy_entropy(self, pitches: np.ndarray) -> float:
        """Normalized Shannon entropy of pitch counts over register semitone bins → ``[0, 1]``; NaN if empty."""
        if pitches.size == 0:
            return float("nan")
        if pitches.size == 1:
            return 0.0
        counts, _ = np.histogram(pitches, bins=self._bin_edges)
        total = counts.sum()
        if total == 0:
            return float("nan")
        pmf = counts / total
        pmf = pmf[pmf > 0]
        if pmf.size == 0:
            return 0.0
        entropy = -float(np.sum(pmf * np.log(pmf)))
        if self._max_entropy <= 0:
            return 0.0
        U = entropy / self._max_entropy
        # max(..., 0.0) avoids -0.0 from np.clip on floating-point underflow
        return max(0.0, float(np.clip(U, 0.0, 1.0)))

    def _append_row(
        self,
        results: dict[str, list],
        *,
        t_center: float,
        interval_start: float,
        interval_end: float,
        window_start: float,
        window_end: float,
        pitches: np.ndarray,
    ) -> None:
        dur = float(interval_end - interval_start)
        count = int(pitches.size)
        results["t"].append(float(t_center))
        results["interval_start"].append(float(interval_start))
        results["interval_end"].append(float(interval_end))
        results["interval_duration"].append(dur)
        results["window_start"].append(float(window_start))
        results["window_end"].append(float(window_end))
        results["active_note_count"].append(count)
        if count == 0:
            results["min_pitch"].append(float("nan"))
            results["max_pitch"].append(float("nan"))
        elif count == 1:
            m = float(pitches[0])
            results["min_pitch"].append(m)
            results["max_pitch"].append(m)
        else:
            results["min_pitch"].append(float(np.min(pitches)))
            results["max_pitch"].append(float(np.max(pitches)))
        span = self.compute_registral_span(pitches)
        dp = self.compute_mean_pairwise_registral_distance(pitches)
        centroid = self.compute_registral_centroid(pitches)
        std = self.compute_registral_std(pitches)
        results["dispersion_degree"].append(span)
        results["registral_span"].append(span)
        results["mean_pairwise_registral_distance"].append(dp)
        results["registral_centroid"].append(centroid)
        results["registral_std"].append(std)
        R = self.register_width_semitones
        norm_degree = self.scale_dispersion_by_register_width(span, R)
        results["normalized_dispersion_degree"].append(norm_degree)
        results["normalized_registral_span"].append(norm_degree)
        results["normalized_mean_pairwise_registral_distance"].append(self.scale_dispersion_by_register_width(dp, R))
        results["normalized_registral_centroid"].append(self.normalize_centroid_to_band(centroid, self.register_low, R))
        results["normalized_registral_std"].append(self.scale_dispersion_by_register_width(std, R))
        results["occupancy_entropy"].append(self.compute_occupancy_entropy(pitches))

    def _empty_results_dict(self) -> dict[str, list]:
        keys = [
            "t",
            "interval_start",
            "interval_end",
            "interval_duration",
            "window_start",
            "window_end",
            "active_note_count",
            "min_pitch",
            "max_pitch",
            "dispersion_degree",
            "registral_span",
            "mean_pairwise_registral_distance",
            "registral_centroid",
            "registral_std",
            "normalized_dispersion_degree",
            "normalized_registral_span",
            "normalized_mean_pairwise_registral_distance",
            "normalized_registral_centroid",
            "normalized_registral_std",
            "occupancy_entropy",
        ]
        return {k: [] for k in keys}

    def _analyze_fixed_windows(self, window_size: float, progress_callback) -> dict[str, list]:
        half = float(window_size) / 2.0
        results = self._empty_results_dict()
        n = len(self.time_axis)
        for i, t in enumerate(self.time_axis):
            tc = float(t)
            pitches = self._pitches_in_register(tc, window_size)
            ws, we = tc - half, tc + half
            self._append_row(
                results,
                t_center=tc,
                interval_start=ws,
                interval_end=we,
                window_start=ws,
                window_end=we,
                pitches=pitches,
            )
            if progress_callback and n > 0:
                progress_callback((i + 1) / n, "Registral dispersion")
        return results

    def _analyze_event_boundaries(self, progress_callback) -> dict[str, list]:
        """
        Half-open intervals ``[start, end)`` between sorted boundaries (0, score end, all onsets/releases).

        Intervals with no in-register active pitches are **included**: metrics are NaN (same convention as
        empty windows); ``active_note_count`` is 0. ``t`` is the interval midpoint for plotting continuity.
        ``window_start`` / ``window_end`` mirror ``interval_start`` / ``interval_end`` as aliases.
        """
        results = self._empty_results_dict()
        boundaries = collect_sorted_event_boundaries(self.events, self.end_time)
        intervals = list(iter_positive_duration_intervals(boundaries))
        n = len(intervals)
        for i, (ts, te) in enumerate(intervals):
            raw = self._raw_pitches_in_time_span(ts, te)
            pitches = self._apply_pitch_sampling(raw)
            mid = 0.5 * (float(ts) + float(te))
            self._append_row(
                results,
                t_center=mid,
                interval_start=ts,
                interval_end=te,
                window_start=ts,
                window_end=te,
                pitches=pitches,
            )
            if progress_callback and n > 0:
                progress_callback((i + 1) / n, "Registral dispersion (event boundaries)")
        return results

    def analyze_score(self, window_size: float, progress_callback=None, *, observation_mode: str | None = None):
        """
        ``observation_mode``:

        * ``fixed_window`` (default): symmetric windows on ``time_step`` grid; ``window_size`` is required.
        * ``event_boundaries``: one row per maximal interval with constant active pitch set; ``window_size``
          is ignored for indexing (still accepted for API compatibility).
        """
        mode = normalize_observation_mode(observation_mode)
        if mode == OBSERVATION_MODE_EVENT_BOUNDARIES:
            return self._analyze_event_boundaries(progress_callback)
        return self._analyze_fixed_windows(float(window_size), progress_callback)


class RegisterUniformityAnalyzer(RegistralDispersionAnalyzer):
    """
    Backward-compatible API: same score parsing and windows, but :meth:`analyze_score` returns only
    ``t`` and ``U`` (where ``U`` is ``occupancy_entropy``), matching the pre–registral-dispersion tool.
    """

    def __init__(
        self,
        score_path: str,
        register_low_ps: float,
        register_high_ps: float,
        time_step: float = 0.25,
        pitch_sampling_mode: str | None = None,
        analysis_profile: str | None = None,
        tie_policy: str = DEFAULT_TIE_POLICY,
    ):
        prof = ANALYSIS_PROFILE_COMPONENT_WEIGHTED if analysis_profile is None else analysis_profile
        super().__init__(
            score_path,
            register_low_ps,
            register_high_ps,
            time_step,
            pitch_sampling_mode,
            analysis_profile=prof,
            tie_policy=tie_policy,
        )

    def analyze_score(self, window_size: float, progress_callback=None, **_kwargs):
        full = RegistralDispersionAnalyzer.analyze_score(
            self,
            window_size,
            progress_callback,
            observation_mode=OBSERVATION_MODE_FIXED_WINDOW,
        )
        return {"t": full["t"], "U": full["occupancy_entropy"]}

    def compute_uniformity(self, pitches: np.ndarray) -> float:
        """Same as :meth:`compute_occupancy_entropy` (legacy name)."""
        return self.compute_occupancy_entropy(pitches)
