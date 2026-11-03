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
4. Giá trị thực tế của phần "dự đoán" là **một khung đo lường trung thực**: chấm thưởng đúng luật, không nhìn trước tương lai, và luôn so với baseline ngẫu nhiên.
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

## 6. Hướng phát triển đề xuất

- Thêm Power 5/35 sau khi xác nhận cơ cấu giải chính thức. Keno và Bingo18 cũng cần định nghĩa `GameSpec` riêng.
- Tính kiểm định χ² theo cửa sổ trượt để phát hiện thay đổi lồng cầu hoặc bộ bi theo thời gian. Đây là ứng dụng thống kê hữu ích nhất của bộ dữ liệu.
- Thêm phân tích "độ phổ biến của vé", tức tránh các bộ số nhiều người chọn để giảm rủi ro chia jackpot. Đây là cách duy nhất có cơ sở để cải thiện kỳ vọng khi trúng.
- Nếu thử LSTM hoặc Transformer: dùng PyTorch dưới dạng extra tuỳ chọn, giữ nguyên khung walk-forward và baseline log-loss ở §3.5.
