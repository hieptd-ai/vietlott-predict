"""
Prediction ledger: the tickets each method predicted *before* a draw, recorded as soon as the
previous result was known, and scored once the predicted draw happens.

Unlike the walk-forward simulation (re-computed on every run), ledger entries are written once and
committed (``predictions/<product>.jsonl``), so they form a tamper-evident live track record.
"""

import json
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

from machine_learning.games import GameSpec

REPO_ROOT = Path(__file__).resolve().parents[2]
LEDGER_DIR = REPO_ROOT / "predictions"


def ledger_path(product: str, ledger_dir: Optional[Path] = None) -> Path:
    """NDJSON file holding ``product``'s recorded predictions."""
    return (ledger_dir or LEDGER_DIR) / f"{product}.jsonl"


def load_ledger(product: str, ledger_dir: Optional[Path] = None) -> List[dict]:
    """All recorded predictions for ``product`` (oldest first); empty when none were recorded yet."""
    path = ledger_path(product, ledger_dir)
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def append_prediction(prediction: dict, generated_at: str, ledger_dir: Optional[Path] = None) -> bool:
    """Record a :func:`machine_learning.analysis.predict_next_draw` result once per ``after_id``.

    Returns ``False`` (and writes nothing) when a prediction made after the same draw already exists,
    so re-runs never overwrite what was predicted before the result was known.
    """
    product = prediction["product"]
    if any(e["after_id"] == prediction["after_id"] for e in load_ledger(product, ledger_dir)):
        return False
    entry = {
        "product": product,
        "after_id": prediction["after_id"],
        "after_date": prediction["after_date"],
        "target_date": prediction["target_date"],
        "generated_at": generated_at,
        "seed": prediction["seed"],
        "strategies": [
            {
                "key": r["key"],
                "name": r["name"],
                "tickets": [list(map(int, t)) for t in r["tickets"]],
                **({"selected": list(r["selected"])} if r.get("selected") else {}),
            }
            for r in prediction["strategies"]
        ],
        "picks": {
            role: {k: v for k, v in meta.items() if k != "number_probabilities"}
            for role, meta in prediction.get("picks", {}).items()
        },
    }
    path = ledger_path(product, ledger_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False, separators=(",", ":")) + "\n")
    return True


def _next_id(after_id: str) -> str:
    return str(int(after_id) + 1).zfill(len(after_id))


def score_ledger(entries: List[dict], df: pd.DataFrame, game: GameSpec) -> dict:
    """Score every recorded prediction whose draw has happened; summarise per method.

    The predicted draw is the one whose id follows ``after_id``.
    """
    draws = {str(r.id): r for r in df.itertuples(index=False)}
    scored, pending = [], []
    summary: Dict[str, dict] = {}
    for entry in entries:
        draw = draws.get(_next_id(entry["after_id"]))
        if draw is None:
            pending.append(entry)
            continue
        result = list(draw.result) + ([int(draw.bonus)] if draw.bonus is not None and not pd.isna(draw.bonus) else [])
        per_strategy = []
        for row in entry["strategies"]:
            outcomes = [game.score(t, result) for t in row["tickets"]]
            gain = sum(tier.value for _, _, tier in outcomes if tier)
            cost = len(row["tickets"]) * game.ticket_price
            best = max((m for m, _, _ in outcomes), default=0)
            winners = sum(1 for _, _, tier in outcomes if tier)
            per_strategy.append(
                {"key": row["key"], "name": row["name"], "best": best, "winners": winners, "gain": gain, "cost": cost}
            )
            agg = summary.setdefault(
                row["key"],
                {
                    "key": row["key"],
                    "name": row["name"],
                    "draws": 0,
                    "cost": 0,
                    "gain": 0,
                    "winners": 0,
                    "matches": 0,
                    "tickets": 0,
                },
            )
            agg["draws"] += 1
            agg["cost"] += cost
            agg["gain"] += gain
            agg["winners"] += winners
            agg["matches"] += sum(m for m, _, _ in outcomes)
            agg["tickets"] += len(outcomes)
        scored.append(
            {
                "after_id": entry["after_id"],
                "draw_id": str(draw.id),
                "draw_date": str(draw.date),
                "generated_at": entry["generated_at"],
                "main": list(draw.result),
                "bonus": int(draw.bonus) if draw.bonus is not None and not pd.isna(draw.bonus) else None,
                "strategies": per_strategy,
            }
        )
    for agg in summary.values():
        agg["profit"] = agg["gain"] - agg["cost"]
        agg["roi"] = agg["profit"] / agg["cost"] * 100 if agg["cost"] else 0.0
        agg["avg_matches"] = agg["matches"] / agg["tickets"] if agg["tickets"] else 0.0
    return {
        "n_recorded": len(entries),
        "n_scored": len(scored),
        "pending": [
            {"after_id": e["after_id"], "target_date": e["target_date"], "generated_at": e["generated_at"]}
            for e in pending
        ],
        "scored": scored[-20:],
        "summary": sorted(summary.values(), key=lambda a: -a["avg_matches"]),
    }


def load_replay_summary(product: str, replay_dir: Optional[Path] = None) -> Optional[dict]:
    """Summary written by ``replay.py`` for ``product`` (None when the replay has not been run)."""
    path = (replay_dir or LEDGER_DIR / "replay") / f"{product}-summary.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
