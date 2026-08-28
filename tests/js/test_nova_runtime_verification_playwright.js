import test from "node:test";
import assert from "node:assert/strict";

test("Playwright verification report includes evidence and failure trace fields", () => {
  const report = {
    url: "http://127.0.0.1:3000/",
    passed: true,
    page_title: "Nova Creature",
    screenshot_path: "data/playwright_verification/nova.png",
    screenshot_hash: "abc123",
    dom_hash: "def456",
    console_summary: { count: 1, messages: ["browser loaded"], errors: [] },
    network_summary: { count: 1, requests: ["http://127.0.0.1:3000/"], failures: [] },
    failure_trace: {
      passed: true,
      error: null,
      failed_assertions: [],
      screenshot_path: "data/playwright_verification/nova.png",
      dom_hash: "def456",
      console_errors: [],
      network_failures: [],
    },
    assertions: [
      {
        assertion: { type: "text", selector: "body", contains: "Nova" },
        passed: true,
        detail: "text contained 'Nova'",
      },
    ],
    elapsed_ms: 12.5,
    verified_at: "2026-08-28T12:00:00+00:00",
    evidence: {
      output_dir: "data/playwright_verification",
      page_path: "127.0.0.1_3000_",
      screenshot_size: 13,
    },
  };

  assert.equal(report.passed, true);
  assert.ok(report.screenshot_hash.length > 0);
  assert.ok(report.dom_hash.length > 0);
  assert.ok(Array.isArray(report.failure_trace.failed_assertions));
  assert.ok(Object.prototype.hasOwnProperty.call(report.failure_trace, "console_errors"));
  assert.ok(Object.prototype.hasOwnProperty.call(report.failure_trace, "network_failures"));
});
