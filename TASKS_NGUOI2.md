# Việc của Người 2: Nguyễn Chí Tài (2A202603223)

**Vai trò:** QA / metric + Review + Report (track T12, Vendor Batch Acceptance)

> Cập nhật 15/11/2026: đã hoàn thiện test, QA thực chạy, review được người dùng xác nhận, báo cáo và speaker notes. Các ô còn trống phản ánh nhãn giảng viên, hoạt động trình bày hoặc bàn giao/push còn chờ thực tế; không đánh dấu khống.

Phần pipeline, tools, report T12 và slide đã có trên `main`. Việc của Tài là kiểm tra, làm vòng review thật,
hoàn thiện báo cáo nhóm và **tự commit bằng tài khoản Git của mình**. README yêu cầu mỗi thành viên có ≥ 1 commit
thực chất, và giảng viên đối chiếu `git shortlog -sne --all` với `reports/team_contributions.csv`.

---

## 0. Chuẩn bị (làm trước tiên)

```bash
git clone https://github.com/tuyenda2011/K5-Day6-L2-NguyenChiTai-2A202603223-DataGovernanceAndPrivacy.git
cd K5-Day6-L2-NguyenChiTai-2A202603223-DataGovernanceAndPrivacy
git config user.name  "<tên GitHub của Tài>"
git config user.email "<email GitHub của Tài>"
pip install -r requirements.txt          # Python 3.11–3.13
python -m pytest -q                      # phải 0 failed (đã chạy lại: 83 passed, 39 skipped, 0 failed)
python -m tools.verify_manifests         # 14 manifests, 0 failing
```

- [x] Clone repo, cấu hình đúng `user.name` / `user.email` của chính Tài (không dùng máy hay tài khoản của Tuyền)
- [x] `pytest` 0 failed, `verify_manifests` OK

## 1. Đọc để nắm bài

- [x] [docs/tracks/T12.md](docs/tracks/T12.md): đề bài
- [x] [reports/t12_report.md](reports/t12_report.md): cách làm và kết quả
- [x] [reports/metric_contract.md](reports/metric_contract.md): metric, protocol v1 → v3
- [x] [demo/T12_slides_demo.pdf](demo/T12_slides_demo.pdf): slide demo

## 2. QA / tests

File test: [tests/test_t12_pipeline.py](tests/test_t12_pipeline.py)

- [x] Viết thêm **ít nhất 1–2 test của Tài** (một case thành công + một case lỗi/edge). Gợi ý:
  - Review hợp lệ (`reviewer_decision = escalate` + có `review_note`) → batch thành HOLD, `audit_log.jsonl` có dòng `batch_review:escalate`
  - Override thiếu `review_note` → pipeline báo lỗi
  - `review_queue_reviewed.csv` có `item_id` trùng hoặc lạ → báo lỗi
- [x] Chạy `python -m pytest -q` → 0 failed
- [x] Commit: `test(t12): ...`

## 3. Vòng review thật (human-in-the-loop)

Repo không có nhãn giảng viên, nên dùng nhãn mô phỏng:

```bash
python -m tools.demo_t12                 # ghi ra out/t12_demo/
```

- [x] Đã tạo contact sheet offline; chọn cách điền CSV trực tiếp theo xác nhận của người dùng qua hội thoại (không nhận đã thao tác trình duyệt)
- [x] Điền trực tiếp CSV theo xác nhận của Nguyễn Chí Tài: V1–V4 `escalate`, V5 `approve`;
      đủ các cột `reviewer`, `reviewer_decision`, `override_value`, `review_note`, không nhận đã bấm Export CSV trong trình duyệt.
- [x] Lưu file thành `out/t12_demo/poc/review_queue_reviewed.csv` rồi chạy lại pipeline
- [x] Kiểm tra `audit_log.jsonl` có dòng `batch_review:...` và `batch_decisions.csv` đổi đúng

Quy tắc review (pipeline sẽ báo lỗi nếu vi phạm):
- `reviewer_decision` ∈ `approve / reject / edit / escalate / skip`
- Đổi quyết định (`edit`, `reject`) phải có `override_value` (ACCEPT/REWORK/HOLD) **và** `review_note`
- **Không được** chuyển sang ACCEPT khi `accept_supported = False`
- File review cũ không khớp kế hoạch lấy mẫu hiện tại sẽ bị từ chối

> `out/` nằm trong `.gitignore`. Muốn giữ bằng chứng thì chép `review_queue_reviewed.csv` và đoạn `audit_log.jsonl` liên quan
> vào `reports/t12_review/` rồi commit. Ghi rõ đây là review trên **nhãn mô phỏng**.

- [x] Commit: `docs(t12): human review evidence ...`

## 4. Báo cáo nhóm: [reports/group_report.md](reports/group_report.md)

File đã điền đầy đủ cho 2 thành viên; các bảng sinh bằng `python -m tools.build_t12_report_tables`. Nguồn: `t12_report.md`, `metric_contract.md`
và `reports/t12_simulated/`. **Không gõ tay số liệu**, chỉ chép từ file do script sinh ra.

- [x] 00 Header: Group, Challenge T12, 2 thành viên + vai trò, Git URL, tag `demo-180m` (commit `eb4d06d`)
- [x] 01 Problem statement · 02 Data & provenance · 03 Research & design
- [x] 04 Baseline vs PoC: dán bảng từ `reports/t12_simulated/table_baseline_vs_poc.md`, ghi rõ là **mô phỏng**
- [x] Failure modes, human review, giới hạn, references
- [x] 10 Team contribution: 2 dòng, khớp `team_contributions.csv`
- [x] Commit: `docs: fill group report`

## 5. Metric chính thức (chỉ khi giảng viên cấp nhãn `gt/`)

```bash
python -m tools.submit_t12 --mode official
# ghi reports/metrics_baseline.json, reports/metrics_poc.json, reports/table1_baseline_vs_poc.md
```

- [ ] Khi có overlay giảng viên: chạy lệnh trên, commit 3 file kết quả
- [ ] Cập nhật số chính thức vào `group_report.md` (thay cho số mô phỏng)

## 6. Slide và trình bày

- [x] Đã đọc nội dung 16 trang [demo/T12_slides_demo.pdf](demo/T12_slides_demo.pdf), ghi góp ý theo trang trong [speaker notes](demo/T12_nguoi2_speaker_notes.md); chưa gửi cho Tuyền
      (mã nguồn LaTeX không có trên git; muốn sửa thì xin Tuyền thư mục `demo/T12_slides/`)
- [x] Đã soạn đề xuất chia phần, lời dẫn và 10 câu debate trong speaker notes.
- [ ] Hai thành viên xác nhận phân công và thực hiện buổi trình bày (chưa diễn ra). Câu hỏi dễ gặp:
  - Vì sao không batch nào được ACCEPT? (0 lỗi/20 mẫu vẫn có cận trên 15% > 5%)
  - Vì sao không qua guardrail HOLD ≤ 0,4? (giới hạn của budget, nhóm không hạ ngưỡng)
  - Có đổi protocol sau khi xem kết quả không? (có, v2/v3, đã ghi minh bạch, đánh giá lại trên seed mới)

## 7. Cuối cùng

- [x] Điền dòng của Tài trong [reports/team_contributions.csv](reports/team_contributions.csv):
      `git_author_name`, `git_email`, `commit_shas`, `evidence_note`, `presenter`
- [x] `python -m pytest -q` lần cuối → 0 failed
- [x] Tạo các commit thực chất bằng đúng danh tính Git của Tài; nhánh bàn giao theo yêu cầu mới là `nguyen-chi-tai`.
- [ ] Push nhánh `nguyen-chi-tai` lên repo gốc: đã thử nhưng thiếu đăng nhập (`unable to get password from user`); cần tài khoản có quyền ghi.
- [ ] Gửi thông báo cho Tuyền: nội dung bàn giao đã soạn trong `reports/nguoi2_handover.md`, chưa có kênh gửi được xác định.
- [ ] Publish tag `final-24h`: chuẩn bị tag local sau commit bàn giao cuối, chưa đẩy lên GitHub.

---

**Bằng chứng hoàn thành:** test `aabff13`; review `4eb02b4`; report/QA/slide notes `89a0377`. Xem [bàn giao](reports/nguoi2_handover.md), [QA](reports/t12_qa/README.md) và [review](reports/t12_review/README.md). Phần metric chính thức vẫn chờ nhãn giảng viên; guardrail HOLD chưa đạt.

**Kiểm tra trước khi báo xong:** `git shortlog -sne --all` có tên Tài với ≥ 1 commit thực chất (commit chỉ đổi khoảng trắng không tính).
