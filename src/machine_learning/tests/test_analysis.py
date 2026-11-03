"""
Tests for game rules / prize scoring, causal ML features, the ML classifier strategy and the
analysis payload rendered for the docs/analysis dashboard.
"""

import json
import math
import random
from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from machine_learning.analysis import (
    analyse_game,
    decode_tickets,
    encode_tickets,
    hypergeom_pmf,
    play_simulation,
    prepare_draws,
    sum_distribution,
)
from machine_learning.features import build_features, feature_names, occurrence_matrix
from machine_learning.games import MEGA_645, POWER_655
from machine_learning.render_analysis import write_analysis
from machine_learning.strategies import MLClassifierStrategy, PositionalStrategy, RandomModel


def _raw_draws(n: int = 80, pool: int = 55, bonus: bool = True, seed: int = 7) -> pd.DataFrame:
    """Synthetic raw draws in the stored format (main numbers sorted, bonus last for 6/55)."""
    rng = random.Random(seed)
    rows = []
    for i in range(n):
        balls = rng.sample(range(1, pool + 1), 7 if bonus else 6)
        result = sorted(balls[:6]) + ([balls[6]] if bonus else [])
        rows.append({"date": str(date(2024, 1, 1) + timedelta(days=2 * i)), "id": f"{i + 1:05d}", "result": result})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Game rules
# ---------------------------------------------------------------------------


def test_bonus_number_is_not_a_regular_match():
    result = [1, 2, 3, 4, 5, 6, 7]  # 7 is the bonus
    matches, bonus_hit, tier = POWER_655.score([1, 2, 3, 4, 5, 7], result)
    assert matches == 5 and bonus_hit
    assert tier.key == "jackpot2"
    matches, bonus_hit, tier = POWER_655.score([1, 2, 3, 4, 5, 9], result)
    assert matches == 5 and not bonus_hit
    assert tier.key == "first" and tier.value == 40_000_000
    matches, _, tier = POWER_655.score([1, 2, 3, 40, 41, 7], result)
    assert matches == 3 and tier.key == "third"
    assert POWER_655.prize([10, 11, 12, 13, 14, 7], result) == 0
    print("bonus number only decides Jackpot 2")


def test_match_and_tier_probabilities_are_exact():
    for game in (POWER_655, MEGA_645):
        assert math.isclose(sum(game.match_probabilities()), 1.0)
        assert math.isclose(sum(k * p for k, p in enumerate(game.match_probabilities())), game.expected_matches())
    probs = POWER_655.tier_probabilities()
    assert math.isclose(1 / probs["jackpot1"], math.comb(55, 6))
    p5 = POWER_655.match_probabilities()[5]
    assert math.isclose(probs["jackpot2"] + probs["first"], p5)
    assert POWER_655.expected_value() < POWER_655.ticket_price
    assert MEGA_645.expected_value() < MEGA_645.ticket_price
    print("tier probabilities match combinatorics and the expected value is below the ticket price")


def test_sum_distribution_is_a_distribution_with_the_right_mean():
    dist = sum_distribution(MEGA_645)
    assert math.isclose(sum(dist.values()), 1.0)
    mean = sum(s * p for s, p in dist.items())
    assert math.isclose(mean, 6 * (1 + 45) / 2)
    assert math.isclose(sum(hypergeom_pmf(55, 28, 6)), 1.0)
    print("exact sum distribution verified")


# ---------------------------------------------------------------------------
# PredictModel scoring
# ---------------------------------------------------------------------------


def test_predict_model_strips_bonus_and_scores_with_tiers():
    raw = _raw_draws(30)
    raw["date"] = pd.to_datetime(raw["date"]).dt.date
    model = RandomModel(raw, time_predict=2)
    assert all(len(r) == 6 for r in model.df["result"])
    assert "bonus" in model.df.columns
    model.backtest()
    model.evaluate()
    evaluated = model.df_backtest_evaluate
    assert evaluated["correct_num"].max() <= 6
    cost, gain, profit = model.revenue()
    assert cost == len(raw) * 2 * POWER_655.ticket_price
    assert gain == evaluated["prize"].sum()
    assert profit == gain - cost
    print("PredictModel scores the 6 main numbers and uses the bonus only for Jackpot 2")


def test_bonus_is_split_from_numpy_results():
    """polars -> pandas turns list columns into numpy arrays; the bonus must still be split off."""
    raw = _raw_draws(10)
    raw["result"] = [np.array(r) for r in raw["result"]]
    model = RandomModel(raw)
    assert all(len(r) == 6 for r in model.df["result"])
    assert model.df["bonus"].notna().all()
    scored = model.score_ticket([1, 2, 3, 4, 5, 6], np.array([1, 2, 3, 4, 5, 9, 6]))
    assert scored["correct_num"] == 5 and scored["bonus_hit"] and scored["prize"] == 3_000_000_000
    print("numpy results are split into main numbers and bonus")


# ---------------------------------------------------------------------------
# Features & ML strategy
# ---------------------------------------------------------------------------


def test_features_are_causal():
    raw = prepare_draws(_raw_draws(60), POWER_655)
    occ = occurrence_matrix(raw["result"].tolist(), 1, 55)
    feats = build_features(occ)
    assert feats.shape == (61, 55, len(feature_names()))
    changed = occ.copy()
    changed[40] = 1 - changed[40]
    feats_changed = build_features(changed)
    np.testing.assert_array_equal(feats[:41], feats_changed[:41])
    assert not np.array_equal(feats[41:], feats_changed[41:])
    print("row t only depends on draws before t")


@pytest.mark.parametrize("model_type", ["logistic", "random_forest", "gbm"])
def test_ml_classifier_predicts_valid_tickets(model_type):
    raw = prepare_draws(_raw_draws(70), POWER_655)
    model = MLClassifierStrategy(raw, model_type=model_type, refit_every=20, min_train_draws=20, seed=3)
    probs = model.number_probabilities(None)
    assert probs.shape == (55,)
    assert np.all((probs >= 0) & (probs <= 1))
    ticket = model.predict(raw["date"].iloc[-1] + timedelta(days=2))
    assert len(set(ticket)) == 6 and ticket == sorted(ticket) and all(1 <= n <= 55 for n in ticket)
    top = MLClassifierStrategy(raw, model_type=model_type, selection="top", refit_every=20, min_train_draws=20)
    assert top.predict(None) == top.predict(None)
    print(f"{model_type} classifier yields valid tickets")


def test_ml_classifier_falls_back_to_uniform_without_history():
    raw = prepare_draws(_raw_draws(10), POWER_655)
    model = MLClassifierStrategy(raw, min_train_draws=50)
    np.testing.assert_allclose(model.number_probabilities(None), 6 / 55)
    print("uniform fallback when history is too short")


def test_positional_strategy_respects_order_and_range():
    raw = prepare_draws(_raw_draws(40, pool=45, bonus=False), MEGA_645)
    model = PositionalStrategy(raw, min_val=1, max_val=45)
    for _ in range(20):
        ticket = model.predict(raw["date"].iloc[-1] + timedelta(days=1))
        assert ticket == sorted(set(ticket)) and len(ticket) == 6 and 1 <= ticket[0] and ticket[-1] <= 45
    print("positional tickets are strictly increasing and in range")


# ---------------------------------------------------------------------------
# Analysis payload
# ---------------------------------------------------------------------------


def test_analyse_game_payload(tmp_path):
    df = prepare_draws(_raw_draws(120), POWER_655)
    strategies = [
        ("random", "Random", lambda d, g: RandomModel(d, min_val=g.min_val, max_val=g.max_val)),
        (
            "ml_logistic",
            "ML",
            lambda d, g: MLClassifierStrategy(d, refit_every=20, min_train_draws=30, seed=1),
        ),
    ]
    payload = analyse_game(
        df,
        POWER_655,
        backtest_window=20,
        tickets_per_draw=3,
        ml_eval_draws=40,
        strategies=strategies,
        ml_models=("logistic",),
    )
    assert payload["n_draws"] == 120
    assert len(payload["frequency"]["counts"]) == 55
    assert sum(payload["frequency"]["counts"]) == 120 * 6
    assert payload["frequency"]["uniformity"]["dof"] == 54
    assert math.isclose(sum(payload["shape"]["odd"]["expected"]), 120)
    bt = payload["backtest"]
    assert [s["key"] for s in bt["strategies"]] == ["random", "ml_logistic"]
    assert all(s["tickets"] == 60 for s in bt["strategies"])
    assert all(sum(s["match_dist"]) == 60 for s in bt["strategies"])
    assert 0 <= payload["ml"]["models"][0]["auc"] <= 1
    assert len(payload["ml"]["models"][0]["next_draw_probs"]) == 55
    assert len(payload["suggestions"]) == 2
    assert payload["latest"]["bonus"] is not None
    assert payload["tiers"][1]["needs_bonus"] is True and payload["tiers"][1]["matches"] == 5
    assert payload["simulation"]["start_date"] == "2026-01-01"

    write_analysis({"generated_at": "now", "products": {"power_655": payload}}, tmp_path)
    data = json.loads((tmp_path / "analysis.json").read_text(encoding="utf-8"))
    assert data["products"]["power_655"]["title"] == "Power 6/55"
    assert (tmp_path / "analysis-data.js").read_text(encoding="utf-8").startswith("window.VIETLOTT_ANALYSIS = ")
    print("analysis payload is complete and serialisable")


def test_ticket_encoding_roundtrip():
    tickets = [[1, 9, 22, 33, 41, 55], [3, 4, 5, 6, 7, 8]]
    packed = encode_tickets(tickets)
    assert packed == "010922334155" + "030405060708"
    assert decode_tickets(packed, 6) == tickets
    print("tickets pack into 2-digit strings and back")


def test_play_simulation_is_walk_forward_and_deterministic():
    df = prepare_draws(_raw_draws(90), POWER_655)
    start = df["date"].iloc[60]
    strategies = [("random", "Random", lambda d, g: RandomModel(d, min_val=g.min_val, max_val=g.max_val))]
    sim = play_simulation(df, POWER_655, strategies, start_date=start, max_tickets=4, seed=5)
    assert sim["start_date"] == str(start)
    assert len(sim["draws"]) == 30
    assert sim["draws"][0]["date"] == str(start)
    assert all(d["bonus"] is not None for d in sim["draws"])
    row = sim["strategies"][0]
    assert len(row["tickets"]) == 30
    for packed in row["tickets"] + [row["next"]]:
        tickets = decode_tickets(packed, 6)
        assert len(tickets) == 4
        assert all(len(set(t)) == 6 and all(1 <= n <= 55 for n in t) for t in tickets)
    again = play_simulation(df, POWER_655, strategies, start_date=start, max_tickets=4, seed=5)
    assert again == sim
    print("simulation covers every draw since the start date and is reproducible")
