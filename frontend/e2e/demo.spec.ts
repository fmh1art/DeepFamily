import { createHash } from "node:crypto";
import { spawnSync } from "node:child_process";
import { readFile, writeFile } from "node:fs/promises";
import path from "node:path";

import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

test("executes and exposes a cross-stage join repair", async ({ page }) => {
  await page.goto("/", { waitUntil: "networkidle" });
  await expect(page.getByText("10 files", { exact: true })).toBeVisible();
  await expect(page.locator(".report-panel, .research-workflow, .catalog-provenance")).toHaveCount(0);
  await expect(page.getByTestId("about-notice")).not.toHaveAttribute("open", "");
  await page.locator(".data-handling-disclosure > summary").click();
  const storageDisclosure = page.getByTestId("run-storage-disclosure");
  await expect(storageDisclosure).toContainText("Automatic expiry is disabled on this server");

  await page.getByRole("button", { name: /Join repair/ }).click();
  const createResponsePromise = page.waitForResponse(
    (response) =>
      new URL(response.url()).pathname === "/api/v1/runs" &&
      response.request().method() === "POST",
  );
  await page.getByRole("button", { name: /Run hands-off analysis/ }).click();
  const created = (await (await createResponsePromise).json()) as { run_id: string };

  await expect(page.locator(".report-panel.completed")).toBeVisible();
  const technicalAudit = page.locator(".technical-audit");
  if ((await technicalAudit.getAttribute("open")) === null) {
    await technicalAudit.locator(":scope > summary").click();
  }
  const catalogProvenance = page.getByTestId("catalog-provenance");
  await expect(catalogProvenance.getByText("CoDA-Bench · community 43")).toBeVisible();
  await expect(catalogProvenance.getByText("10 / 10 · external, download-only")).toBeVisible();
  await expect(page.getByText("Analysis", { exact: true }).nth(1)).toBeVisible();
  await expect(page.getByText("Discovery", { exact: true }).nth(1)).toBeVisible();
  await expect(page.getByText("Added by downstream repair")).toBeVisible();
  const sourcesPanel = page.locator(".sources-panel");
  await expect(sourcesPanel.getByText("Data Science for Good: PASSNYC").first()).toBeVisible();
  await expect(sourcesPanel.getByText("Metadata · CC0-1.0").first()).toBeVisible();
  await expect(sourcesPanel.getByText("Integrity verified").first()).toBeVisible();
  await expect(sourcesPanel.getByText("SHA-256 c9d73d462407…")).toBeVisible();
  await expect(sourcesPanel.getByRole("link", { name: "Upstream record ↗" }).first()).toHaveAttribute(
    "href",
    "https://www.kaggle.com/datasets/passnyc/data-science-for-good",
  );
  await expect(page.locator('a[download], a[href*="/api/v1/assets/"]')).toHaveCount(0);
  const repairImpact = page.getByTestId("repair-impact");
  await expect(repairImpact).toBeVisible();
  await expect(repairImpact.getByText("Report gated", { exact: true })).toBeVisible();
  await expect(repairImpact.getByText("Analysis ↶ Discovery", { exact: true })).toBeVisible();
  await expect(repairImpact.getByText("3/3 required variables", { exact: true })).toBeVisible();
  await expect(repairImpact.getByText("Report released", { exact: true })).toBeVisible();
  const metrics = page.locator(".metric-grid");
  await expect(metrics.getByText("0.434725", { exact: true })).toBeVisible();
  await expect(metrics.getByText("-0.513048", { exact: true })).toBeVisible();
  await expect(metrics.getByText("0.586734", { exact: true })).toBeVisible();

  await page.locator(".report-details > summary").click();
  await page.getByRole("tab", { name: /Black\/Hispanic student percentage/ }).click();
  const lineage = page.getByTestId("claim-lineage");
  await expect(lineage.getByText("4 checksummed lineage objects", { exact: true })).toBeVisible();
  await expect(lineage.getByText("pearson percent black hispanic", { exact: true })).toBeVisible();
  await expect(lineage.getByText("-0.513048", { exact: true })).toBeVisible();
  await expect(lineage.getByText("D5 SHSAT Registrations and Testers.csv", { exact: true })).toBeVisible();
  await expect(lineage.getByText("2016 School Explorer.csv", { exact: true })).toBeVisible();

  const runId = created.run_id;
  expect(runId).toMatch(/^run_[a-f0-9]{16}$/);
  const persistedResponse = await page.request.get(`/api/v1/runs/${runId}`);
  expect(persistedResponse.ok()).toBeTruthy();
  const persisted = (await persistedResponse.json()) as {
    run_id: string;
    question: string;
    report: { markdown: string; evidence_refs: string[] };
    evidence: Record<string, { sha256: string | null }>;
  };

  const reportDownloadPromise = page.waitForEvent("download");
  await page.getByRole("button", { name: "Download report" }).click();
  const reportDownload = await reportDownloadPromise;
  expect(reportDownload.suggestedFilename()).toBe(`askdu-${runId}-report.md`);
  const reportPath = await reportDownload.path();
  expect(reportPath).not.toBeNull();
  if (reportPath === null) throw new Error("Playwright did not persist the report download");
  const reportContents = await readFile(reportPath);
  expect(reportContents.toString("utf-8")).toBe(persisted.report.markdown);
  const reportEvidence = persisted.evidence[persisted.report.evidence_refs[0]];
  expect(createHash("sha256").update(reportContents).digest("hex")).toBe(reportEvidence.sha256);

  const evidenceDownloadPromise = page.waitForEvent("download");
  await page.getByRole("button", { name: "Export evidence" }).click();
  const evidenceDownload = await evidenceDownloadPromise;
  expect(evidenceDownload.suggestedFilename()).toBe(`askdu-${runId}-evidence.json`);
  const evidencePath = await evidenceDownload.path();
  expect(evidencePath).not.toBeNull();
  if (evidencePath === null) throw new Error("Playwright did not persist the evidence download");
  const bundle = JSON.parse(await readFile(evidencePath, "utf-8")) as {
    schema_version: string;
    export_manifest: Record<string, string>;
    run: {
      run_id: string;
      question: string;
      assets: Array<Record<string, unknown>>;
      agent_traces: Array<Record<string, unknown>>;
      discovery_hops: Array<Record<string, unknown>>;
      preparation_attempts: Array<Record<string, unknown>>;
      analysis_notebook: Array<Record<string, unknown>>;
      lifecycle_events: Array<{ edge_kind: string }>;
      report: { markdown: string };
    };
  };
  expect(bundle.schema_version).toBe("askdu.evidence-bundle/1.1");
  expect(bundle.export_manifest).toEqual({
    source_rows: "excluded",
    server_credentials: "excluded",
    analysis_outputs: "included",
    construction: "client-side allowlist from the public RunState response",
  });
  expect(bundle.run.run_id).toBe(persisted.run_id);
  expect(bundle.run.question).toBe(persisted.question);
  expect(bundle.run.report.markdown).toBe(persisted.report.markdown);
  expect(bundle.run.lifecycle_events.some((event) => event.edge_kind === "repair")).toBe(true);
  expect(bundle.run.agent_traces).toHaveLength(0);
  expect(bundle.run.discovery_hops).toHaveLength(0);
  expect(bundle.run.preparation_attempts).toHaveLength(0);
  expect(bundle.run.analysis_notebook).toHaveLength(0);
  expect(bundle.run.assets).toHaveLength(2);
  for (const asset of bundle.run.assets) {
    expect(asset).not.toHaveProperty("rows");
    expect(asset).not.toHaveProperty("data");
    expect(asset).not.toHaveProperty("records");
  }

  if (process.env.ASKDU_CAPTURE_PAPER === "1") {
    await page.locator(".question-shell").evaluate((element) => element.remove());
    await page.locator(".claim-list").evaluate((element) => element.remove());
    await page.locator(".workspace").evaluate((element) => element.classList.add("paper-capture"));
    await page.locator(".workspace").evaluate((workspace) => {
      for (const selector of [".catalog-provenance", ".sources-panel", ".repair-impact-panel"]) {
        const panel = document.querySelector(selector);
        if (panel) workspace.append(panel);
      }
      document.querySelector(".technical-audit")?.remove();
    });
    await page.locator(".claim-workbench").evaluate((element) => element.classList.add("capture"));
    await page.locator(".report-evidence").evaluate((element) => element.remove());
    await expect(page.locator(".paper-callout:visible")).toHaveCount(5);
    const projectRoot = path.resolve(process.cwd(), "..");
    const screenshotPath = path.resolve(projectRoot, "paper/figures/demo-ui.png");
    const workspace = page.locator(".workspace");
    const captureBox = await workspace.boundingBox();
    if (captureBox === null) throw new Error("Paper capture workspace has no bounding box");
    const screenshot = await workspace.screenshot({
      path: screenshotPath,
    });
    if (
      screenshot.subarray(0, 8).toString("hex") !== "89504e470d0a1a0a" ||
      screenshot.subarray(12, 16).toString("ascii") !== "IHDR"
    ) {
      throw new Error("Paper capture did not produce a valid PNG header");
    }
    const pixelWidth = screenshot.readUInt32BE(16);
    const pixelHeight = screenshot.readUInt32BE(20);
    const surfaceProcess = spawnSync(path.resolve(projectRoot, "scripts/hash_demo_surface.sh"), [], {
      cwd: projectRoot,
      encoding: "utf-8",
    });
    if (surfaceProcess.status !== 0) {
      throw new Error(`Could not hash the paper capture surface: ${surfaceProcess.stderr}`);
    }
    const demoSurfaceSha256 = surfaceProcess.stdout.trim();
    expect(demoSurfaceSha256).toMatch(/^[0-9a-f]{64}$/);
    const sourceTest = path.resolve(projectRoot, "frontend/e2e/demo.spec.ts");
    const sourceTestSha256 = createHash("sha256")
      .update(await readFile(sourceTest))
      .digest("hex");
    await writeFile(
      path.resolve(projectRoot, "paper/figures/demo-ui.capture.json"),
      `${JSON.stringify(
        {
          schema_version: "askdu-paper-capture-v1",
          scenario: "coda-community43-task959",
          task_id: 959,
          source_test: "frontend/e2e/demo.spec.ts",
          source_test_sha256: sourceTestSha256,
          demo_surface_sha256: demoSurfaceSha256,
          visible_callouts: ["A", "B", "C", "D", "E"],
          screenshot: {
            path: "paper/figures/demo-ui.png",
            sha256: createHash("sha256").update(screenshot).digest("hex"),
            pixel_width: pixelWidth,
            pixel_height: pixelHeight,
            css_width: Math.round(captureBox.width),
            css_height: Math.round(captureBox.height),
            device_scale_factor: Number((pixelWidth / captureBox.width).toFixed(4)),
          },
        },
        null,
        2,
      )}\n`,
      "utf-8",
    );
  } else {
    page.on("dialog", (dialog) => dialog.accept());
    await page.getByRole("button", { name: "Delete run" }).click();
    await expect(
      page.getByRole("status").filter({ hasText: "Run deleted from the active server" }),
    ).toBeVisible();
    expect((await page.request.get(`/api/v1/runs/${runId}`)).status()).toBe(404);
  }
});

test("shows a data-gap diagnosis without releasing a report", async ({ page }) => {
  await page.goto("/", { waitUntil: "networkidle" });

  await page.getByRole("button", { name: /Honest data gap/ }).click();
  await page.getByRole("button", { name: /Run hands-off analysis/ }).click();

  await expect(page.locator(".report-panel.diagnosis")).toBeVisible();
  await expect(page.getByText("Data gap diagnosis", { exact: true })).toBeVisible();
  await expect(page.getByText("The run stopped without a report", { exact: true })).toBeVisible();
  await expect(page.locator(".report-panel.completed")).toHaveCount(0);
});

test("summarizes a category-coverage repair without column-specific assumptions", async ({
  page,
}) => {
  await page.goto("/", { waitUntil: "networkidle" });

  await page.getByRole("button", { name: /Coverage repair/ }).click();
  await page.getByRole("button", { name: /Run hands-off analysis/ }).click();

  await expect(page.locator(".report-panel.completed")).toBeVisible();
  await page.locator(".technical-audit > summary").click();
  const repairImpact = page.getByTestId("repair-impact");
  await expect(repairImpact.getByText("2 requested categories missing", { exact: true })).toBeVisible();
  await expect(repairImpact.getByText("2/2 requested categories", { exact: true })).toBeVisible();
  await expect(repairImpact.getByText("3 artifacts", { exact: true })).toBeVisible();
});

test("publishes the data and software boundary without a raw-data route", async ({ page }) => {
  await page.goto("/#about", { waitUntil: "networkidle" });

  const notice = page.getByTestId("about-notice");
  await notice.scrollIntoViewIfNeeded();
  await notice.locator(":scope > summary").click();
  await expect(notice.getByRole("heading", { name: "Data & software notice" })).toBeVisible();
  await expect(notice.getByText("Research preview · code license pending")).toBeVisible();
  await expect(notice.getByText(/45 Python and three shipped Web dependencies/)).toBeVisible();
  await expect(notice.getByText(/Source bytes stay server-side/)).toBeVisible();

  const inventoryLink = notice.getByRole("link", { name: /Dependency inventory/ });
  await expect(inventoryLink).toHaveAttribute(
    "href",
    "/notices/dependency-license-inventory-v0.4.0.json",
  );
  const response = await page.request.get("/notices/dependency-license-inventory-v0.4.0.json");
  expect(response.ok()).toBeTruthy();
  const inventory = (await response.json()) as {
    backend_application: { third_party_package_count: number };
    frontend_application: { production_package_count: number };
    release_gates: {
      root_project_license_present: boolean;
      container_os_legal_review_complete: boolean;
    };
  };
  expect(inventory.backend_application.third_party_package_count).toBe(45);
  expect(inventory.frontend_application.production_package_count).toBe(3);
  expect(inventory.release_gates.root_project_license_present).toBe(false);
  expect(inventory.release_gates.container_os_legal_review_complete).toBe(false);
  await expect(page.locator('a[download], a[href*="/api/v1/assets/"]')).toHaveCount(0);
});

test("discloses the model-provider metadata boundary before submission", async ({ page }) => {
  await page.route("**/api/v1/environments/current", async (route) => {
    const upstream = await route.fetch();
    const environment = (await upstream.json()) as Record<string, unknown>;
    await route.fulfill({
      response: upstream,
      json: { ...environment, planner_mode: "model", example_questions: [] },
    });
  });

  await page.goto("/", { waitUntil: "networkidle" });

  await page.locator(".data-handling-disclosure > summary").click();
  const disclosure = page.getByTestId("model-processing-disclosure");
  await expect(disclosure).toBeVisible();
  await expect(disclosure.getByText("External model planning is active.")).toBeVisible();
  await expect(disclosure).toContainText("question, authorized catalog metadata");
  await expect(disclosure).toContainText("Complete files and server credentials are not sent");
  await expect(page.getByLabel("Your analytical question")).toHaveValue("");
  await expect(page.getByText("Verified pilots", { exact: true })).toHaveCount(0);
  await expect(page.getByLabel("Your analytical question")).toHaveAttribute(
    "aria-describedby",
    "question-help data-handling-summary question-count",
  );
  const accessibility = await new AxeBuilder({ page }).analyze();
  expect(accessibility.violations.map((violation) => violation.id)).toEqual([]);
});
