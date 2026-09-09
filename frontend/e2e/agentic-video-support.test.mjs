import assert from "node:assert/strict";
import test from "node:test";
import { assertFrameFits, recordingOrigin, replayPolicy } from "./agentic-video-support.mjs";

const origin = recordingOrigin("http://127.0.0.1:8080");
const run = { run_id: "run_recorded", question: "Which country leads within these data?" };
const policy = (pathname, method = "GET", body) => replayPolicy({
  url: new URL(pathname, origin).href, method, body,
}, origin, run);

test("recording origin rejects external hosts, credentials, paths, and query strings", () => {
  for (const value of ["https://127.0.0.1", "http://example.com", "http://a:b@localhost",
    "http://localhost/path", "http://localhost/?secret=value", "http://localhost/#fragment"]) {
    assert.throws(() => recordingOrigin(value));
  }
});
test("exact question-only submission and historical poll are replayed locally", () => {
  assert.equal(policy("/api/v1/runs?background=true", "POST", { question: run.question }), "replay");
  assert.equal(policy("/api/v1/runs/run_recorded"), "replay");
});
test("unexpected extra task inputs cannot create a real run", () => {
  assert.throws(() => policy("/api/v1/runs", "POST", { question: run.question, sources: ["x.csv"] }));
  assert.throws(() => policy("/api/v1/runs", "POST", { question: "changed" }));
});
test("mutations, other run IDs, external requests, and run exports are denied", () => {
  for (const [url, method] of [["/api/v1/runs/run_recorded", "DELETE"],
    ["/api/v1/runs/run_other", "GET"], ["/api/v1/runs/run_recorded/export", "GET"],
    ["https://example.com/beacon", "GET"], ["/api/admin", "POST"]]) {
    assert.equal(policy(url, method), "deny");
  }
});
test("only local reads and the environment read pass through", () => {
  assert.equal(policy("/assets/bundle.js"), "read");
  assert.equal(policy("/api/v1/environments/current"), "environment");
});
test("frame clipping or wrong dimensions fail rather than silently publishing", () => {
  const box = { width: 1600, height: 900 };
  const content = { scrollWidth: 1400, clientWidth: 1400, scrollHeight: 600, clientHeight: 650 };
  assertFrameFits(box, content);
  assert.throws(() => assertFrameFits(box, { ...content, scrollHeight: 680 }));
  assert.throws(() => assertFrameFits(box, { ...content, scrollWidth: 1600 }));
  assert.throws(() => assertFrameFits({ ...box, height: 1000 }, content));
});
