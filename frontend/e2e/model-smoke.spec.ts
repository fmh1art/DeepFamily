import { createHash } from "node:crypto";
import { readFile } from "node:fs/promises";

import { expect, test } from "@playwright/test";

const question = "How many Grade 8 SHSAT registration rows are present in 2016?";

test("rejects an invalid model plan, repairs it, and completes from the browser", async ({
  page,
}) => {
  await page.goto("/", { waitUntil: "networkidle" });

  await expect(page.getByText("10 files", { exact: true })).toBeVisible();
  await expect(page.getByText("Model mode", { exact: true })).toBeVisible();
  await page.locator(".data-handling-disclosure > summary").click();
  await expect(page.getByTestId("model-processing-disclosure")).toBeVisible();
  await expect(page.getByText("Verified pilots", { exact: true })).toHaveCount(0);

  await page.getByLabel("Your analytical question").fill(question);
  const responsePromise = page.waitForResponse(
    (response) =>
      new URL(response.url()).pathname === "/api/v1/runs" &&
      response.request().method() === "POST",
  );
  await page.getByRole("button", { name: /Run hands-off analysis/ }).click();
  const response = await responsePromise;
  expect(response.status()).toBe(202);

  const responseText = await response.text();
  expect(responseText).not.toContain("smoke-key");
  const submitted = JSON.parse(responseText) as { run_id: string; status: string };
  expect(["pending", "running", "completed"]).toContain(submitted.status);

  await expect(page.locator(".report-panel.completed")).toBeVisible();
  const persistedResponse = await page.request.get(`/api/v1/runs/${submitted.run_id}`);
  expect(persistedResponse.ok()).toBeTruthy();
  const run = (await persistedResponse.json()) as {
    status: string;
    contract: {
      compilation: {
        kind: string;
        attempts: number;
        request_sha256s: string[];
        response_sha256s: string[];
      };
    };
    artifacts: Array<{ name: string; value: number }>;
    report: { markdown: string; evidence_refs: string[] };
    evidence: Record<string, { sha256: string }>;
  };
  expect(run.status).toBe("completed");
  expect(run.contract.compilation).toMatchObject({ kind: "model", attempts: 2 });
  expect(run.contract.compilation.request_sha256s).toHaveLength(2);
  expect(run.contract.compilation.response_sha256s).toHaveLength(2);
  expect(run.artifacts).toEqual(
    expect.arrayContaining([expect.objectContaining({ name: "grade8_2016_rows", value: 21 })]),
  );

  const downloadEvent = page.waitForEvent("download");
  await page.getByRole("button", { name: "Download report", exact: true }).click();
  const download = await downloadEvent;
  const file = await download.path();
  expect(file).not.toBeNull();
  if (!file) throw new Error("Report download was not persisted by the browser");
  const bytes = await readFile(file);
  expect(bytes.toString("utf8")).toBe(run.report.markdown);
  expect(createHash("sha256").update(bytes).digest("hex")).toBe(
    run.evidence[run.report.evidence_refs[0]].sha256,
  );
  expect(run.report.markdown).toContain("## Evidence results");
  expect(run.report.markdown).toContain("[E1](#evidence-1)");
  expect(run.report.markdown.match(/<a id="evidence-1"><\/a>/g)).toHaveLength(1);
  expect(run.report.markdown).not.toContain("smoke-key");

  await page.locator(".technical-audit > summary").click();
  await expect(page.getByText("model · 2 attempts", { exact: true })).toBeVisible();
  await expect(page.getByText("Grade 8 SHSAT registrations in 2016", { exact: true })).toBeVisible();
  const rowCountMetric = page.locator(".metric-grid article").filter({ hasText: "Grade8 2016 rows" });
  await expect(rowCountMetric.getByText("21", { exact: true })).toBeVisible();
});
