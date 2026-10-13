/**
 * dashboard/tests/apiClient.test.mjs
 *
 * Automated test suite for server-side Next.js API Client (Phase 6J.2).
 *
 * Validates:
 * 1. Base URL resolution and trailing-slash normalization.
 * 2. Server-side API token retrieval (never exposed to client bundles).
 * 3. Authentication header construction (X-API-Key injection).
 * 4. Error handling for non-2xx responses and network failures.
 * 5. Business list response mapping and sorting parameter.
 * 6. Business detail report nesting and transformation.
 * 7. Missing business (404) handling (returns null, no mock fallback).
 * 8. Change events and outreach drafts mapping and parsing.
 * 9. Pipeline runs preservation including stage_failure_counts.
 * 10. Codebase boundary checks: zero pg imports, zero DATABASE_URL in src/,
 *     and dynamic rendering configured on homepage.
 */

import test from "node:test";
import assert from "node:assert/strict";
import http from "node:http";
import fs from "node:fs";
import path from "node:path";
import createJiti from "jiti";

const jiti = createJiti(process.cwd());

/** @type {import('../src/lib/apiClient')} */
const {
  getBackendBaseUrl,
  getApiAuthToken,
  buildApiHeaders,
  fetchFromBackend,
  getBusinesses,
  getBusinessDetail,
  getChangeEvents,
  getOutreachDrafts,
  getPipelineRuns,
  transformRow,
} = jiti("./src/lib/apiClient.ts");

// Helper to spawn a mock HTTP server on an ephemeral port
function createMockServer(handler) {
  return new Promise((resolve) => {
    const server = http.createServer(handler);
    server.listen(0, "127.0.0.1", () => {
      const port = server.address().port;
      resolve({
        server,
        port,
        url: `http://127.0.0.1:${port}`,
        close: () => new Promise((res) => server.close(res)),
      });
    });
  });
}

// ==============================================================================
// 1. Config & URL Resolution Tests
// ==============================================================================

test("getBackendBaseUrl defaults to http://127.0.0.1:8000 when unconfigured", () => {
  const origInternal = process.env.API_INTERNAL_URL;
  const origApi = process.env.API_URL;
  try {
    delete process.env.API_INTERNAL_URL;
    delete process.env.API_URL;
    assert.equal(getBackendBaseUrl(), "http://127.0.0.1:8000");
  } finally {
    if (origInternal) process.env.API_INTERNAL_URL = origInternal;
    if (origApi) process.env.API_URL = origApi;
  }
});

test("getBackendBaseUrl prioritizes API_INTERNAL_URL and strips trailing slashes", () => {
  const orig = process.env.API_INTERNAL_URL;
  try {
    process.env.API_INTERNAL_URL = "http://backend:8000///";
    assert.equal(getBackendBaseUrl(), "http://backend:8000");
  } finally {
    if (orig) process.env.API_INTERNAL_URL = orig;
    else delete process.env.API_INTERNAL_URL;
  }
});

test("getApiAuthToken reads process.env.API_AUTH_TOKEN server-side only", () => {
  const orig = process.env.API_AUTH_TOKEN;
  try {
    process.env.API_AUTH_TOKEN = "secret-token-xyz";
    assert.equal(getApiAuthToken(), "secret-token-xyz");

    delete process.env.API_AUTH_TOKEN;
    assert.equal(getApiAuthToken(), undefined);
  } finally {
    if (orig) process.env.API_AUTH_TOKEN = orig;
    else delete process.env.API_AUTH_TOKEN;
  }
});

test("Token is never exposed via NEXT_PUBLIC_ env vars or client properties", () => {
  assert.equal(process.env.NEXT_PUBLIC_API_AUTH_TOKEN, undefined);
  assert.equal(process.env.NEXT_PUBLIC_API_KEY, undefined);
});

// ==============================================================================
// 2. Authentication Headers & Network Execution
// ==============================================================================

test("buildApiHeaders injects X-API-Key when API_AUTH_TOKEN is present", () => {
  const orig = process.env.API_AUTH_TOKEN;
  try {
    process.env.API_AUTH_TOKEN = "my-secret-key-123";
    const headers = buildApiHeaders();
    assert.equal(headers["X-API-Key"], "my-secret-key-123");
    assert.equal(headers["Accept"], "application/json");

    // Custom headers can be merged
    const custom = buildApiHeaders({ "X-Custom": "test" });
    assert.equal(custom["X-Custom"], "test");
    assert.equal(custom["X-API-Key"], "my-secret-key-123");
  } finally {
    if (orig) process.env.API_AUTH_TOKEN = orig;
    else delete process.env.API_AUTH_TOKEN;
  }
});

test("buildApiHeaders omits X-API-Key when API_AUTH_TOKEN is empty", () => {
  const orig = process.env.API_AUTH_TOKEN;
  try {
    delete process.env.API_AUTH_TOKEN;
    const headers = buildApiHeaders();
    assert.equal(headers["X-API-Key"], undefined);
    assert.equal(headers["Accept"], "application/json");
  } finally {
    if (orig) process.env.API_AUTH_TOKEN = orig;
    else delete process.env.API_AUTH_TOKEN;
  }
});

test("fetchFromBackend successfully contacts backend with auth headers and parses JSON", async () => {
  let capturedHeaders = null;
  const mock = await createMockServer((req, res) => {
    capturedHeaders = req.headers;
    res.writeHead(200, { "Content-Type": "application/json" });
    res.end(JSON.stringify({ status: "ok", count: 42 }));
  });

  const origUrl = process.env.API_INTERNAL_URL;
  const origToken = process.env.API_AUTH_TOKEN;
  try {
    process.env.API_INTERNAL_URL = mock.url;
    process.env.API_AUTH_TOKEN = "test-auth-token";

    const data = await fetchFromBackend("/api/test");
    assert.deepEqual(data, { status: "ok", count: 42 });
    assert.equal(capturedHeaders["x-api-key"], "test-auth-token");
  } finally {
    await mock.close();
    if (origUrl) process.env.API_INTERNAL_URL = origUrl;
    else delete process.env.API_INTERNAL_URL;
    if (origToken) process.env.API_AUTH_TOKEN = origToken;
    else delete process.env.API_AUTH_TOKEN;
  }
});

test("fetchFromBackend throws sanitized error on non-2xx responses without leaking secrets", async () => {
  const mock = await createMockServer((req, res) => {
    res.writeHead(403, { "Content-Type": "application/json" });
    res.end(JSON.stringify({ detail: "Forbidden access" }));
  });

  const origUrl = process.env.API_INTERNAL_URL;
  try {
    process.env.API_INTERNAL_URL = mock.url;
    await assert.rejects(
      async () => {
        await fetchFromBackend("/api/forbidden");
      },
      (err) => {
        assert.equal(err.status, 403);
        assert.match(err.message, /Forbidden access/);
        return true;
      }
    );
  } finally {
    await mock.close();
    if (origUrl) process.env.API_INTERNAL_URL = origUrl;
    else delete process.env.API_INTERNAL_URL;
  }
});

test("fetchFromBackend throws on network failure without crashing", async () => {
  const origUrl = process.env.API_INTERNAL_URL;
  try {
    // Port 59997 is unreachable
    process.env.API_INTERNAL_URL = "http://127.0.0.1:59997";
    await assert.rejects(
      async () => {
        await fetchFromBackend("/api/unreachable");
      },
      (err) => {
        assert.match(err.message, /failed|fetch/i);
        return true;
      }
    );
  } finally {
    if (origUrl) process.env.API_INTERNAL_URL = origUrl;
    else delete process.env.API_INTERNAL_URL;
  }
});

// ==============================================================================
// 3. Business List Mapping Tests
// ==============================================================================

test("getBusinesses requests sort_by=opportunity and maps business records correctly", async () => {
  let requestedUrl = "";
  const mock = await createMockServer((req, res) => {
    requestedUrl = req.url;
    res.writeHead(200, { "Content-Type": "application/json" });
    res.end(
      JSON.stringify({
        success: true,
        businesses: [
          {
            id: 1,
            name: "Alpha Dental",
            city: "Austin",
            state: "TX",
            opportunity_score: "85.5",
            primary_problem: "No online booking",
            decision_makers: JSON.stringify([{ name: "Dr. Smith", role: "Owner" }]),
            pipeline_stage: "discovery",
            outreach_status: "contacted",
          },
        ],
      })
    );
  });

  const origUrl = process.env.API_INTERNAL_URL;
  try {
    process.env.API_INTERNAL_URL = mock.url;
    const results = await getBusinesses();

    assert.equal(requestedUrl, "/api/businesses?sort_by=opportunity");
    assert.equal(results.length, 1);
    assert.equal(results[0].id, 1);
    assert.equal(results[0].name, "Alpha Dental");
    assert.equal(results[0].opportunity_score, 85.5);
    assert.equal(results[0].primary_problem, "No online booking");
    assert.deepEqual(results[0].decision_makers, [{ name: "Dr. Smith", role: "Owner" }]);
    assert.equal(results[0].pipeline_stage, "discovery");
  } finally {
    await mock.close();
    if (origUrl) process.env.API_INTERNAL_URL = origUrl;
    else delete process.env.API_INTERNAL_URL;
  }
});

// ==============================================================================
// 4. Business Detail & Report Nesting Tests
// ==============================================================================

test("getBusinessDetail nests flat report fields into business.report correctly", async () => {
  const mockBusiness = {
    id: 10,
    business_name: "Beta Clinic",
    name: "Beta Clinic",
    phone: "555-1234",
    website: "https://betaclinic.com",
    city: "Dallas",
    state: "TX",
    opportunity_score: 92,
    primary_problem: "Slow website",
    overall_opportunity: "High opportunity to improve digital conversion.",
    website_quality_summary: "Average design with missing CTA.",
    seo_summary: "Missing meta tags.",
    automation_summary: "No automated booking system.",
    suggested_services: JSON.stringify(["Web Redesign", "SEO Optimization"]),
    outreach_angles: JSON.stringify(["Emphasize lost mobile leads"]),
    improvement_recommendations: JSON.stringify(["Add online booking"]),
    service_recommendations: JSON.stringify([
      { service_name: "Web Redesign", impact_explanation: "Boosts conversion by 30%" },
    ]),
    opportunity_reasoning: "High volume but poor digital presence",
    competitors: JSON.stringify([{ name: "Gamma Health" }]),
    competitor_gap_summary: "No telehealth offering",
    recurring_complaints: JSON.stringify(["Long hold times"]),
    recurring_praise: JSON.stringify(["Friendly doctors"]),
    common_themes: JSON.stringify(["Modern facility"]),
    bottlenecks: JSON.stringify(["Manual intake"]),
    pain_summary: "Patients complain of phone wait times",
    intent_score: 88,
    outreach_urgency: "high",
    decision_makers: JSON.stringify([{ name: "Jane Doe", title: "COO" }]),
  };

  const mock = await createMockServer((req, res) => {
    if (req.url === "/api/businesses/10") {
      res.writeHead(200, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ success: true, business: mockBusiness }));
    } else {
      res.writeHead(404, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ detail: "Not found" }));
    }
  });

  const origUrl = process.env.API_INTERNAL_URL;
  try {
    process.env.API_INTERNAL_URL = mock.url;
    const detail = await getBusinessDetail(10);

    assert.ok(detail);
    assert.equal(detail.id, "10");
    assert.equal(detail.business_name, "Beta Clinic");
    assert.equal(detail.opportunity_score, 92);
    assert.equal(detail.opportunity_reasoning, "High volume but poor digital presence");
    assert.deepEqual(detail.service_recommendations, [
      { service_name: "Web Redesign", impact_explanation: "Boosts conversion by 30%" },
    ]);
    assert.deepEqual(detail.competitors, [{ name: "Gamma Health" }]);
    assert.deepEqual(detail.recurring_complaints, ["Long hold times"]);
    assert.deepEqual(detail.recurring_praise, ["Friendly doctors"]);
    assert.equal(detail.pain_summary, "Patients complain of phone wait times");

    // Report nested subobject preservation
    assert.ok(detail.report);
    assert.equal(detail.report.overall_opportunity, "High opportunity to improve digital conversion.");
    assert.equal(detail.report.website_quality_summary, "Average design with missing CTA.");
    assert.equal(detail.report.seo_summary, "Missing meta tags.");
    assert.deepEqual(detail.report.suggested_services, ["Web Redesign", "SEO Optimization"]);
    assert.deepEqual(detail.report.outreach_angles, ["Emphasize lost mobile leads"]);
    assert.deepEqual(detail.report.improvement_recommendations, ["Add online booking"]);
  } finally {
    await mock.close();
    if (origUrl) process.env.API_INTERNAL_URL = origUrl;
    else delete process.env.API_INTERNAL_URL;
  }
});

test("getBusinessDetail returns null on HTTP 404 (does not return mock data)", async () => {
  const mock = await createMockServer((req, res) => {
    res.writeHead(404, { "Content-Type": "application/json" });
    res.end(JSON.stringify({ detail: "Business not found" }));
  });

  const origUrl = process.env.API_INTERNAL_URL;
  try {
    process.env.API_INTERNAL_URL = mock.url;
    const result = await getBusinessDetail(999);
    assert.equal(result, null);
  } finally {
    await mock.close();
    if (origUrl) process.env.API_INTERNAL_URL = origUrl;
    else delete process.env.API_INTERNAL_URL;
  }
});

test("getBusinessDetail returns null for invalid non-numeric IDs", async () => {
  assert.equal(await getBusinessDetail("abc"), null);
  assert.equal(await getBusinessDetail(-5), null);
  assert.equal(await getBusinessDetail(0), null);
});

// ==============================================================================
// 5. Change Events & Outreach Drafts Mapping Tests
// ==============================================================================

test("getChangeEvents maps and parses detected changes", async () => {
  const mock = await createMockServer((req, res) => {
    assert.equal(req.url, "/api/businesses/5/changes");
    res.writeHead(200, { "Content-Type": "application/json" });
    res.end(
      JSON.stringify({
        success: true,
        changes: [
          {
            id: 101,
            business_id: 5,
            changes: JSON.stringify([{ field: "phone", old: "111", new: "222" }]),
            previous_snapshot_at: "2026-10-01T00:00:00Z",
            current_snapshot_at: "2026-10-10T00:00:00Z",
            change_summary: "Phone number updated",
            detected_at: "2026-10-10T00:00:00Z",
          },
        ],
      })
    );
  });

  const origUrl = process.env.API_INTERNAL_URL;
  try {
    process.env.API_INTERNAL_URL = mock.url;
    const changes = await getChangeEvents(5);

    assert.equal(changes.length, 1);
    assert.equal(changes[0].id, 101);
    assert.equal(changes[0].change_summary, "Phone number updated");
    assert.deepEqual(changes[0].changes, [{ field: "phone", old: "111", new: "222" }]);
  } finally {
    await mock.close();
    if (origUrl) process.env.API_INTERNAL_URL = origUrl;
    else delete process.env.API_INTERNAL_URL;
  }
});

test("getChangeEvents returns empty array on 404 or invalid ID", async () => {
  assert.deepEqual(await getChangeEvents("invalid"), []);

  const mock = await createMockServer((req, res) => {
    res.writeHead(404, { "Content-Type": "application/json" });
    res.end(JSON.stringify({ detail: "Not found" }));
  });

  const origUrl = process.env.API_INTERNAL_URL;
  try {
    process.env.API_INTERNAL_URL = mock.url;
    assert.deepEqual(await getChangeEvents(9999), []);
  } finally {
    await mock.close();
    if (origUrl) process.env.API_INTERNAL_URL = origUrl;
    else delete process.env.API_INTERNAL_URL;
  }
});

test("getOutreachDrafts maps outreach data and returns null on 404", async () => {
  const mock = await createMockServer((req, res) => {
    if (req.url === "/api/businesses/8/outreach") {
      res.writeHead(200, { "Content-Type": "application/json" });
      res.end(
        JSON.stringify({
          success: true,
          outreach: {
            id: 202,
            pain_point_positioning: "Address slow scheduling",
            cold_email_draft: "Hi, let's talk automation.",
            whatsapp_draft: "Quick note regarding appointments.",
          },
        })
      );
    } else {
      res.writeHead(404, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ detail: "No outreach draft found" }));
    }
  });

  const origUrl = process.env.API_INTERNAL_URL;
  try {
    process.env.API_INTERNAL_URL = mock.url;
    const outreach = await getOutreachDrafts(8);
    assert.ok(outreach);
    assert.equal(outreach.pain_point_positioning, "Address slow scheduling");
    assert.equal(outreach.cold_email_draft, "Hi, let's talk automation.");

    const missing = await getOutreachDrafts(999);
    assert.equal(missing, null);
  } finally {
    await mock.close();
    if (origUrl) process.env.API_INTERNAL_URL = origUrl;
    else delete process.env.API_INTERNAL_URL;
  }
});

// ==============================================================================
// 6. Pipeline Runs Field Preservation Tests
// ==============================================================================

test("getPipelineRuns preserves stage_failure_counts, notes, and records", async () => {
  let requestedUrl = "";
  const mock = await createMockServer((req, res) => {
    requestedUrl = req.url;
    res.writeHead(200, { "Content-Type": "application/json" });
    res.end(
      JSON.stringify({
        success: true,
        runs: [
          {
            run_id: "run-2026-10-11-001",
            search_query: "dentists in Austin",
            started_at: "2026-10-11T09:00:00Z",
            finished_at: "2026-10-11T09:05:00Z",
            total_businesses: 25,
            successful_businesses: 20,
            failed_businesses: 5,
            success_rate: 80.0,
            high_opportunity_count: 7,
            stage_failure_counts: JSON.stringify({ extraction: 3, analysis: 2 }),
            business_records: JSON.stringify([{ id: 1 }]),
            notes: JSON.stringify(["Completed with 5 warnings"]),
          },
        ],
      })
    );
  });

  const origUrl = process.env.API_INTERNAL_URL;
  try {
    process.env.API_INTERNAL_URL = mock.url;
    const runs = await getPipelineRuns(10);

    assert.equal(requestedUrl, "/api/runs?limit=10");
    assert.equal(runs.length, 1);
    assert.equal(runs[0].run_id, "run-2026-10-11-001");
    assert.equal(runs[0].search_query, "dentists in Austin");
    assert.equal(runs[0].total_businesses, 25);
    assert.equal(runs[0].successful_businesses, 20);
    assert.equal(runs[0].failed_businesses, 5);
    assert.equal(runs[0].success_rate, 80.0);
    assert.equal(runs[0].high_opportunity_count, 7);
    assert.deepEqual(runs[0].stage_failure_counts, { extraction: 3, analysis: 2 });
    assert.deepEqual(runs[0].notes, ["Completed with 5 warnings"]);
  } finally {
    await mock.close();
    if (origUrl) process.env.API_INTERNAL_URL = origUrl;
    else delete process.env.API_INTERNAL_URL;
  }
});

// ==============================================================================
// 7. Architectural Boundary & Regression Checks
// ==============================================================================

test("Dashboard source code contains zero direct imports of 'pg' or '@/lib/db'", () => {
  const srcDir = path.resolve(process.cwd(), "src");

  function scanDir(dir) {
    const entries = fs.readdirSync(dir, { withFileTypes: true });
    for (const entry of entries) {
      const fullPath = path.join(dir, entry.name);
      if (entry.isDirectory()) {
        scanDir(fullPath);
      } else if (entry.isFile() && (entry.name.endsWith(".ts") || entry.name.endsWith(".tsx"))) {
        const content = fs.readFileSync(fullPath, "utf8");
        assert.doesNotMatch(
          content,
          /from\s+['"]pg['"]/,
          `Found direct 'pg' import in ${fullPath}`
        );
        assert.doesNotMatch(
          content,
          /from\s+['"]@\/lib\/db['"]/,
          `Found '@/lib/db' import in ${fullPath}`
        );
        assert.doesNotMatch(
          content,
          /from\s+['"]\.\.?\/.*db['"]/,
          `Found relative 'db' import in ${fullPath}`
        );
      }
    }
  }

  scanDir(srcDir);
});

test("Dashboard source code contains zero process.env.DATABASE_URL references", () => {
  const srcDir = path.resolve(process.cwd(), "src");

  function scanDir(dir) {
    const entries = fs.readdirSync(dir, { withFileTypes: true });
    for (const entry of entries) {
      const fullPath = path.join(dir, entry.name);
      if (entry.isDirectory()) {
        scanDir(fullPath);
      } else if (entry.isFile() && (entry.name.endsWith(".ts") || entry.name.endsWith(".tsx"))) {
        const content = fs.readFileSync(fullPath, "utf8");
        assert.doesNotMatch(
          content,
          /DATABASE_URL/,
          `Found DATABASE_URL reference in ${fullPath}`
        );
      }
    }
  }

  scanDir(srcDir);
});

test("Homepage explicitly exports dynamic = 'force-dynamic' to prevent static data baking", () => {
  const homePath = path.resolve(process.cwd(), "src/app/page.tsx");
  const content = fs.readFileSync(homePath, "utf8");
  assert.match(
    content,
    /export\s+const\s+dynamic\s*=\s*['"]force-dynamic['"]/,
    "Homepage missing dynamic = 'force-dynamic'"
  );
});

test("Runs page explicitly exports dynamic = 'force-dynamic' to prevent static data baking", () => {
  const runsPath = path.resolve(process.cwd(), "src/app/runs/page.tsx");
  const content = fs.readFileSync(runsPath, "utf8");
  assert.match(
    content,
    /export\s+const\s+dynamic\s*=\s*['"]force-dynamic['"]/,
    "Runs page missing dynamic = 'force-dynamic'"
  );
});

test("package.json test script isolates unit tests from container deployment smoke tests", () => {
  const pkgPath = path.resolve(process.cwd(), "package.json");
  const pkg = JSON.parse(fs.readFileSync(pkgPath, "utf8"));
  assert.ok(pkg.scripts?.test, "package.json must define a 'test' script");
  assert.ok(pkg.scripts?.["test:smoke"], "package.json must define a 'test:smoke' script");
  assert.doesNotMatch(
    pkg.scripts.test,
    /containerSmoke/,
    "npm test must not execute containerSmoke directly"
  );
  assert.doesNotMatch(
    pkg.scripts.test,
    /tests\/\*\.test\.mjs/,
    "npm test must not blindly glob tests/*.test.mjs to avoid executing container smoke tests before Docker image is built"
  );
  assert.match(
    pkg.scripts["test:smoke"],
    /containerSmoke\.test\.mjs/,
    "npm run test:smoke must execute containerSmoke.test.mjs"
  );
});
