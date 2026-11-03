"""
Causal per-number features for draw-level machine learning.

For every draw ``t`` and every number ``n`` the feature vector only uses draws ``0..t-1``, so a model
trained on rows ``< t`` and evaluated on row ``t`` never sees the future.  Row ``T`` (one past the last
stored draw) describes the *next*, not-yet-drawn result and is what live predictions use.
"""

from bisect import bisect_left
from datetime import date, timedelta
from typing import List, Sequence, Tuple

import numpy as np

DEFAULT_WINDOWS: Tuple[int, ...] = (10, 30, 100)


def feature_names(windows: Sequence[int] = DEFAULT_WINDOWS) -> List[str]:
    """Human-readable names, in column order, of the features built by :func:`build_features`."""
    return [f"freq_last_{w}" for w in windows] + ["freq_all", "gap_draws", "in_last_draw"]


def occurrence_matrix(results: Sequence[Sequence[int]], min_val: int, max_val: int) -> np.ndarray:
    """Binary ``(T, N)`` matrix: ``occ[t, n - min_val] = 1`` when number ``n`` was drawn at ``t``."""
    n_numbers = max_val - min_val + 1
    occ = np.zeros((len(results), n_numbers), dtype=np.int8)
    for t, draw in enumerate(results):
        for n in draw:
            if min_val <= int(n) <= max_val:
                occ[t, int(n) - min_val] = 1
    return occ


def build_features(occ: np.ndarray, windows: Sequence[int] = DEFAULT_WINDOWS) -> np.ndarray:
    """Return a ``(T + 1, N, F)`` float array of causal features (see :func:`feature_names`).

    * ``freq_last_w`` – share of the last ``w`` draws containing the number (fewer if history is short);
    * ``freq_all`` – share of all previous draws containing the number;
    * ``gap_draws`` – draws since the number last appeared, divided by ``N`` (≈ its expected gap scale);
    * ``in_last_draw`` – 1 when the number was in the immediately previous draw.
    """
    n_draws, n_numbers = occ.shape
    cumulative = np.vstack([np.zeros((1, n_numbers), dtype=np.int64), np.cumsum(occ, axis=0, dtype=np.int64)])
    t_index = np.arange(n_draws + 1)

    columns = []
    for w in windows:
        start = np.maximum(t_index - w, 0)
        denom = np.maximum(t_index - start, 1)[:, None]
        columns.append((cumulative[t_index] - cumulative[start]) / denom)
    columns.append(cumulative[t_index] / np.maximum(t_index, 1)[:, None])

    gaps = np.zeros((n_draws + 1, n_numbers), dtype=float)
    last_seen = np.full(n_numbers, -1, dtype=np.int64)
    for t in range(n_draws + 1):
        gaps[t] = t - last_seen
        if t < n_draws:
            last_seen[occ[t] == 1] = t
    columns.append(gaps / n_numbers)

    in_last = np.zeros((n_draws + 1, n_numbers), dtype=float)
    in_last[1:] = occ
    columns.append(in_last)

    return np.stack(columns, axis=-1)


def next_draw_date(dates: Sequence) -> date:
    """Best guess of the next draw date for a 3-draws-a-week schedule (same weekday as 3 draws ago + 7 days)."""
    if len(dates) >= 3:
        return dates[-3] + timedelta(days=7)
    return dates[-1] + timedelta(days=1)


def cross_game_features(
    dates: Sequence,
    other_dates: Sequence,
    other_results: Sequence[Sequence[int]],
    min_val: int,
    max_val: int,
    windows: Sequence[int] = (10, 30),
) -> Tuple[np.ndarray, List[str]]:
    """Features from another game's draws held strictly before each target draw date.

    Returns ``(T + 1, N, F)`` – for every draw of the target game (plus the next one) and every number
    ``n`` in ``[min_val, max_val]``: the share of the other game's last ``w`` draws containing ``n``
    and whether ``n`` was in the other game's latest draw.  Numbers outside the other game's range get 0.
    """
    n_numbers = max_val - min_val + 1
    other_max = max((max(r) for r in other_results), default=0)
    other_occ = occurrence_matrix(other_results, min_val, max(max_val, other_max))[:, :n_numbers]
    cumulative = np.vstack([np.zeros((1, n_numbers), dtype=np.int64), np.cumsum(other_occ, axis=0, dtype=np.int64)])
    targets = list(dates) + [next_draw_date(dates)]
    other_dates = list(other_dates)
    out = np.zeros((len(targets), n_numbers, len(windows) + 1), dtype=float)
    for t, target in enumerate(targets):
        k = bisect_left(other_dates, target)  # other draws strictly before the target date
        for j, w in enumerate(windows):
            start = max(0, k - w)
            if k > start:
                out[t, :, j] = (cumulative[k] - cumulative[start]) / (k - start)
        if k > 0:
            out[t, :, len(windows)] = other_occ[k - 1]
    names = [f"other_freq_last_{w}" for w in windows] + ["other_in_last_draw"]
    return out, names


def calendar_features(dates: Sequence, n_numbers: int) -> Tuple[np.ndarray, List[str]]:
    """Weekday / month of each draw (and the next one) plus the number's own position, ``(T + 1, N, 3)``.

    The position lets tree models learn number × calendar interactions, should any exist.
    """
    targets = list(dates) + [next_draw_date(dates)]
    out = np.zeros((len(targets), n_numbers, 3), dtype=float)
    out[:, :, 2] = np.arange(n_numbers) / max(n_numbers - 1, 1)
    for t, target in enumerate(targets):
        out[t, :, 0] = target.weekday() / 6
        out[t, :, 1] = (target.month - 1) / 11
    return out, ["weekday", "month", "number_position"]
