"""BƯỚC 3c — SINH VIÊN VIẾT. Tự động hoá runbook §4 "Runbook: Region Chính Down".

7 bước trên slide, mỗi bước 1 dòng log có ts. Log này CHÍNH LÀ timeline của postmortem.
  1 xac_nhan_outage          — probe cả 2 region, đừng tin 1 lần fail (dùng nhiều lần
                              hoặc gọi health_checker.probe nếu đã viết xong 3a)
  2 thong_bao_incident       — ts của dòng này là mốc "operator biết tin", LUÔN LUÔN
                              SAU t_outage trong chaos-events (không thể trùng — operator
                              không thể biết ngay giây outage xảy ra). Ghi cả 2 ts vào
                              log để postmortem tính được "độ trễ thông báo".
  3 scale_gpu_pool           — gọi HÀM `failover.failover(...)` MỘT LẦN DUY NHẤT. Hàm
                              đó tự làm đủ 5 bước con (verify/restore/scale/wait/cutover)
                              và tự ghi log riêng vào reports/failover-events.jsonl.
  4 verify_state_replica     — KHÔNG gọi lại failover — chỉ ĐỌC kết quả (vector count +
                              weights ở region phụ) từ dict mà bước 3 trả về, để log vào
                              runbook-run.jsonl cho postmortem đọc 1 chỗ duy nhất.
  5 dns_cutover              — cũng chỉ đọc lại: kết quả cutover có ok hay không.
  6 verify_golden_signals    — 10 request thật vào region phụ: p95 latency + error rate
  7 post_incident            — elapsed_s + lệnh đo RTO

BÁN TỰ ĐỘNG, KHÔNG FULL-AUTO (§4: "failover đầu tiên nên là bán tự động — alert +
1-click confirm — tránh flapping gây failover 2 chiều liên tục"). Mặc định phải hỏi
người vận hành confirm; --auto chỉ dùng trong CI/khi chấm điểm.

Chạy:  python dr/runbook.py --primary a --target b --backend fs
"""
import argparse
import json
import pathlib
import sys
import time

import httpx

sys.path.insert(0, ".")
from dr import failover as fo  # noqa: E402

LOG = pathlib.Path("reports/runbook-run.jsonl")
URL = {"a": "http://127.0.0.1:8001", "b": "http://127.0.0.1:8002"}


def step(n, name, **kw):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    ts = time.time()
    kw.update({"ts": ts, "iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts)), "step": n, "name": name})
    line = json.dumps(kw)
    print(line)
    with open(LOG, "a") as f:
        f.write(line + "\n")


def confirm(auto: bool, msg: str) -> bool:
    if auto:
        return True
    return input(f"{msg} [y/N]: ").strip().lower() == "y"


def run(primary: str, target: str, backend: str, auto: bool) -> dict:
    start_time = time.time()
    
    # 1. xac_nhan_outage
    outage_detected = False
    for _ in range(3):
        try:
            httpx.get(URL[primary] + "/readyz", timeout=1.0)
        except Exception:
            outage_detected = True
            break
        time.sleep(1)
    step(1, "xac_nhan_outage", outage_detected=outage_detected)

    # 2. thong_bao_incident
    t_outage = None
    try:
        if pathlib.Path("chaos/chaos-events.jsonl").exists():
            with open("chaos/chaos-events.jsonl") as f:
                for line in f:
                    data = json.loads(line)
                    if data.get("event") == "chaos_injected" and data.get("region") == primary:
                        t_outage = data.get("ts")
    except Exception:
        pass
    step(2, "thong_bao_incident", t_outage=t_outage)

    # 3. scale_gpu_pool (trigger failover)
    if not confirm(auto, "Confirm failover to " + target + "?"):
        return {"ok": False, "reason": "aborted by operator"}
    
    fo_result = fo.failover(target, backend, wait=60.0)
    step(3, "scale_gpu_pool", result=fo_result)

    # 4. verify_state_replica
    try:
        state_r = httpx.get(URL[target] + "/v1/state", timeout=2.0).json()
    except Exception as e:
        state_r = {"error": str(e)}
    step(4, "verify_state_replica", state=state_r)

    # 5. dns_cutover
    step(5, "dns_cutover", cutover_ok=fo_result.get("ok", False))

    # 6. verify_golden_signals
    latencies = []
    errors = 0
    for _ in range(10):
        t0 = time.time()
        try:
            r = httpx.get(URL[target] + "/v1/infer", timeout=2.0)
            if r.status_code == 200:
                latencies.append(time.time() - t0)
            else:
                errors += 1
        except Exception:
            errors += 1
    
    p95 = sorted(latencies)[int(len(latencies) * 0.95)] if latencies else None
    step(6, "verify_golden_signals", p95_latency=p95, error_rate=errors/10.0)

    # 7. post_incident
    step(7, "post_incident", elapsed_s=time.time() - start_time, measure_cmd="python3 tools/measure_rto.py ...")
    
    return {"ok": fo_result.get("ok", False), "elapsed_s": time.time() - start_time}


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--primary", default="a")
    p.add_argument("--target", default="b")
    p.add_argument("--backend", default="fs", choices=["fs", "minio"])
    p.add_argument("--auto", action="store_true")
    a = p.parse_args()
    print(json.dumps(run(a.primary, a.target, a.backend, a.auto), indent=2))
