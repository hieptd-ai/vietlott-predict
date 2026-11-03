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

from machine_learning.analysis import build_analysis

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


@click.command()
@click.option("--out", "out_dir", type=click.Path(path_type=Path), default=DEFAULT_OUT, show_default=True)
@click.option("--tickets", default=10, show_default=True, help="Tickets per draw for every method.")
@click.option("--runs", default=10, show_default=True, help="Random replays per method in the comparison.")
@click.option("--ml-eval", default=300, show_default=True, help="Draws in the walk-forward ML evaluation.")
@click.option("--seed", default=42, show_default=True)
@click.option(
    "--play-from",
    default="2026-01-01",
    show_default=True,
    type=click.DateTime(formats=["%Y-%m-%d"]),
    help="First draw date of the comparison and the profit simulator.",
)
def main(out_dir: Path, tickets: int, runs: int, ml_eval: int, seed: int, play_from) -> None:
    """Build the analysis payload for Power 6/55 and Mega 6/45 and write it for the dashboard."""
    payload = build_analysis(
        ml_eval_draws=ml_eval,
        seed=seed,
        simulation_start=play_from.date(),
        simulation_tickets=tickets,
        n_runs=runs,
    )
    write_analysis(payload, out_dir)


if __name__ == "__main__":
    main()
