# Vietlott Power 655 Prediction Summary

> **Generated**: 2026-11-02 15:02:05
>
> This document contains machine learning predictions for Vietnamese lottery data.
> This is an experimental module for educational purposes only.

## Strategy Performance Comparison

> Sorted by ROI (best → worst).  All strategies backtested with **30 tickets/draw**.
> Note: All ROIs are deeply negative — lottery odds make profit impossible at scale.
> The comparison shows *which strategy loses the least*, not which one is profitable.

| Rank | Strategy | Total Cost (VND) | Total Gain (VND) | Net Profit (VND) | ROI |
|------|----------|-----------------|-----------------|-----------------|-----|
| 1 | Exponential Decay Strategy | 425,400,000 | 81,550,000 | -343,850,000 | -80.83% |
| 2 | Pattern Strategy | 425,400,000 | 78,650,000 | -346,750,000 | -81.51% |
| 3 | Not Repeat Strategy | 425,400,000 | 45,150,000 | -380,250,000 | -89.39% |
| 4 | Long Absence Strategy | 425,400,000 | 44,600,000 | -380,800,000 | -89.52% |
| 5 | Hot Numbers Strategy | 425,400,000 | 42,650,000 | -382,750,000 | -89.97% |
| 6 | Pair Frequency Strategy | 425,400,000 | 41,350,000 | -384,050,000 | -90.28% |
| 7 | Cold Numbers Strategy | 425,400,000 | 40,050,000 | -385,350,000 | -90.59% |
| 8 | Markov Chain Strategy | 425,400,000 | 39,300,000 | -386,100,000 | -90.76% |
| 9 | Random Strategy | 425,400,000 | 39,100,000 | -386,300,000 | -90.81% |


## Strategy Descriptions

### Random Strategy

**How it works**: Generates tickets by shuffling all numbers in the valid range and picking the first `number_predict` entries.  Every number has an equal chance of being selected; no historical data is used.

**Use case**: Serves as an unbiased performance baseline.  Any strategy that cannot beat random selection over a large backtest offers no predictive value.

### Long Absence Strategy

**How it works**: For each draw date, looks back at all past draws and records the last date each number appeared.  Numbers are ranked by how many days have elapsed since they last appeared (numbers that have *never* appeared rank highest). A configurable pool of the `top_n` most-absent numbers is assembled, and `number_predict` numbers are randomly sampled from that pool.

**Key parameter**: `top_n` (default 10) – larger pool → more randomness; smaller pool → stronger bias toward the longest-absent numbers.

**Use case**: Captures the intuition that numbers that have been *overdue* for a long time are somehow more likely to appear.  (Note: for a fair lottery this intuition is mathematically incorrect, but the strategy is included for empirical comparison.)

### Pattern Strategy

**How it works**: Analyses two structural properties of historical draws in a rolling `lookback_days` window:

1. **Spacing patterns** – gaps between consecutive sorted numbers in a ticket.  The most common gaps are used to generate the next number by applying a sampled gap to the previously chosen number.
2. **Range distribution** – the number range 1–55 is split into five equal sub-ranges.  The historical fraction of draws falling in each sub-range is used as a probability weight for choosing the first number.

A `pattern_weight` fraction of the ticket is filled with pattern-derived numbers; the remainder is filled randomly.

**Key parameters**: `lookback_days` (default 180), `pattern_weight` (default 0.6).

### Hot Numbers Strategy

**How it works**: Counts how many times each number appeared over the last `lookback_days` days.  Numbers are sorted from most-frequent to least-frequent.  A weighted pool is built where each number is repeated proportionally to its frequency, then numbers are drawn without replacement from that pool.

A `selection_weight` fraction of the ticket is filled from the frequency-weighted pool; the rest is filled uniformly at random.

**Key parameters**: `lookback_days` (default 365), `selection_weight` (default 0.7).

**Use case**: Tests whether recently hot numbers continue to appear at above-average rates.

### Cold Numbers Strategy

**How it works**: Identical to Hot Numbers Strategy but ranks numbers in the *reverse* order (least frequent first).  The weighted pool gives higher weight to numbers that have appeared fewer times in the lookback window.

**Key parameters**: `lookback_days` (default 365), `selection_weight` (default 0.7).

**Use case**: Tests the complementary hypothesis that rarely-drawn numbers are more likely to appear (mean-reversion / gambler's fallacy).

### Not Repeat Strategy

**How it works**: Collects all numbers that appeared in *any* draw within the last `lookback_days` days.  Whenever enough *non-recent* numbers exist to fill a full ticket they are sampled uniformly.  When the pool of non-recent numbers is too small, remaining slots are filled using an `avoid_weight` probability to decide whether to pick from recent numbers or from the full range.

**Key parameters**: `lookback_days` (default 30), `avoid_weight` (default 0.8).

**Use case**: Models the idea that numbers drawn recently are *less* likely to repeat in the very next draw.

### Exponential Decay Strategy

**How it works**: Every historical draw contributes a score to each number it contained, but the contribution decays exponentially with age: ``weight = exp(-ln(2) × days_ago / half_life_days)``.  Draws from yesterday contribute much more than draws from a year ago.  Numbers are then selected from a pool weighted by their accumulated scores.

Unlike Hot/Cold Numbers Strategy there is **no hard window cutoff** — all history is used, with very old draws contributing negligibly.  The smooth decay avoids abrupt weight changes when a draw ages past a window boundary.

**Key parameters**: `half_life_days` (default 90), `hot` (default True), `selection_weight` (default 0.8).

### Pair Frequency Strategy

**How it works**: Builds a co-occurrence matrix from historical draws: ``cooccurrence[a][b]`` counts draws where numbers ``a`` and ``b`` both appeared.  Tickets are assembled iteratively:

1. The first number is sampled proportional to individual draw frequency.
2. Each subsequent number is sampled proportional to its **average co-occurrence score** with the numbers already selected.

This produces clusters of numbers that historically appear together, exploiting second-order correlations that all single-number strategies ignore.

**Key parameter**: `lookback_days` (default 365).

### Markov Chain Strategy

**How it works**: Models **first-order sequential dependencies** between consecutive draws — a dimension completely ignored by every other strategy.

A transition matrix ``T[a][b]`` is built from the lookback window: ``T[a][b]`` counts the number of times number ``a`` appeared in draw ``t`` **and** number ``b`` appeared in the *next* draw ``t+1``.  This captures cross-draw temporal correlations.

To predict for date ``d``:

1. Identify the most-recent draw before ``d`` — this is the **Markov state**.
2. For each candidate number ``n``, compute an aggregate score by summing ``T[s][n]`` over every number ``s`` in the state draw.
3. Sample ``number_predict`` numbers without replacement, weighted by (score + Laplace smoothing) to retain a non-zero chance for all numbers.

**Key parameters**: `lookback_days` (default 365), `smoothing` (default 0.5).

**Why this is novel**: Unlike Pair Frequency Strategy (which counts numbers that appear *together in the same draw*), Markov Chain counts numbers that appeared in *successive draws*.  If any temporal autocorrelation exists in the physical lottery mechanism, this strategy is best positioned to exploit it.


## Usage Examples

The strategies can be used independently outside this generator script.
Below are minimal runnable examples using Power 6/55 data.

### Install & load data

```python
import polars as pl
from vietlott.config.products import get_config

df_pl = pl.read_ndjson(get_config("power_655").raw_path)
df_pl = df_pl.with_columns(pl.col("date").str.to_date(strict=False))
df_pd = df_pl.to_pandas()
```

### Random baseline

```python
from machine_learning.strategies import RandomModel

model = RandomModel(df_pd, time_predict=5)
model.backtest()
model.evaluate()
cost, gain, profit = model.revenue()
print(f"ROI: {profit / cost * 100:.2f}%")
```

### Hot Numbers (frequency-based)

```python
from machine_learning.strategies import HotNumbersStrategy

model = HotNumbersStrategy(df_pd, time_predict=5, lookback_days=180, selection_weight=0.8)
model.backtest()
model.evaluate()
# Predict for a specific date
from datetime import date
print(model.predict(date(2025, 6, 1)))
```

### Markov Chain (sequential dependency)

```python
from machine_learning.strategies import MarkovChainStrategy

model = MarkovChainStrategy(df_pd, time_predict=5, lookback_days=365, smoothing=0.5)
model.backtest()
model.evaluate()
cost, gain, profit = model.revenue()
print(f"ROI: {profit / cost * 100:.2f}%")
```

### Backtest with a date range

```python
from machine_learning.strategies import PairFrequencyStrategy
from datetime import date

model = PairFrequencyStrategy(df_pd, time_predict=10, lookback_days=365)
# Only evaluate predictions for 2024 draws; full history is still used for lookups
model.backtest(date_from=date(2024, 1, 1), date_to=date(2024, 12, 31))
model.evaluate()
cost, gain, profit = model.revenue()
print(f"2024 ROI: {profit / cost * 100:.2f}%")
```

### Compare strategies head-to-head

```python
from machine_learning.strategies import (
    RandomModel, MarkovChainStrategy, PairFrequencyStrategy,
)

strategies = {
    "Random":       RandomModel(df_pd, time_predict=20),
    "Markov":       MarkovChainStrategy(df_pd, time_predict=20),
    "PairFreq":     PairFrequencyStrategy(df_pd, time_predict=20),
}

for name, model in strategies.items():
    model.backtest()
    model.evaluate()
    cost, gain, profit = model.revenue()
    print(f"{name:20s}  ROI={profit / cost * 100:+.1f}%")
```


## Prediction Models

> **Disclaimer**: These are experimental models for educational purposes only. Lottery outcomes are random and cannot be predicted reliably.

### Random Strategy

#### Configuration
| Parameter | Value |
|-----------|-------|
| Strategy | Random Strategy |
| Tickets per day | 30 |
| Ticket price | 10,000 VND |
| Number range | 1 - 55 |
| Numbers to pick | 6 |

#### Backtest Period
| Metric | Value |
|--------|-------|
| Start date | 2017-08-01 00:00:00 |
| End date | 2026-10-31 00:00:00 |
| Total draws | 1,418 |
| Total predictions | 42,540 |

#### Financial Summary
| Metric | Value |
|--------|-------|
| Total cost | 425,400,000 VND |
| Total gain | 39,100,000 VND |
| Net profit/loss | -386,300,000 VND |
| ROI | -90.81% |

#### Match Distribution
  - **4 matches**: 24 times
  - **3 matches**: 542 times
  - **2 matches**: 4,694 times
  - **1 matches**: 16,718 times
  - **0 matches**: 20,562 times

#### Best Results (5+ matches)
No results with 5+ matches found.

### Long Absence Strategy

#### Configuration
| Parameter | Value |
|-----------|-------|
| Strategy | Long Absence Strategy |
| Tickets per day | 30 |
| Ticket price | 10,000 VND |
| Number range | 1 - 55 |
| Numbers to pick | 6 |

#### Backtest Period
| Metric | Value |
|--------|-------|
| Start date | 2017-08-01 00:00:00 |
| End date | 2026-10-31 00:00:00 |
| Total draws | 1,418 |
| Total predictions | 42,540 |

#### Financial Summary
| Metric | Value |
|--------|-------|
| Total cost | 425,400,000 VND |
| Total gain | 44,600,000 VND |
| Net profit/loss | -380,800,000 VND |
| ROI | -89.52% |

#### Match Distribution
  - **4 matches**: 31 times
  - **3 matches**: 582 times
  - **2 matches**: 4,677 times
  - **1 matches**: 16,966 times
  - **0 matches**: 20,284 times

#### Best Results (5+ matches)
No results with 5+ matches found.

### Pattern Strategy

#### Configuration
| Parameter | Value |
|-----------|-------|
| Strategy | Pattern Strategy |
| Tickets per day | 30 |
| Ticket price | 10,000 VND |
| Number range | 1 - 55 |
| Numbers to pick | 6 |

#### Backtest Period
| Metric | Value |
|--------|-------|
| Start date | 2017-08-01 00:00:00 |
| End date | 2026-10-31 00:00:00 |
| Total draws | 1,418 |
| Total predictions | 42,540 |

#### Financial Summary
| Metric | Value |
|--------|-------|
| Total cost | 425,400,000 VND |
| Total gain | 78,650,000 VND |
| Net profit/loss | -346,750,000 VND |
| ROI | -81.51% |

#### Match Distribution
  - **5 matches**: 1 times
  - **4 matches**: 24 times
  - **3 matches**: 533 times
  - **2 matches**: 4,580 times
  - **1 matches**: 16,700 times
  - **0 matches**: 20,702 times

#### Best Results (5+ matches)
| date                | result                   | predicted                |   correct_num |
|:--------------------|:-------------------------|:-------------------------|--------------:|
| 2017-12-05 00:00:00 | [27, 38, 40, 42, 46, 55] | [27, 38, 40, 42, 46, 51] |             5 |

### Hot Numbers Strategy

#### Configuration
| Parameter | Value |
|-----------|-------|
| Strategy | Hot Numbers Strategy |
| Tickets per day | 30 |
| Ticket price | 10,000 VND |
| Number range | 1 - 55 |
| Numbers to pick | 6 |

#### Backtest Period
| Metric | Value |
|--------|-------|
| Start date | 2017-08-01 00:00:00 |
| End date | 2026-10-31 00:00:00 |
| Total draws | 1,418 |
| Total predictions | 42,540 |

#### Financial Summary
| Metric | Value |
|--------|-------|
| Total cost | 425,400,000 VND |
| Total gain | 42,650,000 VND |
| Net profit/loss | -382,750,000 VND |
| ROI | -89.97% |

#### Match Distribution
  - **4 matches**: 27 times
  - **3 matches**: 583 times
  - **2 matches**: 4,643 times
  - **1 matches**: 16,843 times
  - **0 matches**: 20,444 times

#### Best Results (5+ matches)
No results with 5+ matches found.

### Cold Numbers Strategy

#### Configuration
| Parameter | Value |
|-----------|-------|
| Strategy | Cold Numbers Strategy |
| Tickets per day | 30 |
| Ticket price | 10,000 VND |
| Number range | 1 - 55 |
| Numbers to pick | 6 |

#### Backtest Period
| Metric | Value |
|--------|-------|
| Start date | 2017-08-01 00:00:00 |
| End date | 2026-10-31 00:00:00 |
| Total draws | 1,418 |
| Total predictions | 42,540 |

#### Financial Summary
| Metric | Value |
|--------|-------|
| Total cost | 425,400,000 VND |
| Total gain | 40,050,000 VND |
| Net profit/loss | -385,350,000 VND |
| ROI | -90.59% |

#### Match Distribution
  - **4 matches**: 25 times
  - **3 matches**: 551 times
  - **2 matches**: 4,645 times
  - **1 matches**: 16,789 times
  - **0 matches**: 20,530 times

#### Best Results (5+ matches)
No results with 5+ matches found.

### Not Repeat Strategy

#### Configuration
| Parameter | Value |
|-----------|-------|
| Strategy | Not Repeat Strategy |
| Tickets per day | 30 |
| Ticket price | 10,000 VND |
| Number range | 1 - 55 |
| Numbers to pick | 6 |

#### Backtest Period
| Metric | Value |
|--------|-------|
| Start date | 2017-08-01 00:00:00 |
| End date | 2026-10-31 00:00:00 |
| Total draws | 1,418 |
| Total predictions | 42,540 |

#### Financial Summary
| Metric | Value |
|--------|-------|
| Total cost | 425,400,000 VND |
| Total gain | 45,150,000 VND |
| Net profit/loss | -380,250,000 VND |
| ROI | -89.39% |

#### Match Distribution
  - **4 matches**: 29 times
  - **3 matches**: 613 times
  - **2 matches**: 4,814 times
  - **1 matches**: 16,762 times
  - **0 matches**: 20,322 times

#### Best Results (5+ matches)
No results with 5+ matches found.

### Exponential Decay Strategy

#### Configuration
| Parameter | Value |
|-----------|-------|
| Strategy | Exponential Decay Strategy |
| Tickets per day | 30 |
| Ticket price | 10,000 VND |
| Number range | 1 - 55 |
| Numbers to pick | 6 |

#### Backtest Period
| Metric | Value |
|--------|-------|
| Start date | 2017-08-01 00:00:00 |
| End date | 2026-10-31 00:00:00 |
| Total draws | 1,418 |
| Total predictions | 42,540 |

#### Financial Summary
| Metric | Value |
|--------|-------|
| Total cost | 425,400,000 VND |
| Total gain | 81,550,000 VND |
| Net profit/loss | -343,850,000 VND |
| ROI | -80.83% |

#### Match Distribution
  - **5 matches**: 1 times
  - **4 matches**: 25 times
  - **3 matches**: 581 times
  - **2 matches**: 4,720 times
  - **1 matches**: 16,708 times
  - **0 matches**: 20,505 times

#### Best Results (5+ matches)
| date                | result                 | predicted              |   correct_num |
|:--------------------|:-----------------------|:-----------------------|--------------:|
| 2021-06-22 00:00:00 | [3, 9, 32, 33, 41, 43] | [3, 9, 17, 33, 41, 43] |             5 |

### Pair Frequency Strategy

#### Configuration
| Parameter | Value |
|-----------|-------|
| Strategy | Pair Frequency Strategy |
| Tickets per day | 30 |
| Ticket price | 10,000 VND |
| Number range | 1 - 55 |
| Numbers to pick | 6 |

#### Backtest Period
| Metric | Value |
|--------|-------|
| Start date | 2017-08-01 00:00:00 |
| End date | 2026-10-31 00:00:00 |
| Total draws | 1,418 |
| Total predictions | 42,540 |

#### Financial Summary
| Metric | Value |
|--------|-------|
| Total cost | 425,400,000 VND |
| Total gain | 41,350,000 VND |
| Net profit/loss | -384,050,000 VND |
| ROI | -90.28% |

#### Match Distribution
  - **4 matches**: 26 times
  - **3 matches**: 567 times
  - **2 matches**: 4,604 times
  - **1 matches**: 16,687 times
  - **0 matches**: 20,656 times

#### Best Results (5+ matches)
No results with 5+ matches found.

### Markov Chain Strategy

#### Configuration
| Parameter | Value |
|-----------|-------|
| Strategy | Markov Chain Strategy |
| Tickets per day | 30 |
| Ticket price | 10,000 VND |
| Number range | 1 - 55 |
| Numbers to pick | 6 |

#### Backtest Period
| Metric | Value |
|--------|-------|
| Start date | 2017-08-01 00:00:00 |
| End date | 2026-10-31 00:00:00 |
| Total draws | 1,418 |
| Total predictions | 42,540 |

#### Financial Summary
| Metric | Value |
|--------|-------|
| Total cost | 425,400,000 VND |
| Total gain | 39,300,000 VND |
| Net profit/loss | -386,100,000 VND |
| ROI | -90.76% |

#### Match Distribution
  - **4 matches**: 22 times
  - **3 matches**: 566 times
  - **2 matches**: 4,604 times
  - **1 matches**: 16,732 times
  - **0 matches**: 20,616 times

#### Best Results (5+ matches)
No results with 5+ matches found.




---

## Disclaimer

This prediction summary is for educational and research purposes only. Lottery outcomes are random and cannot be reliably predicted. Never gamble more than you can afford to lose.
