# Metric contract (khai báo bắt buộc — chốt ở phút 30, trước khi chạy eval)

> Các metric chuẩn đã được cài trong `src/metrics/tracks.py`. File này là nơi nhóm **cam kết** cách dùng chúng.
> Không đổi testset, threshold hay trọng số sau khi đã thấy kết quả eval.

| Mục | Khai báo của nhóm |
|---|---|
| Track | T12 · Vendor Batch Acceptance under Audit Budget |
| Primary metric (tên đúng như evaluator in ra) | `MAE error-rate estimate` và `Bad-batch Recall`. Hai chỉ số được báo riêng, không gộp thành một điểm |
| Tăng tốt hay giảm tốt? | MAE càng thấp càng tốt; Bad-batch Recall càng cao càng tốt |
| Đơn vị đánh giá (image / region / pair / release / batch / case …) | Một batch của vendor |
| Công thức + numerator / denominator | MAE là trung bình của \|tỉ lệ lỗi ước lượng − tỉ lệ lỗi thật\| trên tất cả các batch. Recall là số batch xấu (tỉ lệ lỗi thật trên 5%) không bị ACCEPT chia cho tổng số batch xấu. Batch nào thiếu trong file kết quả sẽ bị tính là ACCEPT |
| Cách ghép prediction ↔ GT (IoU? id? tolerance?) | Ghép theo `batch_id`, mỗi batch đúng một dòng; pipeline luôn xuất đủ mọi batch |
| Candidate pool cố định | Toàn bộ `batches.csv` của input (với fixture là 5 batch, mỗi batch 100 mẫu) |
| Review budget B / K | Mỗi batch được kiểm tối đa `audit_budget_per_batch` mẫu khác nhau, đọc từ `acceptance_policy.yaml` (fixture là 20); AuditOracle sẽ từ chối khi vượt. Người duyệt xem lại tất cả các batch, batch HOLD xếp lên đầu |
| Seed | 42 cho cả baseline và PoC; nhóm không chọn seed theo kết quả |
| Threshold policy (chọn trên dev như thế nào) | Nhóm không tune ngưỡng mà lấy nguyên `max_error_rate = 0.05` và `confidence_level = 0.95` từ policy (nếu policy thiếu độ tin cậy thì dùng 0.95). Quyết định dựa trên kiểm định một phía ngay tại ngưỡng, mỗi chiều cho phép sai 2,5%, bằng đúng mức của khoảng tin cậy 95% hai phía: REWORK khi `p_rework` < 0.025, ACCEPT khi `p_accept` < 0.025, còn lại là HOLD. Nếu config ghi khác policy thì pipeline theo policy và ghi `policy_config_conflict` vào audit log |
| Eval split (không dùng để tune) | Nhãn ẩn của giảng viên (`gt/`), chỉ đọc được qua AuditOracle; nhóm chưa xem bộ nhãn này. Nhãn mô phỏng (`tools/demo_t12.py`) chỉ dùng để kiểm tra pipeline chạy đúng |
| Chỉ số lỗi xấu (miss / false alarm / false reject) | Nặng nhất là bỏ lọt (batch xấu bị ACCEPT, tức 1 − Recall). Tiếp theo là REWORK nhầm batch tốt (false reject rate) và tỉ lệ HOLD (guardrail ≤ 0.4) |
| Slices sẽ báo cáo (≥2) | Từng batch (phần `slices` của evaluator) và từng nhóm `risk_tag` trong mỗi batch (`stratum_estimates.csv`) |
| Cách báo độ bất định khi N nhỏ (Wilson CI / bootstrap) | Khoảng tin cậy chính xác cho quần thể hữu hạn, tính từ phân phối hypergeometric vì mẫu được lấy không hoàn lại. Với PoC, khoảng của từng nhóm `risk_tag` được tính ở mức α/H (Bonferroni, H là số nhóm) rồi cộng theo trọng số kích thước nhóm. Mỗi batch đều ghi kèm `n_audited`, `ci_low`, `ci_high`, `p_accept`, `p_rework` và `decision_method`. Khoảng tin cậy dùng để báo cáo, còn quyết định dựa vào kiểm định ở dòng threshold |
| Ngày giờ chốt + người chốt | 2026-11-14 (protocol v3) · người chốt: Đặng Anh Tuyền |

Nếu baseline = 0 thì ghi rõ "baseline = 0" thay vì phần trăm cải thiện.

## Các phương án so sánh

Mọi phương án dùng chung tập batch, budget, seed và quy tắc quyết định.

| Phương án | Mô tả | Lệnh |
|---|---|---|
| Baseline | Chọn ngẫu nhiên 20 mẫu mỗi batch, không hoàn lại; khoảng tin cậy tính cho cả batch như một nhóm | `--pipeline src.examples.t12_baseline` |
| PoC (v3) | Chia mẫu theo `risk_tag`: mỗi nhóm ít nhất một mẫu, số còn lại chia theo kích thước nhóm (`allocation: proportional`). Tỉ lệ lỗi là trung bình có trọng số theo kích thước nhóm. Quyết định bằng kiểm định tại ngưỡng, xét mọi cách phân bố lỗi vào các nhóm | `--pipeline src.pipeline` |
| Ablation | Giống PoC nhưng chia đều mẫu cho các nhóm (`allocation: balanced`); đây chính là PoC v1 | demo |
| Kiểm tuần tự | Kiểm ở hai mốc chốt trước là 15 và 20 mẫu, dừng sớm nếu đã đủ bằng chứng; mức sai được chia cho số mốc và số nhóm. Báo cáo riêng, không thay cho PoC | demo |
| Đối chứng | Luôn HOLD và luôn REWORK, dùng chung mẫu kiểm và ước lượng của baseline | demo |

Budget 20 mẫu là ràng buộc của đề, không phải cỡ mẫu nhóm tự tính ra. Với 20 trên 100 mẫu thì không thể ACCEPT:
kể cả khi không thấy lỗi nào, khoảng tin cậy 95% vẫn là [0; 0,15], cận trên cao hơn 5%. Baseline chỉ REWORK khi
thấy từ 4 lỗi trở lên (cận dưới lúc đó là 0,07); từ 0 đến 3 lỗi thì HOLD. Khi chỉ có một nhóm như baseline,
kiểm định cho đúng cùng quyết định với quy tắc khoảng tin cậy; điều này có test kiểm tra cho mọi số lỗi.

## Lịch sử thay đổi protocol

| Phiên bản | Thay đổi | Nhóm đã thấy gì trước khi đổi |
|---|---|---|
| v1 | PoC chia đều mẫu cho các nhóm `risk_tag`; chưa có kiểm tuần tự | Chưa thấy kết quả nào |
| v2 (2026-11-14) | PoC chuyển sang chia mẫu theo kích thước nhóm, giữ cách chia đều làm ablation, thêm phương án kiểm tuần tự [15, 20], tách riêng bộ sinh số ngẫu nhiên cho nhãn mô phỏng | Đã thấy kết quả mô phỏng của v1 (MAE của PoC kém baseline ở seed 42). Chưa thấy nhãn giảng viên |
| v3 (2026-11-14) | Thay cách ra quyết định: dùng kiểm định tại ngưỡng thay cho khoảng tin cậy Bonferroni, mức sai mỗi chiều giữ nguyên. Cách ước lượng, khoảng tin cậy báo cáo, cách lấy mẫu, ngưỡng và budget không đổi. Kết quả baseline giống hệt v2 | Đã thấy kết quả mô phỏng của v2 trên seed 42–61 (PoC HOLD 0,84 so với baseline 0,78, do Bonferroni quá chặt). Chưa thấy nhãn giảng viên |

Vì nhóm đã dùng seed 42–61 trong lúc thiết kế v2 và v3, kết quả trên bộ seed này chỉ để tham khảo. Trước khi chạy v3,
nhóm chốt một bộ seed mới từ 1000 đến 1099 (100 lần lặp), chưa từng chạy, và dùng nó cho phép so sánh mô phỏng chính;
kết quả của tất cả các seed đều được báo cáo. Đánh giá thật sự vẫn là trên nhãn ẩn của giảng viên. Kết quả của v1
không tái lập được bằng code hiện tại vì bộ sinh nhãn đã thay đổi; số liệu ablation chia đều trong `reports/t12_simulated/`
là bản chạy lại bằng code v3.
