"""
Per-number probabilities of every prediction method, draw by draw.

For a draw on ``target_date`` each method gets a vector ``p[n]`` = the probability that number ``n``
is in the method's ticket for that draw, built only from draws before ``target_date``:

* ML methods: the model's predicted probability that ``n`` is drawn (re-trained on earlier draws);
* ``random``: exactly ``pick / pool``;
* other methods (heuristics, consensus): the share of ``samples`` sampled tickets containing ``n``
  (an unbiased Monte-Carlo estimate of the inclusion probability; sums to ``pick``);
* ``top5_roi``: the mean of the vectors of the five methods it combined for that draw;
* ``ml_avg``: the mean of the ML models - the distribution behind the homepage's 20 most-probable tickets.

Entries are append-only (``predictions/probabilities/<product>.jsonl``): the live entry for the next draw
is written by ``predict_next.py`` before the draw; ``main()`` backfills earlier draws walk-forward (the
models only use data before each draw - see the no-look-ahead tests).  Values are stored in permille.
"""

import json
import math
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional, Sequence

import click
import numpy as np
import pandas as pd
from loguru import logger

from machine_learning.analysis import (
    ML_PROBABILITY_KEYS,
    TOP_ROI_KEY,
    default_strategies,
    load_draws,
    load_sources,
)
from machine_learning.games import GAMES, GameSpec
from machine_learning.ledger import LEDGER_DIR, load_replay_entries

PROB_DIR = LEDGER_DIR / "probabilities"
ML_AVG_KEY = "ml_avg"


def method_probabilities(
    models: Dict[str, object],
    game: GameSpec,
    target_date,
    samples: int = 2000,
    seed: int = 7,
    top_roi_keys: Optional[Sequence[str]] = None,
) -> Dict[str, List[float]]:
    """Per-number probability vector of every method for the draw on ``target_date``."""
    numbers = np.arange(game.min_val, game.max_val + 1)
    out: Dict[str, List[float]] = {}
    for index, (key, model) in enumerate(models.items()):
        if key == "random":
            vec = np.full(game.pool, game.pick / game.pool)
        elif key in ML_PROBABILITY_KEYS and hasattr(model, "number_probabilities"):
            vec = np.asarray(model.number_probabilities(target_date), dtype=float)
        else:
            model.reseed(seed * 1000 + index)
            counts = np.zeros(game.pool)
            for _ in range(samples):
                counts[np.asarray(model.predict(target_date)) - game.min_val] += 1
            vec = counts / samples
        out[key] = [float(v) for v in vec]
    if top_roi_keys and all(k in out for k in top_roi_keys):
        out[TOP_ROI_KEY] = [float(v) for v in np.mean([out[k] for k in top_roi_keys], axis=0)]
    ml = [out[k] for k in ML_PROBABILITY_KEYS if k in out]
    if ml:
        out[ML_AVG_KEY] = [float(v) for v in np.mean(ml, axis=0)]
    assert len(numbers) == game.pool
    return out


def pack(vec: Sequence[float]) -> str:
    """Probabilities as concatenated 3-digit permille values (0..999)."""
    return "".join(f"{min(999, max(0, int(round(v * 1000)))):03d}" for v in vec)


def unpack(packed: str) -> List[float]:
    """Inverse of :func:`pack` (permille precision)."""
    return [int(packed[i : i + 3]) / 1000 for i in range(0, len(packed), 3)]


def prob_path(product: str, prob_dir: Optional[Path] = None) -> Path:
    return (prob_dir or PROB_DIR) / f"{product}.jsonl"


def load_probabilities(product: str, prob_dir: Optional[Path] = None) -> List[dict]:
    """Recorded probability entries for ``product`` (oldest first)."""
    path = prob_path(product, prob_dir)
    if not path.exists():
        return []
    entries = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return sorted(entries, key=lambda e: int(e["draw_id"]))


def append_probabilities(entries: Sequence[dict], product: str, prob_dir: Optional[Path] = None) -> int:
    """Append entries whose ``draw_id`` is not recorded yet; returns how many were written."""
    known = {e["draw_id"] for e in load_probabilities(product, prob_dir)}
    fresh = [e for e in entries if e["draw_id"] not in known]
    if fresh:
        path = prob_path(product, prob_dir)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            for entry in sorted(fresh, key=lambda e: int(e["draw_id"])):
                handle.write(json.dumps(entry, ensure_ascii=False, separators=(",", ":")) + "\n")
    return len(fresh)


def make_entry(
    draw_id: str, target_date, trained_until_id: str, probs: Dict[str, List[float]], source: str, **extra
) -> dict:
    return {
        "draw_id": draw_id,
        "date": str(target_date),
        "trained_until_id": trained_until_id,
        "source": source,
        "probs": {k: pack(v) for k, v in probs.items()},
        **extra,
    }


def backfill(
    df: pd.DataFrame,
    game: GameSpec,
    sources,
    start: date,
    samples: int = 2000,
    seed: int = 42,
    replay_entries: Optional[List[dict]] = None,
) -> List[dict]:
    """Walk-forward probability entries for every stored draw from ``start``.

    Uses one model per method over the full history: predictions for a draw only use earlier draws
    (proven by the no-look-ahead tests), which avoids re-training from scratch for every draw.
    ``top5_roi`` and the best method come from the leak-free replay entries of the same draw.
    """
    replay = {e["draw_id"]: e for e in replay_entries or []}
    models = {key: factory(df, game) for key, _, factory in default_strategies(seed, sources)}
    entries = []
    first = next((i for i, d in enumerate(df["date"]) if d >= start), len(df))
    total = len(df) - first
    for n, position in enumerate(range(max(first, 1), len(df)), start=1):
        draw = df.iloc[position]
        trained_until = str(df["id"].iloc[position - 1])
        rp = replay.get(str(draw.id), {})
        probs = method_probabilities(models, game, draw.date, samples, top_roi_keys=rp.get("top_roi_keys"))
        entries.append(
            make_entry(str(draw.id), draw.date, trained_until, probs, "backfill", best_key=rp.get("best_key"))
        )
        if n % 10 == 0 or n == total:
            logger.info(f"{game.key} probabilities {n}/{total}")
    return entries


def evaluate(entries: Sequence[dict], df: pd.DataFrame, game: GameSpec) -> dict:
    """How well each method's probabilities ranked the numbers that were actually drawn."""
    from sklearn.metrics import roc_auc_score

    draws = {str(r.id): list(r.result) for r in df.itertuples(index=False)}
    base = game.pick / game.pool
    per: Dict[str, dict] = {}
    for entry in entries:
        main = draws.get(entry["draw_id"])
        if main is None:
            continue
        y = np.zeros(game.pool)
        y[np.asarray(main) - game.min_val] = 1
        for key, packed in entry["probs"].items():
            agg = per.setdefault(key, {"key": key, "draws": 0, "y": [], "p": [], "drawn_prob": 0.0, "top6_hits": 0})
            p = np.asarray(unpack(packed))
            agg["draws"] += 1
            agg["y"].append(y)
            agg["p"].append(p)
            agg["drawn_prob"] += float(p[y == 1].mean())
            agg["top6_hits"] += int(y[np.argsort(-p, kind="stable")[: game.pick]].sum())
    rows = []
    for agg in per.values():
        y = np.concatenate(agg.pop("y"))
        p = np.clip(np.concatenate(agg.pop("p")), 1e-4, 1 - 1e-4)
        n = agg["draws"]
        log_loss = float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))
        base_loss = float(-np.mean(y * math.log(base) + (1 - y) * math.log(1 - base)))
        try:
            auc = float(roc_auc_score(y, p)) if len(set(np.round(p, 6))) > 1 else 0.5
        except ValueError:
            auc = 0.5
        rows.append(
            {
                "key": agg["key"],
                "draws": n,
                "mean_drawn_prob": agg["drawn_prob"] / n if n else 0.0,
                "base_prob": base,
                "auc": auc,
                "log_loss": log_loss,
                "base_log_loss": base_loss,
                "top6_hits": agg["top6_hits"] / n if n else 0.0,
                "expected_top6_hits": game.expected_matches(),
            }
        )
    rows.sort(key=lambda r: -r["auc"])
    return {"n_draws": max((r["draws"] for r in rows), default=0), "rows": rows}


@click.command()
@click.option("--from", "start", default="2026-01-01", show_default=True, type=click.DateTime(formats=["%Y-%m-%d"]))
@click.option("--product", "products", multiple=True)
@click.option("--samples", default=2000, show_default=True, help="Sampled tickets per heuristic method and draw.")
@click.option("--seed", default=42, show_default=True)
def main(start, products, samples: int, seed: int) -> None:
    """Backfill per-number probabilities of every method for each stored draw from ``--from``."""
    sources = load_sources()
    for key in products or GAMES:
        game = GAMES[key]
        df = load_draws(game)
        entries = backfill(df, game, sources, start.date(), samples, seed, load_replay_entries(key))
        written = append_probabilities(entries, key)
        logger.info(f"{game.title}: {written} probability entries written")


if __name__ == "__main__":
    main()


METHOD_LABELS = {
    "ml_avg": "TB 3 mô hình ML (cơ sở của 20 bộ)",
    TOP_ROI_KEY: "Kết hợp 5 ROI cao nhất",
}


def probabilities_payload(product: str, game: GameSpec, df: pd.DataFrame, prob_dir: Optional[Path] = None) -> dict:
    """Dashboard data: every recorded entry (with the result once drawn), method names and the evaluation."""
    entries = load_probabilities(product, prob_dir)
    names = {key: name for key, name, _ in default_strategies(42, None)}
    names["ml_multi"] = "ML đa nguồn (sản phẩm khác + lịch quay)"
    names.update(METHOD_LABELS)
    draws = {str(r.id): r for r in df.itertuples(index=False)}
    out = []
    for entry in entries:
        draw = draws.get(entry["draw_id"])
        out.append(
            {
                **entry,
                "main": list(draw.result) if draw is not None else None,
                "bonus": (
                    int(draw.bonus) if draw is not None and draw.bonus is not None and not pd.isna(draw.bonus) else None
                ),
                "drawn_date": str(draw.date) if draw is not None else None,
            }
        )
    keys = []
    for entry in entries:
        for key in entry["probs"]:
            if key not in keys:
                keys.append(key)
    return {
        "title": game.title,
        "pick": game.pick,
        "range": [game.min_val, game.max_val],
        "has_bonus": game.has_bonus,
        "base": game.pick / game.pool,
        "methods": [{"key": k, "name": names.get(k, k)} for k in keys],
        "entries": out,
        "evaluation": evaluate(entries, df, game),
    }
