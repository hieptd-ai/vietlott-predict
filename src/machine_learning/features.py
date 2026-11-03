"""
Causal per-number features for draw-level machine learning.

For every draw ``t`` and every number ``n`` the feature vector only uses draws ``0..t-1``, so a model
trained on rows ``< t`` and evaluated on row ``t`` never sees the future.  Row ``T`` (one past the last
stored draw) describes the *next*, not-yet-drawn result and is what live predictions use.
"""

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
