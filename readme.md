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
| Power 655 | 1430 | 2017-08-01 | 2026-11-28 | 1430 | 00001 | 01430 |
| Power 645 | 1397 | 2017-10-25 | 2026-11-27 | 1397 | 00198 | 01594 |
| Power 535 | 518 | 2025-06-29 | 2026-11-28 | 1035 | 00001 | 01035 |
| Keno | 751 | 2022-12-04 | 2026-11-28 | 93628 | #0110271 | #0304639 |
| 3D | 1164 | 2019-04-22 | 2026-11-27 | 1164 | 00001 | 01164 |
| 3D Pro | 811 | 2021-09-14 | 2026-11-28 | 811 | 00001 | 00811 |
| Bingo18 | 724 | 2024-12-03 | 2026-11-28 | 102575 | 0083123 | 0198411 |

## Power 6/55 Analysis

### Recent Results (Last 10 draws)
| date | id | result | process_time |
| --- | --- | --- | --- |
| 2026-11-28 | 01430 | [4, 27, 37, 39, 42, 49, 23] | 2026-11-28T12:00:15Z |
| 2026-11-26 | 01429 | [14, 18, 24, 28, 34, 55, 32] | 2026-11-26T12:00:05Z |
| 2026-11-24 | 01428 | [36, 40, 43, 46, 50, 55, 15] | 2026-11-24T12:00:05Z |
| 2026-11-21 | 01427 | [7, 29, 44, 45, 50, 54, 39] | 2026-11-21T12:00:05Z |
| 2026-11-19 | 01426 | [3, 13, 21, 23, 38, 43, 16] | 2026-11-19T12:00:05Z |
| 2026-11-17 | 01425 | [6, 20, 36, 41, 49, 52, 34] | 2026-11-18T00:00:05Z |
| 2026-11-14 | 01424 | [5, 28, 36, 42, 45, 47, 51] | 2026-11-14T12:00:05Z |
| 2026-11-12 | 01423 | [17, 25, 33, 34, 35, 36, 48] | 2026-11-12T12:00:05Z |
| 2026-11-10 | 01422 | [1, 2, 21, 38, 39, 51, 12] | 2026-11-10T12:00:05Z |
| 2026-11-07 | 01421 | [5, 19, 20, 26, 44, 53, 39] | 2026-11-07T12:00:05Z |

### Number Frequency (All Time)
| result | count | % | -1 | 1result | 1count | 1% | -2 | 2result | 2count | 2% |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 194 | 1.94 |  | 21 | 179 | 1.79 |  | 41 | 211 | 2.11 |
| 2 | 165 | 1.65 |  | 22 | 210 | 2.1 |  | 42 | 185 | 1.85 |
| 3 | 191 | 1.91 |  | 23 | 194 | 1.94 |  | 43 | 202 | 2.02 |
| 4 | 149 | 1.49 |  | 24 | 184 | 1.84 |  | 44 | 185 | 1.85 |
| 5 | 186 | 1.86 |  | 25 | 165 | 1.65 |  | 45 | 187 | 1.87 |
| 6 | 149 | 1.49 |  | 26 | 170 | 1.7 |  | 46 | 185 | 1.85 |
| 7 | 165 | 1.65 |  | 27 | 170 | 1.7 |  | 47 | 181 | 1.81 |
| 8 | 196 | 1.96 |  | 28 | 164 | 1.64 |  | 48 | 193 | 1.93 |
| 9 | 198 | 1.98 |  | 29 | 193 | 1.93 |  | 49 | 178 | 1.78 |
| 10 | 169 | 1.69 |  | 30 | 164 | 1.64 |  | 50 | 185 | 1.85 |
| 11 | 190 | 1.9 |  | 31 | 192 | 1.92 |  | 51 | 201 | 2.01 |
| 12 | 184 | 1.84 |  | 32 | 189 | 1.89 |  | 52 | 183 | 1.83 |
| 13 | 179 | 1.79 |  | 33 | 182 | 1.82 |  | 53 | 192 | 1.92 |
| 14 | 185 | 1.85 |  | 34 | 202 | 2.02 |  | 54 | 172 | 1.72 |
| 15 | 169 | 1.69 |  | 35 | 173 | 1.73 |  | 55 | 184 | 1.84 |
| 16 | 178 | 1.78 |  | 36 | 174 | 1.74 |  |  |  |  |
| 17 | 164 | 1.64 |  | 37 | 162 | 1.62 |  |  |  |  |
| 18 | 186 | 1.86 |  | 38 | 177 | 1.77 |  |  |  |  |
| 19 | 176 | 1.76 |  | 39 | 178 | 1.78 |  |  |  |  |
| 20 | 194 | 1.94 |  | 40 | 196 | 1.96 |  |  |  |  |

### Frequency Analysis by Period

#### Last 30 Days
| result | count | % | -1 | 1result | 1count | 1% | -2 | 2result | 2count | 2% |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 1 | 1.02 |  | 22 | 2 | 2.04 |  | 43 | 3 | 3.06 |
| 2 | 1 | 1.02 |  | 23 | 2 | 2.04 |  | 44 | 2 | 2.04 |
| 3 | 1 | 1.02 |  | 24 | 1 | 1.02 |  | 45 | 3 | 3.06 |
| 4 | 1 | 1.02 |  | 25 | 1 | 1.02 |  | 46 | 2 | 2.04 |
| 5 | 2 | 2.04 |  | 26 | 2 | 2.04 |  | 47 | 1 | 1.02 |
| 6 | 2 | 2.04 |  | 27 | 1 | 1.02 |  | 48 | 1 | 1.02 |
| 7 | 1 | 1.02 |  | 28 | 3 | 3.06 |  | 49 | 3 | 3.06 |
| 9 | 1 | 1.02 |  | 29 | 2 | 2.04 |  | 50 | 2 | 2.04 |
| 10 | 1 | 1.02 |  | 31 | 1 | 1.02 |  | 51 | 2 | 2.04 |
| 11 | 1 | 1.02 |  | 32 | 1 | 1.02 |  | 52 | 2 | 2.04 |
| 12 | 2 | 2.04 |  | 33 | 2 | 2.04 |  | 53 | 2 | 2.04 |
| 13 | 1 | 1.02 |  | 34 | 4 | 4.08 |  | 54 | 2 | 2.04 |
| 14 | 2 | 2.04 |  | 35 | 1 | 1.02 |  | 55 | 3 | 3.06 |
| 15 | 1 | 1.02 |  | 36 | 5 | 5.1 |  |  |  |  |
| 16 | 1 | 1.02 |  | 37 | 1 | 1.02 |  |  |  |  |
| 17 | 1 | 1.02 |  | 38 | 3 | 3.06 |  |  |  |  |
| 18 | 2 | 2.04 |  | 39 | 5 | 5.1 |  |  |  |  |
| 19 | 1 | 1.02 |  | 40 | 1 | 1.02 |  |  |  |  |
| 20 | 3 | 3.06 |  | 41 | 2 | 2.04 |  |  |  |  |
| 21 | 2 | 2.04 |  | 42 | 2 | 2.04 |  |  |  |  |

#### Last 60 Days
| result | count | % | -1 | 1result | 1count | 1% | -2 | 2result | 2count | 2% |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 4 | 2.12 |  | 22 | 2 | 1.06 |  | 42 | 4 | 2.12 |
| 2 | 3 | 1.59 |  | 23 | 5 | 2.65 |  | 43 | 3 | 1.59 |
| 3 | 1 | 0.53 |  | 24 | 4 | 2.12 |  | 44 | 3 | 1.59 |
| 4 | 4 | 2.12 |  | 25 | 2 | 1.06 |  | 45 | 5 | 2.65 |
| 5 | 3 | 1.59 |  | 26 | 3 | 1.59 |  | 46 | 2 | 1.06 |
| 6 | 5 | 2.65 |  | 27 | 5 | 2.65 |  | 47 | 1 | 0.53 |
| 7 | 6 | 3.17 |  | 28 | 4 | 2.12 |  | 48 | 2 | 1.06 |
| 9 | 2 | 1.06 |  | 29 | 2 | 1.06 |  | 49 | 3 | 1.59 |
| 10 | 2 | 1.06 |  | 30 | 2 | 1.06 |  | 50 | 6 | 3.17 |
| 11 | 4 | 2.12 |  | 31 | 4 | 2.12 |  | 51 | 3 | 1.59 |
| 12 | 4 | 2.12 |  | 32 | 1 | 0.53 |  | 52 | 4 | 2.12 |
| 13 | 5 | 2.65 |  | 33 | 2 | 1.06 |  | 53 | 4 | 2.12 |
| 14 | 5 | 2.65 |  | 34 | 6 | 3.17 |  | 54 | 3 | 1.59 |
| 15 | 2 | 1.06 |  | 35 | 3 | 1.59 |  | 55 | 5 | 2.65 |
| 16 | 3 | 1.59 |  | 36 | 6 | 3.17 |  |  |  |  |
| 17 | 3 | 1.59 |  | 37 | 3 | 1.59 |  |  |  |  |
| 18 | 6 | 3.17 |  | 38 | 3 | 1.59 |  |  |  |  |
| 19 | 2 | 1.06 |  | 39 | 6 | 3.17 |  |  |  |  |
| 20 | 5 | 2.65 |  | 40 | 2 | 1.06 |  |  |  |  |
| 21 | 3 | 1.59 |  | 41 | 4 | 2.12 |  |  |  |  |

#### Last 90 Days
| result | count | % | -1 | 1result | 1count | 1% | -2 | 2result | 2count | 2% |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 7 | 2.56 |  | 21 | 5 | 1.83 |  | 41 | 6 | 2.2 |
| 2 | 4 | 1.47 |  | 22 | 4 | 1.47 |  | 42 | 5 | 1.83 |
| 3 | 2 | 0.73 |  | 23 | 7 | 2.56 |  | 43 | 4 | 1.47 |
| 4 | 5 | 1.83 |  | 24 | 7 | 2.56 |  | 44 | 4 | 1.47 |
| 5 | 4 | 1.47 |  | 25 | 6 | 2.2 |  | 45 | 7 | 2.56 |
| 6 | 6 | 2.2 |  | 26 | 4 | 1.47 |  | 46 | 4 | 1.47 |
| 7 | 8 | 2.93 |  | 27 | 8 | 2.93 |  | 47 | 5 | 1.83 |
| 8 | 2 | 0.73 |  | 28 | 6 | 2.2 |  | 48 | 3 | 1.1 |
| 9 | 5 | 1.83 |  | 29 | 2 | 0.73 |  | 49 | 5 | 1.83 |
| 10 | 3 | 1.1 |  | 30 | 2 | 0.73 |  | 50 | 8 | 2.93 |
| 11 | 10 | 3.66 |  | 31 | 6 | 2.2 |  | 51 | 4 | 1.47 |
| 12 | 4 | 1.47 |  | 32 | 3 | 1.1 |  | 52 | 6 | 2.2 |
| 13 | 6 | 2.2 |  | 33 | 3 | 1.1 |  | 53 | 5 | 1.83 |
| 14 | 7 | 2.56 |  | 34 | 6 | 2.2 |  | 54 | 5 | 1.83 |
| 15 | 3 | 1.1 |  | 35 | 3 | 1.1 |  | 55 | 6 | 2.2 |
| 16 | 4 | 1.47 |  | 36 | 7 | 2.56 |  |  |  |  |
| 17 | 5 | 1.83 |  | 37 | 4 | 1.47 |  |  |  |  |
| 18 | 8 | 2.93 |  | 38 | 5 | 1.83 |  |  |  |  |
| 19 | 2 | 0.73 |  | 39 | 6 | 2.2 |  |  |  |  |
| 20 | 5 | 1.83 |  | 40 | 2 | 0.73 |  |  |  |  |

### Top 10 Numbers by Days Since Last Appearance
| result | last_date | days_since |
| --- | --- | --- |
| 8 | 2026-09-08 | 81 |
| 30 | 2026-10-20 | 39 |
| 9 | 2026-10-29 | 30 |
| 11 | 2026-10-31 | 28 |
| 10 | 2026-11-03 | 25 |
| 22 | 2026-11-03 | 25 |
| 31 | 2026-11-03 | 25 |
| 19 | 2026-11-07 | 21 |
| 26 | 2026-11-07 | 21 |
| 53 | 2026-11-07 | 21 |

### Days Since Last Appearance - All Numbers
| result | last_date | days_since |
| --- | --- | --- |
| 1 | 2026-11-10 | 18 |
| 2 | 2026-11-10 | 18 |
| 3 | 2026-11-19 | 9 |
| 4 | 2026-11-28 | 0 |
| 5 | 2026-11-14 | 14 |
| 6 | 2026-11-17 | 11 |
| 7 | 2026-11-21 | 7 |
| 8 | 2026-09-08 | 81 |
| 9 | 2026-10-29 | 30 |
| 10 | 2026-11-03 | 25 |
| 11 | 2026-10-31 | 28 |
| 12 | 2026-11-10 | 18 |
| 13 | 2026-11-19 | 9 |
| 14 | 2026-11-26 | 2 |
| 15 | 2026-11-24 | 4 |
| 16 | 2026-11-19 | 9 |
| 17 | 2026-11-12 | 16 |
| 18 | 2026-11-26 | 2 |
| 19 | 2026-11-07 | 21 |
| 20 | 2026-11-17 | 11 |
| 21 | 2026-11-19 | 9 |
| 22 | 2026-11-03 | 25 |
| 23 | 2026-11-28 | 0 |
| 24 | 2026-11-26 | 2 |
| 25 | 2026-11-12 | 16 |
| 26 | 2026-11-07 | 21 |
| 27 | 2026-11-28 | 0 |
| 28 | 2026-11-26 | 2 |
| 29 | 2026-11-21 | 7 |
| 30 | 2026-10-20 | 39 |
| 31 | 2026-11-03 | 25 |
| 32 | 2026-11-26 | 2 |
| 33 | 2026-11-12 | 16 |
| 34 | 2026-11-26 | 2 |
| 35 | 2026-11-12 | 16 |
| 36 | 2026-11-24 | 4 |
| 37 | 2026-11-28 | 0 |
| 38 | 2026-11-19 | 9 |
| 39 | 2026-11-28 | 0 |
| 40 | 2026-11-24 | 4 |
| 41 | 2026-11-17 | 11 |
| 42 | 2026-11-28 | 0 |
| 43 | 2026-11-24 | 4 |
| 44 | 2026-11-21 | 7 |
| 45 | 2026-11-21 | 7 |
| 46 | 2026-11-24 | 4 |
| 47 | 2026-11-14 | 14 |
| 48 | 2026-11-12 | 16 |
| 49 | 2026-11-28 | 0 |
| 50 | 2026-11-24 | 4 |
| 51 | 2026-11-14 | 14 |
| 52 | 2026-11-17 | 11 |
| 53 | 2026-11-07 | 21 |
| 54 | 2026-11-21 | 7 |
| 55 | 2026-11-26 | 2 |



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

