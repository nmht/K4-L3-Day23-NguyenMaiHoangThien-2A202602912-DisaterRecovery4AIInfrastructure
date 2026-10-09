# Postmortem — DR Drill Lab 23

Theo đúng template §4 "Sau Failover: Blameless Postmortem". Blameless: câu hỏi là
"hệ thống/process nào cho phép chuyện này", không phải "ai làm sai".

## 1. Timeline (mọi dòng phải có evidence path:line)

| ISO time | Sự kiện | Evidence |
|---|---|---|
| 2026-10-09T04:45:24 | outage bắt đầu | `chaos/chaos-events.jsonl:2` |
| 2026-10-09T04:45:24 | user đầu tiên bị ảnh hưởng | `reports/drill-2-withdr.jsonl:6` |
| 2026-10-09T04:45:43 | health check alert | `reports/health-events.jsonl:2` |
| 2026-10-09T04:45:48 | operator confirm cutover | `reports/failover-events.jsonl:1` |
| 2026-10-09T04:46:00 | resolved (request đầu tiên OK từ region phụ) | `reports/drill-2-withdr.jsonl:42` |

## 2. RTO/RPO đo được vs mục tiêu — gap ở bước nào?

- RTO mục tiêu: 300s · đo được: `36.0s` · gap: `-264.0s`
- RPO mục tiêu: 300s · đo được: `14.06s` (`7` doc bị mất) · gap: `-285.94s`
- **Bước tốn nhiều giây nhất:** `Health check` — vì hệ thống cấu hình khoảng thời gian đo lặp lại là 5 giây và cần tới 3 lần lỗi liên tiếp mới xác nhận chết, do đó tốn luôn 15 giây đầu tiên mà không làm gì được.

## 3. Root cause (5 whys)

Không phải "vì tôi chạy chaos script". Câu hỏi: *nếu đây là outage thật, bước nào
trong runbook của tôi sẽ thất bại?*
- Tại sao RTO lại mất tới hơn 35 giây? Vì hệ thống dựa vào cơ chế health_check tiêu tốn mất 15-20 giây đầu.
- Tại sao health check cần tới 15 giây? Vì `threshold = 3`, `interval = 5s`.
- Tại sao lại là 3 và 5? Để hệ thống không nhạy quá mức và tránh hiện tượng flapping do độ trễ mạng gây ra.
- Trong trường hợp diễn tập này, Runbook có thể thất bại ở đâu? Nếu bước restore state bị treo hoặc snapshot không thành công do không có bản replica nào (chưa có kỳ đồng bộ nào xảy ra), bước 3 sẽ lỗi khiến Region phụ khởi động lại bằng dữ liệu rỗng.

## 4. Action items (có owner + deadline)

| # | Action | Owner | Deadline | Giảm RTO/RPO bao nhiêu giây |
|---|---|---|---|---|
| 1 | Bổ sung giới hạn thời gian (timeout) cứng vào bước khôi phục snapshot để tránh block cả quá trình | on-call | Next Sprint | Đảm bảo RTO không lố 300s nếu lỗi storage |
| 2 | Giảm thời gian replicate đồng bộ dữ liệu xuống 10s một lần thay vì 30s | Data Engineer | Q4/2026 | Giảm RPO khoảng 20s |

## 5. Ba câu hỏi bắt buộc trả lời

1. `interval × threshold` của bạn là bao nhiêu giây? Nó chiếm bao nhiêu % RTO?
- interval = 5s, threshold = 3, tích số là 15 giây. 15 giây này chiếm khoảng 41% trên tổng RTO đo được (~36.0s).
2. Nếu hạ interval xuống 1s, RTO giảm mấy giây — và bạn trả giá gì (§4 flapping)?
- RTO sẽ giảm khoảng 12 giây, nhưng trả giá bằng việc network jitter (mạng chập chờn 1-2 giây) cũng sẽ vô tình thỏa mãn điều kiện và trigger tự động failover nhầm. Điều này dẫn tới 2 vùng nhảy qua nhảy lại liên tục (flapping), làm mất ổn định hệ thống.
3. Nếu outage kéo dài 6 giờ và region chính mất dữ liệu vĩnh viễn, `docs_lost` của bạn có nghĩa gì với khách hàng?
- `docs_lost` (hiện là 7 document) đại diện cho số lượng tài liệu khách hàng đã nhận được phản hồi thành công (200 OK) tại Region A nhưng chưa kịp đồng bộ (replicate) sang Region B trước khi sự cố xảy ra. Nếu A mất vĩnh viễn, khách hàng sẽ mất trắng 7 document này và chúng ta phải yêu cầu khách hàng upload lại.
