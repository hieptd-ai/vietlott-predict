"""
Positional (order-statistic) strategy, adapted from the ``PositionalStrategy`` of thanhnhu/vietlott.

Draws are stored sorted, so the k-th smallest number has its own distribution: position 0 is small,
the last position is large.  This strategy builds a Laplace-smoothed histogram per sorted position
from past draws and samples a ticket left to right under ``num[k] > num[k-1]``, leaving room for the
remaining positions.

Honest note: this shapes tickets to *look* like real draws; it cannot change the hypergeometric match
probabilities of a uniform lottery.
"""

import random
from collections import Counter
from datetime import date, timedelta
from typing import Dict, List, Optional

import pandas as pd

from machine_learning.strategies.base import PredictModel


class PositionalStrategy(PredictModel):
    """Sample each sorted position from its own historical histogram."""

    def __init__(
        self,
        df: pd.DataFrame,
        time_predict: int = 1,
        min_val: int = PredictModel.POWER_655_MIN_VAL,
        max_val: int = PredictModel.POWER_655_MAX_VAL,
        lookback_days: Optional[int] = None,
        smoothing: float = 1.0,
    ):
        """
        Args:
            df: Historical draws.
            time_predict: Tickets per draw during backtests.
            min_val / max_val: Inclusive number range.
            lookback_days: Only use draws in this many days before the target (``None`` = all).
            smoothing: Laplace pseudo-count added to every value of every position.
        """
        super().__init__(df, time_predict, min_val, max_val)
        self.lookback_days = lookback_days
        self.smoothing = smoothing
        self._cache: Dict[date, List[Counter]] = {}
        self._prepare_historical_data()

    def _prepare_historical_data(self) -> None:
        self.df_sorted = self.df.sort_values("date").reset_index(drop=True)
        self.df_sorted["date"] = pd.to_datetime(self.df_sorted["date"]).dt.date

    def _position_counts(self, target_date: date) -> List[Counter]:
        if target_date in self._cache:
            return self._cache[target_date]
        mask = self.df_sorted["date"] < target_date
        if self.lookback_days is not None:
            mask &= self.df_sorted["date"] >= target_date - timedelta(days=self.lookback_days)
        counts = [Counter() for _ in range(self.number_predict)]
        for draw in self.df_sorted.loc[mask, "result"]:
            ordered = sorted(int(n) for n in draw)[: self.number_predict]
            for k, n in enumerate(ordered):
                counts[k][n] += 1
        self._cache[target_date] = counts
        return counts

    def predict(self, date=None):
        target = pd.Timestamp(date).date() if date is not None else self.df_sorted["date"].max() + timedelta(days=1)
        counts = self._position_counts(target)
        ticket: List[int] = []
        prev = self.min_val - 1
        for k in range(self.number_predict):
            hi = self.max_val - (self.number_predict - 1 - k)
            feasible = list(range(prev + 1, hi + 1))
            weights = [counts[k].get(v, 0) + self.smoothing for v in feasible]
            choice = random.choices(feasible, weights=weights, k=1)[0] if sum(weights) > 0 else random.choice(feasible)
            ticket.append(choice)
            prev = choice
        return ticket
