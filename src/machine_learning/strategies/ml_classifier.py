"""
Supervised machine-learning strategy: per-number "will it be drawn next?" classification.

Each (draw, number) pair is one training row with causal features from
:mod:`machine_learning.features` and the label "number appeared in this draw".  The classifier is
re-fitted walk-forward every ``refit_every`` draws on strictly earlier rows only, so backtests have no
look-ahead.  Predicted probabilities become a ticket either by sampling without replacement
(``selection="sample"``, varied tickets) or by taking the ``number_predict`` most likely numbers
(``selection="top"``).

Honest note: Vietlott draws are independent and uniform.  A well-calibrated model should converge to
``p ≈ pick / pool`` for every number and ROC-AUC ≈ 0.5; :mod:`machine_learning.analysis` measures exactly
that, which makes this strategy a *test of predictability* rather than an edge.
"""

from bisect import bisect_left
from datetime import date as date_type
from typing import Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from machine_learning.features import DEFAULT_WINDOWS, build_features, feature_names, occurrence_matrix
from machine_learning.strategies.base import PredictModel

MODEL_TYPES = ("logistic", "random_forest", "gbm")

# (sorted draw dates, occurrence matrix) -> extra (T + 1, N, F) features and their names
FeatureBuilder = Callable[[Sequence[date_type], np.ndarray], Tuple[np.ndarray, List[str]]]


def make_classifier(model_type: str, random_state: Optional[int] = None):
    """Build an unfitted scikit-learn classifier for ``model_type``."""
    if model_type == "logistic":
        from sklearn.linear_model import LogisticRegression
        from sklearn.pipeline import make_pipeline
        from sklearn.preprocessing import StandardScaler

        return make_pipeline(StandardScaler(), LogisticRegression(max_iter=500))
    if model_type == "random_forest":
        from sklearn.ensemble import RandomForestClassifier

        return RandomForestClassifier(
            n_estimators=150, max_depth=6, min_samples_leaf=50, n_jobs=-1, random_state=random_state
        )
    if model_type == "gbm":
        from sklearn.ensemble import HistGradientBoostingClassifier

        return HistGradientBoostingClassifier(max_depth=3, learning_rate=0.05, max_iter=150, random_state=random_state)
    raise ValueError(f"model_type={model_type!r} must be one of {MODEL_TYPES}")


def _to_date(value) -> date_type:
    return pd.Timestamp(value).date()


class MLClassifierStrategy(PredictModel):
    """Walk-forward scikit-learn classifier (logistic / random forest / gradient boosting) per number."""

    def __init__(
        self,
        df: pd.DataFrame,
        time_predict: int = 1,
        min_val: int = PredictModel.POWER_655_MIN_VAL,
        max_val: int = PredictModel.POWER_655_MAX_VAL,
        model_type: str = "logistic",
        refit_every: int = 1,
        min_train_draws: int = 60,
        selection: str = "sample",
        temperature: float = 1.0,
        seed: Optional[int] = None,
        extra_features: Sequence[FeatureBuilder] = (),
    ):
        """
        Args:
            df: Historical draws (``date`` + ``result``).
            time_predict: Tickets per draw during backtests.
            min_val / max_val: Inclusive number range.
            model_type: ``"logistic"``, ``"random_forest"`` or ``"gbm"``.
            refit_every: Re-train the classifier every this many draws (walk-forward). The default 1
                re-trains after every new draw.
            min_train_draws: Below this many past draws the strategy falls back to uniform picks.
            selection: ``"sample"`` (weighted sampling) or ``"top"`` (highest probabilities).
            temperature: Sharpening (<1) or flattening (>1) of probabilities before sampling.
            seed: Seed for ticket sampling and model randomness.
            extra_features: Builders of additional causal features from other data sources (another
                game's draws, the calendar, ...), concatenated to the per-number features.
        """
        super().__init__(df, time_predict, min_val, max_val)
        if model_type not in MODEL_TYPES:
            raise ValueError(f"model_type={model_type!r} must be one of {MODEL_TYPES}")
        if selection not in ("sample", "top"):
            raise ValueError("selection must be 'sample' or 'top'")
        self.model_type = model_type
        self.refit_every = max(1, int(refit_every))
        self.min_train_draws = max(1, int(min_train_draws))
        self.selection = selection
        self.temperature = float(temperature)
        self.seed = seed
        self._rng = np.random.default_rng(seed)
        self._models: Dict[int, object] = {}
        self.extra_features = list(extra_features)
        self._prepare_historical_data()

    def reseed(self, seed: int) -> None:
        super().reseed(seed)
        self._rng = np.random.default_rng(seed)

    def _prepare_historical_data(self) -> None:
        df_sorted = self.df.sort_values("date").reset_index(drop=True)
        self._dates = [_to_date(d) for d in df_sorted["date"]]
        self._occ = occurrence_matrix(df_sorted["result"].tolist(), self.min_val, self.max_val)
        self._features = build_features(self._occ, DEFAULT_WINDOWS)
        self.feature_names = feature_names(DEFAULT_WINDOWS)
        for builder in getattr(self, "extra_features", []):
            extra, names = builder(self._dates, self._occ)
            if extra.shape[:2] != self._features.shape[:2]:
                raise ValueError(f"extra features shape {extra.shape} does not match {self._features.shape}")
            self._features = np.concatenate([self._features, extra], axis=-1)
            self.feature_names = self.feature_names + list(names)

    def _draw_index(self, target_date) -> int:
        """Number of stored draws strictly before ``target_date`` (``len`` for future dates/None)."""
        if target_date is None:
            return len(self._dates)
        return bisect_left(self._dates, _to_date(target_date))

    def _model_for(self, t: int):
        """Classifier trained on draws before the walk-forward bucket containing ``t`` (cached)."""
        bucket = (t // self.refit_every) * self.refit_every
        if bucket < self.min_train_draws:
            return None
        if bucket not in self._models:
            start = 1  # row 0 has no history at all
            x = self._features[start:bucket].reshape(-1, self._features.shape[-1])
            y = self._occ[start:bucket].reshape(-1)
            model = make_classifier(self.model_type, self.seed)
            model.fit(x, y)
            self._models[bucket] = model
        return self._models[bucket]

    def number_probabilities(self, target_date=None) -> np.ndarray:
        """Predicted probability that each number in ``[min_val, max_val]`` is drawn on ``target_date``."""
        t = self._draw_index(target_date)
        model = self._model_for(t)
        n_numbers = self.max_val - self.min_val + 1
        if model is None:
            return np.full(n_numbers, self.number_predict / n_numbers)
        return model.predict_proba(self._features[t])[:, 1]

    def feature_importance(self, target_date=None) -> Dict[str, float]:
        """Importance (|standardised coefficient| or impurity importance) of each feature."""
        model = self._model_for(self._draw_index(target_date))
        if model is None:
            return {}
        if self.model_type == "logistic":
            coef = model[-1].coef_[0]
            return {name: float(c) for name, c in zip(self.feature_names, coef)}
        if hasattr(model, "feature_importances_"):
            return {name: float(v) for name, v in zip(self.feature_names, model.feature_importances_)}
        return {}

    def predict(self, date=None):
        probs = np.clip(self.number_probabilities(date), 1e-9, None)
        numbers = np.arange(self.min_val, self.max_val + 1)
        if self.selection == "top":
            picked = numbers[np.argsort(-probs, kind="stable")[: self.number_predict]]
        else:
            weights = probs ** (1.0 / max(self.temperature, 1e-6))
            picked = self._rng.choice(numbers, size=self.number_predict, replace=False, p=weights / weights.sum())
        return sorted(int(n) for n in picked)
