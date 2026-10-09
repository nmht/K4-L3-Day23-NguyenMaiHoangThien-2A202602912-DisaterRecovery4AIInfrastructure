# Runbook 1 trang — Region chính down

Runbook phải chạy được lúc 3h sáng bởi người KHÔNG viết nó. Mỗi bước: lệnh copy-paste
được + cách biết bước đó xong.

| # | Bước                       | Lệnh                                                                 | Biết là xong khi                                       | Ai làm         |
| - | -------------------------- | -------------------------------------------------------------------- | ------------------------------------------------------ | -------------- |
| 1 | Xác nhận outage            | `python chaos/kill_region.py status`                                 | `a.alive=false` 3 lần liên tiếp                        | on-call        |
| 2 | Mở incident + bấm giờ RTO  | `echo 'incident opened'`                                             | ts ghi vào `reports/runbook-run.jsonl:1`               | on-call        |
| 3 | Restore state ở region phụ | `python state/snapshot.py get --region b --backend fs`               | Lệnh chạy xong không trả về lỗi                        | on-call        |
| 4 | Scale pool warm→full       | `python edge/scale.py --region b --mode full`                        | `/readyz` của b trả 200                                | on-call / auto |
| 5 | DNS/LB cutover             | `python edge/router.py set-active --region b`                        | `curl localhost:8080/edge/state` cho `active_region=b` | on-call / auto |
| 6 | Verify golden signals      | `curl -I localhost:8080/`                                            | p95 < 300ms, error rate < 1%                           | on-call        |
| 7 | Đo RTO + postmortem        | `python tools/measure_rto.py --loadgen reports/drill-2-withdr.jsonl` | `rto_verdict` != null                                  | on-call        |

**Rollback (failover ngược):** điều kiện nào thì trả traffic về region A? Ai quyết định?

- **Điều kiện**: Region A đã phục hồi, kiểm tra `/healthz` trả về 200 liên tục trong ít nhất 10 phút. Dữ liệu trên A đã được đồng bộ ngược lại từ B để đảm bảo không mất dữ liệu.
- **Ai quyết định**: Việc quyết định cutback (rollback) phải được duyệt bởi Incident Commander thông qua thao tác thủ công. Tuyệt đối không thực hiện auto-failback nhằm tránh hiện tượng flapping (nhảy qua nhảy lại giữa 2 region do mạng chập chờn).
