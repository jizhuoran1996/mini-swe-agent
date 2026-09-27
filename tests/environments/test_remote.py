import json
import os
import select
import shlex
import socket
import subprocess
import sys
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path

import pytest
import requests
from typer.testing import CliRunner

from minisweagent.agents.journal import JournalAgent
from minisweagent.environments import get_environment
from minisweagent.environments.executor import ExecutorEnvironment
from minisweagent.environments.local import LocalEnvironment
from minisweagent.exceptions import Submitted
from minisweagent.executors import get_executor
from minisweagent.executors.sandbox import SandboxError, SandboxManager
from minisweagent.models.replay import RecordingModel
from minisweagent.models.test_models import make_toolcall_output
from minisweagent.run.replay import app, get_replay_environment_config


@contextmanager
def sandbox_server(*args, token=""):
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "minisweagent.run.sandbox_server",
            "--port",
            "0",
            "--token-env",
            "MSWEA_REMOTE_TEST_TOKEN",
            *args,
        ],
        env=os.environ | {"MSWEA_SILENT_STARTUP": "1", "MSWEA_REMOTE_TEST_TOKEN": token},
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        assert select.select([process.stdout], [], [], 15)[0], "Sandbox service did not start"
        ready = process.stdout.readline()
        assert ready, process.stderr.read()
        yield json.loads(ready)
    finally:
        process.terminate()
        _, stderr = process.communicate(timeout=20)
        assert process.returncode == 0, stderr


@pytest.fixture
def server():
    with sandbox_server("--allow-local", "--max-sandboxes", "4") as ready:
        yield ready


def remote_config(server, **kwargs):
    return {
        "backend": "remote",
        "endpoint": server["endpoint"],
        "token_env": "MSWEA_REMOTE_TEST_TOKEN",
        "sandbox": {"backend": "local"},
        "poll_interval": 0.01,
        **kwargs,
    }


def wait_status(endpoint, path, target, headers=None):
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        response = requests.get(endpoint + path, headers=headers, timeout=2)
        response.raise_for_status()
        if response.json()["state"] == target:
            return response.json()
        time.sleep(0.01)
    pytest.fail(f"{path} did not reach {target}: {response.text}")


def test_separate_process_parallel_sessions_and_environment_adapter(server, tmp_path):
    with ThreadPoolExecutor(max_workers=2) as pool:
        executors = list(pool.map(lambda _: get_executor(remote_config(server)), range(2)))
        workspaces = []
        try:
            assert executors[0].sandbox_id != executors[1].sandbox_id
            for executor in executors:
                workspaces.append(Path(executor.execute("pwd")["output"].strip()))
                assert executor.execute('printf "%s" "$PPID"')["output"] == str(server["pid"])
            assert workspaces[0] != workspaces[1]
            commands = []
            for index in range(2):
                script = (
                    "from pathlib import Path\nimport time\n"
                    f"Path({str(tmp_path / str(index))!r}).touch()\n"
                    "deadline = time.monotonic() + 5\n"
                    f"while not Path({str(tmp_path / str(1 - index))!r}).exists():\n"
                    "    assert time.monotonic() < deadline, 'other sandbox did not run concurrently'\n"
                    "    time.sleep(0.01)\n"
                    f"Path('artifact').write_text({str(index)!r})\nprint('overlap')\n"
                )
                commands.append(f"{shlex.quote(sys.executable)} -c {shlex.quote(script)}")
            results = list(pool.map(lambda pair: pair[0].execute(pair[1]), zip(executors, commands)))
            assert [result["output"].strip() for result in results] == ["overlap", "overlap"]
            for index, executor in enumerate(executors):
                assert executor.execute("cat artifact")["output"] == str(index)
                assert (
                    executor.execute('printf "%s" "$VALUE"', env={"VALUE": "a 'quote'; $(exit 9)"})["output"]
                    == "a 'quote'; $(exit 9)"
                )
            environment = ExecutorEnvironment(executor=executors[0])
            with pytest.raises(Submitted) as submitted:
                environment.execute({"command": "printf 'COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT\\nremote-patch'"})
            assert submitted.value.messages[0]["extra"]["submission"] == "remote-patch"
            config = environment.serialize()["info"]["config"]["environment"]["executor"]
            assert config["sandbox"] == {"backend": "local"}
            assert config["token_env"] == "MSWEA_REMOTE_TEST_TOKEN"
        finally:
            list(pool.map(lambda executor: executor.cleanup(), executors))
        assert all(not workspace.exists() for workspace in workspaces)


def test_fifo_idempotent_requests_and_rejected_conflicts(server):
    endpoint = server["endpoint"]
    session_id = uuid.uuid4().hex
    path = f"/sandboxes/{session_id}"
    payload = {"id": session_id, "sandbox": {"backend": "local"}}
    assert requests.post(endpoint + "/sandboxes", json=payload, timeout=2).status_code == 202
    assert requests.post(endpoint + "/sandboxes", json=payload, timeout=2).status_code == 202
    assert (
        requests.post(endpoint + "/sandboxes", json=payload | {"sandbox": {"backend": "docker"}}, timeout=2).status_code
        == 409
    )
    first = {"id": uuid.uuid4().hex, "command": "sleep 0.15; printf first >> history; cat history"}
    second = {"id": uuid.uuid4().hex, "command": "printf second >> history; cat history"}
    for request in (first, second, first):
        assert requests.post(endpoint + path + "/executions", json=request, timeout=2).status_code == 202
    conflict = requests.post(endpoint + path + "/executions", json=first | {"command": "echo changed"}, timeout=2)
    assert conflict.status_code == 409
    assert wait_status(endpoint, path + f"/executions/{first['id']}", "completed")["result"]["output"] == "first"
    assert wait_status(endpoint, path + f"/executions/{second['id']}", "completed")["result"]["output"] == "firstsecond"
    assert requests.delete(endpoint + path, timeout=2).status_code == 202
    wait_status(endpoint, path, "closed")
    # A retry after cleanup still returns the old result, never starts a new sandbox or command.
    assert requests.post(endpoint + "/sandboxes", json=payload, timeout=2).json()["state"] == "closed"
    assert requests.post(endpoint + path + "/executions", json=first, timeout=2).json()["result"]["output"] == "first"
    assert (
        requests.post(
            endpoint + path + "/executions", json={"id": uuid.uuid4().hex, "command": "true"}, timeout=2
        ).status_code
        == 409
    )


def test_remote_timeout_output_cwd_and_heartbeat():
    with sandbox_server("--allow-local", "--lease-seconds", "0.6") as server:
        environment = get_environment(
            {
                "environment_class": "executor",
                "executor": remote_config(server, env={"DEFAULT_VALUE": "configured"}),
            }
        )
        executor = environment.executor
        try:
            time.sleep(1.3)  # Lease must survive a slow LLM turn with no tool calls.
            result = executor.execute("printf ready; sleep 5", timeout=0.1)
            assert result["returncode"] == -1
            assert result["output"] == "ready"
            assert result["extra"]["exception_type"] == "TimeoutExpired"
            assert executor.execute('printf "%s" "$DEFAULT_VALUE"')["output"] == "configured"
            assert executor.execute("mkdir 'sub directory'")["returncode"] == 0
            workspace = executor.execute("pwd")["output"].strip()
            assert (
                executor.execute("pwd", cwd=workspace + "/sub directory")["output"].strip()
                == workspace + "/sub directory"
            )
        finally:
            executor.cleanup()


def test_auth_capacity_expiry_and_no_local_fallback():
    token = "development-test-token"
    headers = {"Authorization": f"Bearer {token}"}
    with sandbox_server("--allow-local", "--max-sandboxes", "1", "--lease-seconds", "0.3", token=token) as server:
        endpoint = server["endpoint"]
        assert requests.get(endpoint + "/health", timeout=2).status_code == 401
        assert requests.get(endpoint + "/health", headers=headers, timeout=2).json()["protocol_version"] == 1
        first = {"id": uuid.uuid4().hex, "sandbox": {"backend": "local"}}
        second = {"id": uuid.uuid4().hex, "sandbox": {"backend": "local"}}
        assert requests.post(endpoint + "/sandboxes", json=first, headers=headers, timeout=2).status_code == 202
        assert requests.post(endpoint + "/sandboxes", json=second, headers=headers, timeout=2).status_code == 429
        time.sleep(0.7)
        assert (
            requests.get(endpoint + f"/sandboxes/{first['id']}", headers=headers, timeout=2).json()["state"] == "closed"
        )
        assert requests.post(endpoint + "/sandboxes", json=second, headers=headers, timeout=2).status_code == 202
    with sandbox_server() as server:
        with pytest.raises(RuntimeError, match="local requires"):
            get_executor(remote_config(server))
        with pytest.raises(RuntimeError, match="Unsupported backend"):
            get_executor(remote_config(server, sandbox={"backend": "minisweagent.executors.local.LocalExecutor"}))
        with pytest.raises(RuntimeError, match="No such file"):
            get_executor(
                remote_config(
                    server, sandbox={"backend": "docker", "image": "unused", "executable": "/missing-docker-binary"}
                )
            )


def test_firecracker_slot_validation_and_private_disks():
    slot = {"tap_device": "tap-test", "guest_ip": "172.16.0.2", "guest_mac": "06:00:AC:10:00:02"}
    with pytest.raises(ValueError, match="unique"):
        SandboxManager(firecracker_networks=[slot, slot])
    manager = SandboxManager(
        firecracker_networks=[
            slot,
            {
                "tap_device": "tap-test-2",
                "guest_ip": "172.16.1.2",
                "guest_mac": "06:00:AC:10:01:02",
            },
        ]
    )
    try:
        with pytest.raises(SandboxError, match="private writable root"):
            manager.create(
                uuid.uuid4().hex,
                {
                    "backend": "firecracker",
                    "copy_root_drive": "false",
                    "kernel_image": "unused",
                    "root_drive": "unused",
                },
            )
        with pytest.raises(SandboxError, match="Unsupported backend"):
            manager.create(uuid.uuid4().hex, {"backend": "remote"})
        # Real failed boots must release their assigned slot, not exhaust the pool.
        for _ in range(2):
            session_id = uuid.uuid4().hex
            manager.create(
                session_id,
                {
                    "backend": "firecracker",
                    "kernel_image": "unused",
                    "root_drive": "unused",
                    "firecracker_executable": "/missing-firecracker-binary",
                },
            )
            deadline = time.monotonic() + 3
            while manager.status(session_id)["state"] != "closed":
                assert time.monotonic() < deadline
                time.sleep(0.01)
            assert "Executable not found" in manager.status(session_id)["error"]
            assert not manager._reserved
        # Hold the registry lock so failed boots cannot release slots while we check concurrent reservations.
        with manager._lock:
            ids = [uuid.uuid4().hex for _ in range(2)]
            config = {
                "backend": "firecracker",
                "kernel_image": "unused",
                "root_drive": "unused",
                "firecracker_executable": "/missing-firecracker-binary",
            }
            for session_id in ids:
                manager.create(session_id, config)
            assert manager._reserved == {0, 1}
            assert {manager._sessions[session_id].config["tap_device"] for session_id in ids} == {
                "tap-test",
                "tap-test-2",
            }
            with pytest.raises(SandboxError, match="No free VM network slots"):
                manager.create(uuid.uuid4().hex, config)
    finally:
        manager.shutdown()


def test_remote_replay_keeps_model_on_a_and_protects_source_workspace(server, tmp_path):
    source = {
        "environment_type": "minisweagent.environments.executor.ExecutorEnvironment",
        "environment": {"executor": remote_config(server, sandbox={"backend": "local", "cwd": str(tmp_path)})},
    }
    with pytest.raises(ValueError, match="fresh workspace"):
        get_replay_environment_config(source, "new")
    source["environment"]["executor"]["sandbox"] = {"backend": "docker", "image": "task-image"}
    derived = get_replay_environment_config(source, "new")
    assert "--pull=never" in derived["executor"]["sandbox"]["run_args"]
    assert "run_args" not in source["environment"]["executor"]["sandbox"]
    source["environment"]["executor"]["sandbox"]["run_args"] = ["-v", "/source:/testbed"]
    with pytest.raises(ValueError, match="mounted storage"):
        get_replay_environment_config(source, "new")

    commands = ['printf "%s" "$LOCATION"', 'echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT; printf "%s" "$LOCATION"']
    responses = [
        make_toolcall_output(
            "",
            [
                {
                    "id": str(index),
                    "type": "function",
                    "function": {"name": "bash", "arguments": json.dumps({"command": command})},
                }
            ],
            [{"command": command, "tool_call_id": str(index)}],
        )
        for index, command in enumerate(commands)
    ]
    model = RecordingModel(
        store_path=str(tmp_path / "tapes"),
        episode_id="source",
        backend={
            "model_class": "minisweagent.models.test_models.DeterministicToolcallModel",
            "model_name": "offline-remote-test",
            "outputs": responses,
        },
    )
    agent = JournalAgent(
        model,
        LocalEnvironment(cwd=str(tmp_path), env={"LOCATION": "A"}),
        system_template="system",
        instance_template="{{ task }}",
        step_limit=3,
    )
    assert agent.run("show execution location")["submission"] == "A"
    agent.save(tmp_path / "source.index.json")
    override = tmp_path / "remote.json"
    override.write_text(
        json.dumps(
            {
                "environment": {
                    "environment_class": "executor",
                    "executor": remote_config(server, sandbox={"backend": "local", "env": {"LOCATION": "B"}}),
                }
            }
        )
    )
    output = tmp_path / "remote.index.json"
    result = CliRunner().invoke(
        app,
        [
            "run",
            "--store",
            str(tmp_path / "tapes"),
            "--source",
            "source",
            "--episode",
            "remote",
            "--output",
            str(output),
            "--environment-config",
            str(override),
            "--timing",
            "instant",
        ],
    )
    assert result.exit_code == 0, result.output
    summary = json.loads(output.with_suffix(".summary.json").read_text())
    assert summary["actual_api_calls"] == 0
    assert summary["submission_matches"] is False
    assert summary["input_difference_rounds"] == 1


def test_resume_uncertain_execution_without_duplicate_side_effects(server):
    executor = get_executor(remote_config(server))
    endpoint = executor.config.endpoint
    try:
        # A bound but non-listening port produces a real connection failure, without mocks.
        with socket.socket() as unavailable:
            unavailable.bind(("127.0.0.1", 0))
            executor.config.endpoint = f"http://127.0.0.1:{unavailable.getsockname()[1]}"
            with pytest.raises(requests.ConnectionError):
                executor.execute("printf once >> artifact; cat artifact")
        assert executor.pending_execution_id
        with pytest.raises(RuntimeError, match="unresolved"):
            executor.execute("echo do-not-run")
        executor.config.endpoint = endpoint
        # Deliver the pending request while the caller still has no result, then let resume retry it.
        path = f"/sandboxes/{executor.sandbox_id}/executions"
        assert requests.post(endpoint + path, json=executor._pending_payload, timeout=2).status_code == 202
        assert executor.resume_execution()["output"] == "once"
        assert executor.pending_execution_id is None
        assert executor.execute("cat artifact")["output"] == "once"
    finally:
        executor.config.endpoint = endpoint
        executor.cleanup()


@pytest.mark.slow
@pytest.mark.skipif(not os.getenv("MSWEA_REMOTE_TEST_IMAGE"), reason="Set MSWEA_REMOTE_TEST_IMAGE for real containers")
@pytest.mark.parametrize(("backend",), [("docker",), ("gvisor",)])  # noqa: PT006 -- AGENTS.md requires tuples
def test_real_remote_containers(backend):
    with sandbox_server() as server, ThreadPoolExecutor(max_workers=2) as pool:
        config = remote_config(
            server,
            sandbox={
                "backend": backend,
                "image": os.environ["MSWEA_REMOTE_TEST_IMAGE"],
                "run_args": ["--rm", "--pull=never"],
            },
        )
        executors = list(pool.map(lambda _: get_executor(config), range(2)))
        try:
            results = list(pool.map(lambda executor: executor.execute("hostname"), executors))
            assert all(result["returncode"] == 0 for result in results)
            assert results[0]["output"] != results[1]["output"]
        finally:
            list(pool.map(lambda executor: executor.cleanup(), executors))


@pytest.mark.slow
@pytest.mark.skipif(
    not os.getenv("MSWEA_REMOTE_TEST_FIRECRACKER"), reason="Set MSWEA_REMOTE_TEST_FIRECRACKER to a VM config JSON"
)
def test_real_remote_firecracker_pair():
    config = json.loads(Path(os.environ["MSWEA_REMOTE_TEST_FIRECRACKER"]).read_text())
    with (
        sandbox_server("--firecracker-networks", config["networks_file"]) as server,
        ThreadPoolExecutor(max_workers=2) as pool,
    ):
        executors = list(pool.map(lambda _: get_executor(remote_config(server, sandbox=config["sandbox"])), range(2)))
        try:
            results = list(
                pool.map(lambda executor: executor.execute("cat /proc/sys/kernel/random/boot_id"), executors)
            )
            assert all(result["returncode"] == 0 for result in results)
            assert results[0]["output"] != results[1]["output"]
        finally:
            list(pool.map(lambda executor: executor.cleanup(), executors))
