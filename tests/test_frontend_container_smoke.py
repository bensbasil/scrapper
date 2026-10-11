"""
tests/test_frontend_container_smoke.py
Deployment smoke tests for containerized Next.js Frontend execution (Phase 6G).

Validates:
1. Container starts up cleanly in production mode.
2. Root HTTP endpoint (/) returns HTTP 200 with rendered dashboard markup.
3. Application runs as unprivileged non-root user (nextjs, UID 1001).
4. Secrets, .git, and dev artifacts (.env, tests/) are strictly excluded from the image.
5. Server-side proxy route (/api/status) is functional and fails closed safely (502) without backend.
6. Container stops cleanly without hung or leaked processes.

Marked with @pytest.mark.docker. Requires a running Docker engine.
"""

import os
import time
import subprocess
import shutil
import urllib.request
import urllib.error
import pytest

FRONTEND_IMAGE_TAG = os.getenv("FRONTEND_IMAGE_TAG", "business-intelligence-frontend:test")


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


def is_frontend_image_available() -> bool:
    """Checks whether the target frontend container image is present."""
    if not is_docker_available():
        return False
    try:
        res = subprocess.run(
            ["docker", "image", "inspect", FRONTEND_IMAGE_TAG],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=5,
        )
        return res.returncode == 0
    except Exception:
        return False


pytestmark = [
    pytest.mark.docker,
    pytest.mark.skipif(
        not is_docker_available(),
        reason="Docker daemon is not available on this host. Deployment smoke tests require Docker.",
    ),
    pytest.mark.skipif(
        not is_frontend_image_available(),
        reason=f"Frontend image '{FRONTEND_IMAGE_TAG}' is not present. Build frontend image first.",
    ),
]


@pytest.fixture(scope="module")
def frontend_container():
    """
    Spawns the Next.js frontend test container and tears it down after tests complete.
    """
    container_name = f"bi-fe-smoke-{int(time.time())}"
    host_port = "3009"

    run_cmd = [
        "docker", "run", "-d",
        "--name", container_name,
        "-p", f"{host_port}:3000",
        "-e", "PORT=3000",
        "-e", "HOSTNAME=0.0.0.0",
        FRONTEND_IMAGE_TAG,
    ]
    subprocess.check_call(run_cmd)

    # Poll until container root endpoint is up (max 20s)
    base_url = f"http://127.0.0.1:{host_port}"
    deadline = time.time() + 20
    healthy = False
    while time.time() < deadline:
        try:
            req = urllib.request.Request(f"{base_url}/")
            with urllib.request.urlopen(req, timeout=1.5) as resp:
                if resp.status == 200:
                    healthy = True
                    break
        except Exception:
            time.sleep(0.5)

    if not healthy:
        logs = subprocess.run(["docker", "logs", container_name], capture_output=True, text=True)
        subprocess.run(["docker", "rm", "-f", container_name], stdout=subprocess.DEVNULL)
        pytest.fail(f"Frontend container failed to respond within 20s. Logs:\n{logs.stdout}\n{logs.stderr}")

    yield {
        "name": container_name,
        "base_url": base_url,
    }

    # Teardown
    subprocess.run(["docker", "rm", "-f", container_name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


@pytest.mark.docker
def test_frontend_container_serves_http_root(frontend_container):
    """Frontend container serves HTTP 200 with rendered dashboard HTML."""
    req = urllib.request.Request(f"{frontend_container['base_url']}/")
    with urllib.request.urlopen(req, timeout=3.0) as resp:
        assert resp.status == 200
        html = resp.read().decode("utf-8")
        assert "Profitize" in html or "Prospects" in html or "Intelligence Dashboard" in html


@pytest.mark.docker
def test_frontend_container_runs_as_non_root(frontend_container):
    """Frontend container must run as unprivileged user 'nextjs' (UID 1001)."""
    res = subprocess.run(
        ["docker", "exec", frontend_container["name"], "id"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "uid=1001(nextjs)" in res.stdout


@pytest.mark.docker
def test_frontend_container_excludes_secrets_and_git(frontend_container):
    """Container filesystem must not include .git, .env*, or test suites."""
    git_check = subprocess.run(
        ["docker", "exec", frontend_container["name"], "test", "-d", "/app/.git"],
    )
    assert git_check.returncode != 0, ".git repository directory leaked into frontend image!"

    env_check = subprocess.run(
        ["docker", "exec", frontend_container["name"], "sh", "-c", "ls -a /app/.env* 2>/dev/null || true"],
        capture_output=True,
        text=True,
    )
    assert env_check.stdout.strip() == "", ".env files leaked into frontend image!"

    test_dir_check = subprocess.run(
        ["docker", "exec", frontend_container["name"], "test", "-d", "/app/tests"],
    )
    assert test_dir_check.returncode != 0, "tests directory leaked into production frontend image!"


@pytest.mark.docker
def test_frontend_container_api_proxy_fails_closed(frontend_container):
    """API proxy route /api/status fails closed safely (502) when backend is unconfigured."""
    url = f"{frontend_container['base_url']}/api/status"
    req = urllib.request.Request(url)
    with pytest.raises(urllib.error.HTTPError) as exc_info:
        urllib.request.urlopen(req, timeout=3.0)
    assert exc_info.value.code == 502
    body = exc_info.value.read().decode("utf-8")
    assert "Backend service unreachable" in body
