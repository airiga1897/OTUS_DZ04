"""Проверить распределение запросов и работоспособность сайта без изменения инфраструктуры."""
import argparse
import concurrent.futures
import json
import time
import urllib.error
import urllib.request
from collections import Counter

def request(url: str) -> tuple[int, float, str, str]:
    started = time.monotonic()
    try:
        with urllib.request.urlopen(url, timeout=25) as response:
            response.read()
            return response.status, time.monotonic()-started, response.headers.get("X-Frontend-Node", ""), response.headers.get("X-Backend-Node", "")
    except (OSError, urllib.error.URLError):
        return 0, time.monotonic()-started, "", ""

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url")
    parser.add_argument("--requests", type=int, default=100)
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--expect-two-fronts", action="store_true")
    parser.add_argument("--expect-two-backends", action="store_true")
    args = parser.parse_args()
    if args.requests < 1 or args.concurrency < 1:
        parser.error("Параметры должны быть положительными")
    started = time.monotonic()
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        results = list(pool.map(request, [args.url] * args.requests))
    elapsed = time.monotonic()-started
    latencies = sorted(r[1] for r in results)
    fronts = Counter(r[2] for r in results if r[2])
    backends = Counter(r[3] for r in results if r[3])
    errors = sum(r[0] != 200 for r in results)
    print(json.dumps({"requests": len(results), "concurrency": args.concurrency, "elapsed_s": round(elapsed,3),
                      "rps": round(len(results)/elapsed,2), "p95_s": round(latencies[min(len(results)-1, int(.95*len(results)))],3),
                      "errors": errors, "fronts": fronts, "backends": backends}, ensure_ascii=False, indent=2))
    return int(errors > 0 or args.expect_two_fronts and len(fronts) != 2 or args.expect_two_backends and len(backends) != 2)

if __name__ == "__main__":
    raise SystemExit(main())

