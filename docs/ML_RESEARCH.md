# Nghiên cứu: công nghệ & Machine Learning cho dự đoán xổ số Vietlott

> Tài liệu này tổng hợp các kỹ thuật dự đoán đã khảo sát, cách repo này hiện thực và đánh giá chúng,
> cùng các kết quả đo được trên dữ liệu thật. Kết quả đầy đủ, cập nhật hằng ngày, xem trên trang
> [Phân tích & Dự đoán](analysis/index.html) (`docs/analysis/`, được deploy lên GitHub Pages tại `/analysis/`).

**Tóm tắt kết luận**

1. Dữ liệu Power 6/55 (1.418 kỳ) và Mega 6/45 (1.386 kỳ) **không lệch có ý nghĩa thống kê khỏi một lồng cầu ngẫu nhiên**.
   Kiểm định đồng đều χ² cho p = 0,41 (6/55) và p = 0,86 (6/45). Kiểm định độc lập giữa hai kỳ liên tiếp cho p = 0,78 (6/55) và p = 0,73 (6/45).
2. Ba mô hình học máy (Logistic Regression, Random Forest, Gradient Boosting) cho **ROC-AUC 0,49 – 0,50** khi đánh giá walk-forward.
   Mức 0,5 tương đương đoán ngẫu nhiên. Log-loss của các mô hình bằng hoặc kém hơn mô hình hằng số `p = 6/N`.
3. Trong backtest 150 kỳ, không chiến lược nào vượt ngưỡng ý nghĩa sau hiệu chỉnh Bonferroni (|z| ≥ 2,87).
   Kỳ vọng hoàn vốn lý thuyết của mọi vé là khoảng **−70%**, bất kể chọn số theo cách nào.
4. Nghiên cứu mở rộng (§5c) so sánh 14 phương pháp, gồm ML huấn luyện lại sau mỗi kỳ, ML đa nguồn (thêm các sản phẩm khác và lịch quay) và ensemble đồng thuận. Mỗi phương pháp mua 10 vé mỗi kỳ trong năm 2026 và được chạy lại 10 lần. Kết quả: **không phương pháp nào vượt ngưỡng ý nghĩa thống kê**, tất cả đều lỗ 80–95%, và phương pháp đứng đầu khác nhau giữa 6/55 và 6/45.
5. Giá trị thực tế của phần "dự đoán" là **một khung đo lường trung thực**: chấm thưởng đúng luật, không nhìn trước tương lai, và luôn so với baseline ngẫu nhiên.
   Khung này không tạo ra lợi thế khi mua vé.

---

## 1. Khảo sát repo tham khảo `thanhnhu/vietlott`

[`thanhnhu/vietlott`](https://github.com/thanhnhu/vietlott) cũng là bản sao của `vietvudanh/vietlott-data`. Repo đó chỉ dùng crawler Python và GitHub Actions, không có crawler Go. Họ bổ sung một tầng dự đoán gọn:

| Thành phần | Ý tưởng | Đánh giá & cách dùng trong repo này |
|---|---|---|
| `datasource.py` | Một điểm nạp dữ liệu duy nhất (jsonl/xlsx), tách số chính khỏi số đặc biệt | Áp dụng: `analysis.prepare_draws()` và `PredictModel._split_bonus()` tách số đặc biệt ngay khi nạp |
| `BaseStrategy._history_before(date)` | Chỉ dùng các kỳ trước ngày dự đoán (causal) | Áp dụng cho mọi chiến lược mới và cho phần đặc trưng ML |
| `FrequencyStrategy` | Tần suất có làm mượt Laplace, lọc vé theo dải tổng và chẵn/lẻ, kèm kiểm định χ² `uniformity_test()` | Lấy ý tưởng kiểm định χ², nhưng **hiệu chỉnh cho việc quay không hoàn lại** (xem §3.1) |
| `PositionalStrategy` | Mô hình hoá riêng từng vị trí đã sắp xếp (order statistic), rồi sinh vé tăng dần | Đã port thành `strategies/positional.py`, dùng phương án histogram |
| `RandomForestStrategy` | `RandomForestRegressor.fit(X, X)`, tức là học ánh xạ đồng nhất từ vé sang vé | **Không áp dụng.** Mục tiêu bằng chính đầu vào nên mô hình không học được quy luật nào về kỳ sau |
| `LSTMStrategy` | Mạng LSTM (TensorFlow) trên ma trận các kỳ, `fit(train, train)` | **Không áp dụng.** Mục tiêu cũng bằng đầu vào và cần TensorFlow (~600 MB). Bài toán dạng chuỗi đã được đánh giá bằng đặc trưng cửa sổ trượt (§2.4) |
| Bảng giải `prices` | `{6: 40 tỷ, 5: 5 tỷ, ...}` | **Sai**, và repo này từng mắc lỗi y hệt (xem §3.3) |

---

## 2. Các họ kỹ thuật dự đoán đã khảo sát

### 2.1 Thống kê tần suất (heuristic)
Gồm số nóng, số lạnh, số lâu chưa về, suy giảm mũ và cặp số hay đi cùng.
- *Giả thuyết:* tần suất trong quá khứ có thông tin về kỳ tới.
- *Thực tế:* với lồng cầu công bằng, mọi bộ số đều có cùng xác suất. "Lâu chưa về" chính là ngộ nhận của người chơi (*gambler's fallacy*).
- *Trong repo:* `frequency.py`, `long_absence.py`, `exponential_decay.py`, `pair_frequency.py`, `not_repeat.py`.

### 2.2 Mô hình xác suất Bayes (Dirichlet – Multinomial)
- Coi xác suất ra của từng số là ẩn, đặt prior Dirichlet(α). Posterior sau T kỳ là `(count_n + α) / (6T + Nα)`.
- Mô hình này chính là "tần suất làm mượt Laplace" của `thanhnhu`. Khi T lớn, posterior hội tụ về `1/N` nếu lồng cầu công bằng, và đó là điều ta quan sát được.

### 2.3 Chuỗi Markov và mẫu khoảng cách
- Chuỗi Markov ước lượng ma trận chuyển `T[a][b]`: số a ở kỳ t được theo sau bởi số b ở kỳ t+1. Mẫu khoảng cách thống kê các khoảng giữa những số liền nhau trong một kỳ.
- Chỉ có tác dụng nếu các kỳ phụ thuộc nhau. Kiểm định số trùng giữa hai kỳ liên tiếp (§3.2) không thấy dấu hiệu phụ thuộc.
- *Trong repo:* `markov_chain.py`, `pattern.py`.

### 2.4 Học có giám sát theo từng số (repo này hiện thực)
Bài toán được đặt lại thành **phân loại nhị phân**:

| Mỗi mẫu | Đặc trưng (chỉ dùng các kỳ < t) | Nhãn |
|---|---|---|
| (kỳ t, số n) | tần suất trong 10/30/100 kỳ gần nhất, tần suất toàn bộ, số kỳ chưa về (chuẩn hoá theo N), có ra ở kỳ t−1 hay không | n có nằm trong 6 số chính của kỳ t không |

- Mô hình: `LogisticRegression` (đã chuẩn hoá đặc trưng), `RandomForestClassifier`, `HistGradientBoostingClassifier` (scikit-learn).
- Huấn luyện **walk-forward**: tại kỳ t chỉ huấn luyện trên các kỳ < t, và huấn luyện lại sau mỗi `refit_every` kỳ.
- Từ xác suất dự đoán sinh ra vé theo hai cách: lấy mẫu không hoàn lại theo trọng số (`selection="sample"`) hoặc lấy 6 số có xác suất cao nhất (`"top"`).
- Cách đặt bài toán này đúng chuẩn hơn `fit(X, X)`. Nó cho phép đo khả năng dự đoán bằng các chỉ số tiêu chuẩn: ROC-AUC, log-loss, Brier và hiệu chuẩn (calibration).
- *Trong repo:* `features.py`, `strategies/ml_classifier.py`.

### 2.5 Học sâu theo chuỗi (LSTM / GRU / Transformer)
- Có thể đưa chuỗi các kỳ (one-hot 55 chiều mỗi kỳ) vào LSTM hoặc Transformer để dự đoán vector xác suất của kỳ tới, huấn luyện bằng binary cross-entropy.
- Về lý thuyết, mạng sâu chỉ khai thác được những phụ thuộc thực sự có trong dữ liệu. Các mô hình tuyến tính và cây với đặc trưng cửa sổ trượt (vốn đã bao phủ tần suất ngắn hạn và dài hạn) cho AUC ≈ 0,5.
  Mạng sâu với ~1.400 mẫu lại rất dễ overfit.
- Vì vậy repo **không thêm TensorFlow hoặc PyTorch**. Nếu muốn thử, nên dùng đúng khung đánh giá ở §3.4 (walk-forward, so log-loss với baseline) thay vì `fit(X, X)`.

### 2.6 Mô phỏng Monte Carlo và "vé đẹp"
- Có thể sinh vé ngẫu nhiên rồi lọc theo dải tổng hoặc tỉ lệ chẵn/lẻ phổ biến (như `FrequencyStrategy(shape=True)` của `thanhnhu`).
- Cách này không đổi xác suất trúng của từng vé. Lợi ích hợp lý duy nhất là **tránh các bộ số nhiều người chọn** (1-2-3-4-5-6, ngày sinh ≤ 31), để nếu trúng jackpot thì ít phải chia giải hơn.

---

## 3. Phương pháp đánh giá (đã hiện thực trong `src/machine_learning/analysis.py`)

### 3.1 Kiểm định đồng đều χ², hiệu chỉnh cho quay không hoàn lại
Mỗi kỳ có đúng 6 số khác nhau, nên số lần xuất hiện của các số tương quan âm với nhau. Với `p = 6/N`, thống kê sau xấp xỉ χ² với N−1 bậc tự do khi lồng cầu công bằng:

```
χ² = Σ (O_n − T·p)² / (T · p · (1−p) · N/(N−1))
```

Nếu dùng công thức χ² thông thường, thống kê sẽ bị lệch (và lệch theo hướng có hệ thống) vì bỏ qua tương quan âm này.

### 3.2 Độc lập giữa hai kỳ liên tiếp
Số trùng giữa kỳ t và kỳ t+1 tuân theo phân phối siêu bội với kỳ vọng `36/N`. Ta làm z-test trên trung bình quan sát được.

### 3.3 Chấm thưởng đúng luật
- Power 6/55 lưu `result = [6 số chính…, số đặc biệt]`. Trước đây code đếm cả số đặc biệt như một số thường, và gán **5 số = 5 tỷ**.
  Lỗi này khiến báo cáo cũ cho ra ROI **+3.647%**.
- Luật đúng với Power 6/55:

| Giải | Điều kiện | Giá trị (mức khởi điểm) |
|---|---|---|
| Jackpot 1 | 6 số chính | 30 tỷ |
| Jackpot 2 | 5 số chính + số đặc biệt | 3 tỷ |
| Giải Nhất | 5 số chính | 40 triệu |
| Giải Nhì | 4 số chính | 500 nghìn |
| Giải Ba | 3 số chính | 50 nghìn |

- Luật đúng với Mega 6/45: Jackpot (6 số) 12 tỷ, Giải Nhất (5 số) 10 triệu, Giải Nhì (4 số) 300 nghìn, Giải Ba (3 số) 30 nghìn.
- Đã sửa trong `games.py`, `strategies/base.py` và `backtest.py`. `StrategyBacktester` trước đây tính chi phí cho `time_predict` vé nhưng chỉ chấm một vé. Nay mọi vé đều được chấm.

### 3.4 Backtest walk-forward và ý nghĩa thống kê
- Mỗi chiến lược mua K vé mỗi kỳ trong W kỳ gần nhất. Chỉ số chính là số trúng trung bình mỗi vé, so với kỳ vọng `36/N`.
- Sai số chuẩn được tính trên trung bình từng kỳ, vì các vé trong cùng một kỳ tương quan với nhau.
- Có 12 chiến lược được so cùng lúc, nên dùng **hiệu chỉnh Bonferroni**: chỉ coi là có ý nghĩa khi |z| ≥ 2,87.
- ROI chỉ dùng để tham khảo. Nó bị chi phối bởi các giải hiếm, nên phương sai rất lớn.

### 3.5 Đánh giá mô hình ML
- So với **baseline hằng số** `p = 6/N`, dùng log-loss và Brier.
- Dùng **ROC-AUC** để đo khả năng xếp hạng số nào dễ ra hơn (0,5 là ngẫu nhiên).
- Xem **calibration** theo 5 nhóm xác suất.
- So **số trúng trung bình khi chọn top-6** với kỳ vọng `36/N`.

---

## 4. Kết quả (snapshot 2026-11-02)

| | Power 6/55 | Mega 6/45 |
|---|---|---|
| Số kỳ | 1.418 | 1.386 |
| χ² đồng đều, p-value | 0,414 | 0,857 |
| Độc lập 2 kỳ liên tiếp, p-value | 0,784 | 0,732 |
| Kỳ vọng hoàn vốn lý thuyết / vé | −70,1% | −71,6% |
| ROC-AUC: Logistic / RF / GBM | 0,504 / 0,488 / 0,505 | 0,492 / 0,487 / 0,492 |
| Log-loss: Logistic so với baseline | 0,34461 so với 0,34461 | 0,39274 so với 0,39267 |
| |z| lớn nhất trong backtest 150 kỳ | 1,79 (Số lạnh, âm) | 1,66 (Lâu chưa về) |

Với cả hai sản phẩm, không có bằng chứng nào cho thấy dữ liệu có cấu trúc khai thác được. Các xác suất mô hình logistic dự đoán cho kỳ tới chỉ nằm trong khoảng 10,5% – 11,2%, sát mức nền 10,9% của 6/55.

---

## 5. Kiến trúc đã hiện thực

```text
data/power655.jsonl, power645.jsonl
        │  analysis.load_draws()  (tách số đặc biệt)
        ▼
features.py ── đặc trưng causal (T+1, N, F)
strategies/*  ── 12 chiến lược, gồm PositionalStrategy và MLClassifierStrategy
games.py      ── luật giải, xác suất siêu bội chính xác, kỳ vọng hoàn vốn
        │
analysis.py   ── tần suất, χ², độc lập, phân phối tổng/chẵn lẻ/nhỏ lớn, cặp số,
        │        backtest walk-forward, đánh giá ML, vé gợi ý
        ▼
render_analysis.py ──▶ docs/analysis/analysis.json + analysis-data.js
        ▼
docs/analysis/index.html  (HTML + SVG thuần, không phụ thuộc thư viện, có dark mode, dùng được trên điện thoại)
```

- Chạy cục bộ:

```bash
make render-analysis
```

  Lệnh này tương đương `uv run --extra ml python src/machine_learning/render_analysis.py`. Sau đó mở `docs/analysis/index.html`.

- Trên CI: workflow **Deploy GitHub Pages** tự sinh lại dữ liệu phân tích mỗi ngày trước khi deploy.

## 5b. Mô phỏng "chơi từ năm 2026"

Mục **Mô phỏng 2026** trên dashboard cho phép bạn chọn chiến lược hoặc mô hình ML (hoặc tự nhập một bộ số), số vé mỗi kỳ (1–10) và ngày bắt đầu (từ 01/01/2026). Trang sẽ tính cho từng kỳ: tiền mua vé, tiền thưởng, lãi/lỗ lũy kế và ROI. Trang cũng hiển thị vé dự đoán cho kỳ tới và xếp hạng mọi chiến lược với cùng thiết lập.

- **Phần sinh vé (Python, chạy trong GitHub Actions):** `analysis.play_simulation()` sinh trước tối đa 10 vé cho mỗi kỳ từ 2026 theo kiểu walk-forward, tức là chỉ dùng các kỳ trước ngày quay. Kết quả được nén thành chuỗi số 2 chữ số trong `analysis-data.js`.
- **Phần tính lợi nhuận (trình duyệt):** chấm vé theo đúng luật giải (số đặc biệt chỉ xét Jackpot 2), với jackpot tính ở mức khởi điểm vì dữ liệu không có giá trị jackpot thực tế từng kỳ.
- Cách làm này không cần server, nên chạy được trên GitHub Pages miễn phí. Kết quả trên trang đã được đối chiếu với cách tính độc lập bằng Python.

Kết quả mẫu (Power 6/55, 130 kỳ từ 01/01/2026, 5 vé mỗi kỳ):
- ML Logistic Regression: chi 6,5 triệu, thu 350 nghìn, ROI **−94,6%**.
- Chiến lược tốt nhất trong bảng xếp hạng: ROI −81,5%.
- Kỳ vọng lý thuyết: −70,1%.

Sai khác giữa các chiến lược chỉ là do may rủi trên số vé nhỏ.

## 5c. Nghiên cứu mở rộng: nhiều nguồn dữ liệu, huấn luyện lại sau mỗi kỳ, bảng so sánh năm 2026

### Câu hỏi
Có phương pháp nào chọn bộ số trúng tốt hơn chọn ngẫu nhiên không, khi dùng thêm nhiều nguồn dữ liệu và huấn luyện lại mô hình sau mỗi kỳ quay mới?

### Các nguồn dữ liệu đã khảo sát
| Nguồn | Có trong repo? | Dùng thế nào |
|---|---|---|
| Lịch sử kỳ quay của chính sản phẩm (vietlott.vn, đồng bộ qua `vietvudanh/vietlott-data`) | Có | Mọi phương pháp |
| Kết quả các sản phẩm khác (6/55, 6/45, 5/35) | Có | Đặc trưng chéo: tần suất của số *n* trong 10/30 kỳ gần nhất của sản phẩm khác, và *n* có ra ở kỳ gần nhất của sản phẩm đó không. Chỉ dùng các kỳ quay **trước** ngày đang xét (`cross_game_features`) |
| Lịch quay | Có (suy ra từ ngày) | Thứ trong tuần, tháng, vị trí của số. Cho phép mô hình cây tìm tương tác số × lịch (`calendar_features`) |
| Kết quả của nhiều phương pháp | Tự sinh | Phương pháp đồng thuận: 6 phương pháp bỏ phiếu cho các số (`ConsensusStrategy`) |
| Repo `thanhnhu/vietlott` | Có | Dữ liệu trùng với repo gốc (cùng nguồn vietlott.vn). Đã lấy ý tưởng chiến lược theo vị trí |
| Giá trị jackpot từng kỳ, số vé bán ra, độ phổ biến của bộ số | **Không** (vietlott.vn không cung cấp dạng mở) | Không ảnh hưởng xác suất ra số. Nếu có thì chỉ giúp ước lượng tiền thưởng (chia jackpot), không giúp đoán số |

### Huấn luyện lại sau mỗi kỳ
- `MLClassifierStrategy` mặc định huấn luyện lại sau **mỗi** kỳ (`refit_every=1`), kể cả khi mô phỏng năm 2026 (mỗi kỳ chỉ học từ các kỳ trước nó).
- Workflow `sync-data.yml` chạy 2 lần/ngày. Khi có kết quả mới, nó chạy `predict_next.py` để huấn luyện lại mọi phương pháp trên toàn bộ dữ liệu, sinh 10 vé cho kỳ tới và ghi vào `predictions/<sản phẩm>.jsonl` (chỉ thêm, không sửa).
- Sau mỗi kỳ quay, dashboard chấm các dự đoán đã ghi trước đó. Đây là kết quả "thật", bổ sung cho mô phỏng.

### Bảng thống kê chung năm 2026 (10 vé/kỳ, 10 lần chạy, snapshot 2026-11-03)
**Power 6/55:** 130 kỳ, chi 13 triệu đồng mỗi lần chạy. Vé ngẫu nhiên trúng trung bình 0,6545 số/vé, ROI kỳ vọng −70,1%.

| # | Phương pháp | Trúng TB/vé | z | ROI TB | ROI thấp → cao |
|---|---|---|---|---|---|
| 1 | Tránh số vừa ra | 0,7022 | +1,08 | −91,7% | −94,2% → −88,1% |
| 2 | Lâu chưa về | 0,7012 | +1,28 | −91,5% | −95,8% → −82,3% |
| 3 | ML: Gradient Boosting | 0,6622 | +1,20 | −91,6% | −95,8% → −83,5% |
| 4 | Chuỗi Markov | 0,6579 | +0,38 | −90,5% | −94,2% → −86,5% |
| 7 | ML đa nguồn (sản phẩm khác + lịch) | 0,6535 | −0,16 | −91,6% | −95,0% → −86,9% |
| 11 | Ngẫu nhiên (baseline) | 0,6518 | −0,42 | −91,1% | −95,4% → −86,9% |
| 12 | Đồng thuận (ensemble) | 0,6509 | −0,36 | −92,4% | −96,2% → −89,2% |
| 13 | ML: Logistic Regression | 0,6460 | −1,30 | −89,6% | −94,6% → −83,1% |

**Mega 6/45:** 131 kỳ. Vé ngẫu nhiên trúng trung bình 0,8000 số/vé, ROI kỳ vọng −71,6%.

| # | Phương pháp | Trúng TB/vé | z | ROI TB | ROI thấp → cao |
|---|---|---|---|---|---|
| 1 | Lâu chưa về | 0,8431 | +1,18 | −88,5% | −92,7% → −84,0% |
| 2 | Theo vị trí | 0,8203 | +1,51 | −90,2% | −93,6% → −85,6% |
| 4 | Đồng thuận (ensemble) | 0,8168 | +1,35 | −86,9% | −92,2% → −79,2% |
| 6 | ML đa nguồn | 0,8021 | +0,31 | −90,4% | −95,2% → −84,7% |
| 12 | Ngẫu nhiên (baseline) | 0,7957 | −0,62 | −88,8% | −94,5% → −83,5% |

Bảng đầy đủ 14 phương pháp, kèm số vé trúng từng giải, xem trên dashboard (mục **Bảng so sánh 2026**).

**Đánh giá ML (walk-forward 300 kỳ, huấn luyện lại sau mỗi 10 kỳ):**

| Mô hình | ROC-AUC 6/55 | ROC-AUC 6/45 |
|---|---|---|
| Logistic Regression | 0,503 | 0,491 |
| Random Forest | 0,492 | 0,485 |
| Gradient Boosting | 0,496 | 0,494 |
| GBM đa nguồn | 0,496 | 0,487 |

Log-loss của mọi mô hình bằng hoặc **kém hơn** mô hình hằng số `p = 6/N`.

### Kết luận: phương pháp nào tốt nhất?
1. **Không có phương pháp nào tốt hơn chọn ngẫu nhiên một cách có ý nghĩa thống kê.**
   - Với 14 phương pháp so sánh cùng lúc, ngưỡng Bonferroni là |z| ≥ 2,91. |z| lớn nhất chỉ là 1,51.
   - Phương pháp đứng đầu khác nhau giữa hai sản phẩm ("Tránh số vừa ra" ở 6/55, "Lâu chưa về" ở 6/45). Đó là dấu hiệu của nhiễu, không phải của một quy luật.
2. **Thêm nguồn dữ liệu không giúp được gì.**
   - Mô hình đa nguồn có AUC ≈ 0,49–0,50 và log-loss kém hơn mô hình chỉ dùng một nguồn: đặc trưng thừa chỉ làm tăng overfit.
   - Điều này đúng với giả thuyết các lồng cầu độc lập nhau.
3. **Ensemble không tạo ra lợi thế.** Kết hợp các phương pháp vốn không có tín hiệu vẫn cho ra một phương pháp không có tín hiệu.
4. **Mọi phương pháp đều lỗ 80–95% số tiền mua vé trong năm 2026.**
   - Mức này còn tệ hơn kỳ vọng lý thuyết −70%, vì kỳ vọng lý thuyết đã tính phần đóng góp của jackpot, mà không phương pháp nào trúng jackpot.
   - Không lần chạy nào có lãi.
5. **Nên dùng tên nào làm "phương pháp tốt nhất"?**
   - Dashboard tự gắn nhãn cho phương pháp đứng đầu bảng (theo số trúng trung bình), kèm cảnh báo "không có ý nghĩa thống kê".
   - Cách duy nhất để biết một phương pháp có lợi thế thật là theo dõi **nhật ký dự đoán** qua nhiều kỳ trong tương lai. Kỳ vọng là thứ hạng sẽ xáo trộn liên tục.

## 5d. Gợi ý trên trang chủ: 20 bộ "xác suất cao nhất" và 10 bộ "dễ trúng nhất"

- **20 bộ có xác suất ra cao nhất (theo mô hình):**
  - Lấy trung bình xác suất ra của từng số từ 3 mô hình ML (Logistic, Gradient Boosting, ML đa nguồn), được huấn luyện lại trên toàn bộ dữ liệu sau mỗi kỳ.
  - Coi các số là độc lập: điểm của một bộ là tổng log xác suất của 6 số. Xét mọi tổ hợp 6 số trong 14 số có xác suất cao nhất, rồi lấy 20 bộ điểm cao nhất (`top_probability_tickets`).
  - Hệ số `×r` là mức cao hơn vé ngẫu nhiên *theo mô hình*. Thực tế r chỉ khoảng 1,0–1,2, vì các mô hình gần như không phân biệt được số nào dễ ra hơn (AUC ≈ 0,5).
- **10 bộ dễ trúng nhất:**
  - Là 10 vé kỳ tới của phương pháp đứng đầu bảng so sánh năm 2026 (nhiều số trúng nhất mỗi vé khi chơi 10 vé mỗi kỳ).
  - Hiện là "Tránh số vừa ra" cho 6/55 và "Lâu chưa về" cho 6/45.
- **Ghi lại và thẩm định:**
  - Cả 30 bộ được ghi vào nhật ký trước giờ quay (`picks_top20`, `picks_best10`) và được chấm tự động khi có kết quả.
  - Trang chủ hiển thị kết quả thẩm định kỳ trước và kết quả lũy kế.
  - Đây là cách trung thực để kiểm chứng: nếu các bộ "xác suất cao" không thực sự trúng nhiều hơn vé ngẫu nhiên qua nhiều kỳ, chúng không có giá trị dự đoán.

## 5e. Chiến lược "Kết hợp 5 ROI cao nhất" và phân tích từ 01/01/2025 đến nay

### Cách hoạt động (`top5_roi`)
- Trước **mỗi kỳ quay**, xếp hạng 14 phương pháp còn lại theo lãi/lỗ tích lũy (cùng số vé nên tương đương ROI) của chính các vé chúng đã mua ở các kỳ **trước đó**.
- Có 30 kỳ "khởi động" trước 01/01/2025 để chiến lược có bảng xếp hạng ngay từ kỳ đầu.
- Lấy 2 vé của mỗi phương pháp trong top 5, được 10 vé.
- Vé cho kỳ tới lấy từ top 5 theo ROI trung bình của cả giai đoạn. Danh sách top 5 được ghi kèm trong nhật ký dự đoán.
- Có test kiểm tra không nhìn trước kết quả: đổi kết quả kỳ cuối thì vé của chiến lược không đổi.

### Kết quả (10 vé/kỳ, 5 lần chạy, 2025-01-01 → 2026-11, snapshot 2026-11-03)
| | Power 6/55 (285 kỳ) | Mega 6/45 (287 kỳ) |
|---|---|---|
| Vé ngẫu nhiên kỳ vọng | 0,6545 số/vé, ROI −70,1% | 0,8000 số/vé, ROI −71,6% |
| Đứng đầu (trúng TB/vé) | Tránh số vừa ra 0,6839 (z +0,95) | Lâu chưa về 0,8281 (z +1,08) |
| \|z\| lớn nhất | 1,52 (Mẫu khoảng cách, âm) | 2,22 (Theo vị trí) |
| Ngưỡng Bonferroni (15 phương pháp) | 2,94 | 2,94 |
| **Kết hợp 5 ROI cao nhất** | hạng 6/15: 0,6594 số/vé, ROI −90,1% | hạng 12/15: 0,7981 số/vé, ROI −90,0% |
| Ngẫu nhiên (baseline) | hạng 5: 0,6596, ROI −89,6% | hạng 11: 0,7990, ROI −89,7% |
| Lần chạy có lãi | 2/75 (Cặp số và Số lạnh, mỗi phương pháp 1 lần, nhờ trúng Giải Nhất 40 triệu) | 0/75 |

### Nhận xét
1. **Kết hợp 5 ROI cao nhất không tốt hơn chọn ngẫu nhiên**, và cũng không tốt hơn từng phương pháp thành phần.
   - Xếp hạng theo ROI chủ yếu bám theo các lần trúng Giải Nhì/Nhất hiếm hoi, tức là bám theo may rủi.
   - Ở lần chạy 1 của 6/55, chính phương pháp **Ngẫu nhiên** nằm trong top 5 ở cả 285 kỳ.
   - Nói cách khác, "chọn phương pháp đang thắng" không có quán tính: phương pháp ROI cao ở các kỳ trước không tiếp tục cao ở kỳ sau.
2. Mở rộng dữ liệu từ 2025 (gấp đôi số kỳ) không thay đổi kết luận của §5c. Không phương pháp nào vượt ngưỡng ý nghĩa thống kê, và phương pháp đứng đầu vẫn khác nhau giữa 6/55 và 6/45.
3. Hai lần chạy có lãi (+48–50%) đều đến từ **một** vé trúng Giải Nhất trong khoảng 2.850 vé. Đây là ví dụ điển hình cho thấy ROI dao động rất mạnh và không thể dùng ROI của vài trăm kỳ để chọn chiến lược.

## 6. Hướng phát triển đề xuất

- Thêm Power 5/35 làm sản phẩm được dự đoán (hiện chỉ dùng làm nguồn dữ liệu phụ) sau khi xác nhận cơ cấu giải chính thức. Keno và Bingo18 cũng cần định nghĩa `GameSpec` riêng.
- Tính kiểm định χ² theo cửa sổ trượt để phát hiện thay đổi lồng cầu hoặc bộ bi theo thời gian. Đây là ứng dụng thống kê hữu ích nhất của bộ dữ liệu.
- Thêm phân tích "độ phổ biến của vé", tức tránh các bộ số nhiều người chọn để giảm rủi ro chia jackpot. Đây là cách duy nhất có cơ sở để cải thiện kỳ vọng khi trúng.
- Nếu thử LSTM hoặc Transformer: dùng PyTorch dưới dạng extra tuỳ chọn, giữ nguyên khung walk-forward và baseline log-loss ở §3.5.
