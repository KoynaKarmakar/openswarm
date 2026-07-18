"""
VERITAS Fabric load test — 50 concurrent simulated users, 2 minutes.

Outputs percentile latencies and writes results.json.

Usage:
    # With backend running on localhost:8000
    python load_test.py

    # Custom target / duration
    python load_test.py --url http://localhost:8000 --users 50 --duration 120

Requires: httpx (already in backend/requirements.txt)
"""

import asyncio
import argparse
import json
import time
import statistics
import random
from pathlib import Path
import httpx

CUSTOMER_IDS   = [f"CUST{str(i).zfill(5)}" for i in range(1, 11)]
ACCOUNT_IDS    = [f"CUST{str(i).zfill(5)}{str(j).zfill(1)}" for i in range(1, 11) for j in range(10, 11)]
CHAT_MESSAGES  = [
    "What is the co-lending policy for Tier A customers?",
    "Is customer CUST00001 eligible for co-lending?",
    "Explain the UEBT fraud detection threshold",
    "What documents are needed for KYC verification?",
    "Check fraud risk for account CUST000010",
]

# ------------------------------------------------------------------
# Auth — get a JWT token once, reuse across all workers
# ------------------------------------------------------------------

async def get_token(client: httpx.AsyncClient, base_url: str) -> str:
    r = await client.post(
        f"{base_url}/auth/token",
        data={"username": "demo@idbi.bank", "password": "demo1234"},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    r.raise_for_status()
    return r.json()["access_token"]


# ------------------------------------------------------------------
# Individual scenario coroutines
# ------------------------------------------------------------------

async def scenario_identity(client: httpx.AsyncClient, base_url: str, token: str) -> tuple[str, float, bool]:
    cid = random.choice(CUSTOMER_IDS)
    t0 = time.perf_counter()
    ok = False
    try:
        r = await client.post(
            f"{base_url}/identity/verify",
            json={"customer_id": cid},
            headers={"Authorization": f"Bearer {token}"},
            timeout=15.0,
        )
        ok = r.status_code == 200
    except Exception:
        pass
    return "identity", time.perf_counter() - t0, ok


async def scenario_fraud(client: httpx.AsyncClient, base_url: str, token: str) -> tuple[str, float, bool]:
    aid = random.choice(ACCOUNT_IDS)
    t0 = time.perf_counter()
    ok = False
    try:
        r = await client.post(
            f"{base_url}/fraud/check",
            json={"account_id": aid},
            headers={"Authorization": f"Bearer {token}"},
            timeout=15.0,
        )
        ok = r.status_code == 200
    except Exception:
        pass
    return "fraud", time.perf_counter() - t0, ok


async def scenario_assistant(client: httpx.AsyncClient, base_url: str, token: str) -> tuple[str, float, bool]:
    msg = random.choice(CHAT_MESSAGES)
    t0 = time.perf_counter()
    ok = False
    try:
        r = await client.post(
            f"{base_url}/assistant/chat",
            json={"message": msg},
            headers={"Authorization": f"Bearer {token}"},
            timeout=30.0,
        )
        ok = r.status_code == 200
    except Exception:
        pass
    return "assistant", time.perf_counter() - t0, ok


SCENARIOS = [scenario_identity, scenario_fraud, scenario_assistant]


# ------------------------------------------------------------------
# Worker — one virtual user
# ------------------------------------------------------------------

async def worker(worker_id: int, base_url: str, token: str, stop_event: asyncio.Event,
                 results_list: list) -> None:
    async with httpx.AsyncClient() as client:
        while not stop_event.is_set():
            scenario = random.choice(SCENARIOS)
            endpoint, latency_s, success = await scenario(client, base_url, token)
            results_list.append({
                "worker": worker_id,
                "endpoint": endpoint,
                "latency_ms": round(latency_s * 1000, 2),
                "success": success,
            })
            await asyncio.sleep(random.uniform(0.05, 0.5))


# ------------------------------------------------------------------
# Percentile helper
# ------------------------------------------------------------------

def percentile(data: list[float], p: float) -> float:
    if not data:
        return 0.0
    s = sorted(data)
    idx = int(len(s) * p / 100)
    return s[min(idx, len(s) - 1)]


# ------------------------------------------------------------------
# Main
# ------------------------------------------------------------------

async def run(base_url: str, num_users: int, duration_s: int) -> None:
    print(f"\nVERITAS Fabric Load Test")
    print(f"  Target   : {base_url}")
    print(f"  Users    : {num_users}")
    print(f"  Duration : {duration_s}s")
    print()

    # Auth
    async with httpx.AsyncClient() as client:
        print("Authenticating… ", end="", flush=True)
        token = await get_token(client, base_url)
        print("OK\n")

    results: list[dict] = []
    stop = asyncio.Event()

    tasks = [asyncio.create_task(worker(i, base_url, token, stop, results)) for i in range(num_users)]
    print(f"Running {num_users} workers for {duration_s}s…", flush=True)

    for elapsed in range(duration_s):
        await asyncio.sleep(1)
        if (elapsed + 1) % 10 == 0:
            print(f"  {elapsed + 1}s elapsed — {len(results)} requests so far")

    stop.set()
    await asyncio.gather(*tasks, return_exceptions=True)

    # Aggregate
    by_endpoint: dict[str, list[dict]] = {}
    for r in results:
        by_endpoint.setdefault(r["endpoint"], []).append(r)

    summary: dict = {
        "config": {"base_url": base_url, "num_users": num_users, "duration_s": duration_s},
        "total_requests": len(results),
        "total_success": sum(1 for r in results if r["success"]),
        "by_endpoint": {},
    }

    print(f"\n{'─'*60}")
    print(f"{'Endpoint':<15} {'Count':>7} {'OK%':>6} {'p50ms':>8} {'p95ms':>8} {'p99ms':>8}")
    print(f"{'─'*60}")

    for ep, ep_results in sorted(by_endpoint.items()):
        latencies = [r["latency_ms"] for r in ep_results]
        ok_count  = sum(1 for r in ep_results if r["success"])
        ok_pct    = ok_count / len(ep_results) * 100 if ep_results else 0
        p50 = percentile(latencies, 50)
        p95 = percentile(latencies, 95)
        p99 = percentile(latencies, 99)
        print(f"{ep:<15} {len(ep_results):>7} {ok_pct:>5.1f}% {p50:>8.1f} {p95:>8.1f} {p99:>8.1f}")
        summary["by_endpoint"][ep] = {
            "count": len(ep_results),
            "ok_pct": round(ok_pct, 1),
            "p50_ms": round(p50, 1),
            "p95_ms": round(p95, 1),
            "p99_ms": round(p99, 1),
            "mean_ms": round(statistics.mean(latencies), 1) if latencies else 0,
        }

    all_latencies = [r["latency_ms"] for r in results]
    total_ok      = sum(1 for r in results if r["success"])
    print(f"{'─'*60}")
    print(f"{'ALL':<15} {len(results):>7} {total_ok / len(results) * 100:>5.1f}% "
          f"{percentile(all_latencies,50):>8.1f} {percentile(all_latencies,95):>8.1f} {percentile(all_latencies,99):>8.1f}")
    print(f"{'─'*60}\n")

    # Write results
    out_path = Path(__file__).parent / "results.json"
    out_path.write_text(json.dumps(summary, indent=2))
    print(f"Results written to {out_path}\n")


def main():
    parser = argparse.ArgumentParser(description="VERITAS Fabric load test")
    parser.add_argument("--url",      default="http://localhost:8000", help="Backend base URL")
    parser.add_argument("--users",    type=int, default=50,  help="Concurrent virtual users")
    parser.add_argument("--duration", type=int, default=120, help="Test duration in seconds")
    args = parser.parse_args()
    asyncio.run(run(args.url, args.users, args.duration))


if __name__ == "__main__":
    main()
