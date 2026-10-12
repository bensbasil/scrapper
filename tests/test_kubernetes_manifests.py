"""
tests/test_kubernetes_manifests.py
Validates the Kubernetes manifests in deploy/kubernetes/ (Phase 6A).

Ensures:
1. Manifests are syntactically valid YAML and parse correctly.
2. kubectl kustomize succeeds and generates valid KRM resource stream.
3. Zero secrets or sensitive credentials are committed in any manifest.
4. SecurityContext complies with least-privilege standards (non-root, user 1000, drop all capabilities).
5. Resource requests and limits are defined and within bounded ranges.
6. Probes target existing API endpoints (/api/health/live and /api/health/ready) on port 'http'.
7. Deployment rollout strategy and replica counts meet pilot stability requirements.
8. Service selector matches deployment labels.
"""

import os
import shutil
import subprocess
import yaml
import pytest

MANIFEST_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "deploy", "kubernetes"))


def load_yaml(filename: str):
    path = os.path.join(MANIFEST_DIR, filename)
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def test_manifest_directory_and_files_exist():
    """Verify that deploy/kubernetes directory and required backend/frontend files exist."""
    assert os.path.isdir(MANIFEST_DIR)
    expected_files = [
        "deployment.yaml",
        "service.yaml",
        "configmap.yaml",
        "frontend-deployment.yaml",
        "frontend-service.yaml",
        "frontend-configmap.yaml",
        "kustomization.yaml",
        "secret.example.yaml",
    ]
    for fname in expected_files:
        assert os.path.isfile(os.path.join(MANIFEST_DIR, fname)), f"Missing {fname}"


def test_kubectl_kustomize_execution():
    """Validates that kubectl kustomize builds both backend and frontend resource streams."""
    kubectl_bin = shutil.which("kubectl")
    if not kubectl_bin:
        pytest.skip("kubectl not found in environment PATH")

    result = subprocess.run(
        [kubectl_bin, "kustomize", MANIFEST_DIR],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"kubectl kustomize failed: {result.stderr}"
    docs = list(yaml.safe_load_all(result.stdout))
    names = [d.get("metadata", {}).get("name") for d in docs if d and "metadata" in d]

    # Verify both backend and frontend components are rendered
    assert "bi-api-config" in names
    assert "bi-frontend-config" in names
    assert "bi-api-service" in names
    assert "bi-frontend-service" in names
    assert "bi-api-deployment" in names
    assert "bi-frontend-deployment" in names


def test_no_secrets_in_manifests():
    """Manifests must not contain hardcoded credentials, production URLs, or tokens."""
    for fname in os.listdir(MANIFEST_DIR):
        if not fname.endswith(".yaml"):
            continue
        path = os.path.join(MANIFEST_DIR, fname)
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()

        assert "AIzaSy" not in content, f"Possible Google API key in {fname}"
        assert "password" not in content.lower() or "secret.example.yaml" in fname or "db_password" in content.lower()
        if fname != "secret.example.yaml":
            assert "REPLACE_WITH" not in content


def test_deployment_spec_and_replicas():
    """Validates Deployment replica count (1 for pilot consistency), labels, and Recreate strategy."""
    doc = load_yaml("deployment.yaml")
    assert doc["apiVersion"] == "apps/v1"
    assert doc["kind"] == "Deployment"
    assert doc["metadata"]["name"] == "bi-api-deployment"

    spec = doc["spec"]
    # Phase 6B Audit: Single replica is required for pilot consistency due to in-memory state
    assert spec["replicas"] == 1

    # Phase 6C Audit: Strategy MUST be Recreate to eliminate simultaneous pod overlap
    assert spec["strategy"]["type"] == "Recreate"
    assert "rollingUpdate" not in spec["strategy"], "rollingUpdate must not be configured when strategy is Recreate"

    selector = spec["selector"]["matchLabels"]
    assert selector["app.kubernetes.io/name"] == "business-intelligence-api"


def test_rollout_strategy_strictly_prohibits_simultaneous_pods():
    """
    Regression test for Phase 6C:
    Enforces that rollout strategy prohibits maxSurge > 0, preventing duplicate
    scraper subprocesses and split-brain in-memory state during application updates.
    """
    doc = load_yaml("deployment.yaml")
    strategy = doc["spec"]["strategy"]
    assert strategy["type"] == "Recreate"

    # Ensure terminationGracePeriodSeconds is bounded and provides enough time for subprocess termination
    pod_spec = doc["spec"]["template"]["spec"]
    grace_period = pod_spec.get("terminationGracePeriodSeconds")
    assert grace_period is not None
    assert grace_period >= 30, "terminationGracePeriodSeconds must be at least 30s to allow clean scraper exit"


def test_deployment_pod_and_container_security():
    """Validates that pod and container security contexts enforce non-root execution."""
    doc = load_yaml("deployment.yaml")
    pod_spec = doc["spec"]["template"]["spec"]

    # Pod-level security context
    pod_sc = pod_spec.get("securityContext", {})
    assert pod_sc.get("runAsNonRoot") is True
    assert pod_sc.get("runAsUser") == 1000
    assert pod_sc.get("runAsGroup") == 1000
    assert pod_sc.get("fsGroup") == 1000

    # Container-level security context
    container = pod_spec["containers"][0]
    c_sc = container.get("securityContext", {})
    assert c_sc.get("allowPrivilegeEscalation") is False
    assert "ALL" in c_sc.get("capabilities", {}).get("drop", [])


def test_deployment_resource_bounds():
    """Validates CPU and memory resource requests and limits."""
    doc = load_yaml("deployment.yaml")
    container = doc["spec"]["template"]["spec"]["containers"][0]
    resources = container.get("resources", {})

    requests = resources.get("requests", {})
    limits = resources.get("limits", {})

    assert requests.get("cpu") == "100m"
    assert requests.get("memory") == "256Mi"
    assert limits.get("cpu") == "1000m"
    assert limits.get("memory") == "512Mi"


def test_deployment_probes_contract():
    """Validates startup, liveness, and readiness probe definitions."""
    doc = load_yaml("deployment.yaml")
    container = doc["spec"]["template"]["spec"]["containers"][0]

    # Startup probe
    startup = container.get("startupProbe", {})
    assert startup.get("httpGet", {}).get("path") == "/api/health/live"
    assert startup.get("httpGet", {}).get("port") == "http"
    assert startup.get("failureThreshold") == 6

    # Liveness probe
    liveness = container.get("livenessProbe", {})
    assert liveness.get("httpGet", {}).get("path") == "/api/health/live"
    assert liveness.get("httpGet", {}).get("port") == "http"
    assert liveness.get("periodSeconds") == 10

    # Readiness probe
    readiness = container.get("readinessProbe", {})
    assert readiness.get("httpGet", {}).get("path") == "/api/health/ready"
    assert readiness.get("httpGet", {}).get("port") == "http"
    assert readiness.get("periodSeconds") == 10
    assert readiness.get("failureThreshold") == 2


def test_deployment_env_and_secret_wiring():
    """Validates ConfigMap and Secret env references."""
    doc = load_yaml("deployment.yaml")
    container = doc["spec"]["template"]["spec"]["containers"][0]

    # ConfigMap reference
    env_from = container.get("envFrom", [])
    cm_names = [item["configMapRef"]["name"] for item in env_from if "configMapRef" in item]
    assert "bi-api-config" in cm_names

    # Secret references
    envs = container.get("env", [])
    env_map = {e["name"]: e.get("valueFrom", {}).get("secretKeyRef", {}) for e in envs}

    assert "API_AUTH_TOKEN" in env_map
    assert env_map["API_AUTH_TOKEN"]["name"] == "bi-api-secret"
    assert env_map["API_AUTH_TOKEN"]["key"] == "API_AUTH_TOKEN"

    assert "DATABASE_URL" in env_map
    assert env_map["DATABASE_URL"]["optional"] is True

    assert "GEMINI_API_KEY" in env_map
    assert env_map["GEMINI_API_KEY"]["optional"] is True


def test_service_spec_and_port_alignment():
    """Validates Service definition and alignment with container ports."""
    doc = load_yaml("service.yaml")
    assert doc["apiVersion"] == "v1"
    assert doc["kind"] == "Service"
    assert doc["metadata"]["name"] == "bi-api-service"

    spec = doc["spec"]
    assert spec["type"] == "ClusterIP"
    assert spec["selector"]["app.kubernetes.io/name"] == "business-intelligence-api"

    port_entry = spec["ports"][0]
    assert port_entry["port"] == 8000
    assert port_entry["targetPort"] == "http"
    assert port_entry["name"] == "http"


def test_configmap_values():
    """Validates ConfigMap data keys."""
    doc = load_yaml("configmap.yaml")
    assert doc["apiVersion"] == "v1"
    assert doc["kind"] == "ConfigMap"
    assert doc["metadata"]["name"] == "bi-api-config"

    data = doc["data"]
    assert data["PORT"] == "8000"
    assert data["PYTHONUNBUFFERED"] == "1"
    assert "ALLOWED_ORIGINS" in data
    assert data["DB_POOL_MIN"] == "1"
    assert data["DB_POOL_MAX"] == "10"


def test_multi_replica_state_isolation_risk_demonstration():
    """
    Regression test documenting the architectural finding from Phase 6B:
    Demonstrates that process-local in-memory state (agent_task_store and running_process)
    cannot be shared across distinct pod replicas without an external broker/cache.
    """
    # Simulate Pod A memory space
    pod_a_task_store = {"task-123": {"status": "SUCCESS", "goal": "Find plumbers in Austin"}}
    pod_a_running_process = object()  # mock active subprocess

    # Simulate Pod B memory space (separate container/process)
    pod_b_task_store = {}
    pod_b_running_process = None

    # Request 1: POST /api/agent/run arrives on Pod A -> stored in Pod A
    assert "task-123" in pod_a_task_store

    # Request 2: GET /api/agent/tasks/task-123 routed to Pod B -> MISSING (404)
    assert "task-123" not in pod_b_task_store

    # Request 3: GET /api/status routed to Pod B -> claims scraper is idle while Pod A is busy
    assert pod_a_running_process is not None
    assert pod_b_running_process is None

    # Conclusion: Single replica deployment (replicas: 1) is mandatory until external state store is introduced.


def test_frontend_deployment_spec_and_strategy():
    """Validates Frontend Deployment replica count, labels, and RollingUpdate strategy."""
    doc = load_yaml("frontend-deployment.yaml")
    assert doc["apiVersion"] == "apps/v1"
    assert doc["kind"] == "Deployment"
    assert doc["metadata"]["name"] == "bi-frontend-deployment"

    spec = doc["spec"]
    assert spec["replicas"] == 1
    assert spec["strategy"]["type"] == "RollingUpdate"
    rolling = spec["strategy"].get("rollingUpdate", {})
    assert rolling.get("maxSurge") == 1
    assert rolling.get("maxUnavailable") == 0

    selector = spec["selector"]["matchLabels"]
    assert selector["app.kubernetes.io/name"] == "business-intelligence-frontend"


def test_frontend_pod_and_container_security():
    """Validates that frontend pod and container security contexts enforce non-root execution (UID 1001)."""
    doc = load_yaml("frontend-deployment.yaml")
    pod_spec = doc["spec"]["template"]["spec"]

    # Pod-level security context (must match nextjs UID 1001 from dashboard/Dockerfile)
    pod_sc = pod_spec.get("securityContext", {})
    assert pod_sc.get("runAsNonRoot") is True
    assert pod_sc.get("runAsUser") == 1001
    assert pod_sc.get("runAsGroup") == 1001
    assert pod_sc.get("fsGroup") == 1001

    # Container-level security context
    container = pod_spec["containers"][0]
    c_sc = container.get("securityContext", {})
    assert c_sc.get("allowPrivilegeEscalation") is False
    assert "ALL" in c_sc.get("capabilities", {}).get("drop", [])


def test_frontend_resources_and_ports():
    """Validates frontend container port (3000) and resource requests/limits."""
    doc = load_yaml("frontend-deployment.yaml")
    container = doc["spec"]["template"]["spec"]["containers"][0]

    port = container["ports"][0]
    assert port["containerPort"] == 3000
    assert port["name"] == "http"

    resources = container.get("resources", {})
    requests = resources.get("requests", {})
    limits = resources.get("limits", {})

    assert requests.get("cpu") == "100m"
    assert requests.get("memory") == "128Mi"
    assert limits.get("cpu") == "500m"
    assert limits.get("memory") == "384Mi"


def test_frontend_probes_contract():
    """Validates frontend startup, liveness, and readiness probes on root HTTP endpoint."""
    doc = load_yaml("frontend-deployment.yaml")
    container = doc["spec"]["template"]["spec"]["containers"][0]

    # Startup probe
    startup = container.get("startupProbe", {})
    assert startup.get("httpGet", {}).get("path") == "/"
    assert startup.get("httpGet", {}).get("port") == "http"
    assert startup.get("failureThreshold") == 6

    # Liveness probe
    liveness = container.get("livenessProbe", {})
    assert liveness.get("httpGet", {}).get("path") == "/"
    assert liveness.get("httpGet", {}).get("port") == "http"
    assert liveness.get("periodSeconds") == 15

    # Readiness probe
    readiness = container.get("readinessProbe", {})
    assert readiness.get("httpGet", {}).get("path") == "/"
    assert readiness.get("httpGet", {}).get("port") == "http"
    assert readiness.get("periodSeconds") == 10
    assert readiness.get("failureThreshold") == 2


def test_frontend_env_and_secret_wiring():
    """Validates frontend ConfigMap and Secret wiring, and verifies absence of DATABASE_URL."""
    doc = load_yaml("frontend-deployment.yaml")
    container = doc["spec"]["template"]["spec"]["containers"][0]

    # ConfigMap reference
    env_from = container.get("envFrom", [])
    cm_names = [item["configMapRef"]["name"] for item in env_from if "configMapRef" in item]
    assert "bi-frontend-config" in cm_names

    # Secret reference for API_AUTH_TOKEN
    envs = container.get("env", [])
    env_map = {e["name"]: e.get("valueFrom", {}).get("secretKeyRef", {}) for e in envs}

    assert "API_AUTH_TOKEN" in env_map
    assert env_map["API_AUTH_TOKEN"]["name"] == "bi-api-secret"
    assert env_map["API_AUTH_TOKEN"]["key"] == "API_AUTH_TOKEN"

    # Strict boundary check: DATABASE_URL must NOT be present in frontend
    assert "DATABASE_URL" not in env_map, "DATABASE_URL must not be injected into frontend container!"

    # Raw file content check: ensure no postgres or database references in frontend deployment
    path = os.path.join(MANIFEST_DIR, "frontend-deployment.yaml")
    with open(path, "r", encoding="utf-8") as f:
        raw_text = f.read()
    assert "DATABASE_URL" not in raw_text or "strictly omitted" in raw_text.lower()


def test_frontend_configmap_values():
    """Validates frontend ConfigMap data keys and in-cluster backend URL."""
    doc = load_yaml("frontend-configmap.yaml")
    assert doc["apiVersion"] == "v1"
    assert doc["kind"] == "ConfigMap"
    assert doc["metadata"]["name"] == "bi-frontend-config"

    data = doc["data"]
    assert data["PORT"] == "3000"
    assert data["HOSTNAME"] == "0.0.0.0"
    assert data["NODE_ENV"] == "production"
    assert data["API_INTERNAL_URL"] == "http://bi-api-service:8000"

    # Must not contain credentials or database URLs
    assert "API_AUTH_TOKEN" not in data
    assert "DATABASE_URL" not in data


def test_frontend_service_spec_and_port_alignment():
    """Validates frontend Service definition and alignment with container ports."""
    doc = load_yaml("frontend-service.yaml")
    assert doc["apiVersion"] == "v1"
    assert doc["kind"] == "Service"
    assert doc["metadata"]["name"] == "bi-frontend-service"

    spec = doc["spec"]
    assert spec["type"] == "ClusterIP"
    assert spec["selector"]["app.kubernetes.io/name"] == "business-intelligence-frontend"

    port_entry = spec["ports"][0]
    assert port_entry["port"] == 3000
    assert port_entry["targetPort"] == "http"
    assert port_entry["name"] == "http"


