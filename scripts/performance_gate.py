"""Small repeatable latency/concurrency gate for the deployed local API."""
from __future__ import annotations

import argparse
import json
import statistics
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import httpx


def percentile(values: list[float], ratio: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int((len(ordered) - 1) * ratio))]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--requests", type=int, default=60)
    parser.add_argument("--concurrency", type=int, default=10)
    parser.add_argument("--p95-limit-ms", type=float, default=500)
    parser.add_argument("--min-qps", type=float, default=20)
    parser.add_argument("--output", default="reports/platform-performance-latest.json")
    args = parser.parse_args()
    if args.base_url != 'http://127.0.0.1:18084':
        raise RuntimeError('The load test is restricted to the isolated API copy on 18084')

    with httpx.Client(base_url=args.base_url, timeout=15) as client:
        login = client.post("/api/v1/auth/login", json={"username": "student", "password": "student123"})
        login.raise_for_status()
        token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    paths = ("/api/v1/dashboard", "/api/v1/courses", "/api/v1/assignments", "/api/v1/learning/reports")

    # A preceding acceptance run may already have consumed the shared per-IP API quota.
    # Wait for a fresh window so the benchmark measures application latency, not old traffic.
    with httpx.Client(base_url=args.base_url, timeout=15, headers=headers) as client:
        for attempt in range(2):
            probe = client.get(paths[0])
            remaining = int(probe.headers.get("X-RateLimit-Remaining", "0"))
            if probe.status_code == 200 and remaining >= args.requests:
                break
            if attempt == 1:
                raise RuntimeError("API rate-limit window did not recover before performance test")
            time.sleep(min(60, int(probe.headers.get("Retry-After", "60"))))

    def hit(index: int) -> tuple[int, float]:
        started = time.perf_counter()
        response = benchmark_client.get(paths[index % len(paths)])
        return response.status_code, (time.perf_counter() - started) * 1000

    started = time.perf_counter()
    results: list[tuple[int, float]] = []
    with httpx.Client(base_url=args.base_url, timeout=15, headers=headers) as benchmark_client:
        with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
            futures = [pool.submit(hit, index) for index in range(args.requests)]
            for future in as_completed(futures):
                results.append(future.result())
    elapsed = time.perf_counter() - started
    latencies = [latency for _, latency in results]
    errors = sum(status != 200 for status, _ in results)
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "base_url": args.base_url,
        "requests": args.requests,
        "concurrency": args.concurrency,
        "successful": args.requests - errors,
        "errors": errors,
        "latency_p50_ms": round(statistics.median(latencies), 2),
        "latency_p95_ms": round(percentile(latencies, 0.95), 2),
        "latency_max_ms": round(max(latencies), 2),
        "throughput_qps": round(args.requests / elapsed, 2),
    }
    report["passed"] = errors == 0 and report["latency_p95_ms"] <= args.p95_limit_ms and report["throughput_qps"] >= args.min_qps
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
