"""
Consensus (ensemble) strategy: combine the picks of several strategies by voting.

For each draw, every base strategy generates ``votes_per_model`` tickets using only earlier draws.
Each number's score is how many of those tickets contain it, so numbers favoured by several methods
(frequency, recency, Markov, ML, ...) score highest.  Tickets are sampled without replacement with
weights ``(votes + smoothing) ** power``.

Honest note: combining methods that each have no edge over a uniform draw still has no edge; the
ensemble is included so its "wisdom of the crowd" claim can be measured like any other strategy.
"""

import random
from collections import Counter
from datetime import date
from typing import Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from machine_learning.strategies.base import PredictModel

BaseFactory = Callable[[pd.DataFrame], PredictModel]


class ConsensusStrategy(PredictModel):
    """Vote-weighted ensemble of other strategies."""

    def __init__(
        self,
        df: pd.DataFrame,
        base_factories: Sequence[Tuple[str, BaseFactory]],
        time_predict: int = 1,
        min_val: int = PredictModel.POWER_655_MIN_VAL,
        max_val: int = PredictModel.POWER_655_MAX_VAL,
        votes_per_model: int = 10,
        smoothing: float = 0.5,
        power: float = 1.5,
    ):
        """
        Args:
            df: Historical draws.
            base_factories: ``(name, factory(df))`` pairs building the voting strategies.
            time_predict: Tickets per draw during backtests.
            min_val / max_val: Inclusive number range.
            votes_per_model: Tickets each base strategy contributes per draw.
            smoothing: Pseudo-vote added to every number so none is impossible.
            power: Sharpening of the vote distribution (>1 favours consensus numbers more).
        """
        super().__init__(df, time_predict, min_val, max_val)
        if not base_factories:
            raise ValueError("ConsensusStrategy needs at least one base strategy")
        self.base_names = [name for name, _ in base_factories]
        self.bases: List[PredictModel] = [factory(df) for _, factory in base_factories]
        self.votes_per_model = votes_per_model
        self.smoothing = smoothing
        self.power = power
        self._votes: Dict[Optional[date], Counter] = {}

    def reseed(self, seed: int) -> None:
        super().reseed(seed)
        for offset, base in enumerate(self.bases, start=1):
            base.reseed(seed * 1000 + offset)
        self._votes.clear()

    def votes(self, target_date=None) -> Counter:
        """Number -> how many base-strategy tickets for ``target_date`` contain it (cached per date)."""
        key = pd.Timestamp(target_date).date() if target_date is not None else None
        if key not in self._votes:
            counts: Counter = Counter()
            for base in self.bases:
                for _ in range(self.votes_per_model):
                    counts.update(base.predict(target_date))
            self._votes[key] = counts
        return self._votes[key]

    def predict(self, date=None):
        counts = self.votes(date)
        numbers = list(range(self.min_val, self.max_val + 1))
        weights = np.array([(counts.get(n, 0) + self.smoothing) ** self.power for n in numbers], dtype=float)
        picked: List[int] = []
        pool, pool_w = numbers[:], list(weights)
        while len(picked) < self.number_predict:
            choice = random.choices(range(len(pool)), weights=pool_w, k=1)[0]
            picked.append(pool.pop(choice))
            pool_w.pop(choice)
        return sorted(picked)
