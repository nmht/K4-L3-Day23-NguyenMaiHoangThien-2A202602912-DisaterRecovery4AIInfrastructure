# RTO/RPO Evidence — Lab 23

Quy tắc duy nhất: mỗi con số ở đây phải trỏ được về **một dòng log thật**
(`đường/dẫn.jsonl:số_dòng`). `pytest tests/test_rto_evidence.py` sẽ mở từng file ra kiểm tra.
Con số không có evidence = trượt, bất kể các phần khác.

## 1. Drill 1 — không có DR (baseline)

| Chỉ số | Giá trị | Cách đo | Evidence |
|---|---|---|---|
| t_outage | `2026-10-09T04:44:04` | chaos kill | `chaos/chaos-events.jsonl:1` |
| Request fail đầu tiên | `+0.0s` | dòng `ok:false` đầu tiên sau t_outage | `reports/drill-1-nodr.jsonl:6` |
| Request thành công sau đó | không có | không có dòng `ok:true` nào sau t_outage | `reports/drill-1-nodr.jsonl:54` |
| RTO | `NO_RECOVERY` | `tools/measure_rto.py` | `reports/drill-1-nodr.jsonl:54` |

## 2. Drill 2 — có DR

| Mốc | +giây từ t_outage | Cách đo | Evidence |
|---|---|---|---|
| t_outage (mốc 0) | 0 | `action:kill` | `chaos/chaos-events.jsonl:2` |
| User thấy lỗi đầu tiên | 0.0 | dòng `ok:false` đầu | `reports/drill-2-withdr.jsonl:6` |
| Health check phát hiện | 19.65 | `to:UNHEALTHY, region:a` | `reports/health-events.jsonl:2` |
| Snapshot restore xong | 24.91 | `step:2_restore_snapshot` | `reports/failover-events.jsonl:2` |
| Region phụ ready | 31.18 | `step:4_wait_ready` | `reports/failover-events.jsonl:4` |
| DNS cutover | 31.18 | `step:5_dns_cutover` | `reports/failover-events.jsonl:5` |
| **RTO đo được** | 36.0 | dòng `ok:true` đầu sau lỗi | `reports/drill-2-withdr.jsonl:42` |

| Chỉ số | Đo được | Mục tiêu (slide §1) | Verdict |
|---|---|---|---|
| RTO — Inference API | `36.0s` | 300s (5 phút) | PASS |
| RPO — Vector DB | `14.06s` / `7` doc | 300s (5 phút) | PASS |

## 3. RTO của tôi gồm những gì (bắt buộc — đây là phần chấm điểm hiểu bài)

| Thành phần | Giây | Nó đến từ đâu | Giảm được bằng cách nào |
|---|---|---|---|
| Health-check detect floor | 15.0 | `interval_s × threshold` trong `reports/health-events.jsonl:2` | Giảm interval hoặc threshold (tuy nhiên sẽ tăng rủi ro bị flap do nhiễu mạng) |
| Snapshot restore | 2.1 | 2_restore → 3_scale | Dùng ổ cứng SSD, giảm dung lượng state, dùng storage class nhanh hơn |
| GPU pool warm-up | 7.0 | `waited_s` ở `4_wait_ready` | Pre-warm GPU pool (chạy sẵn resource, nhưng sẽ tốn chi phí rảnh rỗi) |
| DNS/LB TTL cache | 5.4 | t_recovered − t_cutover | Hạ TTL xuống 1s tại DNS server hoặc client config |
