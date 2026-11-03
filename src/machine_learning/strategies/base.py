"""
Base class for all lottery prediction strategies.

All concrete strategy classes must inherit from ``PredictModel`` and override
the :meth:`predict` method.  The base class provides:

* shared constants (number range, prize table, column names);
* generic :meth:`backtest` that calls ``predict`` once per row in the dataset;
* :meth:`evaluate` that flattens the backtest results and computes accuracy
  statistics; and
* :meth:`revenue` that estimates profit/loss given the prize structure.

Stored Power 6/55 results carry the bonus number last (``[n1..n6, bonus]``).  The constructor splits it
into a separate ``bonus`` column so strategies only ever learn from, and are scored against, the six
main numbers; the bonus is used solely to decide the Jackpot 2 tier (see :mod:`machine_learning.games`).
"""

import pandas as pd

from machine_learning.games import POWER_655, GameSpec


class PredictModel:
    """
    Abstract base model for Vietlott lottery number prediction.

    Sub-classes implement :meth:`predict` with their own selection logic.
    The remaining methods (:meth:`backtest`, :meth:`evaluate`, :meth:`revenue`)
    are generic and work unchanged for every strategy.

    Class-level constants
    ---------------------
    POWER_655_MIN_VAL / POWER_655_MAX_VAL
        Inclusive number range for Power 6/55 (1–55).
    number_predict
        How many distinct numbers form a single ticket (6).
    ticket_price
        Cost of a single ticket in VND (10,000).
    game
        :class:`~machine_learning.games.GameSpec` with the prize tiers used for scoring.  Defaults to
        Power 6/55; assign ``MEGA_645`` (and ``max_val=45``) to evaluate Mega 6/45.
    col_*
        Column name constants used across backtest / evaluate DataFrames.
    """

    POWER_655_MIN_VAL = 1
    POWER_655_MAX_VAL = 55  # assume we are using power655
    number_predict = 6
    ticket_price = 10000

    game: GameSpec = POWER_655

    col_date = "date"
    col_result = "result"
    col_predict = "predicted"
    col_predict_time = "predict_time"
    col_predict_metadata = "predict_metadata"
    col_correct = "is_correct"
    col_correct_num = "correct_num"
    col_bonus = "bonus"
    col_bonus_hit = "bonus_hit"
    col_prize = "prize"

    def __init__(
        self,
        df: pd.DataFrame,
        time_predict: int = 1,
        min_val: int = POWER_655_MIN_VAL,
        max_val: int = POWER_655_MAX_VAL,
    ):
        """
        Parameters
        ----------
        df:
            Historical lottery draw data.  Must contain at least a ``date``
            column and a ``result`` column where each cell is a list of drawn
            numbers.
        time_predict:
            Number of independent tickets to generate per draw date during
            backtesting.  Higher values increase cost but give the model more
            chances to match any given draw.
        min_val:
            Smallest valid lottery number (inclusive).
        max_val:
            Largest valid lottery number (inclusive).
        """
        self.df = self._split_bonus(df)
        self.df_backtest = None
        self.df_backtest_explode = None
        self.df_backtest_evaluate = None
        self.time_predict = time_predict
        self.min_val = min_val
        self.max_val = max_val

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @classmethod
    def _split_bonus(cls, df: pd.DataFrame) -> pd.DataFrame:
        """Return a copy of ``df`` whose ``result`` holds only the main numbers.

        Any number stored after the first ``number_predict`` (the Power 6/55 bonus) moves to a
        ``bonus`` column, so it is neither learned from nor counted as a regular match.
        """
        if cls.col_result not in df.columns or cls.col_bonus in df.columns:
            return df
        out = df.copy()
        # polars -> pandas yields numpy arrays rather than lists, so accept any non-string sequence
        results = [[int(n) for n in r] if cls._is_sequence(r) else r for r in out[cls.col_result].tolist()]
        if not any(cls._is_sequence(r) and len(r) > cls.number_predict for r in results):
            return out
        out[cls.col_bonus] = [
            r[cls.number_predict] if cls._is_sequence(r) and len(r) > cls.number_predict else None for r in results
        ]
        out[cls.col_result] = [r[: cls.number_predict] if cls._is_sequence(r) else r for r in results]
        return out

    @staticmethod
    def _is_sequence(value) -> bool:
        return hasattr(value, "__len__") and hasattr(value, "__getitem__") and not isinstance(value, (str, bytes))

    def score_ticket(self, ticket, main_numbers, bonus=None) -> dict:
        """Score ``ticket`` against a draw; returns match count, bonus hit, full-match flag and prize."""
        main_numbers = [int(n) for n in main_numbers]
        if len(main_numbers) > self.number_predict:
            if bonus is None:
                bonus = main_numbers[self.number_predict]
            main_numbers = main_numbers[: self.number_predict]
        correct, correct_num = self._compare_list(main_numbers, ticket)
        bonus_hit = bonus is not None and not pd.isna(bonus) and int(bonus) in set(ticket)
        tier = self.game.tier_for(correct_num, bonus_hit)
        return {
            PredictModel.col_correct: correct,
            PredictModel.col_correct_num: correct_num,
            PredictModel.col_bonus_hit: bonus_hit,
            PredictModel.col_prize: tier.value if tier else 0,
        }

    @classmethod
    def _count_number(cls, number_series):
        """Return a frequency table for numbers across all draw rows."""
        return number_series.explode().value_counts().to_frame("times")

    @classmethod
    def _compare_list(cls, l1, l2):
        """
        Compare two number lists.

        Returns
        -------
        (is_full_match, intersection_size)
            ``is_full_match`` is ``True`` only when every element of ``l1``
            appears in ``l2``.
        """
        l1_s = set(l1)
        l2_s = set(l2)
        inter = l1_s.intersection(l2_s)
        return len(inter) == len(l1), len(inter)

    # ------------------------------------------------------------------
    # Core interface
    # ------------------------------------------------------------------

    def predict(self, date):
        """
        Predict lottery numbers for the given draw date.

        Sub-classes **must** override this method.

        Parameters
        ----------
        date:
            The draw date for which predictions should be generated.
            Only data strictly *before* this date should be used to avoid
            look-ahead bias.

        Returns
        -------
        list[int]
            A sorted list of ``number_predict`` distinct integers in
            ``[min_val, max_val]``.
        """
        pass

    def backtest(self, date_from=None, date_to=None):
        """
        Run the strategy over rows in ``self.df``.

        For each row the strategy generates ``time_predict`` tickets.  Each
        ticket is compared against the actual draw result and the outcome is
        stored as a list of dicts under the ``predict_metadata`` column.

        Results are saved to ``self.df_backtest``.

        Parameters
        ----------
        date_from:
            Optional start date (inclusive) for the backtest period.  Only
            rows with ``date >= date_from`` are evaluated.  The full
            ``self.df`` is still available to strategies for historical
            lookups; this only limits *which* dates are evaluated.
        date_to:
            Optional end date (inclusive) for the backtest period.  Only
            rows with ``date <= date_to`` are evaluated.
        """
        _df = self.df.copy()
        if date_from is not None:
            _df = _df[_df["date"] >= date_from]
        if date_to is not None:
            _df = _df[_df["date"] <= date_to]

        def fn_apply(row):
            predicted = []
            bonus = getattr(row, PredictModel.col_bonus, None)
            for i in range(self.time_predict):
                loop_predict = self.predict(row.date)
                predicted.append(
                    {
                        PredictModel.col_predict + "_idx": i,
                        PredictModel.col_predict: loop_predict,
                        **self.score_ticket(loop_predict, row.result, bonus),
                    }
                )

            return predicted

        _df["predict_metadata"] = _df.apply(fn_apply, axis=1)
        self.df_backtest = _df

    def evaluate(self):
        """
        Flatten backtest metadata and compute accuracy statistics.

        Populates ``self.df_backtest_explode`` and
        ``self.df_backtest_evaluate``, then returns a summary dict with:

        * ``correct_time`` – total number of fully-correct tickets.
        * ``count_correct_num`` – frequency distribution of match counts.
        """
        self.df_backtest_explode = self.df_backtest.explode(PredictModel.col_predict_metadata)
        self.df_backtest_evaluate = pd.concat(
            [
                self.df_backtest_explode.reset_index(drop=True),
                pd.json_normalize(self.df_backtest_explode[PredictModel.col_predict_metadata]).reset_index(drop=True),
            ],
            axis="columns",
        )

        return {
            "correct_time": self.df_backtest_evaluate[PredictModel.col_correct].sum(),
            "count_correct_num": self.df_backtest_evaluate.value_counts(PredictModel.col_correct_num),
        }

    def revenue(self):
        """
        Estimate financial outcome of the backtest.

        Returns
        -------
        (cost, gain, profit)
            All values in VND.  ``profit = gain - cost``.  Prizes follow :attr:`game` (minimum jackpot
        values), with the bonus number only deciding the Jackpot 2 tier.
        """
        cost = len(self.df_backtest_evaluate) * self.ticket_price
        gain = int(self.df_backtest_evaluate[PredictModel.col_prize].fillna(0).astype("int64").sum())

        return cost, gain, gain - cost
