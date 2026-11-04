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
from itertools import combinations
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
from machine_learning.ledger import LEDGER_DIR, load_ledger, load_replay_entries, next_draw_id

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
    """Per-number probability vector of every method for the draw on ``target_date`` (date or ISO string)."""
    target_date = pd.Timestamp(target_date).date()
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
    ledger_entries: Optional[List[dict]] = None,
    end: Optional[date] = None,
) -> List[dict]:
    """Walk-forward probability entries for every stored draw from ``start`` (to ``end`` inclusive).

    Uses one model per method over the full history: predictions for a draw only use earlier draws
    (proven by the no-look-ahead tests), which avoids re-training from scratch for every draw.
    ``top5_roi`` and the best method come from the leak-free replay entries of the same draw, or from
    the live ledger prediction made before that draw when the replay does not cover it.
    """
    replay = {e["draw_id"]: e for e in replay_entries or []}
    for entry in ledger_entries or []:
        draw_id = next_draw_id(entry["after_id"])
        if draw_id in replay:
            continue
        top = next((r for r in entry["strategies"] if r["key"] == TOP_ROI_KEY), {})
        replay[draw_id] = {
            "top_roi_keys": top.get("selected"),
            "best_key": entry.get("picks", {}).get("best", {}).get("method_key"),
        }
    models = {key: factory(df, game) for key, _, factory in default_strategies(seed, sources)}
    entries = []
    first = next((i for i, d in enumerate(df["date"]) if d >= start), len(df))
    stop = next((i for i, d in enumerate(df["date"]) if end and d > end), len(df))
    total = stop - first
    for n, position in enumerate(range(max(first, 1), stop), start=1):
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
@click.option(
    "--to", "end", default=None, type=click.DateTime(formats=["%Y-%m-%d"]), help="Last draw date (inclusive)."
)
def main(start, products, samples: int, seed: int, end) -> None:
    """Backfill per-number probabilities of every method for each stored draw from ``--from``."""
    sources = load_sources()
    for key in products or GAMES:
        game = GAMES[key]
        df = load_draws(game)
        entries = backfill(
            df,
            game,
            sources,
            start.date(),
            samples,
            seed,
            load_replay_entries(key),
            load_ledger(key),
            end.date() if end else None,
        )
        written = append_probabilities(entries, key)
        logger.info(f"{game.title}: {written} probability entries written")


if __name__ == "__main__":
    main()


METHOD_LABELS = {
    "ml_avg": "TB 3 mô hình ML (cơ sở của 20 bộ)",
    TOP_ROI_KEY: "Kết hợp 5 ROI cao nhất",
}


def probabilities_payload(
    product: str, game: GameSpec, df: pd.DataFrame, prob_dir: Optional[Path] = None, since: Optional[str] = "2026-01-01"
) -> dict:
    """Dashboard data for draws since ``since`` (earlier entries only warm up the voting ranking).

    Every entry carries the result once drawn and its voting suggestion; plus method names and codes,
    the evaluation of the probabilities and the totals of the 10 voting tickets.
    """
    entries = load_probabilities(product, prob_dir)
    votes = {v["draw_id"]: v for v in vote_history(entries, df, game)}
    shown = [e for e in entries if not since or e["date"] >= since]
    names = {key: name for key, name, _ in default_strategies(42, None)}
    names["ml_multi"] = "ML đa nguồn (sản phẩm khác + lịch quay)"
    names.update(METHOD_LABELS)
    draws = {str(r.id): r for r in df.itertuples(index=False)}
    out = []
    for entry in shown:
        draw = draws.get(entry["draw_id"])
        vote = {k: v for k, v in votes[entry["draw_id"]].items() if k not in ("draw_id", "date", "source", "tickets")}
        out.append(
            {
                **entry,
                "main": list(draw.result) if draw is not None else None,
                "bonus": (
                    int(draw.bonus) if draw is not None and draw.bonus is not None and not pd.isna(draw.bonus) else None
                ),
                "drawn_date": str(draw.date) if draw is not None else None,
                "vote": vote,
            }
        )
    keys = []
    for entry in shown:
        for key in entry["probs"]:
            if key not in keys:
                keys.append(key)
    return {
        "title": game.title,
        "pick": game.pick,
        "range": [game.min_val, game.max_val],
        "has_bonus": game.has_bonus,
        "base": game.pick / game.pool,
        "methods": [{"key": k, "name": names.get(k, k), "code": METHOD_CODES.get(k, k)} for k in keys],
        "voting": {
            "select": VOTE_SELECT,
            "numbers": VOTE_NUMBERS,
            "vote_tickets": VOTE_TICKETS,
            "method_tickets": BEST_METHOD_TICKETS,
            "voters": voting_keys(keys),
        },
        "entries": out,
        "evaluation": evaluate(shown, df, game),
        "vote_summary": summarise_votes(list(votes.values()), game, since),
    }


# ---------------------------------------------------------------------------
# Voting: 10 suggested tickets built from the probability table
# ---------------------------------------------------------------------------

METHOD_CODES = {
    "random": "NGN",
    "hot": "SNG",
    "cold": "SLH",
    "long_absence": "LCV",
    "not_repeat": "TSR",
    "pattern": "MKC",
    "exp_decay": "SGM",
    "pair": "CSO",
    "markov": "MKV",
    "positional": "TVT",
    "ml_logistic": "MLR",
    "ml_gbm": "MLG",
    "ml_multi": "MLD",
    "consensus": "DTH",
    TOP_ROI_KEY: "T5R",
    ML_AVG_KEY: "TB3",
}
# composite columns: shown in the table, but neither averaged nor voting (they would double-count)
COMPOSITE_KEYS = (TOP_ROI_KEY, ML_AVG_KEY)
VOTE_KEY = "picks_vote10"
VOTE_SELECT = 7
VOTE_NUMBERS = 8
VOTE_TICKETS = 5
BEST_METHOD_TICKETS = 5


def voting_keys(keys: Sequence[str]) -> List[str]:
    """Methods that vote: every method except the uniform baseline and the composite columns."""
    return [k for k in keys if k != "random" and k not in COMPOSITE_KEYS]


def average_probabilities(probs: Dict[str, Sequence[float]]) -> np.ndarray:
    """'TB các phương pháp': mean over every method except the composite columns (random included)."""
    rows = [probs[k] for k in probs if k not in COMPOSITE_KEYS]
    return np.mean(rows, axis=0)


def top_numbers(vec: Sequence[float], game: GameSpec, n: int) -> List[int]:
    """The ``n`` numbers with the highest probability (ties: smaller number first)."""
    order = sorted(range(len(vec)), key=lambda i: (-vec[i], i))
    return [game.min_val + i for i in order[:n]]


def draw_auc(vec: Sequence[float], drawn: Sequence[int], game: GameSpec) -> float:
    """Mann-Whitney AUC of one draw: chance that a drawn number got a higher probability than a non-drawn one."""
    drawn_idx = {n - game.min_val for n in drawn}
    pos = [vec[i] for i in drawn_idx]
    neg = [vec[i] for i in range(len(vec)) if i not in drawn_idx]
    wins = sum((p > q) + 0.5 * (p == q) for p in pos for q in neg)
    return wins / (len(pos) * len(neg)) if pos and neg else 0.5


def rank_methods(prior_aucs: Dict[str, List[float]], keys: Sequence[str]) -> List[str]:
    """Methods ordered by their mean per-draw AUC on earlier draws (no history: table order)."""
    order = {k: i for i, k in enumerate(keys)}
    return sorted(keys, key=lambda k: (-(np.mean(prior_aucs[k]) if prior_aucs.get(k) else 0.5), order[k]))


def vote_picks(probs: Dict[str, Sequence[float]], ranking: Sequence[str], game: GameSpec) -> dict:
    """10 suggested tickets from one draw's probability table.

    * every voting method picks its ``VOTE_SELECT`` (7) most probable numbers;
    * the ``VOTE_NUMBERS`` (8) numbers picked by most methods are kept (ties: higher average);
    * ``VOTE_TICKETS`` (5) tickets: the 6-of-8 combinations with the most votes (then average);
    * ``BEST_METHOD_TICKETS`` (5) tickets: the 6 most probable numbers of each of the best methods in
      ``ranking`` (skipping a ticket that is already suggested).
    """
    voters = voting_keys(list(probs))
    avg = average_probabilities(probs)
    chosen_by: Dict[int, List[str]] = {}
    for key in voters:
        for n in top_numbers(probs[key], game, VOTE_SELECT):
            chosen_by.setdefault(n, []).append(METHOD_CODES.get(key, key.upper()[:3]))
    votes = {n: len(codes) for n, codes in chosen_by.items()}
    candidates = sorted(
        range(game.min_val, game.max_val + 1), key=lambda n: (-votes.get(n, 0), -avg[n - game.min_val], n)
    )
    selected = sorted(candidates[:VOTE_NUMBERS])

    def combo_score(combo):
        return (-sum(votes.get(n, 0) for n in combo), -sum(avg[n - game.min_val] for n in combo), combo)

    vote_tickets = [list(c) for c in sorted(combinations(selected, game.pick), key=combo_score)[:VOTE_TICKETS]]
    method_tickets, seen = [], {tuple(t) for t in vote_tickets}
    for key in ranking:
        if len(method_tickets) == BEST_METHOD_TICKETS:
            break
        ticket = sorted(top_numbers(probs[key], game, game.pick))
        if tuple(ticket) in seen:
            continue
        seen.add(tuple(ticket))
        method_tickets.append({"key": key, "code": METHOD_CODES.get(key, key), "ticket": ticket})
    return {
        "chosen_by": {str(n): codes for n, codes in sorted(chosen_by.items())},
        "selected": selected,
        "vote_tickets": vote_tickets,
        "method_tickets": method_tickets,
        "best_methods": list(ranking[:BEST_METHOD_TICKETS]),
        "tickets": vote_tickets + [m["ticket"] for m in method_tickets],
    }


def vote_history(entries: Sequence[dict], df: pd.DataFrame, game: GameSpec) -> List[dict]:
    """Voting suggestion for every recorded draw, each ranked only with draws before it, plus results."""
    draws = {str(r.id): r for r in df.itertuples(index=False)}
    prior_aucs: Dict[str, List[float]] = {}
    out = []
    for entry in sorted(entries, key=lambda e: int(e["draw_id"])):
        probs = {k: unpack(v) for k, v in entry["probs"].items()}
        ranking = rank_methods(prior_aucs, voting_keys(list(probs)))
        picks = vote_picks(probs, ranking, game)
        draw = draws.get(entry["draw_id"])
        row = {"draw_id": entry["draw_id"], "date": entry["date"], "source": entry.get("source"), **picks}
        if draw is not None:
            result = list(draw.result) + (
                [int(draw.bonus)] if draw.bonus is not None and not pd.isna(draw.bonus) else []
            )
            outcomes = [game.score(t, result) for t in picks["tickets"]]
            row["result"] = {
                "main": list(draw.result),
                "matches": [m for m, _, _ in outcomes],
                "tiers": [t.key if t else None for _, _, t in outcomes],
                "gain": sum(t.value for _, _, t in outcomes if t),
                "selected_hits": len(set(picks["selected"]) & set(draw.result)),
            }
            for key in voting_keys(list(probs)):  # only after scoring: the ranking for later draws
                prior_aucs.setdefault(key, []).append(draw_auc(probs[key], list(draw.result), game))
        out.append(row)
    return out


def summarise_votes(history: Sequence[dict], game: GameSpec, since: Optional[str] = None) -> dict:
    """Totals of the 10 voting tickets (and of each half) over the validated draws since ``since``.

    Tickets of one draw share numbers, so they are not independent: ``z`` compares the per-draw mean
    matches with chance using their spread across draws (``z_naive`` treats every ticket as independent).
    """
    scored = [h for h in history if "result" in h and (not since or h["date"] >= since)]
    expected = game.expected_matches()
    pmf = game.match_probabilities()
    var = sum((k - expected) ** 2 * p for k, p in enumerate(pmf))

    values = {t.key: t.value for t in game.tiers}

    def clustered_z(per_draw):
        d = len(per_draw)
        if d < 2:
            return 0.0
        mean = sum(per_draw) / d
        sd = math.sqrt(sum((x - mean) ** 2 for x in per_draw) / (d - 1))
        return (mean - expected) / (sd / math.sqrt(d)) if sd else 0.0

    def part(lo, hi):
        matches = [m for h in scored for m in h["result"]["matches"][lo:hi]]
        tiers = [t for h in scored for t in h["result"]["tiers"][lo:hi] if t]
        per_draw = [
            sum(h["result"]["matches"][lo:hi]) / len(h["result"]["matches"][lo:hi])
            for h in scored
            if h["result"]["matches"][lo:hi]
        ]
        n = len(matches)
        avg = sum(matches) / n if n else 0.0
        z = clustered_z(per_draw)
        z_naive = (avg - expected) / math.sqrt(var / n) if n else 0.0
        gain = sum(values[t] for t in tiers)
        cost = n * game.ticket_price
        counts: Dict[str, int] = {}
        for t in tiers:
            counts[t] = counts.get(t, 0) + 1
        return {
            "tickets": n,
            "avg_matches": avg,
            "z": z,
            "p_value": math.erfc(abs(z) / math.sqrt(2)),
            "z_naive": z_naive,
            "winners": len(tiers),
            "tiers": counts,
            "cost": cost,
            "gain": gain,
            "roi": (gain - cost) / cost * 100 if cost else 0.0,
        }

    total_gain = sum(h["result"]["gain"] for h in scored)
    cost = sum(len(h["tickets"]) for h in scored) * game.ticket_price
    # hits of the 8 selected numbers are hypergeometric: 8 of the pool, 6 drawn
    k, pool = VOTE_NUMBERS, game.pool
    sel_mean = k * game.pick / pool
    sel_var = sel_mean * (pool - game.pick) / pool * (pool - k) / (pool - 1)
    sel_hits = sum(h["result"]["selected_hits"] for h in scored) / len(scored) if scored else 0.0
    sel_z = (sel_hits - sel_mean) / math.sqrt(sel_var / len(scored)) if scored else 0.0
    return {
        "since": since,
        "n_draws": len(scored),
        "cost": cost,
        "gain": total_gain,
        "roi": (total_gain - cost) / cost * 100 if cost else 0.0,
        "expected_avg_matches": expected,
        "all": part(0, VOTE_TICKETS + BEST_METHOD_TICKETS),
        "vote": part(0, VOTE_TICKETS),
        "methods": part(VOTE_TICKETS, VOTE_TICKETS + BEST_METHOD_TICKETS),
        "selected_hits": sel_hits,
        "expected_selected_hits": sel_mean,
        "selected_z": sel_z,
        "selected_p_value": math.erfc(abs(sel_z) / math.sqrt(2)),
    }
