# QA thực chạy — phần Nguyễn Chí Tài

Thu từ Python 3.13 trong `.venv`, không chép kết quả pytest lịch sử. `qa_summary.json` ghi commit/thời điểm UTC/môi trường/số test. Run tương ứng ngày 15/11/2026 tại Việt Nam.

- `test_results.txt`: **83 passed, 39 skipped, 0 failed**, không warning sau khi đọc queue bằng dtype chuỗi.
- `verify_manifests.txt`: **14 manifests, 0 failing**.
- `requirements_lock.txt`: `pip freeze` của môi trường QA này, không thay policy hoặc requirements chung.
- `demo_execution.txt`, `metrics_*.json`, `SIMULATED_DATA.json`: demo mới, nhãn mô phỏng, trước review. Review giữ nhãn quyết định nên metric chất lượng không đổi.
- `table_*.md`: tạo bằng `python -m tools.build_t12_report_tables`; không nhập tay số liệu. Bảng baseline/slices/study lấy nguồn lịch sử `reports/t12_simulated/`; JSON và bảng compare lần chạy mới lưu riêng ở đây.

## Ca QA bổ sung

| Ca | Điều được chứng minh |
|---|---|
| Escalate hợp lệ trên batch REWORK | Thành HOLD, đúng owner/reason, raw giữ nguyên, log append-only có before/after, gate cập nhật |
| Note rỗng | Exit 2, xóa output thành công cũ |
| Note chỉ khoảng trắng | Không lách yêu cầu giải thích |
| ID review trùng | Không áp quyết định mơ hồ nhiều lần |
| ID ngoài input | Không đưa batch lạ vào kết quả |

Chạy `python -m pytest -q` và `python -m tools.verify_manifests` từ gốc repo. Test cần GT skip vì thiếu overlay; không phải PASS cho đánh giá chính thức. Chưa tuyên bố đạt guardrail hoặc sẵn sàng release.
