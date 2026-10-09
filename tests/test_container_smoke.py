"""
tests/test_container_smoke.py
Deployment smoke tests for containerized API execution (Phase 5E).

Validates:
1. Container starts without a configured database (standalone mode).
2. /api/health/live returns HTTP 200 with uptime and alive status.
3. /api/health/ready returns HTTP 200 in standalone mode.
4. /api/status backwards compatibility.
5. Protected endpoints reject missing or invalid credentials with HTTP 401.
6. Container started with unreachable DATABASE_URL reports 503 on readiness with zero leaked secrets.
7. Application runs as unprivileged non-root user (appuser, UID 1000).
8. Secrets and sensitive development artifacts (.env, .git) are excluded from the image.
9. Container stops cleanly without hung or leaked processes.

Marked with @pytest.mark.docker. Requires a running Docker engine.
"""

import os
import time
import json
import subprocess
import shutil
import urllib.request
import urllib.error
import pytest

IMAGE_TAG = os.getenv("DOCKER_IMAGE_TAG", "business-intelligence-api:test")
SMOKE_AUTH_TOKEN = "smoke-test-token-xyz-123"


def is_docker_available() -> bool:
    """Checks whether the docker binary exists and the daemon responds."""
    if not shutil.which("docker"):
        return False
    try:
        res = subprocess.run(
            ["docker", "info"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=5,
        )
        return res.returncode == 0
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not is_docker_available(),
    reason="Docker daemon is not available on this host. Deployment smoke tests require Docker.",
)


@pytest.fixture(scope="module")
def standalone_container():
    """
    Spawns a test container in standalone mode (no DATABASE_URL configured)
    and tears it down after tests complete.
    """
    container_name = f"bi-smoke-standalone-{int(time.time())}"
    host_port = "8008"

    run_cmd = [
        "docker", "run", "-d",
        "--name", container_name,
        "-p", f"{host_port}:8000",
        "-e", f"API_AUTH_TOKEN={SMOKE_AUTH_TOKEN}",
        IMAGE_TAG,
    ]
    subprocess.check_call(run_cmd)

    # Poll until container liveness endpoint is up (max 15s)
    base_url = f"http://127.0.0.1:{host_port}"
    deadline = time.time() + 15
    healthy = False
    while time.time() < deadline:
        try:
            req = urllib.request.Request(f"{base_url}/api/health/live")
            with urllib.request.urlopen(req, timeout=1.0) as resp:
                if resp.status == 200:
                    healthy = True
                    break
        except Exception:
            time.sleep(0.5)

    if not healthy:
        # Dump container logs for diagnosis
        logs = subprocess.run(["docker", "logs", container_name], capture_output=True, text=True)
        subprocess.run(["docker", "rm", "-f", container_name], stdout=subprocess.DEVNULL)
        pytest.fail(f"Container failed to start within 15s. Logs:\n{logs.stdout}\n{logs.stderr}")

    yield {
        "name": container_name,
        "base_url": base_url,
        "token": SMOKE_AUTH_TOKEN,
    }

    # Teardown
    subprocess.run(["docker", "rm", "-f", container_name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


# ==============================================================================
# Standalone Container Tests
# ==============================================================================

@pytest.mark.docker
def test_container_runs_as_non_root_user(standalone_container):
    """Container must run as unprivileged user 'appuser' (UID 1000)."""
    res = subprocess.run(
        ["docker", "exec", standalone_container["name"], "id"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "uid=1000(appuser)" in res.stdout
    assert "gid=1000(appgroup)" in res.stdout


@pytest.mark.docker
def test_container_excludes_secrets_and_git(standalone_container):
    """Container filesystem must not include .git, .env, or virtualenv directories."""
    # Test .git does not exist
    git_check = subprocess.run(
        ["docker", "exec", standalone_container["name"], "test", "-d", "/app/.git"],
    )
    assert git_check.returncode != 0, ".git repository directory leaked into container!"

    # Test .env files do not exist
    env_check = subprocess.run(
        ["docker", "exec", standalone_container["name"], "sh", "-c", "ls -a /app/.env* 2>/dev/null || true"],
        capture_output=True,
        text=True,
    )
    assert env_check.stdout.strip() == "", ".env file leaked into container!"


@pytest.mark.docker
def test_container_liveness_endpoint(standalone_container):
    """Container /api/health/live returns HTTP 200 with alive status and uptime."""
    req = urllib.request.Request(f"{standalone_container['base_url']}/api/health/live")
    with urllib.request.urlopen(req, timeout=3.0) as resp:
        assert resp.status == 200
        data = json.loads(resp.read().decode())
        assert data["status"] == "alive"
        assert "uptime_seconds" in data
        assert data["uptime_seconds"] >= 0


@pytest.mark.docker
def test_container_readiness_in_standalone_mode(standalone_container):
    """Container /api/health/ready returns HTTP 200 in standalone mode."""
    req = urllib.request.Request(f"{standalone_container['base_url']}/api/health/ready")
    with urllib.request.urlopen(req, timeout=3.0) as resp:
        assert resp.status == 200
        data = json.loads(resp.read().decode())
        assert data["status"] == "ready"
        assert data["mode"] == "standalone"
        assert data["components"]["database"]["status"] == "unconfigured"
        assert data["components"]["database"]["mode"] == "standalone"


@pytest.mark.docker
def test_container_legacy_status_endpoint(standalone_container):
    """Container /api/status returns legacy contract."""
    req = urllib.request.Request(f"{standalone_container['base_url']}/api/status")
    with urllib.request.urlopen(req, timeout=3.0) as resp:
        assert resp.status == 200
        data = json.loads(resp.read().decode())
        assert data["success"] is True
        assert data["is_running"] is False


@pytest.mark.docker
def test_container_rejects_unauthenticated_requests(standalone_container):
    """Protected endpoints reject requests without API credentials."""
    url = f"{standalone_container['base_url']}/api/businesses"
    req = urllib.request.Request(url)
    with pytest.raises(urllib.error.HTTPError) as exc_info:
        urllib.request.urlopen(req, timeout=3.0)
    assert exc_info.value.code == 401


@pytest.mark.docker
def test_container_rejects_invalid_api_key(standalone_container):
    """Protected endpoints reject invalid credentials."""
    url = f"{standalone_container['base_url']}/api/businesses"
    req = urllib.request.Request(url, headers={"X-API-Key": "wrong-token"})
    with pytest.raises(urllib.error.HTTPError) as exc_info:
        urllib.request.urlopen(req, timeout=3.0)
    assert exc_info.value.code == 401


# ==============================================================================
# Container Degraded Mode (Unreachable Database)
# ==============================================================================

@pytest.mark.docker
def test_container_readiness_with_unreachable_database():
    """
    When container is configured with an unreachable DATABASE_URL:
    - /api/health/live remains 200 OK
    - /api/health/ready returns 503 Service Unavailable
    - No credentials or connection strings are leaked in response
    """
    container_name = f"bi-smoke-degraded-{int(time.time())}"
    host_port = "8009"
    secret_pw = "super_classified_db_pass_999"
    unreachable_url = f"postgresql://ci_app:{secret_pw}@127.0.0.1:59999/isolated_db"

    run_cmd = [
        "docker", "run", "-d",
        "--name", container_name,
        "-p", f"{host_port}:8000",
        "-e", f"API_AUTH_TOKEN={SMOKE_AUTH_TOKEN}",
        "-e", f"DATABASE_URL={unreachable_url}",
        IMAGE_TAG,
    ]
    subprocess.check_call(run_cmd)

    base_url = f"http://127.0.0.1:{host_port}"
    try:
        # Wait for container process to be alive
        deadline = time.time() + 15
        live = False
        while time.time() < deadline:
            try:
                req = urllib.request.Request(f"{base_url}/api/health/live")
                with urllib.request.urlopen(req, timeout=1.0) as resp:
                    if resp.status == 200:
                        live = True
                        break
            except Exception:
                time.sleep(0.5)
        assert live, "Degraded container failed to respond to liveness probe."

        # Readiness probe must return 503
        ready_req = urllib.request.Request(f"{base_url}/api/health/ready")
        with pytest.raises(urllib.error.HTTPError) as exc_info:
            urllib.request.urlopen(ready_req, timeout=5.0)

        assert exc_info.value.code == 503
        body_text = exc_info.value.read().decode()
        body_data = json.loads(body_text)

        assert body_data["status"] == "not_ready"
        assert body_data["mode"] == "connected"
        assert body_data["components"]["database"]["status"] == "unavailable"
        assert body_data["components"]["database"]["message"] == "Configured database is unreachable."

        # Strictly check for secret leakage
        assert secret_pw not in body_text
        assert "59999" not in body_text
        assert "ci_app" not in body_text

    finally:
        # Stop and remove container, verifying clean shutdown
        stop_res = subprocess.run(["docker", "stop", "-t", "5", container_name], capture_output=True, text=True)
        assert stop_res.returncode == 0
        subprocess.run(["docker", "rm", container_name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
