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
| Power 655 | 1426 | 2017-08-01 | 2026-11-19 | 1426 | 00001 | 01426 |
| Power 645 | 1394 | 2017-10-25 | 2026-11-20 | 1394 | 00198 | 01591 |
| Power 535 | 510 | 2025-06-29 | 2026-11-20 | 1019 | 00001 | 01019 |
| Keno | 743 | 2022-12-04 | 2026-11-20 | 92676 | #0110271 | #0303687 |
| 3D | 1161 | 2019-04-22 | 2026-11-20 | 1161 | 00001 | 01161 |
| 3D Pro | 807 | 2021-09-14 | 2026-11-19 | 807 | 00001 | 00807 |
| Bingo18 | 716 | 2024-12-03 | 2026-11-20 | 101303 | 0083123 | 0197139 |

## Power 6/55 Analysis

### Recent Results (Last 10 draws)
| date | id | result | process_time |
| --- | --- | --- | --- |
| 2026-11-19 | 01426 | [3, 13, 21, 23, 38, 43, 16] | 2026-11-19T12:00:05Z |
| 2026-11-17 | 01425 | [6, 20, 36, 41, 49, 52, 34] | 2026-11-18T00:00:05Z |
| 2026-11-14 | 01424 | [5, 28, 36, 42, 45, 47, 51] | 2026-11-14T12:00:05Z |
| 2026-11-12 | 01423 | [17, 25, 33, 34, 35, 36, 48] | 2026-11-12T12:00:05Z |
| 2026-11-10 | 01422 | [1, 2, 21, 38, 39, 51, 12] | 2026-11-10T12:00:05Z |
| 2026-11-07 | 01421 | [5, 19, 20, 26, 44, 53, 39] | 2026-11-07T12:00:05Z |
| 2026-11-05 | 01420 | [6, 20, 34, 41, 49, 52, 36] | 2026-11-05T12:00:05Z |
| 2026-11-03 | 01419 | [10, 22, 31, 39, 43, 54, 14] | 2026-11-03T12:00:05Z |
| 2026-10-31 | 01418 | [12, 18, 22, 26, 28, 55, 11] | 2026-10-31T12:00:05Z |
| 2026-10-29 | 01417 | [9, 29, 33, 38, 45, 46, 53] | 2026-10-29T12:00:05Z |

### Number Frequency (All Time)
| result | count | % | -1 | 1result | 1count | 1% | -2 | 2result | 2count | 2% |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 194 | 1.94 |  | 21 | 179 | 1.79 |  | 41 | 211 | 2.11 |
| 2 | 165 | 1.65 |  | 22 | 210 | 2.1 |  | 42 | 184 | 1.84 |
| 3 | 191 | 1.91 |  | 23 | 193 | 1.93 |  | 43 | 201 | 2.01 |
| 4 | 148 | 1.48 |  | 24 | 183 | 1.83 |  | 44 | 184 | 1.84 |
| 5 | 186 | 1.86 |  | 25 | 165 | 1.65 |  | 45 | 186 | 1.86 |
| 6 | 149 | 1.49 |  | 26 | 170 | 1.7 |  | 46 | 184 | 1.84 |
| 7 | 164 | 1.64 |  | 27 | 169 | 1.69 |  | 47 | 181 | 1.81 |
| 8 | 196 | 1.96 |  | 28 | 163 | 1.63 |  | 48 | 193 | 1.93 |
| 9 | 198 | 1.98 |  | 29 | 192 | 1.92 |  | 49 | 177 | 1.77 |
| 10 | 169 | 1.69 |  | 30 | 164 | 1.64 |  | 50 | 183 | 1.83 |
| 11 | 190 | 1.9 |  | 31 | 192 | 1.92 |  | 51 | 201 | 2.01 |
| 12 | 184 | 1.84 |  | 32 | 188 | 1.88 |  | 52 | 183 | 1.83 |
| 13 | 179 | 1.79 |  | 33 | 182 | 1.82 |  | 53 | 192 | 1.92 |
| 14 | 184 | 1.84 |  | 34 | 201 | 2.01 |  | 54 | 171 | 1.71 |
| 15 | 168 | 1.68 |  | 35 | 173 | 1.73 |  | 55 | 182 | 1.82 |
| 16 | 178 | 1.78 |  | 36 | 173 | 1.73 |  |  |  |  |
| 17 | 164 | 1.64 |  | 37 | 161 | 1.61 |  |  |  |  |
| 18 | 185 | 1.85 |  | 38 | 177 | 1.77 |  |  |  |  |
| 19 | 176 | 1.76 |  | 39 | 176 | 1.76 |  |  |  |  |
| 20 | 194 | 1.94 |  | 40 | 195 | 1.95 |  |  |  |  |

### Frequency Analysis by Period

#### Last 30 Days
| result | count | % | -1 | 1result | 1count | 1% | -2 | 2result | 2count | 2% |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 1 | 1.1 |  | 24 | 1 | 1.1 |  | 47 | 1 | 1.1 |
| 2 | 1 | 1.1 |  | 25 | 1 | 1.1 |  | 48 | 1 | 1.1 |
| 3 | 1 | 1.1 |  | 26 | 2 | 2.2 |  | 49 | 2 | 2.2 |
| 5 | 2 | 2.2 |  | 27 | 1 | 1.1 |  | 50 | 2 | 2.2 |
| 6 | 3 | 3.3 |  | 28 | 3 | 3.3 |  | 51 | 2 | 2.2 |
| 7 | 1 | 1.1 |  | 29 | 1 | 1.1 |  | 52 | 2 | 2.2 |
| 9 | 2 | 2.2 |  | 31 | 3 | 3.3 |  | 53 | 3 | 3.3 |
| 10 | 1 | 1.1 |  | 33 | 2 | 2.2 |  | 54 | 1 | 1.1 |
| 11 | 1 | 1.1 |  | 34 | 4 | 4.4 |  | 55 | 1 | 1.1 |
| 12 | 2 | 2.2 |  | 35 | 2 | 2.2 |  |  |  |  |
| 13 | 1 | 1.1 |  | 36 | 4 | 4.4 |  |  |  |  |
| 14 | 2 | 2.2 |  | 37 | 1 | 1.1 |  |  |  |  |
| 16 | 1 | 1.1 |  | 38 | 3 | 3.3 |  |  |  |  |
| 17 | 1 | 1.1 |  | 39 | 3 | 3.3 |  |  |  |  |
| 18 | 3 | 3.3 |  | 41 | 3 | 3.3 |  |  |  |  |
| 19 | 2 | 2.2 |  | 42 | 2 | 2.2 |  |  |  |  |
| 20 | 3 | 3.3 |  | 43 | 2 | 2.2 |  |  |  |  |
| 21 | 2 | 2.2 |  | 44 | 2 | 2.2 |  |  |  |  |
| 22 | 2 | 2.2 |  | 45 | 2 | 2.2 |  |  |  |  |
| 23 | 1 | 1.1 |  | 46 | 1 | 1.1 |  |  |  |  |

#### Last 60 Days
| result | count | % | -1 | 1result | 1count | 1% | -2 | 2result | 2count | 2% |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 6 | 3.3 |  | 22 | 2 | 1.1 |  | 43 | 2 | 1.1 |
| 2 | 3 | 1.65 |  | 23 | 5 | 2.75 |  | 44 | 2 | 1.1 |
| 3 | 2 | 1.1 |  | 24 | 3 | 1.65 |  | 45 | 4 | 2.2 |
| 4 | 3 | 1.65 |  | 25 | 3 | 1.65 |  | 46 | 2 | 1.1 |
| 5 | 3 | 1.65 |  | 26 | 4 | 2.2 |  | 47 | 1 | 0.55 |
| 6 | 5 | 2.75 |  | 27 | 5 | 2.75 |  | 48 | 3 | 1.65 |
| 7 | 5 | 2.75 |  | 28 | 4 | 2.2 |  | 49 | 3 | 1.65 |
| 9 | 3 | 1.65 |  | 29 | 1 | 0.55 |  | 50 | 4 | 2.2 |
| 10 | 3 | 1.65 |  | 30 | 2 | 1.1 |  | 51 | 3 | 1.65 |
| 11 | 5 | 2.75 |  | 31 | 4 | 2.2 |  | 52 | 5 | 2.75 |
| 12 | 4 | 2.2 |  | 33 | 2 | 1.1 |  | 53 | 4 | 2.2 |
| 13 | 6 | 3.3 |  | 34 | 5 | 2.75 |  | 54 | 2 | 1.1 |
| 14 | 5 | 2.75 |  | 35 | 3 | 1.65 |  | 55 | 3 | 1.65 |
| 15 | 1 | 0.55 |  | 36 | 5 | 2.75 |  |  |  |  |
| 16 | 3 | 1.65 |  | 37 | 2 | 1.1 |  |  |  |  |
| 17 | 3 | 1.65 |  | 38 | 4 | 2.2 |  |  |  |  |
| 18 | 6 | 3.3 |  | 39 | 4 | 2.2 |  |  |  |  |
| 19 | 2 | 1.1 |  | 40 | 1 | 0.55 |  |  |  |  |
| 20 | 5 | 2.75 |  | 41 | 5 | 2.75 |  |  |  |  |
| 21 | 4 | 2.2 |  | 42 | 3 | 1.65 |  |  |  |  |

#### Last 90 Days
| result | count | % | -1 | 1result | 1count | 1% | -2 | 2result | 2count | 2% |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 8 | 2.93 |  | 21 | 7 | 2.56 |  | 41 | 6 | 2.2 |
| 2 | 4 | 1.47 |  | 22 | 4 | 1.47 |  | 42 | 4 | 1.47 |
| 3 | 3 | 1.1 |  | 23 | 6 | 2.2 |  | 43 | 3 | 1.1 |
| 4 | 4 | 1.47 |  | 24 | 7 | 2.56 |  | 44 | 4 | 1.47 |
| 5 | 6 | 2.2 |  | 25 | 7 | 2.56 |  | 45 | 7 | 2.56 |
| 6 | 6 | 2.2 |  | 26 | 5 | 1.83 |  | 46 | 3 | 1.1 |
| 7 | 8 | 2.93 |  | 27 | 7 | 2.56 |  | 47 | 5 | 1.83 |
| 8 | 3 | 1.1 |  | 28 | 5 | 1.83 |  | 48 | 3 | 1.1 |
| 9 | 6 | 2.2 |  | 29 | 2 | 0.73 |  | 49 | 4 | 1.47 |
| 10 | 5 | 1.83 |  | 30 | 2 | 0.73 |  | 50 | 6 | 2.2 |
| 11 | 11 | 4.03 |  | 31 | 7 | 2.56 |  | 51 | 4 | 1.47 |
| 12 | 4 | 1.47 |  | 32 | 2 | 0.73 |  | 52 | 6 | 2.2 |
| 13 | 7 | 2.56 |  | 33 | 3 | 1.1 |  | 53 | 5 | 1.83 |
| 14 | 7 | 2.56 |  | 34 | 6 | 2.2 |  | 54 | 4 | 1.47 |
| 15 | 3 | 1.1 |  | 35 | 3 | 1.1 |  | 55 | 4 | 1.47 |
| 16 | 4 | 1.47 |  | 36 | 7 | 2.56 |  |  |  |  |
| 17 | 5 | 1.83 |  | 37 | 3 | 1.1 |  |  |  |  |
| 18 | 9 | 3.3 |  | 38 | 5 | 1.83 |  |  |  |  |
| 19 | 3 | 1.1 |  | 39 | 4 | 1.47 |  |  |  |  |
| 20 | 5 | 1.83 |  | 40 | 2 | 0.73 |  |  |  |  |

### Top 10 Numbers by Days Since Last Appearance
| result | last_date | days_since |
| --- | --- | --- |
| 8 | 2026-09-08 | 72 |
| 32 | 2026-09-15 | 65 |
| 15 | 2026-10-01 | 49 |
| 40 | 2026-10-13 | 37 |
| 4 | 2026-10-15 | 35 |
| 30 | 2026-10-20 | 30 |
| 24 | 2026-10-22 | 28 |
| 37 | 2026-10-22 | 28 |
| 7 | 2026-10-24 | 26 |
| 27 | 2026-10-27 | 23 |

### Days Since Last Appearance - All Numbers
| result | last_date | days_since |
| --- | --- | --- |
| 1 | 2026-11-10 | 9 |
| 2 | 2026-11-10 | 9 |
| 3 | 2026-11-19 | 0 |
| 4 | 2026-10-15 | 35 |
| 5 | 2026-11-14 | 5 |
| 6 | 2026-11-17 | 2 |
| 7 | 2026-10-24 | 26 |
| 8 | 2026-09-08 | 72 |
| 9 | 2026-10-29 | 21 |
| 10 | 2026-11-03 | 16 |
| 11 | 2026-10-31 | 19 |
| 12 | 2026-11-10 | 9 |
| 13 | 2026-11-19 | 0 |
| 14 | 2026-11-03 | 16 |
| 15 | 2026-10-01 | 49 |
| 16 | 2026-11-19 | 0 |
| 17 | 2026-11-12 | 7 |
| 18 | 2026-10-31 | 19 |
| 19 | 2026-11-07 | 12 |
| 20 | 2026-11-17 | 2 |
| 21 | 2026-11-19 | 0 |
| 22 | 2026-11-03 | 16 |
| 23 | 2026-11-19 | 0 |
| 24 | 2026-10-22 | 28 |
| 25 | 2026-11-12 | 7 |
| 26 | 2026-11-07 | 12 |
| 27 | 2026-10-27 | 23 |
| 28 | 2026-11-14 | 5 |
| 29 | 2026-10-29 | 21 |
| 30 | 2026-10-20 | 30 |
| 31 | 2026-11-03 | 16 |
| 32 | 2026-09-15 | 65 |
| 33 | 2026-11-12 | 7 |
| 34 | 2026-11-17 | 2 |
| 35 | 2026-11-12 | 7 |
| 36 | 2026-11-17 | 2 |
| 37 | 2026-10-22 | 28 |
| 38 | 2026-11-19 | 0 |
| 39 | 2026-11-10 | 9 |
| 40 | 2026-10-13 | 37 |
| 41 | 2026-11-17 | 2 |
| 42 | 2026-11-14 | 5 |
| 43 | 2026-11-19 | 0 |
| 44 | 2026-11-07 | 12 |
| 45 | 2026-11-14 | 5 |
| 46 | 2026-10-29 | 21 |
| 47 | 2026-11-14 | 5 |
| 48 | 2026-11-12 | 7 |
| 49 | 2026-11-17 | 2 |
| 50 | 2026-10-27 | 23 |
| 51 | 2026-11-14 | 5 |
| 52 | 2026-11-17 | 2 |
| 53 | 2026-11-07 | 12 |
| 54 | 2026-11-03 | 16 |
| 55 | 2026-10-31 | 19 |



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

