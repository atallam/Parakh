"""Concurrent agent execution (C5.5): many runs at once, no lost or mixed-up results."""

import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from parakh.orchestration.graph import run_pipeline

RUNS = 50
WORKERS = 10


@pytest.mark.load
def test_parallel_pipelines(fake_llm, tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("MAX_LLM_CALLS_PER_MINUTE", "10000")
    llm = fake_llm('{"title": "T", "bullets": ["b"], "confidence": 0.9}')

    def one(i: int) -> tuple[int, float, bool]:
        start = time.perf_counter()
        result = run_pipeline(f"document {i}", client=llm.client(agent_name=f"load-{i}"))
        return i, time.perf_counter() - start, result.summary is not None

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        results = list(pool.map(one, range(RUNS)))

    assert all(ok for _, _, ok in results)
    assert len(llm.calls) == RUNS
    prompts = {call["prompt"] for call in llm.calls}
    assert all(any(f"document {i}" in p for p in prompts) for i in range(RUNS))
    latencies = sorted(t for _, t, _ in results)
    assert latencies[int(RUNS * 0.95) - 1] < 2.0  # p95 with a fake LLM
