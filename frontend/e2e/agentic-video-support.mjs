import assert from "node:assert/strict";

// Recording can read only a loopback Web deployment. It cannot submit a model job.
export function recordingOrigin(value) {
  const url = new URL(value);
  assert.ok(["127.0.0.1", "localhost", "[::1]"].includes(url.hostname), "Use a loopback host");
  assert.equal(url.protocol, "http:");
  assert.ok(!url.username && !url.password && !url.search && !url.hash);
  assert.equal(url.pathname, "/");
  return url;
}

export function replayPolicy({ url, method, body }, origin, run) {
  const target = new URL(url);
  if (target.origin !== origin.origin) return "deny";
  if (target.pathname === "/api/v1/runs" && method === "POST") {
    assert.deepEqual(body, { question: run.question }, "Only the original question may be replayed");
    return "replay";
  }
  if (target.pathname === `/api/v1/runs/${run.run_id}` && method === "GET") return "replay";
  if (method !== "GET" || target.pathname.startsWith("/api/v1/runs")) return "deny";
  if (target.pathname === "/api/v1/environments/current") return "environment";
  return "read";
}

export function assertFrameFits(box, content, width = 1600, height = 900) {
  assert.equal(box.width, width);
  assert.equal(box.height, height);
  assert.ok(content.scrollWidth <= content.clientWidth + 1, "Scene has hidden horizontal content");
  assert.ok(content.scrollHeight <= content.clientHeight + 1, "Scene has hidden vertical content");
}
