"""
Re-train every method on all known draws and record its tickets for the next draw in the ledger.

Run after each data update (the ``sync-data.yml`` workflow does this), e.g.::

    uv run --extra ml python src/machine_learning/predict_next.py
"""

from pathlib import Path
from typing import Optional

import click
import pandas as pd
from loguru import logger

from machine_learning.analysis import default_strategies, load_draws, load_sources, predict_next_draw
from machine_learning.games import GAMES
from machine_learning.ledger import append_prediction


@click.command()
@click.option("--tickets", default=10, show_default=True, help="Tickets per method for the next draw.")
@click.option("--seed", default=42, show_default=True)
@click.option("--ledger-dir", type=click.Path(path_type=Path), default=None, help="Defaults to ./predictions.")
def main(tickets: int, seed: int, ledger_dir: Optional[Path]) -> None:
    """Predict the next Power 6/55 and Mega 6/45 draw with every method and append it to the ledger."""
    sources = load_sources()
    generated_at = pd.Timestamp.now(tz="Asia/Ho_Chi_Minh").isoformat(timespec="seconds")
    for key, game in GAMES.items():
        df = load_draws(game)
        prediction = predict_next_draw(df, game, default_strategies(seed, sources), tickets, seed)
        written = append_prediction(prediction, generated_at, ledger_dir)
        state = "recorded" if written else "already recorded"
        logger.info(f"{game.title}: prediction after draw #{prediction['after_id']} {state}")


if __name__ == "__main__":
    main()
