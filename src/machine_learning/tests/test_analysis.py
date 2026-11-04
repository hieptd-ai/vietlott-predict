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
    default_strategies,
    encode_tickets,
    hypergeom_pmf,
    multi_source_builders,
    predict_next_draw,
    prepare_draws,
    simulate_and_compare,
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
        ml_eval_draws=40,
        strategies=strategies,
        ml_models=("logistic",),
        simulation_start=df["date"].iloc[100],
        simulation_tickets=3,
        n_runs=2,
    )
    assert payload["n_draws"] == 120
    assert len(payload["frequency"]["counts"]) == 55
    assert sum(payload["frequency"]["counts"]) == 120 * 6
    assert payload["frequency"]["uniformity"]["dof"] == 54
    assert math.isclose(sum(payload["shape"]["odd"]["expected"]), 120)
    comparison = payload["comparison"]
    assert sorted(r["key"] for r in comparison["rows"]) == ["ml_logistic", "random"]
    assert all(r["tickets_per_run"] == 20 * 3 and r["runs"] == 2 for r in comparison["rows"])
    assert [r["rank"] for r in comparison["rows"]] == [1, 2]
    assert comparison["best_key"] == comparison["rows"][0]["key"]
    models = {m["model"]: m for m in payload["ml"]["models"]}
    assert set(models) == {"logistic", "gbm_multi"}
    assert models["gbm_multi"]["n_features"] == 6 + 3  # base features + calendar (no other sources)
    assert 0 <= models["logistic"]["auc"] <= 1
    assert len(models["logistic"]["next_draw_probs"]) == 55
    keys = [r["key"] for r in payload["next_draw"]["strategies"]]
    assert keys == ["random", "ml_logistic", "picks_top20", "picks_best10"]
    picks = payload["picks"]
    assert len(picks["top"]["tickets"]) == 20 and len(picks["top"]["ratios"]) == 20
    assert picks["top"]["ratios"] == sorted(picks["top"]["ratios"], reverse=True)
    assert picks["best"]["method_key"] == payload["comparison"]["best_key"] and len(picks["best"]["tickets"]) == 3
    assert picks["recorded"] is False and picks["validation"] is None
    assert payload["ledger"]["n_recorded"] == 0
    assert payload["latest"]["bonus"] is not None
    assert payload["tiers"][1]["needs_bonus"] is True and payload["tiers"][1]["matches"] == 5
    assert payload["simulation"]["start_date"] == str(df["date"].iloc[100])

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


def _random_strategy():
    return [("random", "Random", lambda d, g: RandomModel(d, min_val=g.min_val, max_val=g.max_val))]


def test_simulation_and_comparison_are_walk_forward_and_reproducible():
    df = prepare_draws(_raw_draws(90), POWER_655)
    start = df["date"].iloc[60]
    sim, comparison, next_draw = simulate_and_compare(df, POWER_655, _random_strategy(), start, 4, n_runs=3, seed=5)
    assert sim["start_date"] == str(start)
    assert len(sim["draws"]) == 30 and sim["draws"][0]["date"] == str(start)
    row = sim["strategies"][0]
    assert len(row["tickets"]) == 30
    for packed in row["tickets"] + [row["next"]]:
        tickets = decode_tickets(packed, 6)
        assert len(tickets) == 4
        assert all(len(set(t)) == 6 and all(1 <= n <= 55 for n in t) for t in tickets)
    table = comparison["rows"][0]
    assert table["runs"] == 3 and table["tickets_per_run"] == 120
    assert table["cost"] == 120 * 10_000
    assert table["roi_min"] <= table["mean_roi"] <= table["roi_max"]
    assert 0 <= table["p_profit"] <= 1 and table["p_adjusted"] >= table["p_value"]
    assert comparison["n_draws"] == 30 and comparison["tickets_per_draw"] == 4
    assert decode_tickets(row["next"], 6) == next_draw["strategies"][0]["tickets"]
    again = simulate_and_compare(df, POWER_655, _random_strategy(), start, 4, n_runs=3, seed=5)
    assert again[0] == sim and again[1]["rows"][0]["avg_matches"] == table["avg_matches"]
    print("comparison replays every draw since the start date reproducibly")


def test_predict_next_draw_matches_simulation_next_tickets():
    df = prepare_draws(_raw_draws(90), POWER_655)
    sim, _, _ = simulate_and_compare(df, POWER_655, _random_strategy(), df["date"].iloc[80], 5, n_runs=1, seed=9)
    standalone = predict_next_draw(df, POWER_655, _random_strategy(), 5, seed=9)
    assert decode_tickets(sim["strategies"][0]["next"], 6) == standalone["strategies"][0]["tickets"]
    assert standalone["after_id"] == df["id"].iloc[-1]
    print("ledger predictions equal the dashboard's next-draw tickets")


def test_cross_game_features_only_use_earlier_draws():
    from machine_learning.features import cross_game_features

    dates = [date(2026, 1, d) for d in (2, 4, 6)]
    other_dates = [date(2026, 1, d) for d in (1, 3, 5, 7)]
    other_results = [[1, 2, 3, 4, 5, 6], [1, 7, 8, 9, 10, 11], [12, 13, 14, 15, 16, 17], [1, 2, 3, 4, 5, 6]]
    feats, names = cross_game_features(dates, other_dates, other_results, 1, 55, windows=(2,))
    assert feats.shape == (4, 55, 2) and names == ["other_freq_last_2", "other_in_last_draw"]
    assert feats[0, 0, 0] == 1.0 and feats[0, 6, 0] == 0.0  # only the 01-01 draw precedes 01-02
    assert feats[1, 0, 0] == 1.0 and feats[1, 6, 0] == 0.5  # 01-01 and 01-03 precede 01-04
    assert feats[2, 0, 1] == 0.0 and feats[2, 11, 1] == 1.0  # latest earlier draw is 01-05
    print("cross-game features never look at same-day or later draws")


def test_multi_source_ml_and_consensus_strategies():
    df = prepare_draws(_raw_draws(90), POWER_655)
    other = prepare_draws(_raw_draws(90, pool=45, bonus=False, seed=3), MEGA_645)[["date", "result"]]
    builders, used = multi_source_builders(POWER_655, {"power_645": other})
    assert used == ["6/45", "lịch quay"]
    strategies = {k: f for k, _, f in default_strategies(seed=1, sources={"power_645": other})}
    multi = strategies["ml_multi"](df, POWER_655)
    assert multi.feature_names[-3:] == ["weekday", "month", "number_position"]
    assert len(multi.feature_names) == 6 + 3 + 3
    consensus = strategies["consensus"](df, POWER_655)
    for model in (multi, consensus):
        model.reseed(4)
        first = model.predict(df["date"].iloc[-1])
        model.reseed(4)
        assert model.predict(df["date"].iloc[-1]) == first
        assert len(set(first)) == 6 and all(1 <= n <= 55 for n in first)
    assert sum(consensus.votes(df["date"].iloc[-1]).values()) == 6 * 10 * len(consensus.bases)
    print("multi-source ML and the consensus ensemble give valid, reproducible tickets")


def test_ledger_records_once_and_scores_after_the_draw(tmp_path):
    from machine_learning.ledger import append_prediction, load_ledger, score_ledger

    df = prepare_draws(_raw_draws(40), POWER_655)
    known = df.iloc[:-1]
    prediction = predict_next_draw(known, POWER_655, _random_strategy(), 3, seed=2)
    assert append_prediction(prediction, "2026-11-03T00:00:00+07:00", tmp_path)
    assert not append_prediction(prediction, "later", tmp_path)
    entries = load_ledger("power_655", tmp_path)
    assert len(entries) == 1 and entries[0]["after_id"] == known["id"].iloc[-1]
    pending = score_ledger(entries, known, POWER_655)
    assert pending["n_scored"] == 0 and len(pending["pending"]) == 1
    scored = score_ledger(entries, df, POWER_655)
    assert scored["n_scored"] == 1 and scored["scored"][0]["draw_id"] == df["id"].iloc[-1]
    summary = scored["summary"][0]
    assert summary["draws"] == 1 and summary["tickets"] == 3 and summary["cost"] == 30_000
    print("ledger entries are append-only and scored once their draw is known")


def test_top_probability_tickets_rank_by_joint_model_probability():
    from machine_learning.analysis import top_probability_tickets

    probs = np.full(45, 6 / 45)
    probs[[0, 1, 2, 3, 4, 5, 6]] = [0.2, 0.19, 0.18, 0.17, 0.16, 0.15, 0.14]
    top = top_probability_tickets(probs, MEGA_645, n_tickets=5, pool_size=10)
    assert top[0]["ticket"] == [1, 2, 3, 4, 5, 6]
    assert top[1]["ticket"] == [1, 2, 3, 4, 5, 7]
    assert all(a["ratio"] >= b["ratio"] for a, b in zip(top, top[1:]))
    assert len({tuple(t["ticket"]) for t in top}) == 5
    print("top tickets follow the model's joint probability")


def test_ledger_keeps_picks_and_homepage_shows_recorded_tickets(tmp_path):
    from machine_learning.analysis import homepage_picks
    from machine_learning.ledger import append_prediction, load_ledger, score_ledger

    df = prepare_draws(_raw_draws(90), POWER_655)
    strategies = _random_strategy() + [
        ("ml_logistic", "ML", lambda d, g: MLClassifierStrategy(d, refit_every=20, min_train_draws=30, seed=1))
    ]
    known = df.iloc[:-1]
    prediction = predict_next_draw(known, POWER_655, strategies, 4, seed=3, best_key="random", n_top=20)
    assert append_prediction(prediction, "2026-11-03T11:00:00+07:00", tmp_path)
    entry = load_ledger("power_655", tmp_path)[0]
    assert entry["picks"]["best"]["method_key"] == "random" and "number_probabilities" not in entry["picks"]["top"]
    comparison = {"rows": [{"key": "random", "avg_matches": 0.7, "z": 1.0, "mean_roi": -90.0}]}

    pending = homepage_picks(prediction, comparison, [entry], score_ledger([entry], known, POWER_655))
    assert pending["recorded"] and pending["recorded_at"] == "2026-11-03T11:00:00+07:00"
    assert pending["best"]["tickets"] == next(r for r in prediction["strategies"] if r["key"] == "random")["tickets"]
    assert len(pending["top"]["tickets"]) == 20 and pending["validation"] is None

    nxt = predict_next_draw(df, POWER_655, strategies, 4, seed=3, best_key="random")
    validated = homepage_picks(nxt, comparison, [entry], score_ledger([entry], df, POWER_655))
    assert validated["validation"]["draw_id"] == df["id"].iloc[-1]
    assert {p["key"] for p in validated["validation"]["picks"]} == {"picks_top20", "picks_best10"}
    assert {a["key"] for a in validated["summary"]} == {"picks_top20", "picks_best10"}
    print("homepage shows the recorded picks and validates them after the draw")


def test_validation_markdown_lists_picks_first():
    from machine_learning.predict_next import validation_markdown

    scored = {
        "n_recorded": 1,
        "scored": [
            {
                "draw_id": "01419",
                "draw_date": "2026-11-03",
                "main": [1, 2, 3, 4, 5, 6],
                "bonus": 7,
                "strategies": [
                    {"key": "random", "name": "Random", "best": 3, "winners": 1, "gain": 50000},
                    {"key": "picks_top20", "name": "Top 20", "best": 2, "winners": 0, "gain": 0},
                ],
            }
        ],
    }
    text = validation_markdown("Power 6/55", scored)
    assert "kỳ #01419" in text and text.index("Top 20") < text.index("Random")
    assert "Chưa có" in validation_markdown("Mega", {"n_recorded": 0, "scored": []})
    print("validation report is readable")


def _random_variants(n: int):
    """``n`` independent random strategies (distinct seeds via the strategy index)."""
    return [
        (f"rand{i}", f"Random {i}", lambda d, g: RandomModel(d, min_val=g.min_val, max_val=g.max_val)) for i in range(n)
    ]


def test_top_roi_selection_and_ticket_combination():
    from machine_learning.analysis import combine_top_tickets, top_roi_selection

    order = ["a", "b", "c", "d", "e", "f"]
    profits = {"a": -10, "b": 5, "c": 5, "d": 0, "e": -3, "f": 7}
    matches = {"b": 1, "c": 9}
    assert top_roi_selection(profits, matches, order) == ["f", "c", "b", "d", "e"]
    assert top_roi_selection({}, {}, order) == ["a", "b", "c", "d", "e"]
    tickets = {k: [[i, i + 1, i + 2, i + 3, i + 4, i + 5] for i in range(1, 11)] for k in order}
    combined = combine_top_tickets(tickets, ["f", "c", "b", "d", "e"], 10)
    assert len(combined) == 10 and combined[0] == tickets["f"][0] and combined[1] == tickets["f"][1]
    assert combined[2] == tickets["c"][0]
    print("top-5 ROI ranking and 2-tickets-each combination behave as specified")


def test_top5_roi_strategy_is_walk_forward():
    df = prepare_draws(_raw_draws(70), POWER_655)
    start = df["date"].iloc[40]
    strategies = _random_variants(6)
    sim, comparison, next_draw = simulate_and_compare(
        df, POWER_655, strategies, start, 10, n_runs=2, seed=3, warmup_draws=10
    )
    assert comparison["warmup_draws"] == 10 and comparison["n_draws"] == 30
    rows = {r["key"]: r for r in comparison["rows"]}
    assert "top5_roi" in rows and rows["top5_roi"]["tickets_per_run"] == 300
    assert len(comparison["top_roi_keys"]) == 5 and len(comparison["top_roi_latest"]) == 5
    assert sum(u["draws"] for u in comparison["top_roi_usage"]) == 30 * 5
    by_key = {r["key"]: r for r in sim["strategies"]}
    for j in range(30):
        base_tickets = {tuple(t) for k in by_key if k != "top5_roi" for t in decode_tickets(by_key[k]["tickets"][j], 6)}
        assert all(tuple(t) in base_tickets for t in decode_tickets(by_key["top5_roi"]["tickets"][j], 6))
    # changing the last result must not change any top5_roi ticket (rankings only use earlier draws)
    altered = df.copy()
    altered.at[altered.index[-1], "result"] = [1, 2, 3, 4, 5, 6]
    sim2, _, _ = simulate_and_compare(altered, POWER_655, strategies, start, 10, n_runs=2, seed=3, warmup_draws=10)
    assert {r["key"]: r["tickets"] for r in sim2["strategies"]}["top5_roi"] == by_key["top5_roi"]["tickets"]
    top_row = next(r for r in next_draw["strategies"] if r["key"] == "top5_roi")
    assert top_row["selected"] == comparison["top_roi_keys"] and len(top_row["tickets"]) == 10
    assert decode_tickets(by_key["top5_roi"]["next"], 6) == top_row["tickets"]
    print("top-5 ROI method only uses earlier draws and combines the chosen methods' tickets")


def test_truncated_history_gives_the_same_ml_probabilities_as_walk_forward():
    """No look-ahead: a model built only on draws before t predicts draw t exactly like the walk-forward model."""
    df = prepare_draws(_raw_draws(90), POWER_655)
    for model_type in ("logistic", "gbm"):
        full = MLClassifierStrategy(df, model_type=model_type, min_train_draws=30, seed=5)
        for t in (60, 75, 89):
            target = df["date"].iloc[t]
            truncated = MLClassifierStrategy(df.iloc[:t], model_type=model_type, min_train_draws=30, seed=5)
            np.testing.assert_allclose(
                full.number_probabilities(target), truncated.number_probabilities(None), rtol=1e-9
            )
    print("walk-forward ML predictions equal models trained only on earlier draws")


def test_replay_trains_only_on_earlier_draws_and_validates_each_draw():
    from machine_learning.replay import replay_game, summarise

    df = prepare_draws(_raw_draws(75), POWER_655)
    other = prepare_draws(_raw_draws(75, pool=45, bonus=False, seed=8), MEGA_645)[["date", "result"]]
    start = df["date"].iloc[60]
    entries = replay_game(df, POWER_655, {"power_645": other}, start, n_tickets=4, seed=1)
    assert len(entries) == 15
    for entry in entries:
        assert entry["trained_until_date"] < entry["draw_date"]
        assert int(entry["trained_until_id"]) == int(entry["draw_id"]) - 1
        keys = {r["key"] for r in entry["rows"]}
        assert {"random", "ml_logistic", "ml_multi", "consensus", "picks_top20"} <= keys
        for row in entry["rows"]:
            assert len(row["matches"]) == len(row["tickets"]) == len(row["tiers"])
    assert entries[0]["best_key"] is not None  # falls back to consensus before any validation exists
    assert entries[0]["top_roi_keys"] is None and "top5_roi" not in {r["key"] for r in entries[0]["rows"]}
    assert len(entries[1]["top_roi_keys"]) == 5 and "top5_roi" in {r["key"] for r in entries[1]["rows"]}
    # the prediction for a draw cannot depend on its result or any later one
    altered = df.copy()
    for i in range(65, 75):
        altered.at[altered.index[i], "result"] = [1, 2, 3, 4, 5, 6]
    again = replay_game(altered, POWER_655, {"power_645": other}, start, n_tickets=4, seed=1)
    for a, b in zip(entries[:6], again[:6]):
        assert [r["tickets"] for r in a["rows"]] == [r["tickets"] for r in b["rows"]]
    summary = summarise(entries, POWER_655, df["date"].iloc[65])
    assert summary["n_draws"] == 10 and summary["warmup_draws"] == 5
    row = next(r for r in summary["rows"] if r["key"] == "picks_top20")
    assert row["draws"] == 10 and row["tickets"] == 200 and row["cost"] == 2_000_000
    print("replay predicts each draw from earlier draws only and validates it")


def test_every_strategy_predicts_identically_from_truncated_history():
    """No look-ahead in any method: same seed -> same tickets whether later draws exist or not.

    ``ml_multi`` is excluded only because its calendar feature for the *next* draw uses an estimated draw
    date when the history is truncated; it is still trained on earlier draws only (see the replay test).
    """
    df = prepare_draws(_raw_draws(80), POWER_655)
    strategies = [s for s in default_strategies(seed=2) if s[0] != "ml_multi"]
    for t in (70, 79):
        target = df["date"].iloc[t]
        for index, (key, _, factory) in enumerate(strategies):
            full, truncated = factory(df, POWER_655), factory(df.iloc[:t], POWER_655)
            full.reseed(100 + index)
            a = [full.predict(target) for _ in range(5)]
            truncated.reseed(100 + index)
            b = [truncated.predict(target) for _ in range(5)]
            assert a == b, f"{key} differs between full and truncated history at draw {t}"
    print("every method gives the same tickets with or without later draws")


def test_picks_history_merges_replay_and_live_ledger(tmp_path):
    from machine_learning.analysis import picks_history
    from machine_learning.ledger import append_prediction, load_ledger
    from machine_learning.replay import replay_game

    df = prepare_draws(_raw_draws(70), POWER_655)
    other = prepare_draws(_raw_draws(70, pool=45, bonus=False, seed=8), MEGA_645)[["date", "result"]]
    replay = replay_game(df, POWER_655, {"power_645": other}, df["date"].iloc[62], n_tickets=3, seed=1)
    live = predict_next_draw(df.iloc[:-1], POWER_655, _random_strategy(), 3, seed=4, best_key="random", n_top=5)
    append_prediction(live, "2026-11-03T11:00:00+07:00", tmp_path)
    ledger = load_ledger("power_655", tmp_path)
    history = picks_history(df, POWER_655, ledger, replay, since=str(df["date"].iloc[64]))
    ids = [d["draw_id"] for d in history["draws"]]
    assert ids == sorted(ids, key=int) and ids[0] == df["id"].iloc[64] and ids[-1] == df["id"].iloc[-1]
    last = history["draws"][-1]
    assert last["source"] == "live" and last["recorded_at"] == "2026-11-03T11:00:00+07:00"
    assert (
        decode_tickets(last["tickets"]["picks_best10"], 6)
        == next(r for r in live["strategies"] if r["key"] == "picks_best10")["tickets"]
    )
    assert all(d["source"] == "replay" for d in history["draws"][:-1])
    first = history["draws"][0]
    assert int(first["trained_until_id"]) == int(first["draw_id"]) - 1
    assert set(first["tickets"]) <= {"picks_top20", "picks_best10", "top5_roi"} and "picks_top20" in first["tickets"]
    assert len(decode_tickets(first["tickets"]["picks_top20"], 6)) == 20
    assert history["tiers"][1]["needs_bonus"] is True and history["ticket_price"] == 10_000
    print("homepage history merges the replay with live ledger predictions")


def test_method_probabilities_are_proper_and_leak_free(tmp_path):
    from machine_learning.probabilities import (
        append_probabilities,
        backfill,
        evaluate,
        load_probabilities,
        method_probabilities,
        pack,
        unpack,
    )

    assert unpack(pack([0.1094, 0.5, 0.0])) == [0.109, 0.5, 0.0]
    df = prepare_draws(_raw_draws(75), POWER_655)
    strategies = [
        s
        for s in default_strategies(seed=3)
        if s[0] in ("random", "hot", "markov", "ml_logistic", "ml_gbm", "positional")
    ]
    target = df["date"].iloc[70]
    models = {k: f(df, POWER_655) for k, _, f in strategies}
    probs = method_probabilities(
        models, POWER_655, target, samples=300, top_roi_keys=["hot", "markov", "positional", "ml_logistic", "ml_gbm"]
    )
    assert set(probs) == {"random", "hot", "markov", "ml_logistic", "ml_gbm", "positional", "top5_roi", "ml_avg"}
    assert all(len(v) == 55 for v in probs.values())
    assert probs["random"] == [6 / 55] * 55
    for key in ("hot", "markov", "positional"):
        assert abs(sum(probs[key]) - 6) < 1e-9, key  # inclusion probabilities of a 6-number ticket
    for key in ("ml_logistic", "ml_gbm", "top5_roi", "ml_avg"):
        assert abs(sum(probs[key]) - 6) < 0.3, key  # per-number model probabilities sum to about 6
    np.testing.assert_allclose(probs["ml_avg"], np.mean([probs["ml_logistic"], probs["ml_gbm"]], axis=0))
    # leak-free: the same vectors come out of models that only ever saw earlier draws
    truncated = {k: f(df.iloc[:70], POWER_655) for k, _, f in strategies}
    probs_truncated = method_probabilities(
        truncated, POWER_655, target, samples=300, top_roi_keys=["hot", "markov", "positional", "ml_logistic", "ml_gbm"]
    )
    for key in probs:
        np.testing.assert_allclose(probs[key], probs_truncated[key], err_msg=key)

    entries = backfill(df, POWER_655, {}, df["date"].iloc[72], samples=50, seed=3)
    assert [e["draw_id"] for e in entries] == list(df["id"].iloc[72:])
    assert all(int(e["trained_until_id"]) == int(e["draw_id"]) - 1 for e in entries)
    assert append_probabilities(entries, "power_655", tmp_path) == 3
    assert append_probabilities(entries, "power_655", tmp_path) == 0
    assert len(load_probabilities("power_655", tmp_path)) == 3
    report = evaluate(entries, df, POWER_655)
    rows = {r["key"]: r for r in report["rows"]}
    assert report["n_draws"] == 3 and abs(rows["random"]["auc"] - 0.5) < 1e-9
    assert all(0 <= r["auc"] <= 1 and r["mean_drawn_prob"] > 0 for r in rows.values())
    print("per-number probabilities are proper, leak-free and append-only")


def test_probabilities_payload_adds_results_and_names(tmp_path):
    from machine_learning.probabilities import append_probabilities, backfill, probabilities_payload

    df = prepare_draws(_raw_draws(75), POWER_655)
    entries = backfill(df.iloc[:-1], POWER_655, {}, df["date"].iloc[72], samples=40, seed=3)
    append_probabilities(entries, "power_655", tmp_path)
    payload = probabilities_payload("power_655", POWER_655, df, tmp_path)
    assert payload["base"] == 6 / 55 and payload["range"] == [1, 55]
    assert [e["draw_id"] for e in payload["entries"]] == list(df["id"].iloc[72:74])
    assert all(e["main"] is not None and e["drawn_date"] for e in payload["entries"])
    names = {m["key"]: m["name"] for m in payload["methods"]}
    assert names["ml_avg"].startswith("TB 3 mô hình ML") and names["random"] == "Ngẫu nhiên (baseline)"
    assert payload["evaluation"]["n_draws"] == 2
    print("dashboard probability payload carries results, names and the evaluation")
