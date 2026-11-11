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
| Power 655 | 1422 | 2017-08-01 | 2026-11-10 | 1422 | 00001 | 01422 |
| Power 645 | 1389 | 2017-10-25 | 2026-11-08 | 1389 | 00198 | 01586 |
| Power 535 | 500 | 2025-06-29 | 2026-11-10 | 1000 | 00001 | 01000 |
| Keno | 734 | 2022-12-04 | 2026-11-11 | 91515 | #0110271 | #0302526 |
| 3D | 1156 | 2019-04-22 | 2026-11-09 | 1156 | 00001 | 01156 |
| 3D Pro | 803 | 2021-09-14 | 2026-11-10 | 803 | 00001 | 00803 |
| Bingo18 | 707 | 2024-12-03 | 2026-11-11 | 99753 | 0083123 | 0195589 |

## Power 6/55 Analysis

### Recent Results (Last 10 draws)
| date | id | result | process_time |
| --- | --- | --- | --- |
| 2026-11-10 | 01422 | [1, 2, 21, 38, 39, 51, 12] | 2026-11-10T12:00:05Z |
| 2026-11-07 | 01421 | [5, 19, 20, 26, 44, 53, 39] | 2026-11-07T12:00:05Z |
| 2026-11-05 | 01420 | [6, 20, 34, 41, 49, 52, 36] | 2026-11-05T12:00:05Z |
| 2026-11-03 | 01419 | [10, 22, 31, 39, 43, 54, 14] | 2026-11-03T12:00:05Z |
| 2026-10-31 | 01418 | [12, 18, 22, 26, 28, 55, 11] | 2026-10-31T12:00:05Z |
| 2026-10-29 | 01417 | [9, 29, 33, 38, 45, 46, 53] | 2026-10-29T12:00:05Z |
| 2026-10-27 | 01416 | [9, 18, 27, 28, 31, 35, 50] | 2026-10-27T12:00:09Z |
| 2026-10-24 | 01415 | [6, 7, 18, 41, 44, 50, 53] | 2026-10-24T12:01:16.734372 |
| 2026-10-22 | 01414 | [14, 19, 24, 31, 34, 42, 37] | 2026-10-22T12:01:27.562980 |
| 2026-10-20 | 01413 | [13, 20, 23, 30, 50, 55, 45] | 2026-10-20T12:01:23.653270 |

### Number Frequency (All Time)
| result | count | % | -1 | 1result | 1count | 1% | -2 | 2result | 2count | 2% |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 194 | 1.95 |  | 21 | 178 | 1.79 |  | 41 | 210 | 2.11 |
| 2 | 165 | 1.66 |  | 22 | 210 | 2.11 |  | 42 | 183 | 1.84 |
| 3 | 190 | 1.91 |  | 23 | 192 | 1.93 |  | 43 | 200 | 2.01 |
| 4 | 148 | 1.49 |  | 24 | 183 | 1.84 |  | 44 | 184 | 1.85 |
| 5 | 185 | 1.86 |  | 25 | 164 | 1.65 |  | 45 | 185 | 1.86 |
| 6 | 148 | 1.49 |  | 26 | 170 | 1.71 |  | 46 | 184 | 1.85 |
| 7 | 164 | 1.65 |  | 27 | 169 | 1.7 |  | 47 | 180 | 1.81 |
| 8 | 196 | 1.97 |  | 28 | 162 | 1.63 |  | 48 | 192 | 1.93 |
| 9 | 198 | 1.99 |  | 29 | 192 | 1.93 |  | 49 | 176 | 1.77 |
| 10 | 169 | 1.7 |  | 30 | 164 | 1.65 |  | 50 | 183 | 1.84 |
| 11 | 190 | 1.91 |  | 31 | 192 | 1.93 |  | 51 | 200 | 2.01 |
| 12 | 184 | 1.85 |  | 32 | 188 | 1.89 |  | 52 | 182 | 1.83 |
| 13 | 178 | 1.79 |  | 33 | 181 | 1.82 |  | 53 | 192 | 1.93 |
| 14 | 184 | 1.85 |  | 34 | 199 | 2.0 |  | 54 | 171 | 1.72 |
| 15 | 168 | 1.69 |  | 35 | 172 | 1.73 |  | 55 | 182 | 1.83 |
| 16 | 177 | 1.78 |  | 36 | 170 | 1.71 |  |  |  |  |
| 17 | 163 | 1.64 |  | 37 | 161 | 1.62 |  |  |  |  |
| 18 | 185 | 1.86 |  | 38 | 176 | 1.77 |  |  |  |  |
| 19 | 176 | 1.77 |  | 39 | 176 | 1.77 |  |  |  |  |
| 20 | 193 | 1.94 |  | 40 | 195 | 1.96 |  |  |  |  |

### Frequency Analysis by Period

#### Last 30 Days
| result | count | % | -1 | 1result | 1count | 1% | -2 | 2result | 2count | 2% |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 2 | 2.2 |  | 25 | 1 | 1.1 |  | 46 | 1 | 1.1 |
| 2 | 2 | 2.2 |  | 26 | 3 | 3.3 |  | 48 | 1 | 1.1 |
| 4 | 1 | 1.1 |  | 27 | 2 | 2.2 |  | 49 | 1 | 1.1 |
| 5 | 1 | 1.1 |  | 28 | 2 | 2.2 |  | 50 | 4 | 4.4 |
| 6 | 2 | 2.2 |  | 29 | 1 | 1.1 |  | 51 | 2 | 2.2 |
| 7 | 2 | 2.2 |  | 30 | 1 | 1.1 |  | 52 | 1 | 1.1 |
| 9 | 2 | 2.2 |  | 31 | 3 | 3.3 |  | 53 | 4 | 4.4 |
| 10 | 2 | 2.2 |  | 33 | 1 | 1.1 |  | 54 | 1 | 1.1 |
| 11 | 2 | 2.2 |  | 34 | 2 | 2.2 |  | 55 | 2 | 2.2 |
| 12 | 3 | 3.3 |  | 35 | 1 | 1.1 |  |  |  |  |
| 13 | 1 | 1.1 |  | 36 | 1 | 1.1 |  |  |  |  |
| 14 | 3 | 3.3 |  | 37 | 2 | 2.2 |  |  |  |  |
| 16 | 1 | 1.1 |  | 38 | 2 | 2.2 |  |  |  |  |
| 18 | 3 | 3.3 |  | 39 | 3 | 3.3 |  |  |  |  |
| 19 | 2 | 2.2 |  | 40 | 1 | 1.1 |  |  |  |  |
| 20 | 3 | 3.3 |  | 41 | 2 | 2.2 |  |  |  |  |
| 21 | 1 | 1.1 |  | 42 | 2 | 2.2 |  |  |  |  |
| 22 | 2 | 2.2 |  | 43 | 1 | 1.1 |  |  |  |  |
| 23 | 2 | 2.2 |  | 44 | 2 | 2.2 |  |  |  |  |
| 24 | 1 | 1.1 |  | 45 | 3 | 3.3 |  |  |  |  |

#### Last 60 Days
| result | count | % | -1 | 1result | 1count | 1% | -2 | 2result | 2count | 2% |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 6 | 3.3 |  | 22 | 4 | 2.2 |  | 42 | 2 | 1.1 |
| 2 | 3 | 1.65 |  | 23 | 4 | 2.2 |  | 43 | 2 | 1.1 |
| 3 | 1 | 0.55 |  | 24 | 5 | 2.75 |  | 44 | 2 | 1.1 |
| 4 | 4 | 2.2 |  | 25 | 4 | 2.2 |  | 45 | 4 | 2.2 |
| 5 | 2 | 1.1 |  | 26 | 4 | 2.2 |  | 46 | 2 | 1.1 |
| 6 | 5 | 2.75 |  | 27 | 7 | 3.85 |  | 47 | 2 | 1.1 |
| 7 | 7 | 3.85 |  | 28 | 3 | 1.65 |  | 48 | 2 | 1.1 |
| 9 | 3 | 1.65 |  | 29 | 1 | 0.55 |  | 49 | 2 | 1.1 |
| 10 | 3 | 1.65 |  | 30 | 2 | 1.1 |  | 50 | 5 | 2.75 |
| 11 | 7 | 3.85 |  | 31 | 5 | 2.75 |  | 51 | 2 | 1.1 |
| 12 | 4 | 2.2 |  | 32 | 1 | 0.55 |  | 52 | 5 | 2.75 |
| 13 | 5 | 2.75 |  | 33 | 1 | 0.55 |  | 53 | 4 | 2.2 |
| 14 | 5 | 2.75 |  | 34 | 3 | 1.65 |  | 54 | 3 | 1.65 |
| 15 | 2 | 1.1 |  | 35 | 2 | 1.1 |  | 55 | 3 | 1.65 |
| 16 | 2 | 1.1 |  | 36 | 3 | 1.65 |  |  |  |  |
| 17 | 2 | 1.1 |  | 37 | 3 | 1.65 |  |  |  |  |
| 18 | 7 | 3.85 |  | 38 | 4 | 2.2 |  |  |  |  |
| 19 | 2 | 1.1 |  | 39 | 4 | 2.2 |  |  |  |  |
| 20 | 4 | 2.2 |  | 40 | 1 | 0.55 |  |  |  |  |
| 21 | 3 | 1.65 |  | 41 | 4 | 2.2 |  |  |  |  |

#### Last 90 Days
| result | count | % | -1 | 1result | 1count | 1% | -2 | 2result | 2count | 2% |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 8 | 2.93 |  | 21 | 6 | 2.2 |  | 41 | 6 | 2.2 |
| 2 | 6 | 2.2 |  | 22 | 4 | 1.47 |  | 42 | 4 | 1.47 |
| 3 | 3 | 1.1 |  | 23 | 5 | 1.83 |  | 43 | 2 | 0.73 |
| 4 | 4 | 1.47 |  | 24 | 7 | 2.56 |  | 44 | 4 | 1.47 |
| 5 | 6 | 2.2 |  | 25 | 7 | 2.56 |  | 45 | 7 | 2.56 |
| 6 | 5 | 1.83 |  | 26 | 5 | 1.83 |  | 46 | 4 | 1.47 |
| 7 | 8 | 2.93 |  | 27 | 9 | 3.3 |  | 47 | 5 | 1.83 |
| 8 | 4 | 1.47 |  | 28 | 4 | 1.47 |  | 48 | 3 | 1.1 |
| 9 | 7 | 2.56 |  | 29 | 4 | 1.47 |  | 49 | 3 | 1.1 |
| 10 | 5 | 1.83 |  | 30 | 4 | 1.47 |  | 50 | 7 | 2.56 |
| 11 | 11 | 4.03 |  | 31 | 7 | 2.56 |  | 51 | 4 | 1.47 |
| 12 | 4 | 1.47 |  | 32 | 2 | 0.73 |  | 52 | 5 | 1.83 |
| 13 | 6 | 2.2 |  | 33 | 2 | 0.73 |  | 53 | 5 | 1.83 |
| 14 | 7 | 2.56 |  | 34 | 4 | 1.47 |  | 54 | 4 | 1.47 |
| 15 | 4 | 1.47 |  | 35 | 2 | 0.73 |  | 55 | 4 | 1.47 |
| 16 | 4 | 1.47 |  | 36 | 4 | 1.47 |  |  |  |  |
| 17 | 4 | 1.47 |  | 37 | 3 | 1.1 |  |  |  |  |
| 18 | 10 | 3.66 |  | 38 | 6 | 2.2 |  |  |  |  |
| 19 | 3 | 1.1 |  | 39 | 5 | 1.83 |  |  |  |  |
| 20 | 5 | 1.83 |  | 40 | 2 | 0.73 |  |  |  |  |

### Top 10 Numbers by Days Since Last Appearance
| result | last_date | days_since |
| --- | --- | --- |
| 8 | 2026-09-08 | 63 |
| 32 | 2026-09-15 | 56 |
| 47 | 2026-09-15 | 56 |
| 3 | 2026-09-22 | 49 |
| 15 | 2026-10-01 | 40 |
| 17 | 2026-10-10 | 31 |
| 40 | 2026-10-13 | 28 |
| 4 | 2026-10-15 | 26 |
| 25 | 2026-10-15 | 26 |
| 16 | 2026-10-17 | 24 |

### Days Since Last Appearance - All Numbers
| result | last_date | days_since |
| --- | --- | --- |
| 1 | 2026-11-10 | 0 |
| 2 | 2026-11-10 | 0 |
| 3 | 2026-09-22 | 49 |
| 4 | 2026-10-15 | 26 |
| 5 | 2026-11-07 | 3 |
| 6 | 2026-11-05 | 5 |
| 7 | 2026-10-24 | 17 |
| 8 | 2026-09-08 | 63 |
| 9 | 2026-10-29 | 12 |
| 10 | 2026-11-03 | 7 |
| 11 | 2026-10-31 | 10 |
| 12 | 2026-11-10 | 0 |
| 13 | 2026-10-20 | 21 |
| 14 | 2026-11-03 | 7 |
| 15 | 2026-10-01 | 40 |
| 16 | 2026-10-17 | 24 |
| 17 | 2026-10-10 | 31 |
| 18 | 2026-10-31 | 10 |
| 19 | 2026-11-07 | 3 |
| 20 | 2026-11-07 | 3 |
| 21 | 2026-11-10 | 0 |
| 22 | 2026-11-03 | 7 |
| 23 | 2026-10-20 | 21 |
| 24 | 2026-10-22 | 19 |
| 25 | 2026-10-15 | 26 |
| 26 | 2026-11-07 | 3 |
| 27 | 2026-10-27 | 14 |
| 28 | 2026-10-31 | 10 |
| 29 | 2026-10-29 | 12 |
| 30 | 2026-10-20 | 21 |
| 31 | 2026-11-03 | 7 |
| 32 | 2026-09-15 | 56 |
| 33 | 2026-10-29 | 12 |
| 34 | 2026-11-05 | 5 |
| 35 | 2026-10-27 | 14 |
| 36 | 2026-11-05 | 5 |
| 37 | 2026-10-22 | 19 |
| 38 | 2026-11-10 | 0 |
| 39 | 2026-11-10 | 0 |
| 40 | 2026-10-13 | 28 |
| 41 | 2026-11-05 | 5 |
| 42 | 2026-10-22 | 19 |
| 43 | 2026-11-03 | 7 |
| 44 | 2026-11-07 | 3 |
| 45 | 2026-10-29 | 12 |
| 46 | 2026-10-29 | 12 |
| 47 | 2026-09-15 | 56 |
| 48 | 2026-10-17 | 24 |
| 49 | 2026-11-05 | 5 |
| 50 | 2026-10-27 | 14 |
| 51 | 2026-11-10 | 0 |
| 52 | 2026-11-05 | 5 |
| 53 | 2026-11-07 | 3 |
| 54 | 2026-11-03 | 7 |
| 55 | 2026-10-31 | 10 |



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

