"""
Statistical analysis, honest backtests and ML predictability tests for Power 6/55 and Mega 6/45.

:func:`build_analysis` returns one JSON-serialisable dict that the static dashboard in
``docs/analysis/`` renders.  Every observed statistic is paired with its exact expectation under a
fair (uniform, independent) lottery so the page can show *how far* reality is from pure chance:

* number frequencies + a chi-square uniformity test corrected for draws without replacement;
* overlap between consecutive draws vs the hypergeometric expectation (independence test);
* distribution of ticket sums, odd/even and low/high splits vs their exact distributions;
* most frequent pairs vs the expected pair count;
* walk-forward evaluation of ML classifiers (ROC-AUC, log-loss, calibration) vs the constant baseline,
  including a multi-source model fed with another game's draws and the calendar;
* a "play since 2026" comparison of every method (default 10 tickets per draw, repeated over several
  random runs) with one summary table, a significance test against chance and the best method;
* the tickets every method predicts for the next draw, re-trained on all draws known so far.
"""

import math
import random
import time
from collections import Counter
from datetime import date
from itertools import combinations
from typing import Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd
from loguru import logger

from machine_learning.features import (
    DEFAULT_WINDOWS,
    build_features,
    calendar_features,
    cross_game_features,
    feature_names,
    next_draw_date,
    occurrence_matrix,
)
from machine_learning.games import GameSpec, get_game
from machine_learning.ledger import load_replay_entries, load_replay_summary, next_draw_id, score_ledger
from machine_learning.strategies import (
    ColdNumbersStrategy,
    ConsensusStrategy,
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

# extra data sources: product key -> date-sorted DataFrame with ``date`` and main-number ``result``
Sources = Dict[str, pd.DataFrame]

SOURCE_TITLES = {"power_655": "6/55", "power_645": "6/45", "power_535": "5/35"}


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


def load_sources(keys: Sequence[str] = ("power_655", "power_645", "power_535")) -> Sources:
    """Main numbers of every 6/55-style product, used as extra (cross-game) data sources."""
    import polars as pl

    from vietlott.config.products import get_config

    picks = {"power_655": 6, "power_645": 6, "power_535": 5}
    sources: Sources = {}
    for key in keys:
        path = get_config(key).raw_path
        if not path.exists():
            continue
        raw = pl.read_ndjson(path).select(["date", "result"]).to_pandas()
        raw["date"] = pd.to_datetime(raw["date"]).dt.date
        raw["result"] = [sorted(int(n) for n in list(r)[: picks[key]]) for r in raw["result"]]
        sources[key] = raw.sort_values("date").reset_index(drop=True)
    return sources


def multi_source_builders(game: GameSpec, sources: Optional[Sources]) -> Tuple[list, List[str]]:
    """Feature builders from every other product plus the calendar, and the source names they use."""
    builders = []
    used = []
    for key, other in (sources or {}).items():
        if key == game.key:
            continue
        other_dates, other_results = other["date"].tolist(), other["result"].tolist()

        def build(dates, occ, other_dates=other_dates, other_results=other_results, key=key):
            extra, names = cross_game_features(dates, other_dates, other_results, game.min_val, game.max_val)
            return extra, [f"{key}:{n}" for n in names]

        builders.append(build)
        used.append(SOURCE_TITLES.get(key, key))
    builders.append(lambda dates, occ: calendar_features(dates, occ.shape[1]))
    used.append("lịch quay")
    return builders, used


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


def default_strategies(seed: int = 42, sources: Optional[Sources] = None) -> List[Tuple[str, str, StrategyFactory]]:
    """``(key, display name, factory)`` for every method compared on the dashboard.

    ``sources`` (other products' draws) feed the multi-source ML model; without them it only adds the
    calendar to its features.
    """

    def bounds(game: GameSpec) -> dict:
        return {"min_val": game.min_val, "max_val": game.max_val}

    def consensus(df: pd.DataFrame, g: GameSpec) -> ConsensusStrategy:
        b = bounds(g)
        return ConsensusStrategy(
            df,
            [
                ("hot", lambda d: HotNumbersStrategy(d, **b, lookback_days=365)),
                ("long_absence", lambda d: LongAbsenceStrategy(d, **b, top_n=15)),
                ("markov", lambda d: MarkovChainStrategy(d, **b, lookback_days=365)),
                ("pair", lambda d: PairFrequencyStrategy(d, **b, lookback_days=365)),
                ("positional", lambda d: PositionalStrategy(d, **b)),
                ("ml_logistic", lambda d: MLClassifierStrategy(d, **b, model_type="logistic", seed=seed)),
            ],
            **b,
        )

    def multi_source(df: pd.DataFrame, g: GameSpec) -> MLClassifierStrategy:
        builders, _ = multi_source_builders(g, sources)
        return MLClassifierStrategy(df, **bounds(g), model_type="gbm", seed=seed, extra_features=builders)

    multi_name = "ML đa nguồn (sản phẩm khác + lịch quay)" if sources else "ML đa nguồn (lịch quay)"
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
        ("ml_multi", multi_name, multi_source),
        ("consensus", "Đồng thuận nhiều phương pháp (ensemble)", consensus),
    ]


STRATEGY_INFO: Dict[str, Tuple[str, str]] = {
    "random": ("Không dùng dữ liệu", "Chọn ngẫu nhiên đều, làm mốc so sánh"),
    "hot": ("Lịch sử 365 ngày", "Ưu tiên số ra nhiều"),
    "cold": ("Lịch sử 365 ngày", "Ưu tiên số ra ít"),
    "long_absence": ("Toàn bộ lịch sử", "Ưu tiên số lâu chưa về"),
    "not_repeat": ("30 ngày gần nhất", "Tránh số vừa ra"),
    "pattern": ("Lịch sử 180 ngày", "Khoảng cách giữa các số và phân bố theo dải"),
    "exp_decay": ("Toàn bộ lịch sử, trọng số mũ", "Tần suất có trọng số giảm dần theo thời gian"),
    "pair": ("Lịch sử 365 ngày", "Ma trận cặp số đi cùng nhau"),
    "markov": ("Lịch sử 365 ngày", "Xác suất chuyển từ kỳ trước sang kỳ sau"),
    "positional": ("Toàn bộ lịch sử", "Phân bố riêng của từng vị trí đã sắp xếp"),
    "ml_logistic": ("6 đặc trưng tần suất/khoảng cách", "Logistic Regression, huấn luyện lại sau mỗi kỳ"),
    "ml_gbm": ("6 đặc trưng tần suất/khoảng cách", "Gradient Boosting, huấn luyện lại sau mỗi kỳ"),
    "ml_multi": (
        "Sản phẩm đang xét + sản phẩm khác + lịch quay",
        "Gradient Boosting đa nguồn, huấn luyện lại sau mỗi kỳ",
    ),
    "consensus": ("Kết hợp 6 phương pháp", "Bỏ phiếu: số được nhiều phương pháp chọn được ưu tiên"),
    "top5_roi": (
        "ROI tích lũy của các phương pháp khác đến kỳ trước",
        "Trước mỗi kỳ chọn 5 phương pháp có ROI cao nhất, lấy 2 vé của mỗi phương pháp",
    ),
}


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
    refit_every: int = 10,
    seed: int = 42,
    extra_models: Sequence[Tuple[str, str, list, List[str]]] = (),
) -> dict:
    """Walk-forward ROC-AUC / log-loss / calibration of per-number classifiers vs the constant baseline.

    ``extra_models`` are ``(name, model_type, feature_builders, source_names)`` tuples, e.g. the
    multi-source model that adds other products' draws and the calendar to the features.
    """
    from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score

    occ = occurrence_matrix(df["result"].tolist(), game.min_val, game.max_val)
    base_feats = build_features(occ, DEFAULT_WINDOWS)
    dates = list(df["date"])
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
    specs = [(m, m, [], []) for m in model_types] + list(extra_models)
    for name, model_type, builders, source_names in specs:
        started = time.time()
        feats, names = base_feats, feature_names(DEFAULT_WINDOWS)
        for builder in builders:
            extra, extra_names = builder(dates, occ)
            feats, names = np.concatenate([feats, extra], axis=-1), names + list(extra_names)
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
            importance = {n: float(c) for n, c in zip(names, final[-1].coef_[0])}
        elif hasattr(final, "feature_importances_"):
            importance = {n: float(v) for n, v in zip(names, final.feature_importances_)}
        models.append(
            {
                "model": name,
                "model_type": model_type,
                "sources": source_names,
                "n_features": len(names),
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
        logger.info(f"{game.key} ML {name}: auc={models[-1]['auc']:.4f} top_hits={top_hits:.3f}")
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


def encode_tickets(tickets: Sequence[Sequence[int]]) -> str:
    """Pack tickets as one string of zero-padded 2-digit numbers (``pick`` numbers per ticket)."""
    return "".join(f"{int(n):02d}" for ticket in tickets for n in sorted(ticket))


def decode_tickets(packed: str, pick: int) -> List[List[int]]:
    """Inverse of :func:`encode_tickets`."""
    numbers = [int(packed[i : i + 2]) for i in range(0, len(packed), 2)]
    return [numbers[i : i + pick] for i in range(0, len(numbers), pick)]


def next_seed(seed: int, index: int) -> int:
    """Seed used for strategy ``index``'s next-draw tickets (shared by the dashboard and the ledger)."""
    return seed * 1000 + 777 + index


TOP_ROI_KEY = "top5_roi"
TOP_ROI_N = 5
PICK_TOP_KEY = "picks_top20"
PICK_BEST_KEY = "picks_best10"
ML_PROBABILITY_KEYS = ("ml_logistic", "ml_gbm", "ml_multi")


def top_probability_tickets(
    probabilities: Sequence[float], game: GameSpec, n_tickets: int = 20, pool_size: int = 14
) -> List[dict]:
    """The ``n_tickets`` tickets with the highest joint model probability.

    Treats numbers as independent with the given per-number probabilities, so a ticket's score is the
    sum of its numbers' log-probabilities; candidates come from the ``pool_size`` most likely numbers.
    ``ratio`` is how much likelier the ticket is than a uniform ticket *according to the model*.
    """
    probs = np.clip(np.asarray(probabilities, dtype=float), 1e-9, None)
    base = game.pick / game.pool
    numbers = np.arange(game.min_val, game.max_val + 1)
    pool = list(np.argsort(-probs, kind="stable")[: max(pool_size, game.pick)])
    scored = []
    for combo in combinations(sorted(pool), game.pick):
        log_ratio = float(np.sum(np.log(probs[list(combo)] / base)))
        scored.append((log_ratio, [int(numbers[i]) for i in combo]))
    scored.sort(key=lambda item: (-item[0], item[1]))
    return [{"ticket": ticket, "ratio": math.exp(log_ratio)} for log_ratio, ticket in scored[:n_tickets]]


def predict_next_draw(
    df: pd.DataFrame,
    game: GameSpec,
    strategies: Sequence[Tuple[str, str, StrategyFactory]],
    n_tickets: int = 10,
    seed: int = 42,
    models: Optional[Dict[str, PredictModel]] = None,
    best_key: Optional[str] = None,
    n_top: int = 20,
    top_roi_keys: Optional[Sequence[str]] = None,
) -> dict:
    """Tickets every method predicts for the next draw, trained on all draws known so far.

    ML models are fitted on every stored draw, so calling this after each new result re-trains them.
    Pass already-built ``models`` (key -> strategy) to reuse their caches.

    Two extra rows feed the homepage and are recorded and validated like any method:

    * ``picks_top20`` – the ``n_top`` tickets with the highest joint probability under the average of
      the ML models' per-number probabilities;
    * ``picks_best10`` – the next-draw tickets of ``best_key``, the method with the most matches per
      ticket in the comparison (the "easiest to hit" so far).

    With ``top_roi_keys`` (the methods with the highest ROI so far) the adaptive ``top5_roi`` method
    is added too: 2 next-draw tickets from each of them.
    """
    last = df.iloc[-1]
    target = next_draw_date(list(df["date"]))
    models = dict(models or {})
    rows = []
    for index, (key, name, factory) in enumerate(strategies):
        try:
            model = models.get(key) or factory(df, game)
            models[key] = model
            model.reseed(next_seed(seed, index))
            tickets = [model.predict(target) for _ in range(n_tickets)]
        except Exception as exc:
            logger.warning(f"skip next-draw prediction for {key}: {exc}")
            continue
        rows.append({"key": key, "name": name, "tickets": tickets})

    by_key = {r["key"]: r for r in rows}
    chosen = [k for k in (top_roi_keys or []) if k in by_key][:TOP_ROI_N]
    if len(chosen) == TOP_ROI_N:
        rows.append(
            {
                "key": TOP_ROI_KEY,
                "name": f"Kết hợp {TOP_ROI_N} chiến lược ROI cao nhất (xếp lại sau mỗi kỳ)",
                "tickets": combine_top_tickets({k: by_key[k]["tickets"] for k in chosen}, chosen, n_tickets),
                "selected": chosen,
            }
        )

    picks: Dict[str, dict] = {}
    ml = [models[k] for k in ML_PROBABILITY_KEYS if k in models and hasattr(models[k], "number_probabilities")]
    if ml:
        probabilities = np.mean([m.number_probabilities(target) for m in ml], axis=0)
        top = top_probability_tickets(probabilities, game, n_top)
        name = f"{n_top} bộ xác suất cao nhất (trung bình {len(ml)} mô hình ML)"
        rows.append({"key": PICK_TOP_KEY, "name": name, "tickets": [t["ticket"] for t in top]})
        picks["top"] = {
            "key": PICK_TOP_KEY,
            "name": name,
            "models": [k for k in ML_PROBABILITY_KEYS if k in models],
            "ratios": [t["ratio"] for t in top],
            "number_probabilities": [float(x) for x in probabilities],
        }
    by_key = {r["key"]: r for r in rows}
    if best_key not in by_key:
        best_key = "consensus" if "consensus" in by_key else (rows[0]["key"] if rows else None)
    if best_key:
        best = by_key[best_key]
        name = f"{len(best['tickets'])} bộ dễ trúng nhất ({best['name']})"
        rows.append({"key": PICK_BEST_KEY, "name": name, "tickets": best["tickets"]})
        picks["best"] = {"key": PICK_BEST_KEY, "name": name, "method_key": best_key, "method_name": best["name"]}
    return {
        "product": game.key,
        "after_id": str(last["id"]),
        "after_date": str(last["date"]),
        "target_date": str(target),
        "n_tickets": n_tickets,
        "seed": seed,
        "strategies": rows,
        "picks": picks,
    }


def _score_tickets(game: GameSpec, tickets: Sequence[Sequence[int]], main: Sequence[int], bonus) -> List[tuple]:
    result = list(main) + ([int(bonus)] if bonus is not None and not pd.isna(bonus) else [])
    return [game.score(t, result) for t in tickets]


def top_roi_selection(
    profits: Dict[str, float], matches: Dict[str, float], order: Sequence[str], n: int = TOP_ROI_N
) -> List[str]:
    """The ``n`` strategies with the highest cumulative profit (= ROI, equal stakes); ties by matches, then order."""
    rank = {key: i for i, key in enumerate(order)}
    return sorted(order, key=lambda k: (-profits.get(k, 0.0), -matches.get(k, 0.0), rank[k]))[:n]


def combine_top_tickets(
    tickets_by_key: Dict[str, List[List[int]]], keys: Sequence[str], n_tickets: int
) -> List[List[int]]:
    """``n_tickets`` tickets taken round-robin from the selected strategies' own tickets (2 each for 5 x 10)."""
    per = math.ceil(n_tickets / max(len(keys), 1))
    combined = [list(t) for k in keys for t in tickets_by_key[k][:per]]
    return combined[:n_tickets]


def simulate_and_compare(
    df: pd.DataFrame,
    game: GameSpec,
    strategies: Sequence[Tuple[str, str, StrategyFactory]],
    start_date: date = date(2025, 1, 1),
    tickets_per_draw: int = 10,
    n_runs: int = 5,
    seed: int = 42,
    warmup_draws: int = 30,
) -> Tuple[dict, dict, dict]:
    """Play every method on every draw since ``start_date`` and compare them in one table.

    Each method buys ``tickets_per_draw`` tickets per draw, predicted walk-forward (only earlier draws;
    ML re-trained after every draw).  Random methods are replayed ``n_runs`` times with different seeds
    so the table reports averages and spreads rather than one lucky or unlucky run.

    The adaptive ``top5_roi`` method is built on top: before every draw it ranks the other methods by
    the profit (ROI) their tickets made on all earlier draws - including ``warmup_draws`` draws before
    ``start_date`` so it has a ranking from the first draw - and buys 2 tickets of each of the top 5.

    Returns ``(simulation, comparison, next_draw)``: run 0's tickets for the interactive simulator, the
    summary table, and the next-draw tickets (same as :func:`predict_next_draw`).
    """
    first = next((i for i, d in enumerate(df["date"]) if d >= start_date), len(df))
    warm = max(0, first - warmup_draws)
    span = df.iloc[warm:]
    dates = span["date"].tolist()
    mains = span["result"].tolist()
    bonuses = span["bonus"].tolist()
    offset = first - warm  # index of the first scored draw inside ``span``
    played = df.iloc[first:]
    n_draws = len(played)
    match_pmf = game.match_probabilities()
    expected_avg = game.expected_matches()
    per_ticket_var = sum((k - expected_avg) ** 2 * p for k, p in enumerate(match_pmf))
    tier_probs = game.tier_probabilities()

    # 1. walk-forward tickets of every method, every run, warm-up included
    names, models, timing = {}, {}, {}
    tickets: Dict[str, List[List[List[List[int]]]]] = {}
    for index, (key, name, factory) in enumerate(strategies):
        started = time.time()
        try:
            model = factory(df, game)
        except Exception as exc:
            logger.warning(f"skip comparison for {key}: {exc}")
            continue
        models[key], names[key] = model, name
        tickets[key] = []
        for run in range(n_runs):
            model.reseed(seed + index + 1000 * run)
            tickets[key].append([[model.predict(d) for _ in range(tickets_per_draw)] for d in dates])
        timing[key] = time.time() - started
    base_keys = list(tickets)

    # 2. score every ticket once: scores[key][run][draw] = list of (matches, tier)
    scores = {
        key: [
            [_score_tickets(game, t, m, b) for t, m, b in zip(runs_tickets, mains, bonuses)]
            for runs_tickets in tickets[key]
        ]
        for key in base_keys
    }

    # 3. adaptive top-5-by-ROI method, re-ranked before every draw
    selections: List[List[str]] = []
    if len(base_keys) >= TOP_ROI_N:
        tickets[TOP_ROI_KEY], scores[TOP_ROI_KEY] = [], []
        names[TOP_ROI_KEY] = f"Kết hợp {TOP_ROI_N} chiến lược ROI cao nhất (xếp lại sau mỗi kỳ)"
        for run in range(n_runs):
            profit = {k: 0.0 for k in base_keys}
            matched = {k: 0.0 for k in base_keys}
            run_tickets, run_scores = [], []
            for j in range(len(dates)):
                chosen = top_roi_selection(profit, matched, base_keys)
                if run == 0:
                    selections.append(chosen)
                combo = combine_top_tickets({k: tickets[k][run][j] for k in chosen}, chosen, tickets_per_draw)
                run_tickets.append(combo)
                run_scores.append(_score_tickets(game, combo, mains[j], bonuses[j]))
                for k in base_keys:
                    outcome = scores[k][run][j]
                    profit[k] += sum(t.value for _, _, t in outcome if t) - len(outcome) * game.ticket_price
                    matched[k] += sum(m for m, _, _ in outcome)
            tickets[TOP_ROI_KEY].append(run_tickets)
            scores[TOP_ROI_KEY].append(run_scores)
        timing[TOP_ROI_KEY] = 0.0

    # 4. statistics over the scored window only
    sim_rows, rows = [], []
    for key in list(tickets):
        runs, draw_matches = [], np.zeros(n_draws)
        for run in range(n_runs):
            tiers: Counter = Counter()
            gain = matches = winners = 0
            for i, outcome in enumerate(scores[key][run][offset:]):
                for m, _, tier in outcome:
                    matches += m
                    draw_matches[i] += m
                    if tier:
                        tiers[tier.key] += 1
                        gain += tier.value
                        winners += 1
            cost = n_draws * tickets_per_draw * game.ticket_price
            runs.append(
                {
                    "cost": cost,
                    "gain": gain,
                    "profit": gain - cost,
                    "roi": (gain - cost) / cost * 100 if cost else 0.0,
                    "avg_matches": matches / (n_draws * tickets_per_draw) if n_draws else 0.0,
                    "winners": winners,
                    "tiers": tiers,
                }
            )
        sim_rows.append(
            {"key": key, "name": names[key], "tickets": [encode_tickets(t) for t in tickets[key][0][offset:]]}
        )
        n_tickets = n_draws * tickets_per_draw * n_runs
        avg = float(np.mean([r["avg_matches"] for r in runs])) if runs else 0.0
        draw_means = draw_matches / (tickets_per_draw * n_runs)
        se_independent = math.sqrt(per_ticket_var / n_tickets) if n_tickets else 0.0
        se_cluster = float(np.std(draw_means, ddof=1) / math.sqrt(n_draws)) if n_draws > 1 else 0.0
        se = max(se_independent, se_cluster)
        z = (avg - expected_avg) / se if se else 0.0
        rois = [r["roi"] for r in runs]
        best_tier = next(
            (t.key for t in sorted(game.tiers, key=lambda t: -t.value) if any(r["tiers"].get(t.key) for r in runs)),
            None,
        )
        source, method = STRATEGY_INFO.get(key, ("", ""))
        rows.append(
            {
                "key": key,
                "name": names[key],
                "source": source,
                "method": method,
                "runs": n_runs,
                "tickets_per_run": n_draws * tickets_per_draw,
                "avg_matches": avg,
                "avg_matches_sd": float(np.std([r["avg_matches"] for r in runs], ddof=1)) if n_runs > 1 else 0.0,
                "z": z,
                "p_value": _normal_two_sided_p(z),
                "cost": runs[0]["cost"] if runs else 0,
                "mean_gain": float(np.mean([r["gain"] for r in runs])) if runs else 0.0,
                "mean_profit": float(np.mean([r["profit"] for r in runs])) if runs else 0.0,
                "mean_roi": float(np.mean(rois)) if rois else 0.0,
                "roi_sd": float(np.std(rois, ddof=1)) if n_runs > 1 else 0.0,
                "roi_min": float(min(rois)) if rois else 0.0,
                "roi_max": float(max(rois)) if rois else 0.0,
                "p_profit": sum(1 for r in runs if r["profit"] > 0) / n_runs if n_runs else 0.0,
                "mean_winners": float(np.mean([r["winners"] for r in runs])) if runs else 0.0,
                "mean_tiers": {t.key: float(np.mean([r["tiers"].get(t.key, 0) for r in runs])) for t in game.tiers},
                "best_tier": best_tier,
                "seconds": round(timing.get(key, 0.0), 2),
            }
        )
        logger.info(
            f"{game.key} compare {key}: avg={avg:.4f} z={z:+.2f} roi={rows[-1]['mean_roi']:.1f}% ({timing.get(key, 0):.1f}s)"
        )
    n = len(rows)
    for row in rows:
        row["p_adjusted"] = min(1.0, row["p_value"] * n)
    rows.sort(key=lambda r: (-r["avg_matches"], -r["mean_roi"]))
    for rank, row in enumerate(rows, start=1):
        row["rank"] = rank
    threshold = _bonferroni_z(n)
    best = rows[0] if rows else None
    roi_best = max(rows, key=lambda r: r["mean_roi"]) if rows else None
    base_rows = [r for r in rows if r["key"] in base_keys]
    top_roi_keys = [r["key"] for r in sorted(base_rows, key=lambda r: (-r["mean_profit"], -r["avg_matches"]))][
        :TOP_ROI_N
    ]
    picked = Counter(k for chosen in selections[offset:] for k in chosen)
    comparison = {
        "start_date": str(start_date),
        "end_date": str(played["date"].iloc[-1]) if n_draws else None,
        "warmup_draws": offset,
        "n_draws": n_draws,
        "tickets_per_draw": tickets_per_draw,
        "n_runs": n_runs,
        "expected_avg_matches": expected_avg,
        "expected_roi": (game.expected_value() - game.ticket_price) / game.ticket_price * 100,
        "expected_winners": n_draws * tickets_per_draw * sum(tier_probs.values()),
        "bonferroni_z": threshold,
        "best_key": best["key"] if best else None,
        "best_significant": bool(best and best["z"] >= threshold),
        "best_roi_key": roi_best["key"] if roi_best else None,
        "top_roi_keys": top_roi_keys,
        "top_roi_usage": [{"key": k, "name": names[k], "draws": c} for k, c in picked.most_common()],
        "top_roi_latest": selections[-1] if selections else [],
        "rows": rows,
    }
    simulation = {
        "start_date": str(start_date),
        "max_tickets": tickets_per_draw,
        "next_date": str(next_draw_date(list(df["date"]))),
        "draws": [
            {"id": r.id, "date": str(r.date), "main": list(r.result), "bonus": _int(r.bonus)}
            for r in played.itertuples(index=False)
        ],
        "expected_value": game.expected_value(),
        "strategies": sim_rows,
    }
    next_draw = predict_next_draw(
        df,
        game,
        strategies,
        tickets_per_draw,
        seed,
        models=models,
        best_key=comparison["best_key"],
        top_roi_keys=top_roi_keys,
    )
    by_key = {r["key"]: r for r in next_draw["strategies"]}
    for row in simulation["strategies"]:
        row["next"] = encode_tickets(by_key[row["key"]]["tickets"]) if row["key"] in by_key else ""
    return simulation, comparison, next_draw


def analyse_game(
    df: pd.DataFrame,
    game: GameSpec,
    ml_eval_draws: int = 300,
    seed: int = 42,
    strategies: Optional[Sequence[Tuple[str, str, StrategyFactory]]] = None,
    ml_models: Sequence[str] = ("logistic", "random_forest", "gbm"),
    simulation_start: date = date(2025, 1, 1),
    simulation_tickets: int = 10,
    n_runs: int = 5,
    sources: Optional[Sources] = None,
    ledger: Optional[List[dict]] = None,
    replay: Optional[dict] = None,
    replay_entries: Optional[List[dict]] = None,
) -> dict:
    """Full analysis block for one game."""
    random.seed(seed)
    np.random.seed(seed)
    strategies = list(strategies) if strategies is not None else default_strategies(seed, sources)
    simulation, comparison, next_draw = simulate_and_compare(
        df, game, strategies, simulation_start, simulation_tickets, n_runs, seed
    )
    scored = score_ledger(ledger or [], df, game)
    builders, source_names = multi_source_builders(game, sources)
    multi_model = [("gbm_multi", "gbm", builders, source_names)] if ml_models else []
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
                "matches": t.matches,
                "needs_bonus": t.needs_bonus,
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
        "ml": ml_predictability(df, game, ml_models, ml_eval_draws, seed=seed, extra_models=multi_model),
        "comparison": comparison,
        "next_draw": next_draw,
        "simulation": simulation,
        "ledger": scored,
        "picks": {
            **homepage_picks(next_draw, comparison, ledger, scored),
            "replay": replay_picks_summary(replay),
            "history": picks_history(df, game, ledger, replay_entries, (replay or {}).get("validate_from")),
        },
        "replay": replay,
    }


def homepage_picks(next_draw: dict, comparison: dict, ledger: Optional[List[dict]], scored: dict) -> dict:
    """The homepage's 20 most-probable and 10 easiest-to-hit tickets, plus the last validation.

    When the ledger already holds the prediction made after the latest draw, its tickets are shown, so
    the homepage always displays exactly what was recorded and will be validated.
    """
    recorded = next((e for e in (ledger or []) if e["after_id"] == next_draw["after_id"]), None)
    source = recorded or next_draw
    rows = {r["key"]: r for r in source["strategies"]}
    meta = {**next_draw.get("picks", {})}
    for role, value in (recorded or {}).get("picks", {}).items():
        meta[role] = {**meta.get(role, {}), **value}
    top_meta, best_meta = meta.get("top", {}), meta.get("best", {})
    top = rows.get(PICK_TOP_KEY, {"tickets": []})
    computed_top = next((r for r in next_draw["strategies"] if r["key"] == PICK_TOP_KEY), {"tickets": []})
    ratios = top_meta.get("ratios") if computed_top["tickets"] == top["tickets"] else None
    method = next((r for r in comparison["rows"] if r["key"] == best_meta.get("method_key")), None)
    last = scored["scored"][-1] if scored.get("scored") else None
    validation = None
    if last:
        validation = {
            "draw_id": last["draw_id"],
            "draw_date": last["draw_date"],
            "main": last["main"],
            "bonus": last["bonus"],
            "picks": [s for s in last["strategies"] if s["key"] in (PICK_TOP_KEY, PICK_BEST_KEY)],
            "best_method": max(last["strategies"], key=lambda s: (s["best"], s["winners"]), default=None),
        }
    return {
        "after_id": source["after_id"],
        "after_date": source["after_date"],
        "target_date": source["target_date"],
        "recorded": recorded is not None,
        "recorded_at": recorded["generated_at"] if recorded else None,
        "top": {
            "name": top_meta.get("name", ""),
            "models": top_meta.get("models", []),
            "tickets": top["tickets"],
            "ratios": ratios,
        },
        "best": {
            "name": best_meta.get("name", ""),
            "method_key": best_meta.get("method_key"),
            "method_name": best_meta.get("method_name"),
            "tickets": rows.get(PICK_BEST_KEY, {"tickets": []})["tickets"],
            "avg_matches": method["avg_matches"] if method else None,
            "z": method["z"] if method else None,
            "mean_roi": method["mean_roi"] if method else None,
        },
        "validation": validation,
        "summary": [a for a in scored.get("summary", []) if a["key"] in (PICK_TOP_KEY, PICK_BEST_KEY)],
        "window_start": comparison.get("start_date"),
        "window_end": comparison.get("end_date"),
    }


def picks_history(
    df: pd.DataFrame,
    game: GameSpec,
    ledger: Optional[List[dict]],
    replay_entries: Optional[List[dict]],
    since: Optional[str] = None,
) -> dict:
    """Draw-by-draw tickets of the homepage picks (20 most probable, 10 easiest, top-5 ROI) with results.

    Draws predicted live (recorded in the ledger before the draw) come from the ledger; the other draws
    since ``since`` come from the leak-free replay.  Tickets are packed; the browser scores them.
    """
    keys = (PICK_TOP_KEY, PICK_BEST_KEY, TOP_ROI_KEY)
    draws = {str(r.id): r for r in df.itertuples(index=False)}
    history: Dict[str, dict] = {}
    for entry in replay_entries or []:
        if since and entry["draw_date"] < since:
            continue
        rows = [r for r in entry["rows"] if r["key"] in keys]
        history[entry["draw_id"]] = {
            "draw_id": entry["draw_id"],
            "date": entry["draw_date"],
            "main": entry["main"],
            "bonus": entry["bonus"],
            "source": "replay",
            "trained_until_id": entry["trained_until_id"],
            "names": {r["key"]: r["name"] for r in rows},
            "tickets": {r["key"]: encode_tickets(r["tickets"]) for r in rows},
        }
    for entry in ledger or []:
        draw_id = next_draw_id(entry["after_id"])
        draw = draws.get(draw_id)
        if draw is None:
            continue
        rows = [r for r in entry["strategies"] if r["key"] in keys]
        history[draw_id] = {
            "draw_id": draw_id,
            "date": str(draw.date),
            "main": list(draw.result),
            "bonus": _int(draw.bonus),
            "source": "live",
            "trained_until_id": entry["after_id"],
            "recorded_at": entry["generated_at"],
            "names": {r["key"]: r["name"] for r in rows},
            "tickets": {r["key"]: encode_tickets(r["tickets"]) for r in rows},
        }
    return {
        "since": since,
        "ticket_price": game.ticket_price,
        "tiers": [
            {"key": t.key, "label": t.label, "matches": t.matches, "needs_bonus": t.needs_bonus, "value": t.value}
            for t in game.tiers
        ],
        "draws": [history[k] for k in sorted(history, key=int)],
    }


def replay_picks_summary(replay: Optional[dict]) -> Optional[dict]:
    """Homepage view of the replay: totals of the 20 + 10 picks and top5_roi over the replayed draws."""
    if not replay:
        return None
    keys = (PICK_TOP_KEY, PICK_BEST_KEY, TOP_ROI_KEY)
    return {
        "validate_from": replay["validate_from"],
        "validate_to": replay["validate_to"],
        "n_draws": replay["n_draws"],
        "expected_avg_matches": replay["expected_avg_matches"],
        "rows": [
            {
                k: r[k]
                for k in (
                    "key",
                    "name",
                    "draws",
                    "tickets",
                    "avg_matches",
                    "z",
                    "winners",
                    "tiers",
                    "cost",
                    "gain",
                    "roi",
                    "best_match",
                )
            }
            for r in replay["rows"]
            if r["key"] in keys
        ],
    }


def _int(value) -> Optional[int]:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    return int(value)


def build_analysis(games: Sequence[str] = ("power_655", "power_645"), **kwargs) -> dict:
    """Analysis for every requested game, ready to dump as JSON for the dashboard."""
    from machine_learning.ledger import load_ledger

    products = {}
    sources = load_sources()
    for key in games:
        game = get_game(key)
        logger.info(f"analysing {game.title}...")
        products[key] = analyse_game(
            load_draws(game),
            game,
            sources=sources,
            ledger=load_ledger(key),
            replay=load_replay_summary(key),
            replay_entries=load_replay_entries(key),
            **kwargs,
        )
    return {
        "generated_at": pd.Timestamp.now(tz="Asia/Ho_Chi_Minh").isoformat(timespec="seconds"),
        "generated_date": str(date.today()),
        "products": products,
    }
