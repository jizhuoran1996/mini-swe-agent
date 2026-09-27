"""Opt-in two-instance smoke tests against real runtimes; never substitute local execution."""

import json
import os
import shlex
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from minisweagent.executors import get_executor
from tests.environments.test_remote import remote_config, sandbox_server

RUNTIME_CONFIG = (
    json.loads(Path(os.environ["MSWEA_RUNTIME_TEST_CONFIG"]).read_text())
    if os.getenv("MSWEA_RUNTIME_TEST_CONFIG")
    else {"cases": [{"name": "not-configured"}]}
)


@pytest.mark.slow
@pytest.mark.skipif(
    not os.getenv("MSWEA_RUNTIME_TEST_CONFIG"), reason="Set MSWEA_RUNTIME_TEST_CONFIG to real backend configs"
)
@pytest.mark.parametrize(("case",), [(case,) for case in RUNTIME_CONFIG["cases"]], ids=lambda case: case["name"])  # noqa: PT006
def test_real_backend_pair_isolation_and_timeout(case):
    args = ["--vm-networks", RUNTIME_CONFIG["networks_file"]] if RUNTIME_CONFIG.get("networks_file") else []
    configs = case["sandboxes"] if "sandboxes" in case else [case["sandbox"], case["sandbox"]]
    executors = []
    with sandbox_server(*args) as server, ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(get_executor, remote_config(server, sandbox=config)) for config in configs]
        try:
            # Collect successful constructors even if the other one failed, so they always get cleaned up.
            for future in futures:
                if future.exception() is None:
                    executors.append(future.result())
            assert len(executors) == 2, [str(future.exception()) for future in futures]
            assert executors[0].sandbox_id != executors[1].sandbox_id

            def run_one(index):
                script = (
                    "import json,time; from pathlib import Path; start=time.time(); "
                    f"Path('/root/mini-sandbox-marker').write_text('{index}'); "
                    "time.sleep(3); print(json.dumps({'start':start,'end':time.time()}))"
                )
                result = executors[index].execute("python3 -c " + shlex.quote(script), timeout=15)
                assert result["returncode"] == 0, result
                return json.loads(result["output"])

            intervals = list(pool.map(run_one, range(2)))
            # These test guests use host-synchronized wall clocks. Commands must overlap, not queue globally.
            assert max(item["start"] for item in intervals) < min(item["end"] for item in intervals), intervals
            for index, executor in enumerate(executors):
                assert executor.execute("cat /root/mini-sandbox-marker")["output"] == str(index)
                assert executor.execute("pwd", cwd="/tmp")["output"].strip() == "/tmp"
                assert (
                    executor.execute('printf "%s" "$VALUE"', env={"VALUE": "a 'quote'; $(exit 9)"})["output"]
                    == "a 'quote'; $(exit 9)"
                )
                assert executor.execute("exit 42")["returncode"] == 42
            timed_out = executors[0].execute("sleep 10", timeout=0.5)
            assert timed_out["extra"]["exception_type"] == "TimeoutExpired", timed_out
            deadline = time.monotonic() + 20
            while executors[0]._request("GET", executors[0]._path)["state"] != "closed":
                assert time.monotonic() < deadline, "Timed-out sandbox was not reclaimed"
                time.sleep(0.05)
            assert executors[1].execute("cat /root/mini-sandbox-marker")["output"] == "1"
        finally:
            list(pool.map(lambda executor: executor.cleanup(), executors))
