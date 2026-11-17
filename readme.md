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
| Power 655 | 1424 | 2017-08-01 | 2026-11-14 | 1424 | 00001 | 01424 |
| Power 645 | 1392 | 2017-10-25 | 2026-11-15 | 1392 | 00198 | 01589 |
| Power 535 | 506 | 2025-06-29 | 2026-11-16 | 1012 | 00001 | 01012 |
| Keno | 740 | 2022-12-04 | 2026-11-17 | 92229 | #0110271 | #0303240 |
| 3D | 1159 | 2019-04-22 | 2026-11-16 | 1159 | 00001 | 01159 |
| 3D Pro | 805 | 2021-09-14 | 2026-11-14 | 805 | 00001 | 00805 |
| Bingo18 | 713 | 2024-12-03 | 2026-11-17 | 100707 | 0083123 | 0196543 |

## Power 6/55 Analysis

### Recent Results (Last 10 draws)
| date | id | result | process_time |
| --- | --- | --- | --- |
| 2026-11-14 | 01424 | [5, 28, 36, 42, 45, 47, 51] | 2026-11-14T12:00:05Z |
| 2026-11-12 | 01423 | [17, 25, 33, 34, 35, 36, 48] | 2026-11-12T12:00:05Z |
| 2026-11-10 | 01422 | [1, 2, 21, 38, 39, 51, 12] | 2026-11-10T12:00:05Z |
| 2026-11-07 | 01421 | [5, 19, 20, 26, 44, 53, 39] | 2026-11-07T12:00:05Z |
| 2026-11-05 | 01420 | [6, 20, 34, 41, 49, 52, 36] | 2026-11-05T12:00:05Z |
| 2026-11-03 | 01419 | [10, 22, 31, 39, 43, 54, 14] | 2026-11-03T12:00:05Z |
| 2026-10-31 | 01418 | [12, 18, 22, 26, 28, 55, 11] | 2026-10-31T12:00:05Z |
| 2026-10-29 | 01417 | [9, 29, 33, 38, 45, 46, 53] | 2026-10-29T12:00:05Z |
| 2026-10-27 | 01416 | [9, 18, 27, 28, 31, 35, 50] | 2026-10-27T12:00:09Z |
| 2026-10-24 | 01415 | [6, 7, 18, 41, 44, 50, 53] | 2026-10-24T12:01:16.734372 |

### Number Frequency (All Time)
| result | count | % | -1 | 1result | 1count | 1% | -2 | 2result | 2count | 2% |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 194 | 1.95 |  | 21 | 178 | 1.79 |  | 41 | 210 | 2.11 |
| 2 | 165 | 1.66 |  | 22 | 210 | 2.11 |  | 42 | 184 | 1.85 |
| 3 | 190 | 1.91 |  | 23 | 192 | 1.93 |  | 43 | 200 | 2.01 |
| 4 | 148 | 1.48 |  | 24 | 183 | 1.84 |  | 44 | 184 | 1.85 |
| 5 | 186 | 1.87 |  | 25 | 165 | 1.66 |  | 45 | 186 | 1.87 |
| 6 | 148 | 1.48 |  | 26 | 170 | 1.71 |  | 46 | 184 | 1.85 |
| 7 | 164 | 1.65 |  | 27 | 169 | 1.7 |  | 47 | 181 | 1.82 |
| 8 | 196 | 1.97 |  | 28 | 163 | 1.64 |  | 48 | 193 | 1.94 |
| 9 | 198 | 1.99 |  | 29 | 192 | 1.93 |  | 49 | 176 | 1.77 |
| 10 | 169 | 1.7 |  | 30 | 164 | 1.65 |  | 50 | 183 | 1.84 |
| 11 | 190 | 1.91 |  | 31 | 192 | 1.93 |  | 51 | 201 | 2.02 |
| 12 | 184 | 1.85 |  | 32 | 188 | 1.89 |  | 52 | 182 | 1.83 |
| 13 | 178 | 1.79 |  | 33 | 182 | 1.83 |  | 53 | 192 | 1.93 |
| 14 | 184 | 1.85 |  | 34 | 200 | 2.01 |  | 54 | 171 | 1.72 |
| 15 | 168 | 1.69 |  | 35 | 173 | 1.74 |  | 55 | 182 | 1.83 |
| 16 | 177 | 1.78 |  | 36 | 172 | 1.73 |  |  |  |  |
| 17 | 164 | 1.65 |  | 37 | 161 | 1.62 |  |  |  |  |
| 18 | 185 | 1.86 |  | 38 | 176 | 1.77 |  |  |  |  |
| 19 | 176 | 1.77 |  | 39 | 176 | 1.77 |  |  |  |  |
| 20 | 193 | 1.94 |  | 40 | 195 | 1.96 |  |  |  |  |

### Frequency Analysis by Period

#### Last 30 Days
| result | count | % | -1 | 1result | 1count | 1% | -2 | 2result | 2count | 2% |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 1 | 1.19 |  | 26 | 2 | 2.38 |  | 48 | 1 | 1.19 |
| 2 | 1 | 1.19 |  | 27 | 1 | 1.19 |  | 49 | 1 | 1.19 |
| 5 | 2 | 2.38 |  | 28 | 3 | 3.57 |  | 50 | 3 | 3.57 |
| 6 | 2 | 2.38 |  | 29 | 1 | 1.19 |  | 51 | 2 | 2.38 |
| 7 | 1 | 1.19 |  | 30 | 1 | 1.19 |  | 52 | 1 | 1.19 |
| 9 | 2 | 2.38 |  | 31 | 3 | 3.57 |  | 53 | 3 | 3.57 |
| 10 | 1 | 1.19 |  | 33 | 2 | 2.38 |  | 54 | 1 | 1.19 |
| 11 | 1 | 1.19 |  | 34 | 3 | 3.57 |  | 55 | 2 | 2.38 |
| 12 | 2 | 2.38 |  | 35 | 2 | 2.38 |  |  |  |  |
| 13 | 1 | 1.19 |  | 36 | 3 | 3.57 |  |  |  |  |
| 14 | 2 | 2.38 |  | 37 | 1 | 1.19 |  |  |  |  |
| 17 | 1 | 1.19 |  | 38 | 2 | 2.38 |  |  |  |  |
| 18 | 3 | 3.57 |  | 39 | 3 | 3.57 |  |  |  |  |
| 19 | 2 | 2.38 |  | 41 | 2 | 2.38 |  |  |  |  |
| 20 | 3 | 3.57 |  | 42 | 2 | 2.38 |  |  |  |  |
| 21 | 1 | 1.19 |  | 43 | 1 | 1.19 |  |  |  |  |
| 22 | 2 | 2.38 |  | 44 | 2 | 2.38 |  |  |  |  |
| 23 | 1 | 1.19 |  | 45 | 3 | 3.57 |  |  |  |  |
| 24 | 1 | 1.19 |  | 46 | 1 | 1.19 |  |  |  |  |
| 25 | 1 | 1.19 |  | 47 | 1 | 1.19 |  |  |  |  |

#### Last 60 Days
| result | count | % | -1 | 1result | 1count | 1% | -2 | 2result | 2count | 2% |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 6 | 3.43 |  | 22 | 3 | 1.71 |  | 43 | 1 | 0.57 |
| 2 | 3 | 1.71 |  | 23 | 4 | 2.29 |  | 44 | 2 | 1.14 |
| 3 | 1 | 0.57 |  | 24 | 3 | 1.71 |  | 45 | 4 | 2.29 |
| 4 | 4 | 2.29 |  | 25 | 4 | 2.29 |  | 46 | 2 | 1.14 |
| 5 | 3 | 1.71 |  | 26 | 4 | 2.29 |  | 47 | 1 | 0.57 |
| 6 | 4 | 2.29 |  | 27 | 5 | 2.86 |  | 48 | 3 | 1.71 |
| 7 | 6 | 3.43 |  | 28 | 4 | 2.29 |  | 49 | 2 | 1.14 |
| 9 | 3 | 1.71 |  | 29 | 1 | 0.57 |  | 50 | 5 | 2.86 |
| 10 | 3 | 1.71 |  | 30 | 2 | 1.14 |  | 51 | 3 | 1.71 |
| 11 | 6 | 3.43 |  | 31 | 4 | 2.29 |  | 52 | 4 | 2.29 |
| 12 | 4 | 2.29 |  | 33 | 2 | 1.14 |  | 53 | 4 | 2.29 |
| 13 | 5 | 2.86 |  | 34 | 4 | 2.29 |  | 54 | 2 | 1.14 |
| 14 | 5 | 2.86 |  | 35 | 3 | 1.71 |  | 55 | 3 | 1.71 |
| 15 | 1 | 0.57 |  | 36 | 4 | 2.29 |  |  |  |  |
| 16 | 2 | 1.14 |  | 37 | 2 | 1.14 |  |  |  |  |
| 17 | 3 | 1.71 |  | 38 | 3 | 1.71 |  |  |  |  |
| 18 | 7 | 4.0 |  | 39 | 4 | 2.29 |  |  |  |  |
| 19 | 2 | 1.14 |  | 40 | 1 | 0.57 |  |  |  |  |
| 20 | 4 | 2.29 |  | 41 | 4 | 2.29 |  |  |  |  |
| 21 | 3 | 1.71 |  | 42 | 3 | 1.71 |  |  |  |  |

#### Last 90 Days
| result | count | % | -1 | 1result | 1count | 1% | -2 | 2result | 2count | 2% |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 8 | 3.01 |  | 21 | 6 | 2.26 |  | 41 | 5 | 1.88 |
| 2 | 5 | 1.88 |  | 22 | 4 | 1.5 |  | 42 | 4 | 1.5 |
| 3 | 2 | 0.75 |  | 23 | 5 | 1.88 |  | 43 | 2 | 0.75 |
| 4 | 4 | 1.5 |  | 24 | 7 | 2.63 |  | 44 | 4 | 1.5 |
| 5 | 6 | 2.26 |  | 25 | 7 | 2.63 |  | 45 | 7 | 2.63 |
| 6 | 5 | 1.88 |  | 26 | 5 | 1.88 |  | 46 | 3 | 1.13 |
| 7 | 8 | 3.01 |  | 27 | 7 | 2.63 |  | 47 | 6 | 2.26 |
| 8 | 4 | 1.5 |  | 28 | 5 | 1.88 |  | 48 | 3 | 1.13 |
| 9 | 6 | 2.26 |  | 29 | 3 | 1.13 |  | 49 | 3 | 1.13 |
| 10 | 5 | 1.88 |  | 30 | 2 | 0.75 |  | 50 | 6 | 2.26 |
| 11 | 11 | 4.14 |  | 31 | 7 | 2.63 |  | 51 | 5 | 1.88 |
| 12 | 4 | 1.5 |  | 32 | 2 | 0.75 |  | 52 | 5 | 1.88 |
| 13 | 6 | 2.26 |  | 33 | 3 | 1.13 |  | 53 | 5 | 1.88 |
| 14 | 7 | 2.63 |  | 34 | 5 | 1.88 |  | 54 | 4 | 1.5 |
| 15 | 3 | 1.13 |  | 35 | 3 | 1.13 |  | 55 | 4 | 1.5 |
| 16 | 3 | 1.13 |  | 36 | 6 | 2.26 |  |  |  |  |
| 17 | 5 | 1.88 |  | 37 | 3 | 1.13 |  |  |  |  |
| 18 | 9 | 3.38 |  | 38 | 5 | 1.88 |  |  |  |  |
| 19 | 3 | 1.13 |  | 39 | 5 | 1.88 |  |  |  |  |
| 20 | 4 | 1.5 |  | 40 | 2 | 0.75 |  |  |  |  |

### Top 10 Numbers by Days Since Last Appearance
| result | last_date | days_since |
| --- | --- | --- |
| 8 | 2026-09-08 | 67 |
| 32 | 2026-09-15 | 60 |
| 3 | 2026-09-22 | 53 |
| 15 | 2026-10-01 | 44 |
| 40 | 2026-10-13 | 32 |
| 4 | 2026-10-15 | 30 |
| 16 | 2026-10-17 | 28 |
| 13 | 2026-10-20 | 25 |
| 23 | 2026-10-20 | 25 |
| 30 | 2026-10-20 | 25 |

### Days Since Last Appearance - All Numbers
| result | last_date | days_since |
| --- | --- | --- |
| 1 | 2026-11-10 | 4 |
| 2 | 2026-11-10 | 4 |
| 3 | 2026-09-22 | 53 |
| 4 | 2026-10-15 | 30 |
| 5 | 2026-11-14 | 0 |
| 6 | 2026-11-05 | 9 |
| 7 | 2026-10-24 | 21 |
| 8 | 2026-09-08 | 67 |
| 9 | 2026-10-29 | 16 |
| 10 | 2026-11-03 | 11 |
| 11 | 2026-10-31 | 14 |
| 12 | 2026-11-10 | 4 |
| 13 | 2026-10-20 | 25 |
| 14 | 2026-11-03 | 11 |
| 15 | 2026-10-01 | 44 |
| 16 | 2026-10-17 | 28 |
| 17 | 2026-11-12 | 2 |
| 18 | 2026-10-31 | 14 |
| 19 | 2026-11-07 | 7 |
| 20 | 2026-11-07 | 7 |
| 21 | 2026-11-10 | 4 |
| 22 | 2026-11-03 | 11 |
| 23 | 2026-10-20 | 25 |
| 24 | 2026-10-22 | 23 |
| 25 | 2026-11-12 | 2 |
| 26 | 2026-11-07 | 7 |
| 27 | 2026-10-27 | 18 |
| 28 | 2026-11-14 | 0 |
| 29 | 2026-10-29 | 16 |
| 30 | 2026-10-20 | 25 |
| 31 | 2026-11-03 | 11 |
| 32 | 2026-09-15 | 60 |
| 33 | 2026-11-12 | 2 |
| 34 | 2026-11-12 | 2 |
| 35 | 2026-11-12 | 2 |
| 36 | 2026-11-14 | 0 |
| 37 | 2026-10-22 | 23 |
| 38 | 2026-11-10 | 4 |
| 39 | 2026-11-10 | 4 |
| 40 | 2026-10-13 | 32 |
| 41 | 2026-11-05 | 9 |
| 42 | 2026-11-14 | 0 |
| 43 | 2026-11-03 | 11 |
| 44 | 2026-11-07 | 7 |
| 45 | 2026-11-14 | 0 |
| 46 | 2026-10-29 | 16 |
| 47 | 2026-11-14 | 0 |
| 48 | 2026-11-12 | 2 |
| 49 | 2026-11-05 | 9 |
| 50 | 2026-10-27 | 18 |
| 51 | 2026-11-14 | 0 |
| 52 | 2026-11-05 | 9 |
| 53 | 2026-11-07 | 7 |
| 54 | 2026-11-03 | 11 |
| 55 | 2026-10-31 | 14 |



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

