"""Typed result container for registral-dispersion time series."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class RegistralDispersionSeriesResult:
    """
    One row per analysis window or per event-boundary interval.

    ``dispersion_degree`` is the **canonical** registral dispersion metric (semitones):
    ``max(pitches) - min(pitches)``; numerically identical to ``registral_span``.

    ``active_note_count`` is the number of active pitch components **after** applying ``pitch_sampling_mode``.

    ``normalized_dispersion_degree`` divides ``dispersion_degree`` by the selected analytical register width
    ``R = register_high_midi - register_low_midi`` (0–1 scale within the band; secondary descriptor).

    ``interval_start``, ``interval_end``, and ``interval_duration`` identify the temporal support of each
    row. In ``fixed_window`` mode they mirror the symmetric window bounds; in ``event_boundaries`` mode
    they are half-open score-state intervals ``[start, end)``.
    """

    t: list[float]
    interval_start: list[float]
    interval_end: list[float]
    interval_duration: list[float]
    window_start: list[float]
    window_end: list[float]
    active_note_count: list[int]
    min_pitch: list[float]
    max_pitch: list[float]
    dispersion_degree: list[float]
    normalized_dispersion_degree: list[float]
    registral_span: list[float]
    mean_pairwise_registral_distance: list[float]
    registral_centroid: list[float]
    registral_std: list[float]
    normalized_registral_span: list[float]
    normalized_mean_pairwise_registral_distance: list[float]
    normalized_registral_centroid: list[float]
    normalized_registral_std: list[float]
    occupancy_entropy: list[float]

    @classmethod
    def from_legacy(cls, d: dict[str, Any]) -> RegistralDispersionSeriesResult:
        n = len(d["t"])
        d = dict(d)
        if "interval_start" not in d:
            d["interval_start"] = list(d["window_start"])
            d["interval_end"] = list(d["window_end"])
            d["interval_duration"] = [float(d["window_end"][i]) - float(d["window_start"][i]) for i in range(n)]
        if "dispersion_degree" not in d:
            d["dispersion_degree"] = list(d["registral_span"])
        if "normalized_dispersion_degree" not in d:
            d["normalized_dispersion_degree"] = list(d["normalized_registral_span"])
        keys = [
            "interval_start",
            "interval_end",
            "interval_duration",
            "window_start",
            "window_end",
            "active_note_count",
            "min_pitch",
            "max_pitch",
            "dispersion_degree",
            "normalized_dispersion_degree",
            "registral_span",
            "mean_pairwise_registral_distance",
            "registral_centroid",
            "registral_std",
            "normalized_registral_span",
            "normalized_mean_pairwise_registral_distance",
            "normalized_registral_centroid",
            "normalized_registral_std",
            "occupancy_entropy",
        ]
        for k in keys:
            if k not in d:
                d[k] = [float("nan")] * n
            if len(d[k]) != n:
                raise ValueError(f"length mismatch for {k}")
        return cls(
            t=list(d["t"]),
            interval_start=list(d["interval_start"]),
            interval_end=list(d["interval_end"]),
            interval_duration=list(d["interval_duration"]),
            window_start=list(d["window_start"]),
            window_end=list(d["window_end"]),
            active_note_count=list(d["active_note_count"]),
            min_pitch=list(d["min_pitch"]),
            max_pitch=list(d["max_pitch"]),
            dispersion_degree=list(d["dispersion_degree"]),
            normalized_dispersion_degree=list(d["normalized_dispersion_degree"]),
            registral_span=list(d["registral_span"]),
            mean_pairwise_registral_distance=list(d["mean_pairwise_registral_distance"]),
            registral_centroid=list(d["registral_centroid"]),
            registral_std=list(d["registral_std"]),
            normalized_registral_span=list(d["normalized_registral_span"]),
            normalized_mean_pairwise_registral_distance=list(d["normalized_mean_pairwise_registral_distance"]),
            normalized_registral_centroid=list(d["normalized_registral_centroid"]),
            normalized_registral_std=list(d["normalized_registral_std"]),
            occupancy_entropy=list(d["occupancy_entropy"]),
        )

    def as_legacy_dict(self) -> dict[str, list]:
        return {
            "t": self.t,
            "interval_start": self.interval_start,
            "interval_end": self.interval_end,
            "interval_duration": self.interval_duration,
            "window_start": self.window_start,
            "window_end": self.window_end,
            "active_note_count": self.active_note_count,
            "min_pitch": self.min_pitch,
            "max_pitch": self.max_pitch,
            "dispersion_degree": self.dispersion_degree,
            "normalized_dispersion_degree": self.normalized_dispersion_degree,
            "registral_span": self.registral_span,
            "mean_pairwise_registral_distance": self.mean_pairwise_registral_distance,
            "registral_centroid": self.registral_centroid,
            "registral_std": self.registral_std,
            "normalized_registral_span": self.normalized_registral_span,
            "normalized_mean_pairwise_registral_distance": self.normalized_mean_pairwise_registral_distance,
            "normalized_registral_centroid": self.normalized_registral_centroid,
            "normalized_registral_std": self.normalized_registral_std,
            "occupancy_entropy": self.occupancy_entropy,
        }
