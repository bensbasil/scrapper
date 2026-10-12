"""
tests/test_kubernetes_manifests.py
Validates the Kubernetes manifests in deploy/kubernetes/ across:
- Root backward-compatibility forwarder (deploy/kubernetes/)
- Shared application base (deploy/kubernetes/base/)
- Local developer/demo overlay (deploy/kubernetes/overlays/local/)
- Production overlay (deploy/kubernetes/overlays/prod/)

Validates:
1. Root Kustomize rendering.
2. Base rendering.
3. Local overlay rendering.
4. Production overlay rendering.
5. Base includes frontend and backend application resources.
6. Base contains no PostgreSQL workload.
7. Local overlay includes PostgreSQL Deployment, Service, PVC, and schema configuration.
8. Production overlay contains no PostgreSQL workload or PVC.
9. Local backend DATABASE_URL references the local PostgreSQL Service.
10. Production backend references externally provisioned database configuration.
11. Frontend has no DATABASE_URL in every target.
12. No credentials are embedded in ConfigMaps.
13. Secret references and generated Secret names are consistent.
14. Service selectors match pod labels across all workloads.
15. Service ports and target ports match the intended containers.
16. Existing container security settings remain intact.
17. Existing backend and frontend probe assertions continue to pass.
"""

import os
import shutil
import subprocess
import yaml
import pytest

MANIFEST_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "deploy", "kubernetes"))
BASE_DIR = os.path.join(MANIFEST_ROOT, "base")
LOCAL_OVERLAY_DIR = os.path.join(MANIFEST_ROOT, "overlays", "local")
PROD_OVERLAY_DIR = os.path.join(MANIFEST_ROOT, "overlays", "prod")
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def load_yaml(filename: str, directory: str = BASE_DIR):
    path = os.path.join(directory, filename)
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def render_kustomize(target_dir: str):
    """Executes kubectl kustomize and returns parsed YAML documents."""
    kubectl_bin = shutil.which("kubectl")
    if not kubectl_bin:
        pytest.skip("kubectl not found in environment PATH")

    result = subprocess.run(
        [kubectl_bin, "kustomize", target_dir],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"kubectl kustomize failed for {target_dir}: {result.stderr}"
    docs = [d for d in yaml.safe_load_all(result.stdout) if d is not None]
    return docs


# ==============================================================================
# 1. Directory Structure & Rendering Tests
# ==============================================================================

def test_manifest_directory_and_files_exist():
    """Verify that root, base, and overlay directories and files exist."""
    assert os.path.isdir(MANIFEST_ROOT)
    assert os.path.isdir(BASE_DIR)
    assert os.path.isdir(LOCAL_OVERLAY_DIR)
    assert os.path.isdir(PROD_OVERLAY_DIR)

    expected_base_files = [
        "deployment.yaml",
        "service.yaml",
        "configmap.yaml",
        "frontend-deployment.yaml",
        "frontend-service.yaml",
        "frontend-configmap.yaml",
        "kustomization.yaml",
        "secret.example.yaml",
    ]
    for fname in expected_base_files:
        assert os.path.isfile(os.path.join(BASE_DIR, fname)), f"Missing {fname} in base"

    assert os.path.isfile(os.path.join(MANIFEST_ROOT, "kustomization.yaml"))
    assert os.path.isfile(os.path.join(LOCAL_OVERLAY_DIR, "kustomization.yaml"))
    assert os.path.isfile(os.path.join(PROD_OVERLAY_DIR, "kustomization.yaml"))


def test_kubectl_kustomize_execution():
    """Validates that root kubectl kustomize builds backward-compatible resource stream."""
    docs = render_kustomize(MANIFEST_ROOT)
    names = [d.get("metadata", {}).get("name") for d in docs if "metadata" in d]

    assert "bi-api-config" in names
    assert "bi-frontend-config" in names
    assert "bi-api-service" in names
    assert "bi-frontend-service" in names
    assert "bi-api-deployment" in names
    assert "bi-frontend-deployment" in names


def test_base_kustomize_renders_six_core_resources_without_postgres():
    """Base must render exactly 6 core application resources with zero PostgreSQL resources."""
    docs = render_kustomize(BASE_DIR)
    assert len(docs) == 6, f"Expected 6 base resources, got {len(docs)}"

    names = [d.get("metadata", {}).get("name") for d in docs]
    kinds = [d.get("kind") for d in docs]

    assert "bi-api-config" in names
    assert "bi-frontend-config" in names
    assert "bi-api-service" in names
    assert "bi-frontend-service" in names
    assert "bi-api-deployment" in names
    assert "bi-frontend-deployment" in names

    # Strictly no PostgreSQL resources in base
    for d in docs:
        name = d.get("metadata", {}).get("name", "")
        kind = d.get("kind", "")
        assert "postgres" not in name.lower(), f"Unexpected postgres resource in base: {name}"
        assert kind != "PersistentVolumeClaim", "PersistentVolumeClaim must not be in base"


def test_local_overlay_renders_application_and_postgres_resources():
    """Local overlay must render backend, frontend, and PostgreSQL (Deployment, Service, PVC, ConfigMap, Secret)."""
    docs = render_kustomize(LOCAL_OVERLAY_DIR)
    names = [d.get("metadata", {}).get("name") for d in docs]
    kinds = {d.get("metadata", {}).get("name"): d.get("kind") for d in docs}

    # Core workloads
    assert "bi-api-config" in names
    assert "bi-frontend-config" in names
    assert "bi-api-service" in names
    assert "bi-frontend-service" in names
    assert "bi-api-deployment" in names
    assert "bi-frontend-deployment" in names

    # Local PostgreSQL workloads
    assert "bi-postgres-service" in names
    assert kinds.get("bi-postgres-service") == "Service"

    assert "bi-postgres-deployment" in names
    assert kinds.get("bi-postgres-deployment") == "Deployment"

    assert "bi-postgres-pvc" in names
    assert kinds.get("bi-postgres-pvc") == "PersistentVolumeClaim"

    assert "bi-postgres-schema" in names
    assert kinds.get("bi-postgres-schema") == "ConfigMap"

    assert "bi-api-secret" in names
    assert kinds.get("bi-api-secret") == "Secret"


def test_prod_overlay_renders_six_resources_strictly_without_postgres_or_pvc():
    """Production overlay must strictly exclude all PostgreSQL workloads and PVCs."""
    docs = render_kustomize(PROD_OVERLAY_DIR)
    assert len(docs) == 6, f"Expected 6 production resources, got {len(docs)}"

    names = [d.get("metadata", {}).get("name") for d in docs]
    for d in docs:
        name = d.get("metadata", {}).get("name", "")
        kind = d.get("kind", "")
        assert "postgres" not in name.lower(), f"PostgreSQL resource leaked into prod overlay: {name}"
        assert kind != "PersistentVolumeClaim", "PersistentVolumeClaim must not exist in prod overlay"
        assert kind != "Secret", "Plaintext Secrets must not be generated in prod overlay"


# ==============================================================================
# 2. Database Wiring & Credential Boundary Tests
# ==============================================================================

def test_local_overlay_backend_db_url_points_to_in_cluster_postgres():
    """Local overlay must configure backend DATABASE_URL to bi-postgres-service:5432."""
    docs = render_kustomize(LOCAL_OVERLAY_DIR)
    secret_doc = next((d for d in docs if d.get("kind") == "Secret" and d.get("metadata", {}).get("name") == "bi-api-secret"), None)
    assert secret_doc is not None, "bi-api-secret not found in local overlay"

    # Secret contains data or stringData
    data = secret_doc.get("data", {}) or secret_doc.get("stringData", {})
    # In kustomize secretGenerator, data is base64 encoded
    import base64
    if "DATABASE_URL" in data:
        raw_val = data["DATABASE_URL"]
        try:
            db_url = base64.b64decode(raw_val).decode("utf-8")
        except Exception:
            db_url = raw_val
    else:
        pytest.fail("DATABASE_URL missing from bi-api-secret in local overlay")

    assert "bi-postgres-service:5432" in db_url
    assert "postgresql://" in db_url
    assert "bi_db" in db_url


def test_prod_overlay_backend_expects_external_secret_without_in_cluster_service():
    """Production overlay backend Deployment references external Secret without local DB host."""
    docs = render_kustomize(PROD_OVERLAY_DIR)
    api_deploy = next((d for d in docs if d.get("metadata", {}).get("name") == "bi-api-deployment"), None)
    assert api_deploy is not None

    container = api_deploy["spec"]["template"]["spec"]["containers"][0]
    envs = container.get("env", [])
    db_env = next((e for e in envs if e.get("name") == "DATABASE_URL"), None)
    assert db_env is not None
    # Must use secretKeyRef pointing to bi-api-secret
    assert db_env.get("valueFrom", {}).get("secretKeyRef", {}).get("name") == "bi-api-secret"
    assert "value" not in db_env, "Production DATABASE_URL must not be hardcoded in container env"


def test_frontend_has_no_database_url_in_any_target():
    """Frontend deployment must never receive DATABASE_URL in base, local, or prod."""
    for target in [BASE_DIR, LOCAL_OVERLAY_DIR, PROD_OVERLAY_DIR]:
        docs = render_kustomize(target)
        fe_deploy = next((d for d in docs if d.get("metadata", {}).get("name") == "bi-frontend-deployment"), None)
        assert fe_deploy is not None, f"Frontend deployment missing in {target}"

        container = fe_deploy["spec"]["template"]["spec"]["containers"][0]
        envs = container.get("env", [])
        env_names = [e.get("name") for e in envs]
        assert "DATABASE_URL" not in env_names, f"DATABASE_URL leaked into frontend in {target}"


def test_no_secrets_in_manifests():
    """Manifests must not contain hardcoded production credentials, keys, or tokens."""
    for root_path in [BASE_DIR, LOCAL_OVERLAY_DIR, PROD_OVERLAY_DIR]:
        for fname in os.listdir(root_path):
            if not fname.endswith(".yaml"):
                continue
            path = os.path.join(root_path, fname)
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()

            assert "AIzaSy" not in content, f"Possible Google API key in {fname}"
            if fname != "secret.example.yaml":
                assert "REPLACE_WITH" not in content


def test_no_credentials_in_configmaps():
    """ConfigMaps must strictly contain non-sensitive configuration data."""
    for target in [BASE_DIR, LOCAL_OVERLAY_DIR, PROD_OVERLAY_DIR]:
        docs = render_kustomize(target)
        for doc in docs:
            if doc.get("kind") != "ConfigMap":
                continue
            data = doc.get("data", {})
            assert "DATABASE_URL" not in data, f"DATABASE_URL in ConfigMap {doc['metadata']['name']}"
            assert "API_AUTH_TOKEN" not in data, f"API_AUTH_TOKEN in ConfigMap {doc['metadata']['name']}"
            assert "POSTGRES_PASSWORD" not in data, f"POSTGRES_PASSWORD in ConfigMap {doc['metadata']['name']}"


def test_local_schema_file_matches_database_schema():
    """Verifies that local overlay schema file is identical to database/schema.sql."""
    root_schema_path = os.path.join(REPO_ROOT, "database", "schema.sql")
    local_schema_path = os.path.join(LOCAL_OVERLAY_DIR, "01_schema.sql")

    assert os.path.isfile(root_schema_path)
    assert os.path.isfile(local_schema_path)

    with open(root_schema_path, "r", encoding="utf-8") as f1, open(local_schema_path, "r", encoding="utf-8") as f2:
        assert f1.read() == f2.read(), "Local 01_schema.sql has drifted from database/schema.sql"


# ==============================================================================
# 3. Backend Deployment Spec & Security Contexts
# ==============================================================================

def test_deployment_spec_and_replicas():
    """Validates Deployment replica count (1 for pilot consistency), labels, and Recreate strategy."""
    doc = load_yaml("deployment.yaml")
    assert doc["apiVersion"] == "apps/v1"
    assert doc["kind"] == "Deployment"
    assert doc["metadata"]["name"] == "bi-api-deployment"

    spec = doc["spec"]
    assert spec["replicas"] == 1
    assert spec["strategy"]["type"] == "Recreate"
    assert "rollingUpdate" not in spec["strategy"]

    selector = spec["selector"]["matchLabels"]
    assert selector["app.kubernetes.io/name"] == "business-intelligence-api"


def test_rollout_strategy_strictly_prohibits_simultaneous_pods():
    """Regression test: Enforces Recreate strategy to eliminate split-brain scraping."""
    doc = load_yaml("deployment.yaml")
    strategy = doc["spec"]["strategy"]
    assert strategy["type"] == "Recreate"

    pod_spec = doc["spec"]["template"]["spec"]
    grace_period = pod_spec.get("terminationGracePeriodSeconds")
    assert grace_period is not None
    assert grace_period >= 30


def test_deployment_pod_and_container_security():
    """Validates that pod and container security contexts enforce non-root execution (UID 1000)."""
    doc = load_yaml("deployment.yaml")
    pod_spec = doc["spec"]["template"]["spec"]

    pod_sc = pod_spec.get("securityContext", {})
    assert pod_sc.get("runAsNonRoot") is True
    assert pod_sc.get("runAsUser") == 1000
    assert pod_sc.get("runAsGroup") == 1000
    assert pod_sc.get("fsGroup") == 1000

    container = pod_spec["containers"][0]
    c_sc = container.get("securityContext", {})
    assert c_sc.get("allowPrivilegeEscalation") is False
    assert "ALL" in c_sc.get("capabilities", {}).get("drop", [])


def test_deployment_resource_bounds():
    """Validates CPU and memory resource requests and limits in base."""
    doc = load_yaml("deployment.yaml")
    container = doc["spec"]["template"]["spec"]["containers"][0]
    resources = container.get("resources", {})

    requests = resources.get("requests", {})
    limits = resources.get("limits", {})

    assert requests.get("cpu") == "100m"
    assert requests.get("memory") == "256Mi"
    assert limits.get("cpu") == "1000m"
    assert limits.get("memory") == "512Mi"


def test_prod_deployment_resource_tuning():
    """Validates that production overlay applies minimal, justified resource tuning."""
    docs = render_kustomize(PROD_OVERLAY_DIR)
    api_deploy = next((d for d in docs if d.get("metadata", {}).get("name") == "bi-api-deployment"), None)
    assert api_deploy is not None

    container = api_deploy["spec"]["template"]["spec"]["containers"][0]
    resources = container.get("resources", {})

    requests = resources.get("requests", {})
    limits = resources.get("limits", {})

    assert requests.get("cpu") == "250m"
    assert requests.get("memory") == "512Mi"
    assert limits.get("cpu") == "1000m"
    assert limits.get("memory") == "1Gi"


def test_deployment_probes_contract():
    """Validates startup, liveness, and readiness probes on backend port 'http'."""
    doc = load_yaml("deployment.yaml")
    container = doc["spec"]["template"]["spec"]["containers"][0]

    startup = container.get("startupProbe", {})
    assert startup.get("httpGet", {}).get("path") == "/api/health/live"
    assert startup.get("httpGet", {}).get("port") == "http"
    assert startup.get("failureThreshold") == 6

    liveness = container.get("livenessProbe", {})
    assert liveness.get("httpGet", {}).get("path") == "/api/health/live"
    assert liveness.get("httpGet", {}).get("port") == "http"
    assert liveness.get("periodSeconds") == 10

    readiness = container.get("readinessProbe", {})
    assert readiness.get("httpGet", {}).get("path") == "/api/health/ready"
    assert readiness.get("httpGet", {}).get("port") == "http"
    assert readiness.get("periodSeconds") == 10


def test_deployment_env_and_secret_wiring():
    """Validates ConfigMap and Secret wiring in backend Deployment."""
    doc = load_yaml("deployment.yaml")
    container = doc["spec"]["template"]["spec"]["containers"][0]

    env_from = container.get("envFrom", [])
    cm_names = [item["configMapRef"]["name"] for item in env_from if "configMapRef" in item]
    assert "bi-api-config" in cm_names

    envs = container.get("env", [])
    env_map = {e["name"]: e.get("valueFrom", {}).get("secretKeyRef", {}) for e in envs}

    assert "API_AUTH_TOKEN" in env_map
    assert env_map["API_AUTH_TOKEN"]["name"] == "bi-api-secret"
    assert env_map["API_AUTH_TOKEN"]["key"] == "API_AUTH_TOKEN"

    assert "DATABASE_URL" in env_map
    assert env_map["DATABASE_URL"]["name"] == "bi-api-secret"
    assert env_map["DATABASE_URL"]["key"] == "DATABASE_URL"
    assert env_map["DATABASE_URL"].get("optional") is True


# ==============================================================================
# 4. Service Specs & Port Alignment
# ==============================================================================

def test_service_spec_and_port_alignment():
    """Validates backend Service definition and alignment with container ports."""
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
    """Validates backend ConfigMap values."""
    doc = load_yaml("configmap.yaml")
    assert doc["apiVersion"] == "v1"
    assert doc["kind"] == "ConfigMap"
    assert doc["metadata"]["name"] == "bi-api-config"

    data = doc["data"]
    assert data["PORT"] == "8000"
    assert data["PYTHONUNBUFFERED"] == "1"
    assert "http://localhost:3000" in data["ALLOWED_ORIGINS"]


def test_service_selectors_match_pod_labels_across_all_targets():
    """Validates that Service selectors match pod labels for backend, frontend, and postgres."""
    for target in [BASE_DIR, LOCAL_OVERLAY_DIR, PROD_OVERLAY_DIR]:
        docs = render_kustomize(target)
        services = [d for d in docs if d.get("kind") == "Service"]
        deployments = [d for d in docs if d.get("kind") == "Deployment"]

        for svc in services:
            svc_name = svc["metadata"]["name"]
            selector = svc["spec"]["selector"]
            # Find matching deployment
            matching_deploy = None
            for dep in deployments:
                pod_labels = dep["spec"]["template"]["metadata"]["labels"]
                if all(pod_labels.get(k) == v for k, v in selector.items()):
                    matching_deploy = dep
                    break
            assert matching_deploy is not None, f"Service {svc_name} selector {selector} does not match any Deployment in {target}"


# ==============================================================================
# 5. Frontend Manifest Tests
# ==============================================================================

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

    pod_sc = pod_spec.get("securityContext", {})
    assert pod_sc.get("runAsNonRoot") is True
    assert pod_sc.get("runAsUser") == 1001
    assert pod_sc.get("runAsGroup") == 1001
    assert pod_sc.get("fsGroup") == 1001

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

    startup = container.get("startupProbe", {})
    assert startup.get("httpGet", {}).get("path") == "/"
    assert startup.get("httpGet", {}).get("port") == "http"
    assert startup.get("failureThreshold") == 6

    liveness = container.get("livenessProbe", {})
    assert liveness.get("httpGet", {}).get("path") == "/"
    assert liveness.get("httpGet", {}).get("port") == "http"
    assert liveness.get("periodSeconds") == 15

    readiness = container.get("readinessProbe", {})
    assert readiness.get("httpGet", {}).get("path") == "/"
    assert readiness.get("httpGet", {}).get("port") == "http"
    assert readiness.get("periodSeconds") == 10
    assert readiness.get("failureThreshold") == 2


def test_frontend_env_and_secret_wiring():
    """Validates frontend ConfigMap and Secret wiring, and verifies absence of DATABASE_URL."""
    doc = load_yaml("frontend-deployment.yaml")
    container = doc["spec"]["template"]["spec"]["containers"][0]

    env_from = container.get("envFrom", [])
    cm_names = [item["configMapRef"]["name"] for item in env_from if "configMapRef" in item]
    assert "bi-frontend-config" in cm_names

    envs = container.get("env", [])
    env_map = {e["name"]: e.get("valueFrom", {}).get("secretKeyRef", {}) for e in envs}

    assert "API_AUTH_TOKEN" in env_map
    assert env_map["API_AUTH_TOKEN"]["name"] == "bi-api-secret"
    assert env_map["API_AUTH_TOKEN"]["key"] == "API_AUTH_TOKEN"

    assert "DATABASE_URL" not in env_map


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


# ==============================================================================
# 6. Local PostgreSQL Spec & Security Contexts
# ==============================================================================

def test_local_postgres_deployment_spec_and_security():
    """Validates PostgreSQL deployment image, user (UID 70), strategy, and probes."""
    doc = load_yaml("postgres-deployment.yaml", directory=LOCAL_OVERLAY_DIR)
    assert doc["apiVersion"] == "apps/v1"
    assert doc["kind"] == "Deployment"
    assert doc["metadata"]["name"] == "bi-postgres-deployment"

    spec = doc["spec"]
    assert spec["replicas"] == 1
    assert spec["strategy"]["type"] == "Recreate"

    pod_spec = spec["template"]["spec"]
    pod_sc = pod_spec.get("securityContext", {})
    assert pod_sc.get("runAsNonRoot") is True
    assert pod_sc.get("runAsUser") == 70
    assert pod_sc.get("runAsGroup") == 70
    assert pod_sc.get("fsGroup") == 70

    container = pod_spec["containers"][0]
    assert container["image"] == "postgres:15-alpine"

    # Verify probes use pg_isready
    for probe_name in ["livenessProbe", "readinessProbe", "startupProbe"]:
        probe = container.get(probe_name, {})
        cmd = probe.get("exec", {}).get("command", [])
        assert "pg_isready" in cmd, f"{probe_name} must use pg_isready"

    # Verify volume mounts for data and schema init
    mounts = {m["name"]: m["mountPath"] for m in container.get("volumeMounts", [])}
    assert "/var/lib/postgresql/data" in mounts.values()
    assert "/docker-entrypoint-initdb.d" in mounts.values()


def test_local_postgres_service_and_pvc_specs():
    """Validates PostgreSQL ClusterIP Service and PVC requests."""
    svc_doc = load_yaml("postgres-service.yaml", directory=LOCAL_OVERLAY_DIR)
    assert svc_doc["kind"] == "Service"
    assert svc_doc["spec"]["type"] == "ClusterIP"
    assert svc_doc["spec"]["ports"][0]["port"] == 5432
    assert svc_doc["spec"]["selector"]["app.kubernetes.io/name"] == "business-intelligence-postgres"

    pvc_doc = load_yaml("postgres-pvc.yaml", directory=LOCAL_OVERLAY_DIR)
    assert pvc_doc["kind"] == "PersistentVolumeClaim"
    assert "ReadWriteOnce" in pvc_doc["spec"]["accessModes"]
    assert pvc_doc["spec"]["resources"]["requests"]["storage"] == "1Gi"
