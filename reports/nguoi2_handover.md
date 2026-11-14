# Bàn giao phần Nguyễn Chí Tài — 15/11/2026

## Đã thực hiện

- Khôi phục lịch sử Git từ repo gốc vào bản workspace; cấu hình **cục bộ** `nguyen-chi-tai-2005 <chitain26@gmail.com>` theo thông tin người dùng cung cấp. Không thay danh tính Git global.
- Đọc đề T12, báo cáo triển khai, metric contract, mã pipeline và nội dung 16 trang PDF.
- Bổ sung 5 ca QA review; kết quả thực chạy **83 passed, 39 skipped, 0 failed**, không warning. Kiểm sha256 **14 manifests, 0 failing**. Bằng chứng ở `t12_qa/`.
- Chạy demo seed 42; nhận xác nhận rõ của người dùng cho cả 5 batch; điền CSV/replay và lưu bằng chứng vào `t12_review/`. Validator artifact/review PASS; HOLD guardrail FAIL, đã công bố.
- Hoàn thiện `group_report.md` cho đúng 2 thành viên; bảng được dựng từ artifact bằng `python -m tools.build_t12_report_tables`.
- Soạn `demo/T12_nguoi2_speaker_notes.md`: phân công đề xuất, lời dẫn, 10 câu debate và góp ý theo trang PDF.
- Commit thực chất được ghi trong `team_contributions.csv`; không dùng SHA hư cấu hoặc tên tác giả khác.

## Trạng thái Git và nộp bài

Đang hoàn tất commit tài liệu và thử push `main`; kết quả cuối được cập nhật tại đây trước bàn giao. Tag `demo-180m` đã xác minh trỏ đến `eb4d06d21e1a92173bad47de51f393e07b99513e`. Tag `final-24h` chưa được ghi nhận trong bản clone ban đầu.

## Phần phụ thuộc bên ngoài

1. **Nhãn giảng viên:** chưa có `fixtures/t12_vendor_batches/gt/`; chưa tạo metric chính thức. Khi nhận overlay, chạy `python -m tools.submit_t12 --mode official`, kiểm kết quả và đưa metrics chính thức vào báo cáo dưới nhãn rõ ràng. Giữ lại số mô phỏng để truy vết.
2. **HOLD guardrail:** vẫn không đạt trên kết quả hiện tại; không sửa threshold/review để che kết quả này. Muốn cải thiện cần thí nghiệm mới theo protocol đã chốt trước.
3. **Slide/trình bày:** chưa có nguồn LaTeX, chưa diễn ra buổi thuyết trình. Đã có ghi chú và đề xuất chia phần; Tuyền và Tài cần thống nhất lịch/phần trình bày. `presenter` được ghi trạng thái chuẩn bị, không ghi đã trình bày.
4. **Thông báo cho Tuyền:** chưa gửi qua email/chat vì chưa có kênh/người nhận được xác định trong phiên làm việc. Nội dung nhắn đã soạn bên dưới.

## Tin nhắn bàn giao đã soạn cho Tuyền

> Tài đã bổ sung QA review và chạy lại: 83 passed, 39 skipped, 0 failed; 14 manifests OK. Vòng review mô phỏng seed 42 đã được Tài xác nhận và replay, bằng chứng ở reports/t12_review/. Báo cáo nhóm đã điền đủ, có bảng sinh từ script và công bố HOLD guardrail chưa đạt. Đã cập nhật đóng góp Git đúng tài khoản Tài; speaker notes ở demo/T12_nguoi2_speaker_notes.md, có góp ý sửa chú thích trang 9 và kết luận guardrail trang 12. Nhờ Tuyền đối chiếu trạng thái push/tag final-24h bên trên và thống nhất phần trình bày. Metric chính thức vẫn chờ overlay giảng viên.
