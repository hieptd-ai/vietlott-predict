"""
Re-train every method on all known draws, record its tickets for the next draw in the ledger, and
validate the predictions recorded before the draws that have happened since.

Run after each data update (the ``sync-data.yml`` workflow does this), e.g.::

    uv run --extra ml python src/machine_learning/predict_next.py
"""

import json
import os
from pathlib import Path
from typing import Optional

import click
import pandas as pd
from loguru import logger

from machine_learning.analysis import (
    PICK_BEST_KEY,
    PICK_TOP_KEY,
    default_strategies,
    load_draws,
    load_sources,
    predict_next_draw,
)
from machine_learning.games import GAMES
from machine_learning.ledger import LEDGER_DIR, append_prediction, load_ledger, next_draw_id, score_ledger
from machine_learning.probabilities import append_probabilities, make_entry, method_probabilities

REPO_ROOT = Path(__file__).resolve().parents[2]
ANALYSIS_JSON = REPO_ROOT / "docs" / "analysis" / "analysis.json"


def published_comparison(path: Path = ANALYSIS_JSON) -> dict:
    """Product -> ``(best method key, top-ROI method keys)`` of the last published comparison."""
    if not path.exists():
        return {}
    try:
        products = json.loads(path.read_text(encoding="utf-8")).get("products", {})
    except json.JSONDecodeError:
        return {}
    return {
        key: (p.get("comparison", {}).get("best_key"), p.get("comparison", {}).get("top_roi_keys", []))
        for key, p in products.items()
    }


def validation_markdown(title: str, scored: dict) -> str:
    """Short Markdown report of the latest validated prediction (for the GitHub job summary)."""
    if not scored["scored"]:
        return f"### {title}\n\nChưa có dự đoán nào được thẩm định ({scored['n_recorded']} lần đã ghi).\n"
    last = scored["scored"][-1]
    lines = [
        f"### {title}: kỳ #{last['draw_id']} ({last['draw_date']})",
        "",
        f"Kết quả: {' '.join(f'{n:02d}' for n in last['main'])}" + (f" + {last['bonus']:02d}" if last["bonus"] else ""),
        "",
        "| Phương pháp | Trúng nhiều nhất | Vé trúng | Thưởng |",
        "|---|---|---|---|",
    ]
    picks_first = sorted(last["strategies"], key=lambda s: (s["key"] not in (PICK_TOP_KEY, PICK_BEST_KEY), -s["best"]))
    for row in picks_first:
        lines.append(f"| {row['name']} | {row['best']} số | {row['winners']} | {row['gain']:,} đ |")
    return "\n".join(lines) + "\n"


@click.command()
@click.option("--tickets", default=10, show_default=True, help="Tickets per method for the next draw.")
@click.option("--top", default=20, show_default=True, help="Most-probable tickets recorded for the homepage.")
@click.option("--seed", default=42, show_default=True)
@click.option("--ledger-dir", type=click.Path(path_type=Path), default=None, help="Defaults to ./predictions.")
def main(tickets: int, top: int, seed: int, ledger_dir: Optional[Path]) -> None:
    """Validate recorded predictions, then predict the next Power 6/55 and Mega 6/45 draw with every method."""
    sources = load_sources()
    published = published_comparison()
    generated_at = pd.Timestamp.now(tz="Asia/Ho_Chi_Minh").isoformat(timespec="seconds")
    # no timestamp in the scorecard: it only changes (and gets committed) when there is something new
    scorecard, report = {"products": {}}, []
    for key, game in GAMES.items():
        df = load_draws(game)
        strategies = default_strategies(seed, sources)
        best_key, top_roi_keys = published.get(key, (None, []))
        models: dict = {}
        prediction = predict_next_draw(
            df, game, strategies, tickets, seed, models=models, best_key=best_key, n_top=top, top_roi_keys=top_roi_keys
        )
        # per-number probabilities of every method for the next draw, recorded before the draw
        target_id = next_draw_id(prediction["after_id"])
        probs = method_probabilities(models, game, prediction["target_date"], top_roi_keys=top_roi_keys)
        entry = make_entry(
            target_id, prediction["target_date"], prediction["after_id"], probs, "live", best_key=best_key
        )
        entry["recorded_at"] = generated_at
        if append_probabilities([entry], key, None if ledger_dir is None else ledger_dir / "probabilities"):
            logger.info(f"{game.title}: per-number probabilities for draw #{target_id} recorded")
        written = append_prediction(prediction, generated_at, ledger_dir)
        state = "recorded" if written else "already recorded"
        logger.info(f"{game.title}: prediction after draw #{prediction['after_id']} {state}")

        scored = score_ledger(load_ledger(key, ledger_dir), df, game)
        scorecard["products"][key] = {
            "title": game.title,
            "n_recorded": scored["n_recorded"],
            "n_scored": scored["n_scored"],
            "summary": scored["summary"],
            "last": scored["scored"][-1] if scored["scored"] else None,
        }
        report.append(validation_markdown(game.title, scored))
        logger.info(f"{game.title}: {scored['n_scored']} of {scored['n_recorded']} recorded predictions validated")

    out_dir = ledger_dir or LEDGER_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "scorecard.json").write_text(
        json.dumps(scorecard, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "a", encoding="utf-8") as handle:
            handle.write("## Thẩm định dự đoán\n\n" + "\n".join(report))


if __name__ == "__main__":
    main()
