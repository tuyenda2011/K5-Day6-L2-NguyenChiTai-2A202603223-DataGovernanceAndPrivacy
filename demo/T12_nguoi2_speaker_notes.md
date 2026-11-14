# Ghi chú trình bày của Nguyễn Chí Tài — T12

Đã đọc nội dung PDF hiện có gồm 16 trang và đối chiếu với mã nguồn, metric contract, JSON/CSV kết quả. Đây là ghi chú và đề xuất phân công, không phải xác nhận buổi trình bày đã diễn ra. Slide vẫn dùng dữ liệu mô phỏng.

## Đề xuất chia phần

| Trang PDF | Người chuẩn bị | Nội dung |
|---|---|---|
| 1–7 | Tuyền | Bài toán, pipeline, phân tầng, kiểm định và giới hạn budget |
| 8–10 | Tài | Demo kiểm tra/review, kết quả từng batch, CSV và audit log |
| 11–12 | Tuyền | Thí nghiệm 100 seed, MAE/HOLD và đối chứng |
| 13–15 | Tài | Failure modes, minh bạch thay đổi protocol, giới hạn và kết luận |
| 16 / debate | Cả hai | Trả lời theo phần sở hữu; cần thống nhất với Tuyền trước buổi trình bày |

## Lời dẫn của Tài

**Trang 8–10, khoảng 90 giây.** “Phần em phụ trách là QA và vòng review. Bộ test hiện có 83 ca pass, 39 ca skip vì chưa được cấp ground truth, không có ca fail. Em bổ sung năm ca kiểm escalation, lý do rỗng/chỉ khoảng trắng và ID review trùng/lạ. Trên seed 42 mô phỏng, bốn batch giữ HOLD, V5 REWORK. Em đã xem số lỗi audit và CI, xác nhận các quyết định qua hội thoại; công cụ hỗ trợ ghi CSV theo xác nhận rồi pipeline replay. Bằng chứng gồm CSV, raw/final decisions, log và validator ở reports/t12_review. Em không đổi HOLD sang ACCEPT chỉ để qua guardrail.”

Mở `reports/t12_review/contact_sheet.html` offline để giới thiệu giao diện; mở `review_queue_reviewed.csv` và 5 dòng `batch_review:*` cuối `audit_log.jsonl` để giải thích bằng chứng. Không cần nhập lại bằng chứng đã commit trong lúc trình bày. Nếu demo tương tác mới, giữ output riêng và dùng queue mới.

**Trang 13–15, khoảng 90 giây.** “Sai lầm thứ nhất là 0 lỗi trong mẫu đồng nghĩa batch đạt chuẩn. Với random 20/100, CI còn tới 15%; CI phân tầng còn rộng hơn. Sai lầm thứ hai là thay protocol mà không công bố: nhóm đã ghi v2/v3 và tách bộ seed mới. Sai lầm thứ ba là dùng quyền review để ép ACCEPT: pipeline chặn nếu chưa có bằng chứng. Kết quả hiện tại có cải thiện MAE trên mô phỏng chính nhưng chưa qua guardrail, nên chúng em chưa kết luận sẵn sàng nghiệm thu thực tế.”

## Câu hỏi debate và câu trả lời

| Câu hỏi | Trả lời chuẩn bị |
|---|---|
| Vì sao không batch nào ACCEPT? | Budget 20/100 chưa đủ chứng minh tỉ lệ lỗi ≤5% theo mức sai đã chốt; chưa thấy lỗi không đồng nghĩa không có lỗi. Giữ HOLD khi thiếu bằng chứng. |
| Vì sao slide ghi cận trên 15% nhưng PoC V1 là 50%? | 15% là CI random một tầng; 50% là CI Bonferroni ghép các tầng của PoC. Nêu đúng phương pháp, không tráo hai CI. Quyết định v3 dùng kiểm định tại ngưỡng. |
| Recall 1 sao chưa đạt? | HOLD cũng được tính là không bỏ lọt batch xấu. Recall không phản ánh tắc nghiệm thu; cần báo HOLD ≤0,4 và false reject. |
| Sao không REWORK hết để qua guardrail? | All-REWORK qua HOLD nhưng REWORK nhầm mọi batch tốt. Vì vậy có đối chứng và báo false reject, không chỉ tối ưu một chỉ số. |
| Nhóm có đổi protocol sau kết quả? | Có: v2 đổi allocation, v3 đổi quy tắc quyết định sau mô phỏng dev. Ngưỡng/budget/confidence giữ nguyên, lịch sử được ghi rõ; so sánh chính dùng seed 1000–1099 đã chốt trước. |
| 100 seed có phải heldout thật không? | Đây là seed mới trên cùng pool metadata và cơ chế mô phỏng, không phải dữ liệu vendor độc lập. Đánh giá cuối vẫn chờ nhãn giảng viên. |
| Làm review bằng công cụ có phải review giả? | Người dùng đã được trình bày bằng chứng và xác nhận từng quyết định theo nhóm năm batch; công cụ chỉ chuyển xác nhận sang CSV và replay. README ghi rõ phương thức, không nhận đã bấm nút trong trình duyệt. |
| Escalate có đổi quyết định không? | Bốn batch thực review vốn HOLD nên giữ HOLD, đổi owner/lý do và thêm log. Test riêng dùng batch REWORK để chứng minh đường đổi REWORK → HOLD. |
| Có đọc ground truth để chọn mẫu? | Kế hoạch lấy mẫu được chốt và hash trước nhãn. Chỉ AuditOracle lộ nhãn của mẫu được chọn, có giới hạn budget. Evaluator mới đọc nhãn batch để chấm. |
| Các test skip có che lỗi không? | 39 test đánh dấu requires_gt chưa chạy vì không có overlay. Phần QA tự sinh nhãn mô phỏng để kiểm pipeline; không tuyên bố đã pass hidden evaluation. |

## Góp ý cần chuyển cho Tuyền khi sửa LaTeX

- Trang 8: khi demo lại, ưu tiên `python -m tools.demo_t12` và xem output ở `out/`, tránh vô tình ghi đè số liệu lịch sử `reports/t12_simulated/` bằng runtime của máy mới. Kết quả QA mới có thư mục riêng.
- Trang 9: sửa chú thích “pipeline không thấy” thành “pipeline chỉ thấy nhãn các mẫu đã audit qua Oracle”; pipeline có thấy 20 nhãn/batch, không thấy toàn bộ trước khi chọn.
- Trang 12: câu “Không phương án nào qua guardrail” cần nói rõ xét HOLD trung bình của các phương án kiểm mẫu; báo cáo ghi PoC có 1/100 seed đạt. All-REWORK là đối chứng có HOLD=0 nhưng false reject=1.
- Trang 10: có thể thêm đường dẫn bằng chứng review mới và kết quả 83 passed/39 skipped; mô tả rõ xác nhận qua hội thoại và điền CSV được hỗ trợ.
- Trang 15: “0 batch xấu bị ACCEPT” chỉ nằm trong phạm vi mô phỏng đã chạy; không phải bảo đảm cho mọi dữ liệu tương lai.

PDF không được sửa trực tiếp vì repo không có `demo/T12_slides/` LaTeX. Ghi chú này là bản góp ý cụ thể để tích hợp khi có nguồn slide.
