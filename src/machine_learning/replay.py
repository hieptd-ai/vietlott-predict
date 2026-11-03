"""
Replay the live "predict the next draw, then validate it" pipeline on past draws.

For every draw from ``start`` onwards this module does exactly what ``predict_next.py`` does in
production, as if it ran just before that draw:

1. truncate the draw history - and every extra data source - to draws held strictly **before** the
   draw date, then build every strategy and ML model from scratch on that truncated data (models never
   see the draw or anything after it; :func:`_assert_no_future` enforces it);
2. predict 10 tickets per method plus the homepage picks (20 most-probable tickets, 10 tickets of the
   best method) and the adaptive top-5-by-ROI method, where "best" and "top 5" come only from the
   replay's own validation of the *earlier* draws;
3. validate every ticket against the real result.

Draws before ``validate_from`` only warm up the running rankings; the summary covers draws from
``validate_from`` on.  Usage::

    uv run --extra ml python src/machine_learning/replay.py --start 2025-07-01 --validate-from 2026-01-01
"""

import json
import math
import time
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional, Sequence

import click
import pandas as pd
from loguru import logger

from machine_learning.analysis import (
    PICK_BEST_KEY,
    PICK_TOP_KEY,
    TOP_ROI_KEY,
    TOP_ROI_N,
    Sources,
    _normal_two_sided_p,
    default_strategies,
    load_draws,
    load_sources,
    predict_next_draw,
    top_roi_selection,
)
from machine_learning.games import GAMES, GameSpec

REPO_ROOT = Path(__file__).resolve().parents[2]
REPLAY_DIR = REPO_ROOT / "predictions" / "replay"


def _assert_no_future(past: pd.DataFrame, sources: Sources, draw_date: date, draw_id: str) -> None:
    """Fail loudly if any training data is from the predicted draw's date or later."""
    assert past.empty or max(past["date"]) < draw_date, f"draw history reaches {max(past['date'])} >= {draw_date}"
    assert draw_id not in set(past["id"]), f"draw {draw_id} is in its own training data"
    for key, source in sources.items():
        assert source.empty or max(source["date"]) < draw_date, f"source {key} reaches {draw_date}"


def replay_game(
    df: pd.DataFrame,
    game: GameSpec,
    sources: Sources,
    start: date,
    n_tickets: int = 10,
    seed: int = 42,
    end: Optional[date] = None,
) -> List[dict]:
    """Walk-forward replay of the live prediction pipeline for every draw of ``game`` from ``start``.

    Returns one entry per draw: the prediction made before it (with ``best_key`` / ``top_roi_keys``
    chosen from earlier validated draws only) and the validation of every row against the result.
    """
    targets = df[(df["date"] >= start) & ((df["date"] <= end) if end else True)]
    profit: Dict[str, float] = {}
    matched: Dict[str, float] = {}
    entries: List[dict] = []
    started = time.time()
    for n, draw in enumerate(targets.itertuples(index=False), start=1):
        past = df[df["date"] < draw.date]
        past_sources = {k: v[v["date"] < draw.date] for k, v in sources.items()}
        _assert_no_future(past, past_sources, draw.date, str(draw.id))

        strategies = default_strategies(seed, past_sources)
        base_keys = [key for key, _, _ in strategies]
        best_key = max(base_keys, key=lambda k: (matched.get(k, 0.0), -base_keys.index(k))) if matched else None
        top_roi = top_roi_selection(profit, matched, base_keys, TOP_ROI_N) if profit else None
        prediction = predict_next_draw(
            past, game, strategies, n_tickets, seed + int(draw.id), best_key=best_key, top_roi_keys=top_roi
        )

        result = list(draw.result) + ([int(draw.bonus)] if draw.bonus is not None and not pd.isna(draw.bonus) else [])
        rows = []
        for row in prediction["strategies"]:
            outcomes = [game.score(t, result) for t in row["tickets"]]
            gain = sum(t.value for _, _, t in outcomes if t)
            cost = len(row["tickets"]) * game.ticket_price
            matches = sum(m for m, _, _ in outcomes)
            rows.append(
                {
                    "key": row["key"],
                    "name": row["name"],
                    "tickets": row["tickets"],
                    "matches": [m for m, _, _ in outcomes],
                    "tiers": [t.key if t else None for _, _, t in outcomes],
                    "gain": gain,
                    "cost": cost,
                    **({"selected": row["selected"]} if row.get("selected") else {}),
                }
            )
            if row["key"] in base_keys:
                profit[row["key"]] = profit.get(row["key"], 0.0) + gain - cost
                matched[row["key"]] = matched.get(row["key"], 0.0) + matches
        entries.append(
            {
                "draw_id": str(draw.id),
                "draw_date": str(draw.date),
                "trained_until_id": str(past["id"].iloc[-1]),
                "trained_until_date": str(past["date"].iloc[-1]),
                "best_key": prediction.get("picks", {}).get("best", {}).get("method_key"),
                "top_roi_keys": top_roi,
                "main": list(draw.result),
                "bonus": result[game.pick] if len(result) > game.pick else None,
                "rows": rows,
            }
        )
        if n % 10 == 0 or n == len(targets):
            logger.info(f"{game.key} replay {n}/{len(targets)} draws ({time.time() - started:.0f}s)")
    return entries


def summarise(entries: Sequence[dict], game: GameSpec, validate_from: date) -> dict:
    """Per-method validation over the entries from ``validate_from``: matches, z vs chance, tiers, ROI."""
    scored = [e for e in entries if e["draw_date"] >= str(validate_from)]
    expected = game.expected_matches()
    pmf = game.match_probabilities()
    var = sum((k - expected) ** 2 * p for k, p in enumerate(pmf))
    per: Dict[str, dict] = {}
    for entry in scored:
        for row in entry["rows"]:
            agg = per.setdefault(
                row["key"],
                {
                    "key": row["key"],
                    "name": row["name"],
                    "draws": 0,
                    "tickets": 0,
                    "matches": 0,
                    "cost": 0,
                    "gain": 0,
                    "tiers": Counter(),
                    "draw_means": [],
                    "best_match": 0,
                },
            )
            agg["name"] = row["name"]
            agg["draws"] += 1
            agg["tickets"] += len(row["matches"])
            agg["matches"] += sum(row["matches"])
            agg["cost"] += row["cost"]
            agg["gain"] += row["gain"]
            agg["tiers"].update(t for t in row["tiers"] if t)
            agg["draw_means"].append(sum(row["matches"]) / max(len(row["matches"]), 1))
            agg["best_match"] = max(agg["best_match"], max(row["matches"], default=0))
    rows = []
    for agg in per.values():
        avg = agg["matches"] / agg["tickets"] if agg["tickets"] else 0.0
        means = agg.pop("draw_means")
        se_ind = math.sqrt(var / agg["tickets"]) if agg["tickets"] else 0.0
        mean = sum(means) / len(means) if means else 0.0
        se_cl = (
            (sum((m - mean) ** 2 for m in means) / (len(means) - 1)) ** 0.5 / math.sqrt(len(means))
            if len(means) > 1
            else 0.0
        )
        se = max(se_ind, se_cl)
        z = (avg - expected) / se if se else 0.0
        rows.append(
            {
                **agg,
                "tiers": dict(agg["tiers"]),
                "winners": sum(agg["tiers"].values()),
                "avg_matches": avg,
                "z": z,
                "p_value": _normal_two_sided_p(z),
                "profit": agg["gain"] - agg["cost"],
                "roi": (agg["gain"] - agg["cost"]) / agg["cost"] * 100 if agg["cost"] else 0.0,
            }
        )
    n = len(rows)
    for row in rows:
        row["p_adjusted"] = min(1.0, row["p_value"] * n)
    rows.sort(key=lambda r: (-r["avg_matches"], -r["roi"]))
    from machine_learning.analysis import _bonferroni_z

    best_counts = Counter(e["best_key"] for e in scored if e["best_key"])
    top_counts = Counter(k for e in scored for k in (e["top_roi_keys"] or []))
    return {
        "validate_from": str(validate_from),
        "validate_to": scored[-1]["draw_date"] if scored else None,
        "n_draws": len(scored),
        "warmup_draws": len(entries) - len(scored),
        "expected_avg_matches": expected,
        "expected_roi": (game.expected_value() - game.ticket_price) / game.ticket_price * 100,
        "bonferroni_z": _bonferroni_z(n),
        "best_key_usage": best_counts.most_common(),
        "top_roi_usage": top_counts.most_common(),
        "picks_keys": [PICK_TOP_KEY, PICK_BEST_KEY, TOP_ROI_KEY],
        "rows": rows,
        "draws": [
            {
                "draw_id": e["draw_id"],
                "draw_date": e["draw_date"],
                "trained_until_id": e["trained_until_id"],
                "main": e["main"],
                "bonus": e["bonus"],
                "best_key": e["best_key"],
                "picks": [
                    {
                        "key": r["key"],
                        "best": max(r["matches"], default=0),
                        "winners": sum(1 for t in r["tiers"] if t),
                        "gain": r["gain"],
                        "cost": r["cost"],
                    }
                    for r in e["rows"]
                    if r["key"] in (PICK_TOP_KEY, PICK_BEST_KEY, TOP_ROI_KEY)
                ],
            }
            for e in scored
        ],
    }


@click.command()
@click.option("--start", default="2025-07-01", show_default=True, type=click.DateTime(formats=["%Y-%m-%d"]))
@click.option("--validate-from", default="2026-01-01", show_default=True, type=click.DateTime(formats=["%Y-%m-%d"]))
@click.option("--product", "products", multiple=True, help="power_655 / power_645 (default: both).")
@click.option("--tickets", default=10, show_default=True)
@click.option("--seed", default=42, show_default=True)
@click.option("--out", "out_dir", type=click.Path(path_type=Path), default=REPLAY_DIR, show_default=True)
def main(start, validate_from, products, tickets: int, seed: int, out_dir: Path) -> None:
    """Replay predictions and validations draw by draw and write predictions/replay/<product>.jsonl + summary."""
    out_dir.mkdir(parents=True, exist_ok=True)
    sources = load_sources()
    for key in products or GAMES:
        game = GAMES[key]
        entries = replay_game(load_draws(game), game, sources, start.date(), tickets, seed)
        with (out_dir / f"{key}.jsonl").open("w", encoding="utf-8") as handle:
            for entry in entries:
                handle.write(json.dumps(entry, ensure_ascii=False, separators=(",", ":")) + "\n")
        summary = summarise(entries, game, validate_from.date())
        (out_dir / f"{key}-summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
        )
        logger.info(f"{game.title}: replayed {len(entries)} draws, {summary['n_draws']} validated")


if __name__ == "__main__":
    main()
