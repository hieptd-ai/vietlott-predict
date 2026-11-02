"""
Statistical analysis, honest backtests and ML predictability tests for Power 6/55 and Mega 6/45.

:func:`build_analysis` returns one JSON-serialisable dict that the static dashboard in
``docs/analysis/`` renders.  Every observed statistic is paired with its exact expectation under a
fair (uniform, independent) lottery so the page can show *how far* reality is from pure chance:

* number frequencies + a chi-square uniformity test corrected for draws without replacement;
* overlap between consecutive draws vs the hypergeometric expectation (independence test);
* distribution of ticket sums, odd/even and low/high splits vs their exact distributions;
* most frequent pairs vs the expected pair count;
* walk-forward backtest of every strategy, scored with the real prize tiers;
* walk-forward evaluation of ML classifiers (ROC-AUC, log-loss, calibration) vs the constant baseline.
"""

import math
import random
import time
from collections import Counter
from datetime import date, timedelta
from itertools import combinations
from typing import Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd
from loguru import logger

from machine_learning.features import DEFAULT_WINDOWS, build_features, feature_names, occurrence_matrix
from machine_learning.games import GameSpec, get_game
from machine_learning.strategies import (
    ColdNumbersStrategy,
    ExponentialDecayStrategy,
    HotNumbersStrategy,
    LongAbsenceStrategy,
    MarkovChainStrategy,
    MLClassifierStrategy,
    NotRepeatStrategy,
    PairFrequencyStrategy,
    PatternStrategy,
    PositionalStrategy,
    PredictModel,
    RandomModel,
)
from machine_learning.strategies.ml_classifier import make_classifier

StrategyFactory = Callable[[pd.DataFrame, GameSpec], PredictModel]


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------


def load_draws(game: GameSpec, path=None) -> pd.DataFrame:
    """Load a product as a date-sorted DataFrame with ``date``, ``id``, ``result`` (main) and ``bonus``."""
    import polars as pl

    if path is None:
        from vietlott.config.products import get_config

        path = get_config(game.key).raw_path
    raw = pl.read_ndjson(path).select(["date", "id", "result"]).to_pandas()
    return prepare_draws(raw, game)


def prepare_draws(raw: pd.DataFrame, game: GameSpec) -> pd.DataFrame:
    """Normalise a raw ``date``/``id``/``result`` frame: split the bonus, parse dates, sort, dedupe."""
    df = raw.copy()
    df["date"] = pd.to_datetime(df["date"]).dt.date
    splits = [game.split(list(r)) for r in df["result"]]
    df["result"] = [sorted(main) for main, _ in splits]
    df["bonus"] = [bonus for _, bonus in splits]
    if "id" not in df.columns:
        df["id"] = [str(i + 1) for i in range(len(df))]
    df["id"] = df["id"].astype(str)
    df = df.drop_duplicates(subset=["id"], keep="last")
    df = df.sort_values(["date", "id"]).reset_index(drop=True)
    return df[["date", "id", "result", "bonus"]]


# ---------------------------------------------------------------------------
# Exact distributions of a fair draw
# ---------------------------------------------------------------------------


def hypergeom_pmf(pool: int, successes: int, draws: int) -> List[float]:
    """``P(X = k)`` for ``k = 0..draws`` when drawing ``draws`` of ``pool`` with ``successes`` marked."""
    total = math.comb(pool, draws)
    return [math.comb(successes, k) * math.comb(pool - successes, draws - k) / total for k in range(draws + 1)]


def sum_distribution(game: GameSpec) -> Dict[int, float]:
    """Exact probability of each possible sum of the ``pick`` main numbers of a fair draw."""
    max_sum = sum(range(game.max_val - game.pick + 1, game.max_val + 1))
    ways = np.zeros((game.pick + 1, max_sum + 1), dtype=np.int64)
    ways[0, 0] = 1
    for n in range(game.min_val, game.max_val + 1):
        for k in range(game.pick, 0, -1):
            ways[k, n:] = ways[k, n:] + ways[k - 1, : max_sum + 1 - n]
    total = math.comb(game.pool, game.pick)
    return {s: int(ways[game.pick, s]) / total for s in range(max_sum + 1) if ways[game.pick, s]}


def _normal_two_sided_p(z: float) -> float:
    return math.erfc(abs(z) / math.sqrt(2))


def _chi2_sf(stat: float, dof: int) -> Optional[float]:
    try:
        from scipy import stats

        return float(stats.chi2.sf(stat, dof))
    except ImportError:  # pragma: no cover - scipy ships with scikit-learn
        return None


# ---------------------------------------------------------------------------
# Descriptive statistics
# ---------------------------------------------------------------------------


def frequency_analysis(results: Sequence[Sequence[int]], game: GameSpec, recent: int = 100) -> dict:
    """All-time and recent frequency per number, gaps, and the uniformity chi-square test."""
    numbers = list(range(game.min_val, game.max_val + 1))
    n_draws = len(results)
    counts = Counter(n for draw in results for n in draw)
    recent_counts = Counter(n for draw in results[-recent:] for n in draw)
    p = game.pick / game.pool

    expected = n_draws * p
    # draws are without replacement, so per-number counts are negatively correlated; scaling by
    # N/(N-1) makes the statistic chi-square with N-1 degrees of freedom under the null
    variance = n_draws * p * (1 - p) * game.pool / (game.pool - 1)
    chi2 = sum((counts.get(n, 0) - expected) ** 2 for n in numbers) / variance if variance else 0.0
    dof = game.pool - 1

    last_seen = {}
    for t, draw in enumerate(results):
        for n in draw:
            last_seen[n] = t
    gaps = [n_draws - 1 - last_seen[n] if n in last_seen else n_draws for n in numbers]

    return {
        "numbers": numbers,
        "counts": [counts.get(n, 0) for n in numbers],
        "expected": expected,
        "recent_window": min(recent, n_draws),
        "recent_counts": [recent_counts.get(n, 0) for n in numbers],
        "recent_expected": min(recent, n_draws) * p,
        "gaps": gaps,
        "expected_gap": (1 - p) / p,
        "uniformity": {"chi2": chi2, "dof": dof, "p_value": _chi2_sf(chi2, dof)},
    }


def independence_analysis(results: Sequence[Sequence[int]], game: GameSpec) -> dict:
    """Do consecutive draws share more/fewer numbers than chance? (hypergeometric z-test)."""
    overlaps = [len(set(a) & set(b)) for a, b in zip(results[:-1], results[1:])]
    k, n = game.pick, game.pool
    expected = k * k / n
    variance = k * (k / n) * ((n - k) / n) * ((n - k) / (n - 1))
    mean = float(np.mean(overlaps)) if overlaps else 0.0
    z = (mean - expected) / math.sqrt(variance / len(overlaps)) if overlaps else 0.0
    dist = Counter(overlaps)
    pmf = hypergeom_pmf(n, k, k)
    return {
        "mean_overlap": mean,
        "expected_overlap": expected,
        "z": z,
        "p_value": _normal_two_sided_p(z),
        "k": list(range(k + 1)),
        "observed": [dist.get(i, 0) for i in range(k + 1)],
        "expected": [len(overlaps) * pmf[i] for i in range(k + 1)],
    }


def shape_analysis(results: Sequence[Sequence[int]], game: GameSpec, bin_width: int = 15) -> dict:
    """Sum histogram plus odd/even and low/high splits, each against its exact fair distribution."""
    n_draws = len(results)
    sums = [sum(d) for d in results]
    exact = sum_distribution(game)
    lo, hi = min(exact), max(exact)
    edges = list(range(lo - (lo % bin_width), hi + bin_width, bin_width))
    observed_bins, expected_bins, labels = [], [], []
    for a in edges[:-1]:
        b = a + bin_width
        observed_bins.append(sum(1 for s in sums if a <= s < b))
        expected_bins.append(n_draws * sum(p for s, p in exact.items() if a <= s < b))
        labels.append(f"{a}–{b - 1}")
    mean_sum = sum(s * p for s, p in exact.items())

    odd_pool = sum(1 for n in range(game.min_val, game.max_val + 1) if n % 2 == 1)
    low_cut = game.min_val + game.pool // 2 - 1
    low_pool = low_cut - game.min_val + 1
    odd_counts = Counter(sum(1 for n in d if n % 2 == 1) for d in results)
    low_counts = Counter(sum(1 for n in d if n <= low_cut) for d in results)
    odd_pmf = hypergeom_pmf(game.pool, odd_pool, game.pick)
    low_pmf = hypergeom_pmf(game.pool, low_pool, game.pick)
    ks = list(range(game.pick + 1))
    return {
        "sum": {
            "labels": labels,
            "observed": observed_bins,
            "expected": expected_bins,
            "mean_observed": float(np.mean(sums)) if sums else 0.0,
            "mean_expected": mean_sum,
        },
        "odd": {"k": ks, "observed": [odd_counts.get(k, 0) for k in ks], "expected": [n_draws * p for p in odd_pmf]},
        "low": {
            "k": ks,
            "cut": low_cut,
            "observed": [low_counts.get(k, 0) for k in ks],
            "expected": [n_draws * p for p in low_pmf],
        },
    }


def pair_analysis(results: Sequence[Sequence[int]], game: GameSpec, top: int = 12) -> dict:
    """Most frequent number pairs and the expected count of any single pair."""
    pairs = Counter(pair for draw in results for pair in combinations(sorted(draw), 2))
    p_pair = game.pick * (game.pick - 1) / (game.pool * (game.pool - 1))
    expected = len(results) * p_pair
    sd = math.sqrt(len(results) * p_pair * (1 - p_pair))
    return {
        "expected": expected,
        "n_pairs": math.comb(game.pool, 2),
        "top": [
            {"pair": list(pair), "count": count, "z": (count - expected) / sd if sd else 0.0}
            for pair, count in pairs.most_common(top)
        ],
    }


# ---------------------------------------------------------------------------
# Strategy backtest
# ---------------------------------------------------------------------------


def default_strategies(seed: int = 42) -> List[Tuple[str, str, StrategyFactory]]:
    """``(key, display name, factory)`` for every strategy shown on the dashboard."""

    def bounds(game: GameSpec) -> dict:
        return {"min_val": game.min_val, "max_val": game.max_val}

    return [
        ("random", "Ngẫu nhiên (baseline)", lambda df, g: RandomModel(df, **bounds(g))),
        ("hot", "Số nóng (tần suất cao)", lambda df, g: HotNumbersStrategy(df, **bounds(g), lookback_days=365)),
        ("cold", "Số lạnh (tần suất thấp)", lambda df, g: ColdNumbersStrategy(df, **bounds(g), lookback_days=365)),
        ("long_absence", "Lâu chưa về", lambda df, g: LongAbsenceStrategy(df, **bounds(g), top_n=15)),
        ("not_repeat", "Tránh số vừa ra", lambda df, g: NotRepeatStrategy(df, **bounds(g), lookback_days=30)),
        ("pattern", "Mẫu khoảng cách", lambda df, g: PatternStrategy(df, **bounds(g), lookback_days=180)),
        ("exp_decay", "Suy giảm mũ", lambda df, g: ExponentialDecayStrategy(df, **bounds(g), half_life_days=90)),
        ("pair", "Cặp số đi cùng", lambda df, g: PairFrequencyStrategy(df, **bounds(g), lookback_days=365)),
        ("markov", "Chuỗi Markov", lambda df, g: MarkovChainStrategy(df, **bounds(g), lookback_days=365)),
        ("positional", "Theo vị trí (order statistic)", lambda df, g: PositionalStrategy(df, **bounds(g))),
        (
            "ml_logistic",
            "ML: Logistic Regression",
            lambda df, g: MLClassifierStrategy(df, **bounds(g), model_type="logistic", seed=seed),
        ),
        (
            "ml_gbm",
            "ML: Gradient Boosting",
            lambda df, g: MLClassifierStrategy(df, **bounds(g), model_type="gbm", seed=seed),
        ),
    ]


def backtest_strategies(
    df: pd.DataFrame,
    game: GameSpec,
    strategies: Sequence[Tuple[str, str, StrategyFactory]],
    window: int = 150,
    tickets_per_draw: int = 10,
) -> dict:
    """Walk-forward backtest over the last ``window`` draws, ``tickets_per_draw`` tickets each."""
    test = df.tail(window)
    match_pmf = game.match_probabilities()
    expected_avg = game.expected_matches()
    per_ticket_var = sum((k - expected_avg) ** 2 * p for k, p in enumerate(match_pmf))
    rows = []
    for key, name, factory in strategies:
        started = time.time()
        try:
            model = factory(df, game)
            model.game = game
        except Exception as exc:  # optional dependency missing, bad params, ...
            logger.warning(f"skip strategy {key}: {exc}")
            continue
        dist = Counter()
        tiers = Counter()
        gain = 0
        n_tickets = 0
        draw_means = []
        for row in test.itertuples(index=False):
            draw_matches = 0
            for _ in range(tickets_per_draw):
                ticket = model.predict(row.date)
                scored = model.score_ticket(ticket, row.result, row.bonus)
                tier = game.tier_for(scored["correct_num"], scored["bonus_hit"])
                dist[scored["correct_num"]] += 1
                if tier:
                    tiers[tier.key] += 1
                    gain += tier.value
                n_tickets += 1
                draw_matches += scored["correct_num"]
            draw_means.append(draw_matches / tickets_per_draw)
        cost = n_tickets * game.ticket_price
        avg = sum(k * c for k, c in dist.items()) / n_tickets if n_tickets else 0.0
        # tickets bought for the same draw are correlated (a strategy often repeats numbers), so the
        # standard error is taken over per-draw means; it never undercuts the independent-ticket one
        se_independent = math.sqrt(per_ticket_var / n_tickets) if n_tickets else 0.0
        se_cluster = float(np.std(draw_means, ddof=1) / math.sqrt(len(draw_means))) if len(draw_means) > 1 else 0.0
        se = max(se_independent, se_cluster)
        z = (avg - expected_avg) / se if se else 0.0
        rows.append(
            {
                "key": key,
                "name": name,
                "tickets": n_tickets,
                "avg_matches": avg,
                "z": z,
                "p_value": _normal_two_sided_p(z),
                "match_dist": [dist.get(k, 0) for k in range(game.pick + 1)],
                "tiers": {t.key: tiers.get(t.key, 0) for t in game.tiers},
                "cost": cost,
                "gain": gain,
                "roi": (gain - cost) / cost * 100 if cost else 0.0,
                "seconds": round(time.time() - started, 2),
            }
        )
        logger.info(f"{game.key} backtest {key}: avg={avg:.4f} z={z:+.2f} roi={rows[-1]['roi']:.1f}%")
    return {
        "window_draws": len(test),
        "date_from": str(test["date"].iloc[0]) if len(test) else None,
        "date_to": str(test["date"].iloc[-1]) if len(test) else None,
        "tickets_per_draw": tickets_per_draw,
        "expected_avg_matches": expected_avg,
        "expected_match_dist": match_pmf,
        "expected_roi": (game.expected_value() - game.ticket_price) / game.ticket_price * 100,
        "n_strategies": len(rows),
        "bonferroni_z": _bonferroni_z(len(rows)),
        "strategies": [{**r, "p_adjusted": min(1.0, r["p_value"] * len(rows))} for r in rows],
    }


def _bonferroni_z(n_tests: int, alpha: float = 0.05) -> float:
    """Two-sided |z| threshold for family-wise significance ``alpha`` over ``n_tests`` comparisons."""
    from statistics import NormalDist

    return NormalDist().inv_cdf(1 - alpha / (2 * max(n_tests, 1)))


# ---------------------------------------------------------------------------
# ML predictability (walk-forward)
# ---------------------------------------------------------------------------


def ml_predictability(
    df: pd.DataFrame,
    game: GameSpec,
    model_types: Sequence[str] = ("logistic", "random_forest", "gbm"),
    eval_draws: int = 300,
    refit_every: int = 50,
    seed: int = 42,
) -> dict:
    """Walk-forward ROC-AUC / log-loss / calibration of per-number classifiers vs the constant baseline."""
    from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score

    occ = occurrence_matrix(df["result"].tolist(), game.min_val, game.max_val)
    feats = build_features(occ, DEFAULT_WINDOWS)
    n_draws = len(occ)
    start = max(refit_every, n_draws - eval_draws)
    base_rate = game.pick / game.pool
    y_eval = occ[start:].reshape(-1)
    baseline = {
        "log_loss": float(log_loss(y_eval, np.full(len(y_eval), base_rate), labels=[0, 1])),
        "brier": float(brier_score_loss(y_eval, np.full(len(y_eval), base_rate))),
        "auc": 0.5,
        "top_hits": game.expected_matches(),
    }
    models = []
    for model_type in model_types:
        started = time.time()
        probs = np.zeros((n_draws - start, game.pool))
        model = None
        for t in range(start, n_draws):
            if model is None or (t - start) % refit_every == 0:
                model = make_classifier(model_type, seed)
                model.fit(feats[1:t].reshape(-1, feats.shape[-1]), occ[1:t].reshape(-1))
            probs[t - start] = model.predict_proba(feats[t])[:, 1]
        flat = probs.reshape(-1)
        top = np.argsort(-probs, axis=1)[:, : game.pick]
        top_hits = float(np.mean(np.take_along_axis(occ[start:], top, axis=1).sum(axis=1)))
        edges = np.quantile(flat, np.linspace(0, 1, 6))
        calibration = []
        for i in range(5):
            lo, hi = edges[i], edges[i + 1]
            mask = (flat >= lo) & ((flat <= hi) if i == 4 else (flat < hi))
            if mask.any():
                calibration.append(
                    {
                        "predicted": float(flat[mask].mean()),
                        "observed": float(y_eval[mask].mean()),
                        "n": int(mask.sum()),
                    }
                )
        importance = {}
        final = make_classifier(model_type, seed)
        final.fit(feats[1:n_draws].reshape(-1, feats.shape[-1]), occ[1:n_draws].reshape(-1))
        if model_type == "logistic":
            importance = {n: float(c) for n, c in zip(feature_names(DEFAULT_WINDOWS), final[-1].coef_[0])}
        elif hasattr(final, "feature_importances_"):
            importance = {n: float(v) for n, v in zip(feature_names(DEFAULT_WINDOWS), final.feature_importances_)}
        models.append(
            {
                "model": model_type,
                "auc": float(roc_auc_score(y_eval, flat)),
                "log_loss": float(log_loss(y_eval, np.clip(flat, 1e-6, 1 - 1e-6), labels=[0, 1])),
                "brier": float(brier_score_loss(y_eval, flat)),
                "top_hits": top_hits,
                "prob_min": float(flat.min()),
                "prob_max": float(flat.max()),
                "calibration": calibration,
                "importance": importance,
                "next_draw_probs": [float(p) for p in final.predict_proba(feats[n_draws])[:, 1]],
                "seconds": round(time.time() - started, 2),
            }
        )
        logger.info(f"{game.key} ML {model_type}: auc={models[-1]['auc']:.4f} top_hits={top_hits:.3f}")
    return {
        "eval_draws": n_draws - start,
        "refit_every": refit_every,
        "features": feature_names(DEFAULT_WINDOWS),
        "base_rate": base_rate,
        "baseline": baseline,
        "models": models,
    }


# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------


def suggestions(
    df: pd.DataFrame, game: GameSpec, strategies: Sequence[Tuple[str, str, StrategyFactory]], n: int = 3
) -> List[dict]:
    """``n`` tickets per strategy for the next draw (all history used)."""
    next_date = df["date"].iloc[-1] + timedelta(days=1)
    out = []
    for key, name, factory in strategies:
        try:
            model = factory(df, game)
            out.append({"key": key, "name": name, "tickets": [model.predict(next_date) for _ in range(n)]})
        except Exception as exc:
            logger.warning(f"skip suggestions for {key}: {exc}")
    return out


def analyse_game(
    df: pd.DataFrame,
    game: GameSpec,
    backtest_window: int = 150,
    tickets_per_draw: int = 10,
    ml_eval_draws: int = 300,
    seed: int = 42,
    strategies: Optional[Sequence[Tuple[str, str, StrategyFactory]]] = None,
    ml_models: Sequence[str] = ("logistic", "random_forest", "gbm"),
) -> dict:
    """Full analysis block for one game."""
    random.seed(seed)
    np.random.seed(seed)
    strategies = list(strategies) if strategies is not None else default_strategies(seed)
    results = df["result"].tolist()
    last = df.iloc[-1]
    recent = df.tail(12).iloc[::-1]
    probs = game.tier_probabilities()
    return {
        "key": game.key,
        "title": game.title,
        "range": [game.min_val, game.max_val],
        "pick": game.pick,
        "has_bonus": game.has_bonus,
        "ticket_price": game.ticket_price,
        "tiers": [
            {
                "key": t.key,
                "label": t.label,
                "value": t.value,
                "probability": probs[t.key],
                "odds": 1 / probs[t.key] if probs[t.key] else None,
            }
            for t in game.tiers
        ],
        "n_draws": len(df),
        "date_from": str(df["date"].iloc[0]),
        "date_to": str(last["date"]),
        "latest": {"id": last["id"], "date": str(last["date"]), "main": last["result"], "bonus": _int(last["bonus"])},
        "recent": [
            {"id": r.id, "date": str(r.date), "main": list(r.result), "bonus": _int(r.bonus)}
            for r in recent.itertuples(index=False)
        ],
        "frequency": frequency_analysis(results, game),
        "independence": independence_analysis(results, game),
        "shape": shape_analysis(results, game),
        "pairs": pair_analysis(results, game),
        "backtest": backtest_strategies(df, game, strategies, backtest_window, tickets_per_draw),
        "ml": ml_predictability(df, game, ml_models, ml_eval_draws, seed=seed),
        "suggestions": suggestions(df, game, strategies),
    }


def _int(value) -> Optional[int]:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    return int(value)


def build_analysis(games: Sequence[str] = ("power_655", "power_645"), **kwargs) -> dict:
    """Analysis for every requested game, ready to dump as JSON for the dashboard."""
    products = {}
    for key in games:
        game = get_game(key)
        logger.info(f"analysing {game.title}...")
        products[key] = analyse_game(load_draws(game), game, **kwargs)
    return {
        "generated_at": pd.Timestamp.now(tz="Asia/Ho_Chi_Minh").isoformat(timespec="seconds"),
        "generated_date": str(date.today()),
        "products": products,
    }
