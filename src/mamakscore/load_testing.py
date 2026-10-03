# Bounded load execution and latency summaries.
from __future__ import annotations

import asyncio
import math
import time
from collections import Counter
from pathlib import Path

import httpx


def nearest_rank(values: list[float], quantile: float) -> float:
    if not values:
        raise ValueError("at least one latency is required")
    return sorted(values)[max(0, math.ceil(quantile * len(values)) - 1)]


def summarize(latencies: list[float], statuses: list[int], elapsed: float) -> dict[str, object]:
    return {
        "requests": len(statuses),
        "status_counts": dict(Counter(str(s) for s in statuses)),
        "elapsed_seconds": round(elapsed, 6),
        "throughput_per_second": round(len(statuses) / elapsed, 6) if elapsed else 0.0,
        "p50_seconds": round(nearest_rank(latencies, 0.5), 6),
        "p90_seconds": round(nearest_rank(latencies, 0.9), 6),
        "profile": "service-overhead-only",
    }


async def run_load(url: str, deck: Path, *, requests: int, concurrency: int) -> dict[str, object]:
    queue: asyncio.Queue[int] = asyncio.Queue()
    for i in range(requests):
        queue.put_nowait(i)
    latencies: list[float] = []
    statuses: list[int] = []
    data = deck.read_bytes()
    started = time.perf_counter()
    async with httpx.AsyncClient(timeout=70) as client:

        async def worker() -> None:
            while not queue.empty():
                try:
                    index = queue.get_nowait()
                except asyncio.QueueEmpty:
                    return
                tick = time.perf_counter()
                try:
                    response = await client.post(
                        url,
                        data={"application_id": f"load-{index}"},
                        files={"pitch_deck": ("deck.pdf", data, "application/pdf")},
                    )
                    statuses.append(response.status_code)
                except httpx.RequestError:
                    statuses.append(0)
                latencies.append(time.perf_counter() - tick)
                queue.task_done()

        await asyncio.gather(*(worker() for _ in range(min(concurrency, requests))))
    return summarize(latencies, statuses, time.perf_counter() - started)
