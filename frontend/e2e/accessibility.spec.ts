import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

async function expectNoDocumentOverflow(page: Page) {
  const dimensions = await page.evaluate(() => ({
    bodyClientWidth: document.body.clientWidth,
    bodyScrollWidth: document.body.scrollWidth,
    documentClientWidth: document.documentElement.clientWidth,
    documentScrollWidth: document.documentElement.scrollWidth,
  }));

  expect(dimensions.bodyScrollWidth, "body must reflow without horizontal scrolling").toBeLessThanOrEqual(
    dimensions.bodyClientWidth,
  );
  expect(
    dimensions.documentScrollWidth,
    "document must reflow without horizontal scrolling",
  ).toBeLessThanOrEqual(dimensions.documentClientWidth);
}

async function expectNoAutomaticAccessibilityViolations(page: Page) {
  const results = await new AxeBuilder({ page }).analyze();
  const summary = results.violations.map((violation) => ({
    id: violation.id,
    impact: violation.impact,
    help: violation.help,
    targets: violation.nodes.map((node) => node.target.join(" ")),
  }));
  expect(summary, JSON.stringify(summary, null, 2)).toEqual([]);
}

test("supports a question-to-lineage keyboard path with explicit states", async ({ page }) => {
  await page.goto("/", { waitUntil: "networkidle" });

  await page.keyboard.press("Tab");
  const questionSkipLink = page.getByRole("link", { name: "Skip to analytical question" });
  await expect(questionSkipLink).toBeFocused();
  await page.keyboard.press("Enter");

  const question = page.getByRole("textbox", { name: "Your analytical question" });
  await expect(question).toBeFocused();
  await expect(question).toHaveAttribute(
    "aria-describedby",
    "question-help data-handling-summary question-count",
  );

  const joinRepair = page.getByRole("button", { name: /Join repair/ });
  await joinRepair.focus();
  await page.keyboard.press("Enter");
  await expect(joinRepair).toHaveAttribute("aria-pressed", "true");

  await question.focus();
  await page.keyboard.press("Control+Enter");
  await expect(page.locator(".report-panel.completed")).toBeVisible();
  await expect(page.locator("#analysis-results")).toBeFocused();
  await page.locator(".technical-audit > summary").click();
  await expect(page.getByText("Satisfied", { exact: true }).first()).toBeVisible();

  await page.locator(".report-details > summary").click();
  const claimTabs = page.getByRole("tab");
  await expect(claimTabs).toHaveCount(3);
  await claimTabs.first().focus();
  await page.keyboard.press("ArrowDown");
  await expect(claimTabs.nth(1)).toBeFocused();
  await expect(claimTabs.nth(1)).toHaveAttribute("aria-selected", "true");

  const lineage = page.getByRole("tabpanel");
  await expect(lineage.getByText("pearson percent black hispanic", { exact: true })).toBeVisible();
  await page.keyboard.press("Tab");
  await expect(lineage).toBeFocused();
});

test("has no automatic accessibility violations before or after a repaired run", async ({ page }) => {
  await page.goto("/", { waitUntil: "networkidle" });
  await expect(page.getByText("10 files", { exact: true })).toBeVisible();
  await expectNoAutomaticAccessibilityViolations(page);

  await page.getByRole("button", { name: /Join repair/ }).click();
  await page.getByRole("button", { name: /Run hands-off analysis/ }).click();
  await expect(page.locator(".report-panel.completed")).toBeVisible();
  await expectNoAutomaticAccessibilityViolations(page);
});

test("reflows at a conference viewport and an effective 150 percent zoom", async ({ page }) => {
  await page.setViewportSize({ width: 1366, height: 768 });
  await page.goto("/", { waitUntil: "networkidle" });
  await page.getByRole("button", { name: /Join repair/ }).click();
  await page.getByRole("button", { name: /Run hands-off analysis/ }).click();
  await expect(page.locator(".report-panel.completed")).toBeVisible();
  await page.locator(".report-details > summary").click();
  await page.locator(".technical-audit > summary").click();
  await expectNoDocumentOverflow(page);

  const minimumEvidenceFontSize = await page.locator(".lineage-chain small").first().evaluate(
    (element) => Number.parseFloat(getComputedStyle(element).fontSize),
  );
  expect(minimumEvidenceFontSize).toBeGreaterThanOrEqual(10);

  await page.setViewportSize({ width: 911, height: 512 });
  await expectNoDocumentOverflow(page);
  await expect(page.locator(".question-shell > summary")).toBeVisible();
  await page.getByTestId("claim-lineage").scrollIntoViewIfNeeded();
  await expect(page.getByTestId("claim-lineage")).toBeVisible();

  const responsiveColumns = await page.locator(".system-grid").evaluate(
    (element) => getComputedStyle(element).gridTemplateColumns.split(" ").filter(Boolean).length,
  );
  expect(responsiveColumns).toBe(2);
});
