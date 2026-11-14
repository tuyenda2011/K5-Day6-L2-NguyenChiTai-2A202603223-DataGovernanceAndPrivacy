# T12 — Vendor Batch Acceptance: báo cáo triển khai

Pipeline của nhóm đã chạy được trọn vẹn từ đầu đến cuối ở chế độ offline. Tuy nhiên nhóm chưa có bộ nhãn
của giảng viên, nên toàn bộ số liệu trong báo cáo này đến từ nhãn do nhóm tự mô phỏng (các file đều có tiền tố
`simulated_*`), chưa phải điểm chấm chính thức.
Cách tính metric và lịch sử thay đổi protocol (v1, v2, v3) được ghi trong [metric_contract.md](metric_contract.md).

## 1. Bài toán và dữ liệu

Mỗi batch của vendor có 100 mẫu, nhưng nhóm chỉ được kiểm tối đa 20 mẫu. Từ 20 mẫu đó, pipeline phải ước lượng
tỉ lệ lỗi của cả batch, cho biết ước lượng chắc chắn đến đâu, đưa những batch chưa rõ ràng cho người xem lại,
rồi chốt một trong ba quyết định ACCEPT, REWORK hoặc HOLD.

Ba loại sai có hậu quả khác nhau. ACCEPT nhầm một batch xấu là nặng nhất, vì nhãn lỗi sẽ đi thẳng vào các bước sau.
REWORK nhầm một batch tốt làm vendor tốn công sửa lại. Còn nếu HOLD quá nhiều thì việc nghiệm thu bị tắc.
Đây là PoC phục vụ học tập, nhóm không tuyên bố nó đáp ứng yêu cầu pháp lý nào.

Dữ liệu đầu vào nằm trong `fixtures/t12_vendor_batches`: 5 batch, mỗi batch 100 mẫu, là dữ liệu tổng hợp theo giấy
phép CC0. Mỗi mẫu có `risk_tag` thuộc một trong bốn nhóm. Nhóm normal chiếm đông nhất (48–66 mẫu mỗi batch),
sau đó là night (12–27), occlusion (11–20) và small_object (8–11). Trước khi chạy, pipeline kiểm tra sha256 trong
`manifest.csv`. Ngưỡng 5%, budget 20 mẫu và độ tin cậy 95% được đọc từ `acceptance_policy.yaml`.
Nhóm không dùng ảnh thật, không tải thêm dữ liệu và không dùng model có sẵn nào.

## 2. Cách làm

Pipeline gồm năm bước theo đúng đề, cài trong `src/tracks/t12.py`.

**Bước 1: Đọc dữ liệu.** Pipeline kiểm tra manifest, schema, ID bị trùng hoặc bị trống, rồi đọc policy.
Nếu config ghi khác policy, nhóm luôn theo policy và ghi lại điểm khác biệt vào audit log.

**Bước 2: Chọn mẫu.** Toàn bộ danh sách mẫu cần kiểm được chốt và băm hash trước khi xem bất kỳ nhãn nào
(`audit_selection.csv`). Baseline chọn ngẫu nhiên đơn giản 20 mẫu. PoC chia theo `risk_tag`: mỗi nhóm có ít nhất
một mẫu, số còn lại chia theo kích thước của nhóm.

**Bước 3: Ước lượng.** Nhãn chỉ được lấy qua `AuditOracle`, và oracle sẽ từ chối khi vượt budget. Tỉ lệ lỗi được
ước lượng bằng trung bình có trọng số giữa các nhóm, trọng số là tỉ lệ kích thước của từng nhóm trong batch.
Khoảng tin cậy 95% được tính chính xác cho quần thể hữu hạn (lấy mẫu không hoàn lại). Với PoC, khoảng này được
ghép từ khoảng của từng nhóm theo cách Bonferroni nên khá rộng; nhóm chỉ dùng nó để báo cáo.

**Bước 4: Người xem lại.** Pipeline tạo `review_queue.csv` và `contact_sheet.html`, trong đó batch HOLD xếp lên đầu.
Muốn sửa quyết định thì phải ghi tên người duyệt và lý do. Người duyệt không được chuyển một batch sang ACCEPT
khi bằng chứng chưa đủ. File review cũ không khớp với kế hoạch lấy mẫu hiện tại sẽ bị từ chối, và mọi thay đổi
đều được ghi vào `audit_log.jsonl`.

**Bước 5: Ra quyết định.** Phiên bản đầu dựa thẳng vào khoảng tin cậy. Vì khoảng của PoC quá rộng nên ở v3 nhóm
chuyển sang kiểm định trực tiếp tại ngưỡng 5% (hàm `threshold_test`). Với batch 100 mẫu, mức 5% tương ứng tối đa
5 lỗi. Để quyết định REWORK, nhóm giả sử batch chỉ có 5 lỗi, xét mọi cách phân bố 5 lỗi đó vào các nhóm, rồi tính
xác suất lớn nhất để thấy kết quả "xấu" như mẫu đã quan sát (`p_rework`). Nếu ngay cả trường hợp bất lợi nhất này
vẫn dưới 2,5% thì mới REWORK. ACCEPT làm tương tự với giả sử batch có 6 lỗi (`p_accept`).
Hai trường hợp còn lại là HOLD. Mức sai 2,5% cho mỗi chiều giống hệt quy tắc khoảng tin cậy 95% cũ, nên rủi ro
không bị nới ra; điểm khác là không còn phải chia nhỏ mức sai cho từng nhóm. Mỗi batch đều có `reason_code`
và `owner`. Guardrail HOLD ≤ 0,4 chỉ được báo cáo, nhóm không ép đổi HOLD sang quyết định khác để qua guardrail.

Nhóm kiểm tra cách làm này bằng test. Khi liệt kê hết mọi khả năng trên một quần thể nhỏ, xác suất ra quyết định
sai lớn nhất là 0,0179, dưới mức cho phép 0,025, và cả ba loại quyết định đều xuất hiện. Khi chỉ có một nhóm
(trường hợp baseline), kiểm định cho kết quả trùng khớp với quy tắc cũ ở mọi số lỗi, với N = 30, 50, 100 và 1000.
Nhóm cũng có một ví dụ cụ thể trong đó cách Bonferroni ra HOLD còn kiểm định mới ra REWORK. Batch 1000 mẫu tính
mất khoảng 0,3 giây. Nếu phép liệt kê quá lớn, pipeline tự quay về quy tắc cũ và ghi `decision_method = bonferroni_ci`.

## 3. Giới hạn của budget 20 trên 100 mẫu

Bảng dưới là khoảng tin cậy 95% khi chọn ngẫu nhiên 20 trong 100 mẫu, tính bằng hàm `finite_interval`:

| Số lỗi thấy được | 0 | 1 | 2 | 3 | 4 | 5 |
|---|---|---|---|---|---|---|
| Khoảng tin cậy | [0; 0,15] | [0,01; 0,22] | [0,02; 0,29] | [0,05; 0,35] | [0,07; 0,41] | [0,10; 0,46] |
| Quyết định | HOLD | HOLD | HOLD | HOLD | REWORK | REWORK |

Kể cả khi không thấy lỗi nào, cận trên vẫn là 15%, cao hơn hẳn ngưỡng 5%. Nói cách khác, với budget này không
batch nào có thể được ACCEPT. Batch tốt sẽ luôn rơi vào HOLD, nên guardrail HOLD ≤ 0,4 chỉ đạt được khi ít nhất
60% số batch xấu rõ ràng. Đây là giới hạn của budget chứ không phải lỗi cài đặt, và nhóm không hạ ngưỡng để qua guardrail.

## 4. Kết quả trên dữ liệu mô phỏng

Nhóm tạo nhãn mô phỏng cho 5 batch với tỉ lệ lỗi thật lần lượt 1%, 3%, 8%, 15% và 30%. Lỗi được cho tập trung hơn
ở các nhóm rủi ro (trọng số ghi trong [SIMULATED_DATA.json](t12_simulated/SIMULATED_DATA.json)).
Đây không phải tập kiểm tra của giảng viên.

Phép so sánh chính dùng 100 seed (từ 1000 đến 1099). Nhóm chốt bộ seed này trước khi chạy v3, chưa từng dùng nó
khi thiết kế, và giữ lại kết quả của tất cả các seed. Số liệu đầy đủ ở
[study_summary_seeds1000-1099.csv](t12_simulated/study_summary_seeds1000-1099.csv); bảng dưới ghi trung bình ± sai số chuẩn.

| Phương án | MAE | Tỉ lệ HOLD | CI coverage | Bỏ lọt batch xấu | Số mẫu kiểm/batch |
|---|---|---|---|---|---|
| Baseline (ngẫu nhiên) | 0,0477 ± 0,0015 | 0,754 ± 0,011 | 0,988 ± 0,005 | 0 | 20,00 |
| **PoC v3** | 0,0427 ± 0,0016 | 0,742 ± 0,012 | 1,000 ± 0,000 | 0 | 20,00 |
| Chia đều theo nhóm (ablation) | 0,0482 ± 0,0016 | 0,832 ± 0,013 | 1,000 ± 0,000 | 0 | 20,00 |
| Kiểm tuần tự [15, 20] | 0,0460 ± 0,0018 | 0,742 ± 0,012 | 1,000 ± 0,000 | 0 | 19,14 |
| Luôn HOLD (đối chứng) | 0,0477 | 1,000 | 0,988 | 0 | 20,00 |
| Luôn REWORK (đối chứng) | 0,0477 | 0,000 | 0,988 | 0 | 20,00 (REWORK nhầm 100%) |

So từng cặp trên cùng seed, MAE của PoC thấp hơn baseline trung bình 0,0051 (sai số chuẩn 0,0021) và tốt hơn ở
59/100 seed. Tỉ lệ HOLD thấp hơn 0,012 (sai số chuẩn 0,017): 30 seed tốt hơn, 27 seed kém hơn, 43 seed bằng nhau.
Không phương án nào REWORK nhầm hay để lọt batch xấu. Guardrail HOLD ≤ 0,4 đạt ở 0/100 seed với baseline
và 1/100 seed với PoC.

Nhóm cũng giữ lại kết quả trên 20 seed đầu tiên (42–61, [summary](t12_simulated/study_summary_dev_seeds42-61.csv)).
Bộ seed này đã được dùng trong lúc thiết kế nên chỉ mang tính tham khảo. Trên đó PoC lại có MAE kém hơn baseline
0,0048 (sai số chuẩn 0,0050, kém hơn ở 13/20 seed). Tỉ lệ HOLD giảm từ 0,84 ở v2 xuống 0,75 ở v3, trong khi baseline
giữ nguyên 0,78 ở cả hai phiên bản.

Riêng seed 42 ([bảng so sánh](t12_simulated/table_baseline_vs_poc.md) do `src.compare` sinh ra): MAE giảm từ 0,0600
xuống 0,0421, Bad-batch Recall cùng bằng 1,0, tỉ lệ HOLD cùng là 0,8 (cả hai đều không qua guardrail), còn CI coverage
tăng từ 0,8 lên 1,0.

Từ các kết quả trên, nhóm rút ra mấy điểm sau, tất cả đều chỉ đúng trong phạm vi dữ liệu mô phỏng:

- PoC ước lượng chính xác hơn baseline khoảng 0,005 MAE, chênh chừng 2,4 lần sai số chuẩn trên 100 seed mới.
  Trên 20 seed đầu kết quả lại ngược chiều, cho thấy với số lần lặp ít như vậy thì chênh lệch vẫn nằm trong nhiễu.
  Vì vậy không nên dựa vào riêng seed 42 để kết luận.
- Đổi sang kiểm định ở v3 đã xoá được phần HOLD thừa do cách Bonferroni gây ra. Tuy vậy PoC chỉ ngang baseline
  về tỉ lệ HOLD, chưa tốt hơn rõ rệt.
- Kiểm định mới không phải lúc nào cũng tốt hơn. Với cách chia đều (nhóm lớn chỉ có ít mẫu), trường hợp bất lợi nhất
  bị đẩy lên cao, khiến tỉ lệ HOLD tăng lên 0,83 và kém hơn cả baseline.
- Kiểm tuần tự tiết kiệm được khoảng 4% số mẫu (19,14 thay vì 20) mà tỉ lệ HOLD không đổi. Ước lượng tại thời điểm
  dừng có thể bị lệch nên nhóm báo cáo riêng phương án này.
- Không có phương án hợp lệ nào qua được guardrail. Nhóm không chọn lại seed, ngưỡng hay tỉ lệ mô phỏng để che đi kết quả này.

## 5. Các failure mode đề yêu cầu phân tích

Nguyên nhân chung của cả ba trường hợp là 20 mẫu trên 100 cho rất ít thông tin, trong khi ngưỡng 5% lại nằm sát 0.
Vì chưa có nhãn ẩn của fixture, nhóm minh hoạ bằng kết quả mô phỏng và metadata.

**Kết luận chắc chắn chỉ từ 1 mẫu trên 100.** Một mẫu cho khoảng tin cậy gần như từ 0 đến 1 (khoảng [0; 0,97] nếu mẫu
không lỗi, [0,03; 1,0] nếu mẫu lỗi), tức là không nói lên được gì. Ngay cả với 20 mẫu: ở seed 42, baseline thấy 1 lỗi
trong 20 mẫu của V2 nên ước lượng 5%, nhưng khoảng tin cậy trải từ 1% đến 22%. Trong PoC, nhóm occlusion của V5 chỉ có
2 mẫu và cả hai đều lỗi, nên ước lượng riêng cho nhóm này là 100% (xem `stratum_estimates.csv`). Để tránh hiểu sai,
pipeline luôn xuất kèm `n_audited`, `ci_low`, `ci_high`, `p_accept`, `p_rework`, và quyết định dựa trên kiểm định chứ
không dựa vào con số ước lượng. Hai test liên quan là `test_single_audit_cannot_support_a_precise_claim`
và `test_zero_errors_is_not_proof_of_five_percent`.

**Đổi ngưỡng sau khi đã nhìn nhãn.** Ngưỡng 5% và độ tin cậy được đọc thẳng từ `acceptance_policy.yaml`, mã hash của
file được lưu vào `audit_protocol.json`, và config không ghi đè được policy. Kế hoạch lấy mẫu được băm hash trước khi
oracle trả nhãn, nên file review cũ không khớp hash sẽ bị từ chối. Nhóm cũng xin nói rõ: nhóm **đã** đổi cách chia mẫu
(v2) và cách ra quyết định (v3) sau khi xem kết quả mô phỏng. Ngưỡng và mức sai cho phép thì giữ nguyên. Các thay đổi
này được ghi trong metric contract và được đánh giá lại trên bộ seed mới đã chốt trước. Test liên quan:
`test_frozen_policy_overrides_config_and_tolerates_missing_confidence`
và `test_stale_review_is_rejected_when_sampling_protocol_changes`.

**Chưa đủ bằng chứng mà vẫn ACCEPT.** Khi bằng chứng chưa đủ, pipeline luôn HOLD và không bao giờ mặc định ACCEPT.
Ví dụ ở seed 42, V3 là batch xấu (tỉ lệ lỗi thật 8%). PoC tính được `p_rework` = 0,23 và `p_accept` = 1,0 nên để HOLD,
batch này không bị lọt. Người duyệt cũng không thể chuyển sang ACCEPT khi kiểm định chưa ủng hộ (`accept_supported = False`).
Test liên quan: `test_manual_accept_cannot_bypass_uncertainty_and_failed_run_has_no_stale_prediction`
và `test_exact_threshold_test_bounds_wrong_decisions_by_enumeration`.

Ngoài ra nhóm còn xử lý rủi ro dừng kiểm quá sớm. Phương án kiểm tuần tự chia mức sai cho từng mốc kiểm,
và có test kiểm tra độ phủ của khoảng tin cậy tại đúng thời điểm dừng.

## 6. Hướng cải tiến

Đây là những ý tưởng chưa được kiểm chứng. Nếu làm thì cần chốt protocol mới trước và đánh giá trên dữ liệu chưa xem,
không áp ngược vào protocol hiện tại.

- Thêm một nhóm cho các mẫu gán nhãn quá nhanh (mỗi batch có 1–5 mẫu dưới 15 giây), có thể là dấu hiệu làm ẩu.
  Cách này chỉ dùng metadata, không cần nhãn.
- Thay việc xét mọi cách phân bố lỗi bằng một cận chặt hơn dựa trên dữ liệu pilot độc lập, để kiểm định nhạy hơn
  khi cách chia mẫu không cân xứng.
- Góp ý cho người quản lý quy trình: với ngưỡng 5%, budget 20/100 không đủ để chứng minh batch đạt. Cần tăng budget,
  hoặc chấp nhận HOLD là trạng thái bình thường.

## 7. Cách chạy lại

```bash
python -m pytest -q
python -m tools.verify_manifests
python -m tools.demo_t12 --reports reports/t12_simulated          # mô phỏng với seed 42
python -m tools.study_t12 --repeats 100 --seed 1000               # phép so sánh chính, ghi vào out/t12_study/
python -m tools.study_t12 --repeats 20                            # 20 seed đầu (42–61)
python -m tools.submit_t12 --mode official                        # khi có nhãn giảng viên; ghi reports/metrics_*.json và table1
```

## 8. Tài liệu tham khảo

- [Đề T12](../docs/tracks/T12.md), file `acceptance_policy.yaml` và evaluator `src/metrics/tracks.py::eval_t12`.
- Brown, Cai & DasGupta (2001), *Interval Estimation for a Binomial Proportion*, Statistical Science 16(2). Nhóm dựa vào
  bài này để không dùng khoảng Wald.
- [SciPy `hypergeom`](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.hypergeom.html): các hàm CDF, SF, PMF
  dùng để tính khoảng tin cậy và kiểm định.
