"""
Render the analysis dashboard data (``docs/analysis/analysis.json`` and ``analysis-data.js``).

The static page ``docs/analysis/index.html`` reads ``analysis-data.js`` (works from ``file://``);
``analysis.json`` is the same payload for other consumers.

Usage::

    uv run --extra ml python src/machine_learning/render_analysis.py
    uv run --extra ml python src/machine_learning/render_analysis.py --window 100 --tickets 5
"""

import json
import math
from pathlib import Path

import click
from loguru import logger

from machine_learning.analysis import build_analysis, homepage_picks, load_draws, picks_history, replay_picks_summary
from machine_learning.games import get_game
from machine_learning.ledger import load_ledger, load_replay_entries, load_replay_summary, score_ledger

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUT = REPO_ROOT / "docs" / "analysis"


def _compact(value, digits: int = 6):
    """Round floats to ``digits`` significant digits (and NaN/inf to None) to keep the JSON small."""
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return None
        return float(f"{value:.{digits}g}")
    if isinstance(value, dict):
        return {k: _compact(v, digits) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_compact(v, digits) for v in value]
    if hasattr(value, "item"):  # numpy scalar
        return _compact(value.item(), digits)
    return value


def attach_vote_picks(payload: dict) -> None:
    """Add the voting suggestion (next draw, draw-by-draw tickets and totals) to the homepage picks."""
    from machine_learning.analysis import encode_tickets
    from machine_learning.probabilities import (
        METHOD_CODES,
        VOTE_KEY,
        load_probabilities,
        method_names,
        summarise_votes,
        vote_history,
    )

    names = method_names()
    codes = {code: names.get(key, key) for key, code in METHOD_CODES.items()}
    for key, product in payload.get("products", {}).items():
        picks = product.get("picks")
        if picks is None:
            continue
        game = get_game(key)
        history = vote_history(load_probabilities(key), load_draws(game), game)
        if not history:
            continue
        since = (picks.get("history") or {}).get("since") or "2026-01-01"
        nxt = history[-1] if "result" not in history[-1] else None
        picks["vote"] = {
            "next": None
            if nxt is None
            else {
                k: nxt[k]
                for k in ("draw_id", "date", "chosen_by", "selected", "vote_tickets", "method_tickets", "best_methods")
            },
            "summary": summarise_votes(history, game, since),
            "codes": codes,
        }
        by_id = {h["draw_id"]: h for h in history}
        for draw in (picks.get("history") or {}).get("draws", []):
            vote = by_id.get(draw["draw_id"])
            if vote:
                draw["tickets"][VOTE_KEY] = encode_tickets(vote["tickets"])
                draw["names"][VOTE_KEY] = "10 bộ bỏ phiếu"


def write_directions(payload: dict, out_dir: Path, since: str = "2026-01-01") -> None:
    """Write ``directions.json`` / ``directions.js`` and add each draw's most related directions to the picks."""
    from machine_learning.analysis import load_sources
    from machine_learning.directions import directions_payload, long_check
    from machine_learning.probabilities import load_probabilities

    sources = load_sources()
    products = {}
    for key, product in payload.get("products", {}).items():
        game = get_game(key)
        df = load_draws(game)
        data = directions_payload(df, game, sources, load_probabilities(key), since)
        data["long"] = long_check(df, game, sources, until=since)
        products[key] = data
        picks = product.get("picks")
        if picks is None:
            continue
        rows = {d["draw_id"]: d for d in data["draws"]}
        for draw in (picks.get("history") or {}).get("draws", []):
            row = rows.get(draw["draw_id"])
            if row:
                draw["directions"] = {
                    "best": row["best"],
                    "p_best": row["p_best"],
                }
        summary = data["summary"]
        picks["directions"] = {
            "since": summary["since"],
            "n_draws": summary["n_draws"],
            "best": summary["best"],
            "top": summary["directions"][:3],
            "bonferroni_z": summary["bonferroni_z"],
            "follow": [f for f in summary["follow"] if f["window"] == 10],
            "expected_matches": summary["expected_matches"],
        }
    text = json.dumps(_compact({"products": products}), ensure_ascii=False, separators=(",", ":"))
    (out_dir / "directions.json").write_text(text + "\n", encoding="utf-8")
    (out_dir / "directions.js").write_text(f"window.VIETLOTT_DIRECTIONS = {text};\n", encoding="utf-8")
    logger.info(f"wrote {out_dir / 'directions.js'} ({len(text) / 1024:.0f} KiB)")


def write_probabilities(out_dir: Path) -> None:
    """Write ``probabilities.json`` / ``probabilities.js``: per-number probabilities of every method by draw."""
    from machine_learning.probabilities import probabilities_payload

    products = {}
    for key in ("power_655", "power_645"):
        game = get_game(key)
        products[key] = probabilities_payload(key, game, load_draws(game))
    text = json.dumps(_compact({"products": products}), ensure_ascii=False, separators=(",", ":"))
    (out_dir / "probabilities.json").write_text(text + "\n", encoding="utf-8")
    (out_dir / "probabilities.js").write_text(f"window.VIETLOTT_PROBS = {text};\n", encoding="utf-8")
    logger.info(f"wrote {out_dir / 'probabilities.js'} ({len(text) / 1024:.0f} KiB)")


def write_analysis(payload: dict, out_dir: Path) -> None:
    """Write ``analysis.json`` / ``analysis-data.js`` and the homepage's ``picks.json`` / ``picks.js``."""
    out_dir.mkdir(parents=True, exist_ok=True)
    text = json.dumps(_compact(payload), ensure_ascii=False, separators=(",", ":"))
    (out_dir / "analysis.json").write_text(text + "\n", encoding="utf-8")
    (out_dir / "analysis-data.js").write_text(f"window.VIETLOTT_ANALYSIS = {text};\n", encoding="utf-8")
    picks = {
        "generated_at": payload.get("generated_at"),
        "products": {
            key: {
                "title": product["title"],
                "pick": product["pick"],
                "has_bonus": product["has_bonus"],
                **product["picks"],
            }
            for key, product in payload.get("products", {}).items()
            if "picks" in product
        },
    }
    picks_text = json.dumps(_compact(picks), ensure_ascii=False, separators=(",", ":"))
    (out_dir / "picks.json").write_text(picks_text + "\n", encoding="utf-8")
    (out_dir / "picks.js").write_text(f"window.VIETLOTT_PICKS = {picks_text};\n", encoding="utf-8")
    logger.info(f"wrote {out_dir / 'analysis.json'} and analysis-data.js ({len(text) / 1024:.0f} KiB)")


def refresh_picks(out_dir: Path) -> None:
    """Re-score the ledger and rebuild the homepage picks inside an existing ``analysis.json`` (fast)."""
    payload = json.loads((out_dir / "analysis.json").read_text(encoding="utf-8"))
    for key, product in payload["products"].items():
        game = get_game(key)
        ledger = load_ledger(key)
        df = load_draws(game)
        scored = score_ledger(ledger, df, game)
        product["ledger"] = scored
        replay = load_replay_summary(key)
        product["replay"] = replay
        product["picks"] = {
            **homepage_picks(product["next_draw"], product["comparison"], ledger, scored),
            "replay": replay_picks_summary(replay),
            "history": picks_history(df, game, ledger, load_replay_entries(key), (replay or {}).get("validate_from")),
        }
    attach_vote_picks(payload)
    out_dir.mkdir(parents=True, exist_ok=True)
    write_directions(payload, out_dir)
    write_analysis(payload, out_dir)
    write_probabilities(out_dir)


@click.command()
@click.option("--out", "out_dir", type=click.Path(path_type=Path), default=DEFAULT_OUT, show_default=True)
@click.option("--tickets", default=10, show_default=True, help="Tickets per draw for every method.")
@click.option("--runs", default=5, show_default=True, help="Random replays per method in the comparison.")
@click.option("--ml-eval", default=300, show_default=True, help="Draws in the walk-forward ML evaluation.")
@click.option("--seed", default=42, show_default=True)
@click.option(
    "--play-from",
    default="2025-01-01",
    show_default=True,
    type=click.DateTime(formats=["%Y-%m-%d"]),
    help="First draw date of the comparison and the profit simulator.",
)
@click.option(
    "--refresh-picks", "picks_only", is_flag=True, help="Only re-score the ledger and rebuild the homepage picks."
)
def main(out_dir: Path, tickets: int, runs: int, ml_eval: int, seed: int, play_from, picks_only: bool) -> None:
    """Build the analysis payload for Power 6/55 and Mega 6/45 and write it for the dashboard."""
    if picks_only:
        refresh_picks(out_dir)
        return
    payload = build_analysis(
        ml_eval_draws=ml_eval,
        seed=seed,
        simulation_start=play_from.date(),
        simulation_tickets=tickets,
        n_runs=runs,
    )
    attach_vote_picks(payload)
    out_dir.mkdir(parents=True, exist_ok=True)
    write_directions(payload, out_dir)
    write_analysis(payload, out_dir)
    write_probabilities(out_dir)


if __name__ == "__main__":
    main()
