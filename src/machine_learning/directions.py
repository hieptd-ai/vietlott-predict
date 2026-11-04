"""
Validation of every draw: which *direction* relates most to the winning numbers?

A direction is any score that ranks the numbers of the pool **before** a draw:

* a feature of the earlier draws: gap since the last appearance, frequency over 10/30/100 draws, repeat,
  neighbour or tail of the previous draw, pairs with the previous draw, odd/even, low/high, the bonus of the
  previous draw, the numbers just drawn by another product;
* the per-number probability of a prediction method, recorded before the draw (``predictions/probabilities``).

Once the result is known each direction gets the AUC of the drawn numbers: 0.5 = unrelated, 1 = the drawn
numbers were ranked first, 0 = ranked last (then the *reverse* direction is the related one, e.g. "cold"
instead of "hot"). The most related direction of a draw is the one furthest from 0.5.

About 30 directions are scored on every draw, so the best of them always looks related. Every draw is
therefore compared with random results (``p_best``: share of random 6-number results whose best direction is
at least as related), and following the best direction of the earlier draws is replayed draw by draw to check
whether a direction found at validation keeps working on the next draw. Nothing here uses a result before it
is drawn: features only read earlier draws, method probabilities were recorded before the draw, and the
direction followed for a draw is chosen from earlier validations only.

Run for 2026 (writes nothing, prints the summary)::

    uv run --extra ml python src/machine_learning/directions.py --since 2026-01-01
"""

import math
from bisect import bisect_left
from typing import Dict, Iterator, List, Optional, Sequence, Tuple

import click
import numpy as np
import pandas as pd
from scipy.stats import rankdata

from machine_learning.analysis import SOURCE_TITLES, Sources, load_draws, load_sources
from machine_learning.games import GAMES, GameSpec
from machine_learning.probabilities import METHOD_CODES, load_probabilities, method_names, unpack

WARMUP = "2025-07-01"
NULL_SETS = 1000
TOP_SHOWN = 3
FOLLOW_WINDOWS = (1, 10, 30, 0)  # 0 = every earlier draw
METHOD_PREFIX = "m:"
CONTROL_KEY = METHOD_PREFIX + "random"

# key, name, reverse name, binary (a yes/no property of the number)
FEATURES: Tuple[Tuple[str, str, str, bool], ...] = (
    ("gap", "Lâu chưa về", "Mới về gần đây", False),
    ("freq10", "Nóng 10 kỳ", "Lạnh 10 kỳ", False),
    ("freq30", "Nóng 30 kỳ", "Lạnh 30 kỳ", False),
    ("freq100", "Nóng 100 kỳ", "Lạnh 100 kỳ", False),
    ("freq_all", "Nóng cả lịch sử", "Lạnh cả lịch sử", False),
    ("trend", "Đang nóng lên (10 so với 100 kỳ)", "Đang nguội đi (10 so với 100 kỳ)", False),
    ("repeat", "Lặp số kỳ trước", "Không lặp số kỳ trước", True),
    ("recent3", "Ra nhiều trong 3 kỳ gần nhất", "Vắng 3 kỳ gần nhất", False),
    ("neighbor", "Kề số kỳ trước (±1)", "Không kề số kỳ trước", True),
    ("tail", "Cùng đuôi số kỳ trước", "Khác đuôi số kỳ trước", True),
    ("pair", "Hay đi cùng số kỳ trước", "Ít đi cùng số kỳ trước", False),
    ("odd", "Số lẻ", "Số chẵn", True),
    ("high", "Nửa lớn", "Nửa nhỏ", True),
)
BONUS_FEATURE = ("bonus_prev", "Số đặc biệt kỳ trước", "Không phải số ĐB kỳ trước", True)


def direction_specs(game: GameSpec, sources: Optional[Sources]) -> List[dict]:
    """Every direction of ``game``: key, name, reverse name, kind (feature / method / control), binary."""
    specs = [{"key": k, "name": n, "reverse": r, "kind": "feature", "binary": b} for k, n, r, b in FEATURES]
    if game.has_bonus:
        k, n, r, b = BONUS_FEATURE
        specs.append({"key": k, "name": n, "reverse": r, "kind": "feature", "binary": b})
    for key in sorted(sources or {}):
        if key == game.key:
            continue
        title = SOURCE_TITLES.get(key, key)
        specs.append(
            {
                "key": f"src:{key}",
                "name": f"Vừa ra ở {title}",
                "reverse": f"Không ra ở {title}",
                "kind": "feature",
                "binary": True,
            }
        )
    names = method_names()
    for key, code in METHOD_CODES.items():
        name = names.get(key, key)
        specs.append(
            {
                "key": METHOD_PREFIX + key,
                "name": f"{name} ({code})",
                "reverse": f"Ngược {name} ({code})",
                "kind": "control" if key == "random" else "method",
                "binary": False,
                "code": code,
            }
        )
    return specs


def feature_scores(
    df: pd.DataFrame, game: GameSpec, sources: Optional[Sources], start: int = 1
) -> Iterator[Tuple[int, Dict[str, np.ndarray]]]:
    """``(i, scores)`` for every draw ``i >= start`` of ``df``; scores only read draws ``0 .. i-1``."""
    n, lo = game.pool, game.min_val
    numbers = np.arange(lo, game.max_val + 1)
    results = [list(r) for r in df["result"]]
    bonuses = list(df["bonus"])
    dates = list(df["date"])
    occ = np.zeros((len(df), n), dtype=float)
    for i, r in enumerate(results):
        occ[i, [x - lo for x in r]] = 1.0
    cum = np.vstack([np.zeros(n), np.cumsum(occ, axis=0)])  # cum[i] = counts over draws < i
    others = {
        key: ([pd.Timestamp(d).date() for d in s["date"]], [list(r) for r in s["result"]])
        for key, s in (sources or {}).items()
        if key != game.key
    }
    pairs = np.zeros((n, n))
    last_seen = np.full(n, -1)
    for i in range(len(df)):
        if i >= max(start, 1):
            prev = np.array([x - lo for x in results[i - 1]])
            prev_set = set(results[i - 1])
            freq = {w: cum[i] - cum[max(0, i - w)] for w in (3, 10, 30, 100)}
            counts = cum[i]
            expected_pair = np.outer(counts, counts) / i
            with np.errstate(divide="ignore", invalid="ignore"):
                lift = np.where(expected_pair > 0, pairs / expected_pair, 0.0)
            lift[np.arange(n), np.arange(n)] = 0.0
            pair_score = lift[:, prev].sum(axis=1) / len(prev)
            prev_tails = {x % 10 for x in prev_set}
            scores = {
                "gap": np.where(last_seen >= 0, i - last_seen, i + 1).astype(float),
                "freq10": freq[10],
                "freq30": freq[30],
                "freq100": freq[100],
                "freq_all": counts.copy(),
                "trend": freq[10] / min(10, i) - freq[100] / min(100, i),
                "repeat": occ[i - 1].copy(),
                "recent3": freq[3],
                "neighbor": np.array(
                    [float(x not in prev_set and (x - 1 in prev_set or x + 1 in prev_set)) for x in numbers]
                ),
                "tail": np.array([float(x not in prev_set and x % 10 in prev_tails) for x in numbers]),
                "pair": pair_score,
                "odd": (numbers % 2 == 1).astype(float),
                "high": (numbers > (lo + game.max_val) / 2).astype(float),
            }
            if game.has_bonus:
                b = bonuses[i - 1]
                scores["bonus_prev"] = (numbers == int(b)).astype(float) if b is not None and not pd.isna(b) else None
            for key, (o_dates, o_results) in others.items():
                j = bisect_left(o_dates, dates[i]) - 1  # latest draw strictly before the draw date
                scores[f"src:{key}"] = np.isin(numbers, o_results[j]).astype(float) if j >= 0 else None
            yield i, {k: v for k, v in scores.items() if v is not None}
        idx = [x - lo for x in results[i]]
        for a in idx:
            for b in idx:
                if a != b:
                    pairs[a, b] += 1
        last_seen[idx] = i


def auc_table(
    scores: Dict[str, np.ndarray], drawn_idx: Sequence[int], rng: np.random.Generator, null_sets: int = NULL_SETS
) -> dict:
    """AUC of the drawn numbers for every direction, their null variance and the random-result benchmark.

    With ranks ``r`` (ties averaged) the AUC is linear in the rank sum of the drawn numbers, whose variance
    under a random result (``k`` of ``n`` without replacement) is ``k * var(r) * (n - k) / (n - 1)``.
    """
    keys = list(scores)
    drawn_idx = np.asarray(drawn_idx)
    k = len(drawn_idx)
    n = len(next(iter(scores.values())))
    ranks = np.vstack([rankdata(scores[key]) for key in keys])
    denom = k * (n - k)
    base = k * (k + 1) / 2
    auc = (ranks[:, drawn_idx].sum(axis=1) - base) / denom
    var = ranks.var(axis=1) * k * (n - k) / (n - 1) / denom**2
    sets = np.argsort(rng.random((null_sets, n)), axis=1)[:, :k]
    null_auc = (ranks[:, sets].sum(axis=2) - base) / denom
    null_best = np.abs(null_auc - 0.5).max(axis=0)
    strength = np.abs(auc - 0.5)
    best = float(strength.max())
    return {
        "auc": dict(zip(keys, auc.tolist())),
        "var": dict(zip(keys, var.tolist())),
        "strength": best,
        "null_best": float(null_best.mean()),
        "p_best": float((null_best >= best - 1e-12).mean()),
    }


def _signed_name(spec: dict, sign: int) -> str:
    return spec["name"] if sign > 0 else spec["reverse"]


def _top_ticket(score: np.ndarray, sign: int, game: GameSpec, rng: np.random.Generator) -> List[int]:
    order = np.lexsort((rng.random(len(score)), -sign * score))  # ties broken at random, not by number
    return sorted(int(i) + game.min_val for i in order[: game.pick])


def _best_entry(key: str, auc: float, spec: dict, hits: Optional[dict], game: GameSpec) -> dict:
    """One related direction of a draw, named and measured the way it points (AUC >= 0.5)."""
    sign = 1 if auc >= 0.5 else -1
    entry = {"key": key, "sign": sign, "auc": auc if sign > 0 else 1 - auc, "name": _signed_name(spec, sign)}
    if hits is not None:
        entry["hits"] = hits["hits"] if sign > 0 else game.pick - hits["hits"]
        entry["expected"] = hits["expected"] if sign > 0 else game.pick - hits["expected"]
    return entry


def _choose(prior: Sequence[dict], keys: Sequence[str]) -> Optional[Tuple[str, int]]:
    """Direction (and sign) furthest from 0.5 on average over ``prior`` validated draws."""
    best, best_key = -1.0, None
    for key in keys:
        values = [r["auc"][key] for r in prior if key in r["auc"]]
        if not values:
            continue
        mean = sum(values) / len(values)
        if abs(mean - 0.5) > best + 1e-12:
            best, best_key = abs(mean - 0.5), (key, 1 if mean >= 0.5 else -1)
    return best_key


def direction_history(
    df: pd.DataFrame,
    game: GameSpec,
    sources: Optional[Sources],
    prob_entries: Sequence[dict],
    since: str = WARMUP,
    null_sets: int = NULL_SETS,
) -> Tuple[List[dict], List[dict]]:
    """Validated directions of every draw from ``since`` (rows) and the direction specs.

    Each row also says which direction was followed (chosen from the earlier rows only) for every window of
    ``FOLLOW_WINDOWS`` and how its 6 top numbers matched.
    """
    specs = direction_specs(game, sources)
    by_key = {s["key"]: s for s in specs}
    probs = {e["draw_id"]: e for e in prob_entries}
    dates = [str(d) for d in df["date"]]
    start = next((i for i, d in enumerate(dates) if d >= since), len(df))
    rows: List[dict] = []
    for i, scores in feature_scores(df, game, sources, start):
        draw = df.iloc[i]
        entry = probs.get(str(draw["id"]))
        if entry:
            for key, packed in entry["probs"].items():
                if METHOD_PREFIX + key in by_key:
                    scores[METHOD_PREFIX + key] = np.asarray(unpack(packed))
        main = [int(x) for x in draw["result"]]
        drawn_idx = [x - game.min_val for x in main]
        rng = np.random.default_rng(int(draw["id"]))
        table = auc_table(scores, drawn_idx, rng, null_sets)
        ranked = sorted(table["auc"], key=lambda k: (-abs(table["auc"][k] - 0.5), k))
        hits = {
            key: {"hits": int(scores[key][drawn_idx].sum()), "expected": game.pick * float(scores[key].mean())}
            for key in scores
            if by_key[key]["binary"]
        }
        row = {
            "draw_id": str(draw["id"]),
            "date": dates[i],
            "main": main,
            "bonus": None if draw["bonus"] is None or pd.isna(draw["bonus"]) else int(draw["bonus"]),
            "methods": entry is not None,
            "auc": table["auc"],
            "var": table["var"],
            "hits": hits,
            "best": [
                _best_entry(key, table["auc"][key], by_key[key], hits.get(key), game) for key in ranked[:TOP_SHOWN]
            ],
            "strength": table["strength"],
            "null_best": table["null_best"],
            "p_best": table["p_best"],
            "follow": {},
        }
        for window in FOLLOW_WINDOWS:
            prior = rows[-window:] if window else rows
            choice = _choose(prior, list(scores))
            if choice is None:
                continue
            key, sign = choice
            ticket = _top_ticket(scores[key], sign, game, np.random.default_rng([int(draw["id"]), window]))
            signed_auc = table["auc"][key] if sign > 0 else 1 - table["auc"][key]
            row["follow"][str(window)] = {
                "key": key,
                "sign": sign,
                "name": _signed_name(by_key[key], sign),
                "auc": signed_auc,
                "var": table["var"][key],
                "ticket": ticket,
                "matches": len(set(ticket) & set(main)),
            }
        rows.append(row)
    return rows, specs


def _z(values: Sequence[float], variances: Sequence[float]) -> float:
    total_var = sum(variances)
    return (sum(v - 0.5 for v in values)) / math.sqrt(total_var) if total_var > 0 else 0.0


def _p(z: float) -> float:
    return math.erfc(abs(z) / math.sqrt(2))


def bonferroni_z(n_tests: int, alpha: float = 0.05) -> float:
    """Two-sided z threshold for ``n_tests`` comparisons (bisection on the normal tail)."""
    target, lo, hi = alpha / max(n_tests, 1), 0.0, 10.0
    for _ in range(60):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if _p(mid) > target else (lo, mid)
    return (lo + hi) / 2


def summarise_directions(rows: Sequence[dict], specs: Sequence[dict], game: GameSpec, since: str) -> dict:
    """Totals over the draws since ``since``: per direction, the best-of-draw benchmark and the follow replay."""
    shown = [r for r in rows if r["date"] >= since]
    per = []
    for spec in specs:
        key = spec["key"]
        values = [r["auc"][key] for r in shown if key in r["auc"]]
        if not values:
            continue
        variances = [r["var"][key] for r in shown if key in r["auc"]]
        z = _z(values, variances)
        mean = sum(values) / len(values)
        top1 = [r["best"][0]["sign"] for r in shown if r["best"] and r["best"][0]["key"] == key]
        item = {
            "key": key,
            "n": len(values),
            "mean_auc": mean,
            "z": z,
            "p_value": _p(z),
            "sign": 1 if mean >= 0.5 else -1,
            "name": _signed_name(spec, 1 if mean >= 0.5 else -1),
            "related_auc": max(mean, 1 - mean),
            "top1": len(top1),
            "top1_reverse": sum(1 for s in top1 if s < 0),
            "top3": sum(1 for r in shown if any(b["key"] == key for b in r["best"])),
        }
        if spec["binary"]:
            hit_rows = [r["hits"][key] for r in shown if key in r["hits"]]
            hits = sum(h["hits"] for h in hit_rows) / len(hit_rows)
            expected_hits = sum(h["expected"] for h in hit_rows) / len(hit_rows)
            item["hits"] = hits if item["sign"] > 0 else game.pick - hits
            item["expected_hits"] = expected_hits if item["sign"] > 0 else game.pick - expected_hits
        per.append(item)
    per.sort(key=lambda x: -abs(x["z"]))
    expected = game.expected_matches()
    pmf = game.match_probabilities()
    match_var = sum((k - expected) ** 2 * p for k, p in enumerate(pmf))
    follow = []
    for window in FOLLOW_WINDOWS:
        picks = [r["follow"][str(window)] for r in shown if str(window) in r["follow"]]
        if not picks:
            continue
        z = _z([f["auc"] for f in picks], [f["var"] for f in picks])
        matches = sum(f["matches"] for f in picks) / len(picks)
        mz = (matches - expected) / math.sqrt(match_var / len(picks))
        chosen: Dict[str, int] = {}
        for f in picks:
            chosen[f["name"]] = chosen.get(f["name"], 0) + 1
        follow.append(
            {
                "window": window,
                "n": len(picks),
                "mean_auc": sum(f["auc"] for f in picks) / len(picks),
                "z": z,
                "p_value": _p(z),
                "avg_matches": matches,
                "matches_z": mz,
                "matches_p": _p(mz),
                "chosen": sorted(chosen.items(), key=lambda x: -x[1])[:4],
            }
        )
    n_dirs = len(per)
    return {
        "since": since,
        "n_draws": len(shown),
        "n_directions": n_dirs,
        "bonferroni_z": bonferroni_z(n_dirs),
        "expected_matches": expected,
        "best": {
            "strength": sum(r["strength"] for r in shown) / len(shown) if shown else 0.0,
            "null_strength": sum(r["null_best"] for r in shown) / len(shown) if shown else 0.0,
            "significant": sum(1 for r in shown if r["p_best"] < 0.05),
            "mean_p": sum(r["p_best"] for r in shown) / len(shown) if shown else 0.0,
        },
        "directions": per,
        "follow": follow,
    }


def directions_payload(
    df: pd.DataFrame, game: GameSpec, sources: Optional[Sources], prob_entries: Sequence[dict], since: str
) -> dict:
    """Dashboard data: direction specs, the validated draws since ``since`` (newest last) and the summary."""
    rows, specs = direction_history(df, game, sources, prob_entries, since=min(since, WARMUP))
    shown = [r for r in rows if r["date"] >= since]
    draws = [
        {
            "draw_id": r["draw_id"],
            "date": r["date"],
            "main": r["main"],
            "bonus": r["bonus"],
            "auc": {k: round(v, 4) for k, v in r["auc"].items()},
            "hits": {k: v["hits"] for k, v in r["hits"].items()},
            "best": [{k: (round(v, 3) if isinstance(v, float) else v) for k, v in b.items()} for b in r["best"]],
            "strength": round(r["strength"], 4),
            "null_best": round(r["null_best"], 4),
            "p_best": round(r["p_best"], 4),
            "follow": {
                w: {k: (round(v, 4) if isinstance(v, float) else v) for k, v in f.items() if k != "var"}
                for w, f in r["follow"].items()
            },
        }
        for r in shown
    ]
    return {
        "specs": specs,
        "draws": draws,
        "summary": summarise_directions(rows, specs, game, since),
    }


def last_validation(
    df: pd.DataFrame, game: GameSpec, sources: Optional[Sources], prob_entries: Sequence[dict]
) -> Optional[dict]:
    """The directions of the latest drawn result only (for the validation step after each draw)."""
    if len(df) < 2:
        return None
    rows, _ = direction_history(df, game, sources, prob_entries, since=str(df["date"].iloc[-1]))
    if not rows:
        return None
    r = rows[-1]
    return {k: r[k] for k in ("draw_id", "date", "main", "bonus", "best", "strength", "null_best", "p_best")}


def describe_best(best: dict, pick: int = 6) -> str:
    """``Số lẻ (AUC 0,780; 5/6 số trúng thuộc nhóm này, kỳ vọng 3,1)`` text of one related direction."""
    text = f"{best['name']} (AUC {best['auc']:.3f}"
    if best.get("hits") is not None:
        text += f"; {best['hits']}/{pick} số trúng thuộc nhóm này, kỳ vọng {best['expected']:.1f}"
    return (text + ")").replace(".", ",")


@click.command()
@click.option("--since", default="2026-01-01", show_default=True)
@click.option("--product", "products", multiple=True, default=tuple(GAMES), show_default=True)
def main(since: str, products: Sequence[str]) -> None:
    """Print, for every draw since ``--since``, the direction most related to the winning numbers."""
    sources = load_sources()
    for key in products:
        game = GAMES[key]
        payload = directions_payload(load_draws(game), game, sources, load_probabilities(key), since)
        s = payload["summary"]
        click.echo(f"\n== {game.title}: {s['n_draws']} draws since {since}, {s['n_directions']} directions")
        for d in payload["draws"][-5:]:
            best = "; ".join(f"{b['name']} {b['auc']:.3f}" for b in d["best"])
            click.echo(f"  #{d['draw_id']} {d['date']} {d['main']}: {best} (p_best {d['p_best']:.3f})")
        b = s["best"]
        click.echo(
            f"  best direction per draw: |AUC-0.5| {b['strength']:.3f} vs random results {b['null_strength']:.3f}; "
            f"p_best < 0.05 in {b['significant']}/{s['n_draws']} draws"
        )
        for item in s["directions"][:8]:
            click.echo(
                f"  {item['name']:<45} mean AUC {item['mean_auc']:.3f} z {item['z']:+.2f} "
                f"top1 {item['top1']:>3} top3 {item['top3']:>3}"
            )
        click.echo(f"  Bonferroni |z| threshold: {s['bonferroni_z']:.2f}")
        for f in s["follow"]:
            click.echo(
                f"  follow best of last {f['window'] or 'all'}: AUC {f['mean_auc']:.3f} z {f['z']:+.2f}, "
                f"ticket {f['avg_matches']:.3f}/{s['expected_matches']:.3f} z {f['matches_z']:+.2f}"
            )


if __name__ == "__main__":
    main()
