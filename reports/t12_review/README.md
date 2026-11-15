# Review T12 trên nhãn mô phỏng

Reviewer: **Nguyễn Chí Tài (2A202603223)**. Người dùng đã được trình bày số lỗi audit và CI của cả năm batch, rồi trả lời **“Xác nhận cả 5 quyết định”** trong hội thoại ngày 15/11/2026 giờ Việt Nam. Bài cho phép điền trực tiếp CSV.

V1–V4 `escalate` giữ HOLD và chuyển cấp xem xét; V5 `approve` giữ REWORK. Bốn batch HOLD thiếu bằng chứng ACCEPT; V5 có bằng chứng vượt ngưỡng. Không kiểm thêm mẫu, không hạ policy, không dùng nhãn giảng viên.

| Tệp | Bằng chứng |
|---|---|
| `review_confirmation.json` | Câu trả lời xác nhận, cách hỗ trợ và bằng chứng đã trình bày |
| `review_queue_reviewed.csv` | 5 dòng có reviewer/quyết định/lý do/thời điểm và reason/hash gốc |
| `audit_log.jsonl` | Log append-only đầy đủ, 4 `batch_review:escalate` và 1 `batch_review:approve` |
| `batch_decisions_raw.csv`, `batch_decisions.csv` | Trước/sau: nhãn giữ nguyên, owner/lý do cập nhật đúng |
| `audited_samples.csv`, `audit_selection.csv`, `audit_history.csv`, `stratum_estimates.csv` | Các mẫu đã kiểm, budget, kế hoạch, ước lượng theo tầng |
| `audit_protocol.json`, `run_info.json`, `quality_gate.json` | Policy/hash, môi trường/status run, guardrail |
| `decision_log.csv`, `contact_sheet.html` | Lịch sử quyết định, giao diện offline |
| `validation.json`, `replay_execution.txt` | Artifact PASS, review đủ; guardrail FAIL |

## Tái lập

Từ gốc repo sau khi cài requirements:

```powershell
python -m tools.demo_t12
Copy-Item -LiteralPath reports/t12_review/review_queue_reviewed.csv -Destination out/t12_demo/poc/review_queue_reviewed.csv
python -m src.main --config out/t12_demo/config_poc.yaml --output out/t12_demo/poc --pipeline src.pipeline --run-name simulated_poc_reviewed --offline --seed 42
python -c "from pathlib import Path; from tools.submit_t12 import validate_artifacts; print(validate_artifacts(Path('out/t12_demo/poc'), Path('out/t12_demo/input')))"
```

Kết quả: `automated_checks_passed=True`, `human_review_complete=True`, `batches=5`, `audited_samples=100`, `hold_guardrail_pass=False`. Quyết định giữ 4 HOLD/1 REWORK; test QA riêng chứng minh escalation REWORK → HOLD hoạt động.

Nếu code/policy/seed/input làm reason/hash đổi, pipeline phải từ chối CSV cũ: tạo queue mới và yêu cầu reviewer xem lại. Không sửa bằng chứng gốc để qua kiểm tra. `gt/` do demo sinh chỉ là mô phỏng trong `out/`, không chép vào fixture hoặc gọi là nhãn thật.
