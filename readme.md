# Vietlott Data

[![Go](https://img.shields.io/badge/go-1.27%2B-00ADD8.svg)](https://go.dev/)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Data Updated](https://img.shields.io/badge/data-daily%20updated-brightgreen.svg)](https://github.com/hieptd-ai/vietlott-predict/commits/main)
[![GitHub Pages](https://img.shields.io/badge/GitHub%20Pages-Deployed-blue)](https://hieptd-ai.github.io/vietlott-predict/)

> **Open Historical Vietlott Lottery Dataset — Free NDJSON Downloads, Daily Updates, Statistics & Go/Python Tools**
>
> Complete draw history crawled daily from [vietlott.vn](https://vietlott.vn/) for all seven official Vietlott games: Power 6/55, Mega 6/45, Power 5/35, Keno, Max 3D, Max 3D Pro, and Bingo18.

**Dữ liệu kết quả xổ số Vietlott đầy đủ, miễn phí, cập nhật hàng ngày** (Power 6/55, Mega 6/45, Power 5/35, Keno, Max 3D, Max 3D Pro, Bingo18) - open historical Vietlott draw results in NDJSON, from the first draw, MIT licensed. Raw files live in [data/](data/); see [llms.txt](https://hieptd-ai.github.io/vietlott-predict/llms.txt) and [Data Schema](https://hieptd-ai.github.io/vietlott-predict/data-schema/) for machine-readable and developer references.

## Links

- [Website (Vietnamese)](https://hieptd-ai.github.io/vietlott-predict/) & [English Portal (/en/)](https://hieptd-ai.github.io/vietlott-predict/en/) - Interactive dataset portal & statistics
- [Data Schema Reference](https://hieptd-ai.github.io/vietlott-predict/data-schema/) & [Python/Polars Examples](https://hieptd-ai.github.io/vietlott-predict/python-examples/)
- [Blog Post](https://open.substack.com/pub/vietvudanh/p/minh-a-tao-repo-vietlott-data-the) - About this project
- [Crawler Performance Benchmark](docs/BENCHMARK.md) - Speed & resource comparison: Go vs Python crawler

## Supported Lottery Products & Data Schema

| Product | Raw NDJSON File | Dedicated Page | Official Results | `result` Field Structure |
|---------|-----------------|----------------|------------------|--------------------------|
| **Power 6/55** | [data/power655.jsonl](data/power655.jsonl) | [/power-6-55/](https://hieptd-ai.github.io/vietlott-predict/power-6-55/) | [Vietlott 6/55](https://vietlott.vn/vi/trung-thuong/ket-qua-trung-thuong/655) | `int[7]`: 6 main numbers (1–55) + **1 bonus number** (`result[6]`) |
| **Mega 6/45** | [data/power645.jsonl](data/power645.jsonl) | [/mega-6-45/](https://hieptd-ai.github.io/vietlott-predict/mega-6-45/) | [Vietlott 6/45](https://vietlott.vn/vi/trung-thuong/ket-qua-trung-thuong/645) | `int[6]`: 6 winning numbers (1–45), **NO bonus number** |
| **Power 5/35** | [data/power535.jsonl](data/power535.jsonl) | [/power-5-35/](https://hieptd-ai.github.io/vietlott-predict/power-5-35/) | [Vietlott 5/35](https://vietlott.vn/vi/trung-thuong/ket-qua-trung-thuong/535) | `int[6]`: 5 main numbers (1–35) + **1 special number** (`result[5]`) |
| **Keno** | [data/keno.jsonl](data/keno.jsonl) | [/keno/](https://hieptd-ai.github.io/vietlott-predict/keno/) | [Vietlott Keno](https://vietlott.vn/vi/trung-thuong/ket-qua-trung-thuong/winning-number-keno) | `int[20]`: 20 numbers (1–80), plus `big_small` & `odd_even` |
| **Max 3D** | [data/3d.jsonl](data/3d.jsonl) | [/max-3d/](https://hieptd-ai.github.io/vietlott-predict/max-3d/) | [Vietlott Max 3D](https://vietlott.vn/vi/trung-thuong/ket-qua-trung-thuong/max-3d) | `object`: 4 prize tiers (`Giải Đặc biệt`, `Nhất`, `Nhì`, `ba`) -> 20 3-digit strings |
| **Max 3D Pro** | [data/3d_pro.jsonl](data/3d_pro.jsonl) | [/max-3d-pro/](https://hieptd-ai.github.io/vietlott-predict/max-3d-pro/) | [Vietlott Max 3D Pro](https://vietlott.vn/vi/trung-thuong/ket-qua-trung-thuong/max-3dpro) | `object`: 4 prize tiers -> 20 3-digit strings |
| **Bingo18** | [data/bingo18.jsonl](data/bingo18.jsonl) | [/bingo18/](https://hieptd-ai.github.io/vietlott-predict/bingo18/) | [Vietlott Bingo18](https://vietlott.vn/vi/trung-thuong/ket-qua-trung-thuong/winning-number-bingo18) | `int[3]`: 3 numbers (1–6), plus `total` (3–18) & `large_small` |


## Table of Contents

- [Links](#links)
- [Supported Lottery Products & Data Schema](#supported-lottery-products--data-schema)
- [Quick Python Usage Example](#quick-python-usage-example)
- [Predictions](#predictions)
- [Data Statistics](#data-statistics)
- [Power 6/55 Analysis](#power-655-analysis)
  - [Recent Results](#recent-results-last-10-draws)
  - [Number Frequency (All Time)](#number-frequency-all-time)
  - [Frequency Analysis by Period](#frequency-analysis-by-period)
  - [Top 10 Numbers by Days Since Last Appearance](#top-10-numbers-by-days-since-last-appearance)
  - [Days Since Last Appearance - All Numbers](#days-since-last-appearance---all-numbers)
- [How It Works](#how-it-works)
- [Installation & Usage](#installation--usage)
- [Citation & Attribution](#citation--attribution)
- [License](#license)

## Quick Python Usage Example

```python
import polars as pl

# Load Power 6/55 directly from raw NDJSON
df = pl.read_ndjson("https://raw.githubusercontent.com/hieptd-ai/vietlott-predict/main/data/power655.jsonl")
df = df.with_columns([
    pl.col("date").str.to_date(),
    pl.col("result").list.slice(0, 6).alias("main_numbers"),
    pl.col("result").list.get(6).alias("bonus_number"),
])
print(df.head(5))
```


## Predictions

Prediction models are at [/src/machine_learning](./src/machine_learning/).

For background on these models, see the [Machine Learning README](./src/machine_learning/).

## Data Statistics

| Product | Total Draws | Start Date | End Date | Total Records | First ID | Latest ID |
| --- | --- | --- | --- | --- | --- | --- |
| Power 655 | 1421 | 2017-08-01 | 2026-11-07 | 1421 | 00001 | 01421 |
| Power 645 | 1388 | 2017-10-25 | 2026-11-06 | 1388 | 00198 | 01585 |
| Power 535 | 497 | 2025-06-29 | 2026-11-07 | 993 | 00001 | 00993 |
| Keno | 730 | 2022-12-04 | 2026-11-07 | 91129 | #0110271 | #0302140 |
| 3D | 1155 | 2019-04-22 | 2026-11-06 | 1155 | 00001 | 01155 |
| 3D Pro | 802 | 2021-09-14 | 2026-11-07 | 802 | 00001 | 00802 |
| Bingo18 | 703 | 2024-12-03 | 2026-11-07 | 99237 | 0083123 | 0195073 |

## Power 6/55 Analysis

### Recent Results (Last 10 draws)
| date | id | result | process_time |
| --- | --- | --- | --- |
| 2026-11-07 | 01421 | [5, 19, 20, 26, 44, 53, 39] | 2026-11-07T12:00:05Z |
| 2026-11-05 | 01420 | [6, 20, 34, 41, 49, 52, 36] | 2026-11-05T12:00:05Z |
| 2026-11-03 | 01419 | [10, 22, 31, 39, 43, 54, 14] | 2026-11-03T12:00:05Z |
| 2026-10-31 | 01418 | [12, 18, 22, 26, 28, 55, 11] | 2026-10-31T12:00:05Z |
| 2026-10-29 | 01417 | [9, 29, 33, 38, 45, 46, 53] | 2026-10-29T12:00:05Z |
| 2026-10-27 | 01416 | [9, 18, 27, 28, 31, 35, 50] | 2026-10-27T12:00:09Z |
| 2026-10-24 | 01415 | [6, 7, 18, 41, 44, 50, 53] | 2026-10-24T12:01:16.734372 |
| 2026-10-22 | 01414 | [14, 19, 24, 31, 34, 42, 37] | 2026-10-22T12:01:27.562980 |
| 2026-10-20 | 01413 | [13, 20, 23, 30, 50, 55, 45] | 2026-10-20T12:01:23.653270 |
| 2026-10-17 | 01412 | [1, 10, 11, 12, 16, 37, 48] | 2026-10-17T12:01:15.757708 |

### Number Frequency (All Time)
| result | count | % | -1 | 1result | 1count | 1% | -2 | 2result | 2count | 2% |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 193 | 1.94 |  | 21 | 177 | 1.78 |  | 41 | 210 | 2.11 |
| 2 | 164 | 1.65 |  | 22 | 210 | 2.11 |  | 42 | 183 | 1.84 |
| 3 | 190 | 1.91 |  | 23 | 192 | 1.93 |  | 43 | 200 | 2.01 |
| 4 | 148 | 1.49 |  | 24 | 183 | 1.84 |  | 44 | 184 | 1.85 |
| 5 | 185 | 1.86 |  | 25 | 164 | 1.65 |  | 45 | 185 | 1.86 |
| 6 | 148 | 1.49 |  | 26 | 170 | 1.71 |  | 46 | 184 | 1.85 |
| 7 | 164 | 1.65 |  | 27 | 169 | 1.7 |  | 47 | 180 | 1.81 |
| 8 | 196 | 1.97 |  | 28 | 162 | 1.63 |  | 48 | 192 | 1.93 |
| 9 | 198 | 1.99 |  | 29 | 192 | 1.93 |  | 49 | 176 | 1.77 |
| 10 | 169 | 1.7 |  | 30 | 164 | 1.65 |  | 50 | 183 | 1.84 |
| 11 | 190 | 1.91 |  | 31 | 192 | 1.93 |  | 51 | 199 | 2.0 |
| 12 | 183 | 1.84 |  | 32 | 188 | 1.89 |  | 52 | 182 | 1.83 |
| 13 | 178 | 1.79 |  | 33 | 181 | 1.82 |  | 53 | 192 | 1.93 |
| 14 | 184 | 1.85 |  | 34 | 199 | 2.0 |  | 54 | 171 | 1.72 |
| 15 | 168 | 1.69 |  | 35 | 172 | 1.73 |  | 55 | 182 | 1.83 |
| 16 | 177 | 1.78 |  | 36 | 170 | 1.71 |  |  |  |  |
| 17 | 163 | 1.64 |  | 37 | 161 | 1.62 |  |  |  |  |
| 18 | 185 | 1.86 |  | 38 | 175 | 1.76 |  |  |  |  |
| 19 | 176 | 1.77 |  | 39 | 175 | 1.76 |  |  |  |  |
| 20 | 193 | 1.94 |  | 40 | 195 | 1.96 |  |  |  |  |

### Frequency Analysis by Period

#### Last 30 Days
| result | count | % | -1 | 1result | 1count | 1% | -2 | 2result | 2count | 2% |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 2 | 2.04 |  | 24 | 2 | 2.04 |  | 45 | 3 | 3.06 |
| 2 | 1 | 1.02 |  | 25 | 1 | 1.02 |  | 46 | 1 | 1.02 |
| 4 | 1 | 1.02 |  | 26 | 3 | 3.06 |  | 48 | 1 | 1.02 |
| 5 | 1 | 1.02 |  | 27 | 3 | 3.06 |  | 49 | 1 | 1.02 |
| 6 | 3 | 3.06 |  | 28 | 2 | 2.04 |  | 50 | 4 | 4.08 |
| 7 | 3 | 3.06 |  | 29 | 1 | 1.02 |  | 51 | 1 | 1.02 |
| 9 | 2 | 2.04 |  | 30 | 2 | 2.04 |  | 52 | 2 | 2.04 |
| 10 | 2 | 2.04 |  | 31 | 4 | 4.08 |  | 53 | 4 | 4.08 |
| 11 | 2 | 2.04 |  | 33 | 1 | 1.02 |  | 54 | 1 | 1.02 |
| 12 | 3 | 3.06 |  | 34 | 2 | 2.04 |  | 55 | 2 | 2.04 |
| 13 | 1 | 1.02 |  | 35 | 1 | 1.02 |  |  |  |  |
| 14 | 4 | 4.08 |  | 36 | 1 | 1.02 |  |  |  |  |
| 16 | 1 | 1.02 |  | 37 | 2 | 2.04 |  |  |  |  |
| 17 | 1 | 1.02 |  | 38 | 1 | 1.02 |  |  |  |  |
| 18 | 3 | 3.06 |  | 39 | 3 | 3.06 |  |  |  |  |
| 19 | 2 | 2.04 |  | 40 | 1 | 1.02 |  |  |  |  |
| 20 | 3 | 3.06 |  | 41 | 2 | 2.04 |  |  |  |  |
| 21 | 1 | 1.02 |  | 42 | 2 | 2.04 |  |  |  |  |
| 22 | 2 | 2.04 |  | 43 | 1 | 1.02 |  |  |  |  |
| 23 | 3 | 3.06 |  | 44 | 2 | 2.04 |  |  |  |  |

#### Last 60 Days
| result | count | % | -1 | 1result | 1count | 1% | -2 | 2result | 2count | 2% |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 5 | 2.65 |  | 21 | 2 | 1.06 |  | 41 | 4 | 2.12 |
| 2 | 3 | 1.59 |  | 22 | 4 | 2.12 |  | 42 | 2 | 1.06 |
| 3 | 1 | 0.53 |  | 23 | 5 | 2.65 |  | 43 | 2 | 1.06 |
| 4 | 4 | 2.12 |  | 24 | 5 | 2.65 |  | 44 | 2 | 1.06 |
| 5 | 3 | 1.59 |  | 25 | 5 | 2.65 |  | 45 | 4 | 2.12 |
| 6 | 5 | 2.65 |  | 26 | 4 | 2.12 |  | 46 | 2 | 1.06 |
| 7 | 7 | 3.7 |  | 27 | 7 | 3.7 |  | 47 | 2 | 1.06 |
| 8 | 1 | 0.53 |  | 28 | 4 | 2.12 |  | 48 | 2 | 1.06 |
| 9 | 3 | 1.59 |  | 29 | 1 | 0.53 |  | 49 | 2 | 1.06 |
| 10 | 3 | 1.59 |  | 30 | 2 | 1.06 |  | 50 | 6 | 3.17 |
| 11 | 8 | 4.23 |  | 31 | 5 | 2.65 |  | 51 | 2 | 1.06 |
| 12 | 3 | 1.59 |  | 32 | 2 | 1.06 |  | 52 | 5 | 2.65 |
| 13 | 5 | 2.65 |  | 33 | 1 | 0.53 |  | 53 | 5 | 2.65 |
| 14 | 6 | 3.17 |  | 34 | 3 | 1.59 |  | 54 | 4 | 2.12 |
| 15 | 2 | 1.06 |  | 35 | 2 | 1.06 |  | 55 | 3 | 1.59 |
| 16 | 2 | 1.06 |  | 36 | 3 | 1.59 |  |  |  |  |
| 17 | 3 | 1.59 |  | 37 | 3 | 1.59 |  |  |  |  |
| 18 | 7 | 3.7 |  | 38 | 3 | 1.59 |  |  |  |  |
| 19 | 2 | 1.06 |  | 39 | 3 | 1.59 |  |  |  |  |
| 20 | 4 | 2.12 |  | 40 | 1 | 0.53 |  |  |  |  |

#### Last 90 Days
| result | count | % | -1 | 1result | 1count | 1% | -2 | 2result | 2count | 2% |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 7 | 2.56 |  | 21 | 5 | 1.83 |  | 41 | 6 | 2.2 |
| 2 | 6 | 2.2 |  | 22 | 4 | 1.47 |  | 42 | 4 | 1.47 |
| 3 | 3 | 1.1 |  | 23 | 5 | 1.83 |  | 43 | 2 | 0.73 |
| 4 | 4 | 1.47 |  | 24 | 7 | 2.56 |  | 44 | 4 | 1.47 |
| 5 | 6 | 2.2 |  | 25 | 7 | 2.56 |  | 45 | 7 | 2.56 |
| 6 | 5 | 1.83 |  | 26 | 5 | 1.83 |  | 46 | 4 | 1.47 |
| 7 | 9 | 3.3 |  | 27 | 9 | 3.3 |  | 47 | 5 | 1.83 |
| 8 | 4 | 1.47 |  | 28 | 4 | 1.47 |  | 48 | 3 | 1.1 |
| 9 | 7 | 2.56 |  | 29 | 4 | 1.47 |  | 49 | 3 | 1.1 |
| 10 | 5 | 1.83 |  | 30 | 4 | 1.47 |  | 50 | 8 | 2.93 |
| 11 | 11 | 4.03 |  | 31 | 8 | 2.93 |  | 51 | 3 | 1.1 |
| 12 | 3 | 1.1 |  | 32 | 2 | 0.73 |  | 52 | 5 | 1.83 |
| 13 | 6 | 2.2 |  | 33 | 2 | 0.73 |  | 53 | 5 | 1.83 |
| 14 | 7 | 2.56 |  | 34 | 4 | 1.47 |  | 54 | 4 | 1.47 |
| 15 | 4 | 1.47 |  | 35 | 2 | 0.73 |  | 55 | 4 | 1.47 |
| 16 | 4 | 1.47 |  | 36 | 4 | 1.47 |  |  |  |  |
| 17 | 4 | 1.47 |  | 37 | 3 | 1.1 |  |  |  |  |
| 18 | 10 | 3.66 |  | 38 | 5 | 1.83 |  |  |  |  |
| 19 | 4 | 1.47 |  | 39 | 5 | 1.83 |  |  |  |  |
| 20 | 6 | 2.2 |  | 40 | 2 | 0.73 |  |  |  |  |

### Top 10 Numbers by Days Since Last Appearance
| result | last_date | days_since |
| --- | --- | --- |
| 8 | 2026-09-08 | 60 |
| 32 | 2026-09-15 | 53 |
| 47 | 2026-09-15 | 53 |
| 3 | 2026-09-22 | 46 |
| 15 | 2026-10-01 | 37 |
| 17 | 2026-10-10 | 28 |
| 21 | 2026-10-10 | 28 |
| 2 | 2026-10-13 | 25 |
| 40 | 2026-10-13 | 25 |
| 4 | 2026-10-15 | 23 |

### Days Since Last Appearance - All Numbers
| result | last_date | days_since |
| --- | --- | --- |
| 1 | 2026-10-17 | 21 |
| 2 | 2026-10-13 | 25 |
| 3 | 2026-09-22 | 46 |
| 4 | 2026-10-15 | 23 |
| 5 | 2026-11-07 | 0 |
| 6 | 2026-11-05 | 2 |
| 7 | 2026-10-24 | 14 |
| 8 | 2026-09-08 | 60 |
| 9 | 2026-10-29 | 9 |
| 10 | 2026-11-03 | 4 |
| 11 | 2026-10-31 | 7 |
| 12 | 2026-10-31 | 7 |
| 13 | 2026-10-20 | 18 |
| 14 | 2026-11-03 | 4 |
| 15 | 2026-10-01 | 37 |
| 16 | 2026-10-17 | 21 |
| 17 | 2026-10-10 | 28 |
| 18 | 2026-10-31 | 7 |
| 19 | 2026-11-07 | 0 |
| 20 | 2026-11-07 | 0 |
| 21 | 2026-10-10 | 28 |
| 22 | 2026-11-03 | 4 |
| 23 | 2026-10-20 | 18 |
| 24 | 2026-10-22 | 16 |
| 25 | 2026-10-15 | 23 |
| 26 | 2026-11-07 | 0 |
| 27 | 2026-10-27 | 11 |
| 28 | 2026-10-31 | 7 |
| 29 | 2026-10-29 | 9 |
| 30 | 2026-10-20 | 18 |
| 31 | 2026-11-03 | 4 |
| 32 | 2026-09-15 | 53 |
| 33 | 2026-10-29 | 9 |
| 34 | 2026-11-05 | 2 |
| 35 | 2026-10-27 | 11 |
| 36 | 2026-11-05 | 2 |
| 37 | 2026-10-22 | 16 |
| 38 | 2026-10-29 | 9 |
| 39 | 2026-11-07 | 0 |
| 40 | 2026-10-13 | 25 |
| 41 | 2026-11-05 | 2 |
| 42 | 2026-10-22 | 16 |
| 43 | 2026-11-03 | 4 |
| 44 | 2026-11-07 | 0 |
| 45 | 2026-10-29 | 9 |
| 46 | 2026-10-29 | 9 |
| 47 | 2026-09-15 | 53 |
| 48 | 2026-10-17 | 21 |
| 49 | 2026-11-05 | 2 |
| 50 | 2026-10-27 | 11 |
| 51 | 2026-10-15 | 23 |
| 52 | 2026-11-05 | 2 |
| 53 | 2026-11-07 | 0 |
| 54 | 2026-11-03 | 4 |
| 55 | 2026-10-31 | 7 |



## How It Works

Vietlott blocks non-Vietnam IPs ([upstream issue #13](https://github.com/vietvudanh/vietlott-data/issues/13)), so GitHub-hosted runners cannot crawl it. This repository (a fork of [vietvudanh/vietlott-data](https://github.com/vietvudanh/vietlott-data)) keeps its data fresh with the `sync-data.yml` workflow, which copies the NDJSON files crawled in Vietnam by the upstream project twice a day, re-renders this README and the website, and deploys GitHub Pages. A local runner in Vietnam (`bin/github_data.sh`) can crawl vietlott.vn directly instead.

The [analysis & ML dashboard](https://hieptd-ai.github.io/vietlott-predict/analysis/) adds randomness tests, strategy backtests and a "play since 2026" profit simulator; see [docs/ML_RESEARCH.md](docs/ML_RESEARCH.md).

For architecture and runner setup, see [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md). For performance and speed metrics comparing Go vs Python, see [docs/BENCHMARK.md](docs/BENCHMARK.md).


## Installation & Usage

### Go crawler (recommended)

Requires Go 1.27+. Vietlott only answers Vietnamese IPs, so run it from Vietnam.

```bash
make build-crawler                       # builds bin/vietlott-crawler
./bin/vietlott-crawler status            # existing vs latest draw per product
./bin/vietlott-crawler sync --all        # fetch latest draws and backfill gaps
./bin/vietlott-crawler sync --product keno --max-draws 100
./bin/vietlott-crawler render-readme     # regenerate readme.md
./bin/vietlott-crawler render-docs       # regenerate docs/index.html

# Products: power655, power645, power535, keno, bingo18, 3d, 3d_pro
```

### Python CLI (legacy, deprecated)

The Python crawler stays available through the PyPI package and will be removed in a future release.

```bash
# Crawl latest data
uv run vietlott-crawl keno

# Backfill missing data
uv run vietlott-missing power_655

# Available products: power_655, power_645, power_535, keno, 3d, 3d_pro, bingo18
```

### Development Setup

```bash
git clone https://github.com/hieptd-ai/vietlott-predict.git
cd vietlott-predict
uv sync --dev
uv run pytest
```

## Citation & Attribution

If you use this dataset in research, articles, or applications, please cite it as:

```bibtex
@misc{vietlott_data,
  author       = {Viet Vu Danh and hieptd-ai},
  title        = {Vietlott Data: Open Historical Vietnamese Lottery Dataset (NDJSON)},
  year         = {2026},
  url          = {https://github.com/hieptd-ai/vietlott-predict},
  note         = {MIT License. Fork of https://github.com/vietvudanh/vietlott-data. Source data from vietlott.vn, updated daily.}
}
```

## License

This project is licensed under the MIT License - see [LICENSE](LICENSE).

---

<div align="center">
  <strong>If you find this project useful, please consider giving it a star!</strong>
</div>

