/**
 * dashboard/tests/containerSmoke.test.mjs
 *
 * Automated deployment smoke tests for Next.js Frontend Container (Phase 6G).
 *
 * Validates:
 * 1. Frontend container starts up cleanly in production mode.
 * 2. HTTP endpoint (/) serves 200 OK with the rendered Next.js application.
 * 3. Application process runs as unprivileged non-root user (nextjs, UID 1001).
 * 4. Secrets, .git, and dev artifacts (.env, tests/) are strictly excluded from the image.
 * 5. Server-side proxy route (/api/status) is functional and fails closed safely (502) without leaking secrets.
 * 6. Container stops cleanly without hung or leaked processes.
 *
 * Skips gracefully if Docker daemon is not available.
 */

import test from "node:test";
import assert from "node:assert/strict";
import http from "node:http";
import { execSync, spawnSync } from "node:child_process";

const IMAGE_TAG = process.env.FRONTEND_IMAGE_TAG || "business-intelligence-frontend:test";
const TEST_PORT = process.env.FRONTEND_SMOKE_PORT || "3009";
const CONTAINER_NAME = `bi-fe-smoke-${Date.now()}`;

/**
 * Checks whether docker CLI is present and the daemon is responding.
 */
function isDockerAvailable() {
  try {
    const res = spawnSync("docker", ["info"], { stdio: "ignore", timeout: 5000 });
    return res.status === 0;
  } catch {
    return false;
  }
}

/**
 * Helper to perform an HTTP request and return status, headers, and body text.
 */
function fetchUrl(url, timeoutMs = 5000) {
  return new Promise((resolve, reject) => {
    const req = http.get(url, { timeout: timeoutMs }, (res) => {
      let body = "";
      res.on("data", (chunk) => {
        body += chunk;
      });
      res.on("end", () => {
        resolve({
          status: res.statusCode,
          headers: res.headers,
          body,
        });
      });
    });

    req.on("error", reject);
    req.on("timeout", () => {
      req.destroy();
      reject(new Error(`Request to ${url} timed out after ${timeoutMs}ms`));
    });
  });
}

const dockerRunning = isDockerAvailable();

test("Frontend Container Deployment Smoke Test Suite", { skip: !dockerRunning }, async (t) => {
  let containerRunning = false;

  // Setup: Start test container
  try {
    execSync(
      `docker run -d --name ${CONTAINER_NAME} -p ${TEST_PORT}:3000 ` +
      `-e PORT=3000 -e HOSTNAME=0.0.0.0 ${IMAGE_TAG}`,
      { stdio: "pipe", encoding: "utf8" }
    );
    containerRunning = true;
  } catch (err) {
    assert.fail(`Failed to start frontend container from ${IMAGE_TAG}: ${err.message}`);
  }

  // Poll until container is responding (max 20 seconds)
  const baseUrl = `http://127.0.0.1:${TEST_PORT}`;
  let live = false;
  const deadline = Date.now() + 20000;

  while (Date.now() < deadline) {
    try {
      const probe = await fetchUrl(`${baseUrl}/`, 1500);
      if (probe.status === 200) {
        live = true;
        break;
      }
    } catch {
      await new Promise((r) => setTimeout(r, 500));
    }
  }

  if (!live) {
    let logs = "";
    try {
      logs = execSync(`docker logs ${CONTAINER_NAME}`, { encoding: "utf8" });
    } catch {}
    try {
      execSync(`docker rm -f ${CONTAINER_NAME}`, { stdio: "ignore" });
    } catch {}
    assert.fail(`Frontend container did not serve HTTP 200 within 20s. Logs:\n${logs}`);
  }

  // Subtest 1: HTTP Root Serves Dashboard Markup
  await t.test("serves HTTP 200 with dashboard HTML", async () => {
    const res = await fetchUrl(`${baseUrl}/`);
    assert.equal(res.status, 200);
    assert.match(res.headers["content-type"] || "", /text\/html/);
    assert.match(res.body, /Profitize | Intelligence Dashboard|Prospects/);
  });

  // Subtest 2: Non-Root Execution
  await t.test("runs as unprivileged non-root user (nextjs, UID 1001)", () => {
    const idOut = execSync(`docker exec ${CONTAINER_NAME} id`, { encoding: "utf8" });
    assert.match(idOut, /uid=1001\(nextjs\)/);
  });

  // Subtest 3: Exclusion of Secrets, Git, and Tests
  await t.test("strictly excludes .git, .env*, and tests/ from container image", () => {
    const gitCheck = spawnSync("docker", ["exec", CONTAINER_NAME, "test", "-d", "/app/.git"]);
    assert.notEqual(gitCheck.status, 0, ".git repository directory must not be present in image");

    const envCheck = execSync(
      `docker exec ${CONTAINER_NAME} sh -c "ls -a /app/.env* 2>/dev/null || true"`,
      { encoding: "utf8" }
    );
    assert.equal(envCheck.trim(), "", ".env files must not be present in container image");

    const testDirCheck = spawnSync("docker", ["exec", CONTAINER_NAME, "test", "-d", "/app/tests"]);
    assert.notEqual(testDirCheck.status, 0, "tests directory must not be present in production runtime image");
  });

  // Subtest 4: Server-Side API Proxy Route Behavior
  await t.test("server-side proxy route forwards and fails closed safely without backend", async () => {
    const res = await fetchUrl(`${baseUrl}/api/status`);
    // When backend is not running at 127.0.0.1:8000, proxy catches ECONNREFUSED and returns 502
    assert.equal(res.status, 502);
    const data = JSON.parse(res.body);
    assert.equal(data.success, false);
    assert.equal(data.error, "Backend service unreachable");
  });

  // Teardown: Stop and remove container cleanly
  try {
    const stopRes = spawnSync("docker", ["stop", "-t", "5", CONTAINER_NAME]);
    assert.equal(stopRes.status, 0, "Container should stop cleanly within 5 seconds");
    execSync(`docker rm ${CONTAINER_NAME}`, { stdio: "ignore" });
    containerRunning = false;
  } catch (err) {
    if (containerRunning) {
      execSync(`docker rm -f ${CONTAINER_NAME}`, { stdio: "ignore" });
    }
    throw err;
  }
});
