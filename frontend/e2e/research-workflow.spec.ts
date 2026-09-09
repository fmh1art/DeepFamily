import { expect, test } from "@playwright/test";

import type { EnvironmentSummary, RunState } from "../src/types";

const hashA = "a".repeat(64);
const hashB = "b".repeat(64);

function withPaperAlignedTrace(run: RunState): RunState {
  const sources = Object.values(run.assets);
  const source = sources[0];
  const sourceTwo = sources[1] ?? source;
  const initialState = run.materialized_states[0];
  const selectedState = run.materialized_states.at(-1);
  const artifact = run.artifacts[0];
  if (!source || !sourceTwo || !initialState || !selectedState || !artifact) {
    throw new Error("The registry pilot did not produce the fixture objects needed by this test.");
  }
  if (!run.report) {
    throw new Error("The registry pilot did not produce the report needed by this test.");
  }
  const artifactRefs = run.artifacts.map((item) => item.artifact_id);
  const structuredReport = {
    ...run.report,
    executive_summary:
      "SHSAT participation has distinct relationships with the three demographic measures.",
    executive_artifact_refs: artifactRefs,
    sections: run.artifacts.map((item) => ({
      title: item.name.replaceAll("_", " "),
      narrative: `This dimension is grounded in the executed ${item.name} result.`,
      artifact_refs: [item.artifact_id],
    })),
    conclusion:
      "The three executed correlations should be interpreted together within the prepared 2016 Grade 8 cohort.",
    conclusion_artifact_refs: artifactRefs,
    limitations: ["The report is limited to the selected sources and the 2016 Grade 8 cohort."],
  };
  const communityIds = [43, ...Array.from({ length: 29 }, (_, index) => index + 1)];

  const operator = (
    id: string,
    position: number,
    type: string,
    input: string[],
    output: string,
  ) => ({
    operator_id: id,
    position,
    operator_type: type,
    operator_family: "table_transformation" as const,
    input_tables: input,
    output_table: output,
    parameters: type === "Filter" ? { predicates: [{ column: "Year", operator: "eq" }] } : {},
    input_rows: [initialState.row_count],
    output_rows: selectedState.row_count,
    output_columns: selectedState.columns,
    added_columns: [],
    removed_columns: [],
    summary: `${type}: ${input.join(", ")} → ${output} · ${selectedState.row_count} rows`,
  });

  return {
    ...run,
    report: structuredReport,
    discovery_hops: [
      {
        hop_id: "hop_root",
        iteration: 0,
        turn: 0,
        parent_hop_id: null,
        action: "environment_root",
        status: "observed",
        scope: "/",
        destination: "authorized_root",
        query_terms: [],
        candidates: communityIds.map((communityId) => ({
          asset_id: null,
          relative_path: `community_${communityId}`,
          name: `community_${communityId}`,
          kind: "directory" as const,
          community: `community_${communityId}`,
          file_format: null,
          byte_size: null,
          score: null,
        })),
        inspected_asset_id: null,
        inspected_path: null,
        inspected_schema: {},
        selected_asset_ids: [],
        summary: "Opened the authorized root and exposed the community frontier.",
        error: null,
      },
      {
        hop_id: "hop_search",
        iteration: 0,
        turn: 1,
        parent_hop_id: "hop_root",
        action: "search_catalog",
        status: "observed",
        scope: "authorized_root",
        destination: "community_43",
        query_terms: ["SHSAT", "Grade 8", "2016"],
        candidates: [
          {
            asset_id: source.asset_id,
            relative_path: source.relative_path,
            name: source.name,
            kind: "file",
            community: "community_43",
            file_format: source.file_format,
            byte_size: source.byte_size,
            score: 18,
          },
          {
            asset_id: sourceTwo.asset_id,
            relative_path: sourceTwo.relative_path,
            name: sourceTwo.name,
            kind: "file",
            community: "community_43",
            file_format: sourceTwo.file_format,
            byte_size: sourceTwo.byte_size,
            score: 16,
          },
        ],
        inspected_asset_id: null,
        inspected_path: null,
        inspected_schema: {},
        selected_asset_ids: [],
        summary: "Ranked a bounded source frontier from the analytical question.",
        error: null,
      },
      {
        hop_id: "hop_inspect",
        iteration: 0,
        turn: 2,
        parent_hop_id: "hop_search",
        action: "inspect_asset",
        status: "observed",
        scope: "community_43",
        destination: source.relative_path,
        query_terms: [],
        candidates: [],
        inspected_asset_id: source.asset_id,
        inspected_path: source.relative_path,
        inspected_schema: Object.fromEntries(source.columns.map((column) => [column, "string"])),
        selected_asset_ids: [],
        summary: "Inspected a bounded preview and its schema before selection.",
        error: null,
      },
      {
        hop_id: "hop_inspect_2",
        iteration: 0,
        turn: 3,
        parent_hop_id: "hop_inspect",
        action: "inspect_asset",
        status: "observed",
        scope: "community_43",
        destination: sourceTwo.relative_path,
        query_terms: [],
        candidates: [],
        inspected_asset_id: sourceTwo.asset_id,
        inspected_path: sourceTwo.relative_path,
        inspected_schema: Object.fromEntries(
          sourceTwo.columns.map((column) => [column, "string"]),
        ),
        selected_asset_ids: [],
        summary: "Inspected the second candidate before adding it to the evidence set.",
        error: null,
      },
      {
        hop_id: "hop_select",
        iteration: 0,
        turn: 4,
        parent_hop_id: "hop_inspect_2",
        action: "select_sources",
        status: "accepted",
        scope: "community_43",
        destination: "selected_evidence_set",
        query_terms: [],
        candidates: [],
        inspected_asset_id: null,
        inspected_path: null,
        inspected_schema: {},
        selected_asset_ids: [source.asset_id, sourceTwo.asset_id],
        summary: "Selected only files that had already been inspected.",
        error: null,
      },
    ],
    preparation_attempts: [
      {
        attempt_id: "prep_attempt_1",
        turn: 1,
        candidate_id: "candidate_1",
        parent_candidate_id: null,
        status: "materialized",
        reason: "Execute the first complete preparation chain.",
        source_aliases: ["schools", "shsat"],
        operators: [
          operator("candidate_1:op:1", 1, "Filter", ["schools"], "grade_8"),
          operator("candidate_1:op:2", 2, "Join", ["grade_8", "shsat"], "joined"),
          operator("candidate_1:op:3", 3, "Terminate", ["joined"], "joined"),
        ],
        state_id: initialState.state_id,
        output_table: "joined",
        output_rows: initialState.row_count,
        output_columns: initialState.columns,
        observation: "Materialized the first branch; a downstream completeness check requested repair.",
        violation_type: "missing_required_columns",
        error: null,
        request_sha256: hashA,
        response_sha256: hashB,
      },
      {
        attempt_id: "prep_attempt_2",
        turn: 2,
        candidate_id: "candidate_2",
        parent_candidate_id: "candidate_1",
        status: "selected",
        reason: "Backtrack, repair the join keys, and retain the verified branch.",
        source_aliases: ["schools", "shsat"],
        operators: [
          operator("candidate_2:op:1", 1, "Filter", ["schools"], "grade_8"),
          operator("candidate_2:op:2", 2, "Join", ["grade_8", "shsat"], "joined"),
          operator("candidate_2:op:3", 3, "Terminate", ["joined"], "joined"),
        ],
        state_id: selectedState.state_id,
        output_table: "joined",
        output_rows: selectedState.row_count,
        output_columns: selectedState.columns,
        observation: "Selected as the final execution-observed path after backtracking.",
        violation_type: null,
        error: null,
        request_sha256: hashB,
        response_sha256: hashA,
      },
    ],
    analysis_notebook: [
      {
        step_id: "analysis_step_1",
        sequence: 1,
        turn: 1,
        phase: "analyze",
        status: "completed",
        title: "Analyze · task decomposition",
        summary: "Decompose the question into three correlation analyses.",
        analysis_name: null,
        language: "markdown",
        source_code: null,
        parameters: {},
        output: { analyses: ["pearson_percent_asian"] },
        runtime: null,
        duration_ms: null,
        state_refs: [selectedState.state_id],
        artifact_refs: [],
        evidence_refs: [],
      },
      {
        step_id: "analysis_step_2",
        sequence: 2,
        turn: 1,
        phase: "understand",
        status: "completed",
        title: "Understand · prepared table",
        summary: `Inspect ${selectedState.row_count} rows before writing analysis code.`,
        analysis_name: null,
        language: "json",
        source_code: null,
        parameters: {},
        output: { columns: selectedState.columns },
        runtime: null,
        duration_ms: null,
        state_refs: [selectedState.state_id],
        artifact_refs: [],
        evidence_refs: selectedState.evidence_refs,
      },
      {
        step_id: "analysis_step_3",
        sequence: 3,
        turn: 1,
        phase: "code",
        status: "completed",
        title: "Code · pearson_percent_asian",
        summary: "Compiled the validated specification into a bounded SQL cell.",
        analysis_name: artifact.name,
        language: "sql",
        source_code: 'SELECT AVG("Percent Asian") AS value\nFROM data\nWHERE "Year" = :p1;',
        parameters: { p1: 2016 },
        output: null,
        runtime: "sqlite_in_memory",
        duration_ms: null,
        state_refs: [selectedState.state_id],
        artifact_refs: [],
        evidence_refs: [],
      },
      {
        step_id: "analysis_step_4",
        sequence: 4,
        turn: 1,
        phase: "debug",
        status: "failed",
        title: "Debug · pearson_percent_asian",
        summary: "A compiled-cell verification mismatch was retained before safe fallback.",
        analysis_name: artifact.name,
        language: "text",
        source_code: null,
        parameters: {},
        output: "ValueError: verification failed",
        runtime: "sqlite_in_memory",
        duration_ms: null,
        state_refs: [selectedState.state_id],
        artifact_refs: [],
        evidence_refs: [],
      },
      {
        step_id: "analysis_step_5",
        sequence: 5,
        turn: 1,
        phase: "execute",
        status: "completed",
        title: "Execute · pearson_percent_asian",
        summary: "Re-executed through the validated dataframe fallback.",
        analysis_name: artifact.name,
        language: "json",
        source_code: null,
        parameters: {},
        output: artifact.value,
        runtime: "bounded_dataframe_fallback",
        duration_ms: 12.4,
        state_refs: [selectedState.state_id],
        artifact_refs: [artifact.artifact_id],
        evidence_refs: artifact.evidence_refs,
      },
      {
        step_id: "analysis_step_6",
        sequence: 6,
        turn: 4,
        phase: "analyze",
        status: "completed",
        title: "Analyze · cross-dimensional synthesis",
        summary: "Synthesized every executed dimension into one bounded report draft.",
        analysis_name: null,
        language: "json",
        source_code: null,
        parameters: {},
        output: {
          sections: structuredReport.sections.map((section) => section.title),
          artifact_refs: artifactRefs,
          fallback: false,
        },
        runtime: null,
        duration_ms: null,
        state_refs: [selectedState.state_id],
        artifact_refs: artifactRefs,
        evidence_refs: run.artifacts.flatMap((item) => item.evidence_refs),
      },
      {
        step_id: "analysis_step_7",
        sequence: 7,
        turn: 3,
        phase: "answer",
        status: "completed",
        title: "Answer · grounded findings",
        summary: "Accepted only claims linked to executed analysis artifacts.",
        analysis_name: null,
        language: "markdown",
        source_code: null,
        parameters: {},
        output: structuredReport.claims.map((claim) => claim.text),
        runtime: null,
        duration_ms: null,
        state_refs: [],
        artifact_refs: artifactRefs,
        evidence_refs: run.artifacts.flatMap((item) => item.evidence_refs),
      },
      {
        step_id: "analysis_step_8",
        sequence: 8,
        turn: 3,
        phase: "report",
        status: "completed",
        title: "Report · Markdown release",
        summary: "Released the report only after contract and lineage validation.",
        analysis_name: null,
        language: "markdown",
        source_code: null,
        parameters: {},
        output: {
          report_id: structuredReport.report_id,
          title: structuredReport.title,
          executive_summary: structuredReport.executive_summary,
          sections: structuredReport.sections,
          conclusion: structuredReport.conclusion,
          limitations: structuredReport.limitations,
        },
        runtime: null,
        duration_ms: null,
        state_refs: [],
        artifact_refs: artifactRefs,
        evidence_refs: structuredReport.evidence_refs,
      },
    ],
  };
}

function withDecisionReadyReport(run: RunState): RunState {
  const state = run.materialized_states.at(-1);
  const sourceArtifact = run.artifacts[0];
  if (!state || !sourceArtifact || !run.report) {
    throw new Error("The registry pilot did not produce the fixture objects needed by this test.");
  }
  const rankingArtifact = {
    ...sourceArtifact,
    artifact_id: "artifact_happiness_ranking",
    kind: "table",
    name: "top_countries_by_mean_pandemic_happiness_index",
    value: [
      { Country: "Finland", value: 7.824000000000001 },
      { Country: "Denmark", value: 7.634 },
      { Country: "Switzerland", value: 7.547666666666667 },
    ],
    display_precision: 3,
    source_state_ids: [state.state_id],
  };
  const countArtifact = {
    ...sourceArtifact,
    artifact_id: "artifact_pandemic_rows",
    kind: "scalar",
    name: "pandemic_record_count",
    value: 448,
    display_precision: null,
    source_state_ids: [state.state_id],
  };
  return {
    ...run,
    question: "疫情期间哪个国家幸福指数最高？",
    artifacts: [rankingArtifact, countArtifact],
    report: {
      ...run.report,
      title: "疫情期间幸福指数最高的国家",
      markdown: "# 疫情期间幸福指数最高的国家\n\n芬兰在当前数据范围内排名第一。",
      executive_summary: "芬兰在当前疫情期间记录中平均幸福指数最高，为 7.824。",
      executive_artifact_refs: [rankingArtifact.artifact_id, countArtifact.artifact_id],
      sections: [
        {
          title: "国家排名",
          narrative: "平均幸福指数的执行结果显示，芬兰领先于丹麦和瑞士。",
          artifact_refs: [rankingArtifact.artifact_id],
        },
        {
          title: "数据覆盖",
          narrative: "该结论来自筛选后保留的 448 条疫情期间记录。",
          artifact_refs: [countArtifact.artifact_id],
        },
      ],
      conclusion: "在当前数据定义、时间范围与幸福指数指标下，芬兰是排名最高的国家。",
      conclusion_artifact_refs: [rankingArtifact.artifact_id, countArtifact.artifact_id],
      limitations: ["“最幸福”仅按当前数据中的幸福指数衡量，不代表所有生活质量维度。"],
      claims: [
        {
          claim_id: "claim_happiness_ranking",
          text: `Top Countries: ${JSON.stringify(rankingArtifact.value)}.`,
          value: rankingArtifact.value,
          artifact_refs: [rankingArtifact.artifact_id],
          evidence_refs: rankingArtifact.evidence_refs,
        },
        {
          claim_id: "claim_pandemic_rows",
          text: "Pandemic record count: 448.",
          value: 448,
          artifact_refs: [countArtifact.artifact_id],
          evidence_refs: countArtifact.evidence_refs,
        },
      ],
    },
  };
}

test("renders the three paper-aligned execution mechanisms", async ({ page }) => {
  await page.route("**/api/v1/environments/current", async (route) => {
    const response = await route.fetch();
    const environment = (await response.json()) as EnvironmentSummary;
    await route.fulfill({
      response,
      json: { ...environment, planner_mode: "agentic" },
    });
  });
  await page.route("**/api/v1/runs?background=true", async (route) => {
    const target = new URL(route.request().url());
    target.search = "";
    const response = await route.fetch({ url: target.toString() });
    const completed = (await response.json()) as RunState;
    await route.fulfill({
      status: 202,
      contentType: "application/json",
      body: JSON.stringify(withPaperAlignedTrace(completed)),
    });
  });

  await page.goto("/", { waitUntil: "networkidle" });
  await page.getByRole("button", { name: /Run hands-off analysis/ }).click();

  const workbench = page.getByTestId("research-workflow");
  await expect(workbench).toBeVisible();

  await workbench.getByRole("tab", { name: /CoDA-Bench Discover/ }).click();
  const discovery = workbench.getByRole("region", { name: "Data discovery workflow" });
  await expect(
    discovery.getByText("Walks the catalog hop by hop and selects only evidence it actually inspected."),
  ).toBeVisible();
  await expect(discovery.getByRole("button", { name: "Show hop 1: Environment root" })).toBeVisible();
  await expect(discovery.getByRole("button", { name: "Show hop 2: Search catalog" })).toBeVisible();
  await expect(discovery.getByRole("button", { name: "Show hop 3: Inspect asset" })).toBeVisible();
  await expect(discovery.getByRole("button", { name: "Show hop 4: Inspect asset" })).toBeVisible();
  await expect(discovery.getByRole("button", { name: "Show hop 5: Select sources" })).toBeVisible();
  await expect(discovery.getByText("Input · data need")).toBeVisible();
  await expect(discovery.getByText("Output · relevant CSV files")).toBeVisible();
  await expect(discovery.getByLabel("Complete community discovery network")).toBeVisible();
  await expect(discovery.getByText("30 communities · 2 encountered files")).toBeVisible();
  await discovery.getByRole("button", { name: "Show hop 1: Environment root" }).click();
  await expect(discovery.getByText("30 communities · 0 encountered files")).toBeVisible();
  await expect(discovery.locator(".discovery-output-files")).toHaveCount(0);
  await discovery.getByRole("button", { name: "Show hop 2: Search catalog" }).click();
  await expect(discovery.locator(".discovery-step-nav").getByText("2 / 5")).toBeVisible();
  await expect(discovery.locator(".network-nodes .current")).toHaveCount(1);
  await expect(discovery.locator(".network-nodes .visited").first()).toBeVisible();
  await expect(discovery.locator(".network-transitions .current")).toHaveAttribute("data-from", "/");
  await expect(discovery.locator(".network-transitions .current")).toHaveAttribute("data-to", "community_43");
  await discovery.getByRole("button", { name: "Show hop 3: Inspect asset" }).click();
  await expect(discovery.locator(".network-transitions .current")).toHaveAttribute("data-from", "community_43");
  await expect(discovery.locator(".network-transitions .visited")).toHaveCount(1);
  if (process.env.ASKDU_CAPTURE_WORKFLOW === "1") {
    await discovery.screenshot({ path: "test-results/workflow-discovery.png" });
  }

  await workbench.getByRole("tab", { name: /DeepPrep Prepare/ }).click();
  const preparation = workbench.getByRole("region", { name: "Data preparation workflow" });
  await expect(
    preparation.getByText(
      "Executes candidate operator paths, observes results, and backtracks from bad branches.",
    ),
  ).toBeVisible();
  await preparation.locator(".prep-exploration-ledger > summary").click();
  await expect(preparation.getByText("candidate_1", { exact: true })).toBeVisible();
  await expect(preparation.getByText("candidate_2", { exact: true }).first()).toBeVisible();
  await expect(preparation.getByText("Backtrack / expand from candidate_1")).toBeVisible();
  await expect(preparation.getByText("Filter", { exact: true }).first()).toBeVisible();
  await expect(preparation.getByText("Join", { exact: true }).first()).toBeVisible();
  await expect(preparation.getByText("Terminate", { exact: true }).first()).toBeVisible();
  await expect(preparation.getByText("Input · discovered CSV schemas")).toBeVisible();
  await expect(preparation.getByText("Output · analysis-ready table")).toBeVisible();
  await expect(preparation.getByText("Executed data preview")).toBeVisible();
  const expandSchema = preparation.locator(".prep-input-sources").getByRole("button", { name: /Show all \d+ fields/ }).first();
  await expandSchema.click();
  await expect(preparation.getByRole("button", { name: "Show fewer fields" }).first()).toHaveAttribute("aria-expanded", "true");
  await preparation.getByRole("button", { name: "Show fewer fields" }).first().click();
  await expect(preparation.getByText(/Schema changes ·/)).toBeVisible();
  await preparation.locator(".schema-change-details > summary").click();
  await expect(preparation.getByText("Recorded types · input → output", { exact: true })).toBeVisible();
  await preparation.locator(".schema-change-details > summary").click();
  if (process.env.ASKDU_CAPTURE_WORKFLOW === "1") {
    await preparation.screenshot({ path: "test-results/workflow-preparation.png" });
  }

  await workbench.getByRole("tab", { name: /DeepAnalyze Analyze/ }).click();
  const analysis = workbench.getByRole("region", { name: "Data analysis workflow" });
  await expect(
    analysis.getByText(
      "Writes and executes SQL or Python, keeps debug feedback, then grounds the report.",
    ),
  ).toBeVisible();
  await expect(analysis.getByText("Analyze", { exact: true }).first()).toBeVisible();
  await expect(analysis.getByText("Understand", { exact: true }).first()).toBeVisible();
  await expect(analysis.getByText("Code", { exact: true }).first()).toBeVisible();
  await expect(analysis.getByText("Debug", { exact: true }).first()).toBeVisible();
  await expect(analysis.getByText("Execute", { exact: true }).first()).toBeVisible();
  await expect(analysis.getByText("Report", { exact: true }).first()).toBeVisible();
  await expect(analysis.getByText("Input · prepared dataset")).toBeVisible();
  await expect(analysis.getByText("Output · decision-ready report")).toBeVisible();
  await expect(analysis.getByText("Generated report")).toBeVisible();
  await expect(analysis.getByText("pearson percent asian", { exact: true }).first()).toBeVisible();
  await expect(analysis.getByText("Integrated conclusion", { exact: true }).first()).toBeVisible();
  await analysis.locator(".notebook-cell.code .notebook-cell-details > summary").click();
  await expect(analysis.getByText(/SELECT AVG/)).toBeVisible();
  await expect(analysis.getByText(/Bounded dataframe fallback · 12.4 ms/)).toBeVisible();
  if (process.env.ASKDU_CAPTURE_WORKFLOW === "1") {
    await analysis.screenshot({ path: "test-results/workflow-analysis.png" });
  }
});

test("turns table artifacts into a readable report with a chart and full table", async ({
  page,
}) => {
  await page.route("**/api/v1/environments/current", async (route) => {
    const response = await route.fetch();
    const environment = (await response.json()) as EnvironmentSummary;
    await route.fulfill({ response, json: { ...environment, planner_mode: "agentic" } });
  });
  await page.route("**/api/v1/runs?background=true", async (route) => {
    const target = new URL(route.request().url());
    target.search = "";
    const response = await route.fetch({ url: target.toString() });
    const completed = (await response.json()) as RunState;
    await route.fulfill({
      status: 202,
      contentType: "application/json",
      body: JSON.stringify(withDecisionReadyReport(completed)),
    });
  });

  await page.goto("/", { waitUntil: "networkidle" });
  await page.getByRole("button", { name: /Run hands-off analysis/ }).click();

  const report = page.locator(".report-panel.completed");
  await expect(report).toBeVisible();
  await expect(page.locator(".question-shell")).not.toHaveAttribute("open", "");
  await expect(report.locator(".report-details")).not.toHaveAttribute("open", "");
  await expect(report.getByText("Answer at a glance", { exact: true })).toBeVisible();
  await expect(report.getByText("芬兰在当前疫情期间记录中平均幸福指数最高，为 7.824。")).toBeVisible();
  await expect(report.getByRole("button", { name: "Read full answer" })).toHaveCount(0);
  await expect(report.getByText("国家排名", { exact: true })).toBeVisible();
  await expect(report.getByText("数据覆盖", { exact: true })).toBeVisible();
  await expect(report.getByText(/在当前数据定义、时间范围与幸福指数指标下/)).toBeVisible();
  await expect(
    report.getByRole("figure", { name: /Top countries by mean pandemic happiness index bar chart/ }),
  ).toBeVisible();
  const resultTable = report.getByRole("table").first();
  await expect(resultTable.getByRole("columnheader", { name: "Country" })).toBeVisible();
  await expect(resultTable.getByRole("cell", { name: "Finland" })).toBeVisible();
  await expect(resultTable.getByRole("cell", { name: "7.824" })).toBeVisible();
  await expect(report.getByText("Pandemic record count", { exact: true })).toBeVisible();
  for (const label of await report.locator(".artifact-bar-row > strong").all()) {
    const valueBox = await label.boundingBox();
    const chartBox = await report.locator(".artifact-chart").boundingBox();
    expect(valueBox!.x + valueBox!.width).toBeLessThanOrEqual(chartBox!.x + chartBox!.width);
  }
  const evidenceLink = report.getByLabel("Evidence for 国家排名").getByRole("link").first();
  const target = await evidenceLink.getAttribute("href");
  expect(target).toMatch(/^#result-artifact_/);
  await evidenceLink.click();
  await expect(page.locator(target!)).toBeVisible();
  if (process.env.ASKDU_CAPTURE_WORKFLOW === "1") {
    await report.screenshot({ path: "test-results/workflow-report.png" });
  }
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy();
  await expect(page.locator(".technical-audit")).not.toHaveAttribute("open", "");
});

// User-provided long-answer example: a layout fixture, not a new model-quality result.
const longExecutiveAnswer = "Based on the available China-focused records, Peking University is the strongest overall answer, but only within the scope of these rankings and years. In the Times 2016 data, Peking University has the highest listed total score among Chinese universities, with a score of 72.0 and world rank 42; Tsinghua University follows with 70.0 and world rank =47. In the CWUR 2015 data, Peking University is also first in China, with world rank 56, national rank 1, and score 54.26, ahead of Tsinghua University at world rank 78, national rank 2, and score 52.21. In the Shanghai 2015 data, no single institution is separated at the top: Peking University, Shanghai Jiao Tong University, Tsinghua University, and Zhejiang University are all in the 101–150 world-rank band and national-rank band 1–4. Therefore, the best supported conclusion is that Peking University is the leading choice across these executed rankings, while Shanghai does not break the tie among the top Chinese universities.";

for (const [language, text] of [
  ["English", longExecutiveAnswer],
  ["Chinese", "这个结论仅适用于当前数据所覆盖的年份与评价指标，不代表所有维度下的绝对排名。".repeat(16)],
] as const) {
  test(`keeps a long ${language} executive answer compact and expandable without changing its export`, async ({ page }) => {
    await page.route("**/api/v1/environments/current", async (route) => {
      const response = await route.fetch();
      await route.fulfill({ response, json: { ...await response.json(), planner_mode: "agentic" } });
    });
    await page.route("**/api/v1/runs?background=true", async (route) => {
      const target = new URL(route.request().url());
      target.search = "";
      const response = await route.fetch({ url: target.toString() });
      const fixture = withDecisionReadyReport(await response.json() as RunState);
      fixture.report!.executive_summary = text;
      fixture.report!.markdown = `# Layout fixture\n\n${text}\n`;
      await route.fulfill({ status: 202, json: fixture });
    });
    await page.goto("/", { waitUntil: "networkidle" });
    await page.getByRole("button", { name: /Run hands-off analysis/ }).click();
    const answer = page.getByRole("region", { name: "Answer at a glance" });
    const paragraph = answer.locator(".executive-answer-text");
    const toggle = answer.getByRole("button");
    await expect(answer).toBeVisible();
    await expect(paragraph).toHaveText(text);
    await expect(paragraph).toHaveCSS("font-size", "16px");
    await expect(paragraph).toHaveCSS("font-weight", "400");
    await expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect((await paragraph.boundingBox())!.height).toBeLessThanOrEqual(141);
    expect((await answer.boundingBox())!.height).toBeLessThan(250);
    await answer.screenshot({ path: `test-results/executive-answer-${language.toLowerCase()}-desktop.png` });

    await toggle.focus();
    await page.keyboard.press("Enter");
    await expect(toggle).toHaveAttribute("aria-expanded", "true");
    await expect(toggle).toHaveAccessibleName("Show less");
    await expect(toggle).toBeFocused();
    expect((await paragraph.boundingBox())!.height).toBeGreaterThan(141);
    await expect(paragraph).toHaveText(text);

    await page.keyboard.press("Space");
    await expect(toggle).toHaveAttribute("aria-expanded", "false");
    await page.setViewportSize({ width: 390, height: 844 });
    await expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect((await paragraph.boundingBox())!.height).toBeLessThanOrEqual(141);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
    await answer.screenshot({ path: `test-results/executive-answer-${language.toLowerCase()}-mobile.png` });
    await toggle.click();
    await expect(toggle).toHaveAttribute("aria-expanded", "true");
    expect((await paragraph.boundingBox())!.height).toBeGreaterThan(141);
    await toggle.click();

    const downloadPromise = page.waitForEvent("download");
    await page.getByRole("button", { name: /Download report/ }).click();
    const stream = await (await downloadPromise).createReadStream();
    let exported = "";
    for await (const chunk of stream!) exported += chunk.toString();
    expect(exported).toBe(`# Layout fixture\n\n${text}\n`);
  });
}

test("only offers answer expansion when its current layout actually overflows", async ({ page }) => {
  await page.route("**/api/v1/environments/current", async (route) => {
    const response = await route.fetch();
    await route.fulfill({ response, json: { ...await response.json(), planner_mode: "agentic" } });
  });
  await page.route("**/api/v1/runs?background=true", async (route) => {
    const target = new URL(route.request().url());
    target.search = "";
    const response = await route.fetch({ url: target.toString() });
    const fixture = withDecisionReadyReport(await response.json() as RunState);
    fixture.report!.executive_summary = longExecutiveAnswer.slice(0, 300);
    await route.fulfill({ status: 202, json: fixture });
  });
  await page.goto("/", { waitUntil: "networkidle" });
  await page.getByRole("button", { name: /Run hands-off analysis/ }).click();
  const answer = page.getByRole("region", { name: "Answer at a glance" });
  await expect(answer).toBeVisible();
  await expect(answer.getByRole("button")).toHaveCount(0);
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(answer.getByRole("button", { name: "Read full answer" })).toBeVisible();
  await page.setViewportSize({ width: 1600, height: 1100 });
  await expect(answer.getByRole("button")).toHaveCount(0);
});

test("retains large frontiers and uses the executed table in stage inputs and report scope", async ({ page }) => {
  await page.route("**/api/v1/environments/current", async (route) => {
    const response = await route.fetch();
    await route.fulfill({ response, json: { ...await response.json(), planner_mode: "agentic" } });
  });
  await page.route("**/api/v1/runs?background=true", async (route) => {
    const target = new URL(route.request().url());
    target.search = "";
    const response = await route.fetch({ url: target.toString() });
    const run = withPaperAlignedTrace(await response.json() as RunState);
    const search = run.discovery_hops[1];
    search.candidates.unshift(...Array.from({ length: 26 }, (_, index) => ({
      ...search.candidates[0], asset_id: `asset_${index.toString(16).padStart(16, "0")}`,
      name: `extra_${index}.csv`, relative_path: `community_43/nested/extra_${index}.csv`,
    })));
    // A later unselected branch must not become the purported Analysis input.
    run.materialized_states.push({
      ...run.materialized_states[0], state_id: "state_unselected", row_count: 999999,
      columns: ["Unselected branch"], schema: { "Unselected branch": "string" },
      preview_rows: [{ "Unselected branch": "not the analysis input" }],
    });
    const source = Object.values(run.assets)[0];
    run.assets.asset_inspected_unused = {
      ...source, asset_id: "asset_inspected_unused", name: "Inspected but unused.csv",
      relative_path: "community_43/unused.csv",
    };
    await route.fulfill({ status: 202, json: run });
  });
  await page.goto("/", { waitUntil: "networkidle" });
  await page.getByRole("button", { name: /Run hands-off analysis/ }).click();
  const workbench = page.getByTestId("research-workflow");
  await workbench.getByRole("tab", { name: /CoDA-Bench Discover/ }).click();
  await expect(workbench.getByText("30 communities · 28 encountered files")).toBeVisible();
  await expect(workbench.locator(".network-nodes .file.selected")).toHaveCount(2);
  await expect(workbench.locator('.network-nodes .directory[data-path="community_43/nested"]')).toHaveCount(1);
  await workbench.getByRole("tab", { name: /DeepPrep Prepare/ }).click();
  await expect(workbench.getByText("Unselected branch", { exact: true })).toHaveCount(0);
  await workbench.getByRole("tab", { name: /DeepAnalyze Analyze/ }).click();
  await expect(workbench.getByText("Unselected branch", { exact: true })).toHaveCount(0);
  await expect(workbench.getByText("Executed data preview")).toBeVisible();
  const report = page.locator("#final-report");
  await expect(report.locator(".report-scope-strip")).not.toContainText("999,999");
  await expect(report.getByText("sources used", { exact: true })).toBeVisible();
  await report.locator(".report-details > summary").click();
  await expect(report.getByRole("heading", { name: "Sources used in this report" })).toBeVisible();
  await expect(report.locator(".report-source-grid")).not.toContainText("Inspected but unused.csv");
});

test("does not present rejected source selections as discovery output", async ({ page }) => {
  await page.route("**/api/v1/environments/current", async (route) => {
    const response = await route.fetch();
    await route.fulfill({ response, json: { ...await response.json(), planner_mode: "agentic" } });
  });
  await page.route("**/api/v1/runs?background=true", async (route) => {
    const target = new URL(route.request().url());
    target.search = "";
    const response = await route.fetch({ url: target.toString() });
    const run = withPaperAlignedTrace(await response.json() as RunState);
    run.status = "insufficient";
    run.current_stage = "stopped";
    run.report = null;
    const rejected = run.discovery_hops.at(-1)!;
    rejected.status = "rejected";
    rejected.error = "Selected sources must belong to one community.";
    await route.fulfill({ status: 202, json: run });
  });
  await page.goto("/", { waitUntil: "networkidle" });
  await page.getByRole("button", { name: /Run hands-off analysis/ }).click();
  const workbench = page.getByTestId("research-workflow");
  await workbench.getByRole("tab", { name: /CoDA-Bench Discover/ }).click();
  await expect(workbench.getByText("No output · action rejected")).toBeVisible();
  await expect(workbench.locator(".discovery-output-files")).toHaveCount(0);
  await expect(workbench.locator(".network-nodes .selected")).toHaveCount(0);
  await expect(workbench.locator(".network-transitions .current")).toHaveCount(0);
});

test("replays revised source sets without retaining superseded outputs", async ({ page }) => {
  await page.route("**/api/v1/environments/current", async (route) => {
    const response = await route.fetch();
    await route.fulfill({ response, json: { ...await response.json(), planner_mode: "agentic" } });
  });
  await page.route("**/api/v1/runs?background=true", async (route) => {
    const target = new URL(route.request().url());
    target.search = "";
    const response = await route.fetch({ url: target.toString() });
    const run = withPaperAlignedTrace(await response.json() as RunState);
    const original = run.discovery_hops.at(-1)!;
    run.discovery_hops.push({
      ...original, hop_id: "hop_revised_selection", parent_hop_id: original.hop_id,
      iteration: 1, turn: 5, selected_asset_ids: [original.selected_asset_ids[1]],
      summary: "Revised the source set after downstream feedback.",
    });
    await route.fulfill({ status: 202, json: run });
  });
  await page.goto("/", { waitUntil: "networkidle" });
  await page.getByRole("button", { name: /Run hands-off analysis/ }).click();
  const workbench = page.getByTestId("research-workflow");
  await workbench.getByRole("tab", { name: /CoDA-Bench Discover/ }).click();
  await expect(workbench.locator(".discovery-output-files > div")).toHaveCount(1);
  await expect(workbench.locator(".network-nodes .file.selected")).toHaveCount(1);
  await workbench.getByRole("button", { name: "Previous discovery hop" }).click();
  await expect(workbench.locator(".discovery-output-files > div")).toHaveCount(2);
  await expect(workbench.locator(".network-nodes .file.selected")).toHaveCount(2);
});
