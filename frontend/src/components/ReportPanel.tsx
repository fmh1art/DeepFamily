import { type CSSProperties, type KeyboardEvent, useId, useRef, useState } from "react";

import { downloadEvidenceBundle, downloadReportMarkdown } from "../reportExport";
import { sentenceCase } from "../displayText";
import { ExecutiveAnswer } from "./ExecutiveAnswer";
import type {
  AnalysisArtifact,
  CatalogProvenance,
  ReportClaim,
  RunState,
} from "../types";
import {
  asResultRecords,
  formatResultValue,
  humanizeIdentifier,
  StructuredDataView,
  type ResultRecord,
} from "./StructuredDataView";

interface ReportPanelProps {
  run: RunState | null;
  catalogProvenance: CatalogProvenance | null;
}

const artifactLabels: Record<string, string> = {
  final_record_count: "Final records",
  minimum_participation_ratio: "Minimum test-taker / registrant ratio",
  distinct_grade_levels: "Distinct grade levels",
  charter_school_count: "Charter schools",
  community_school_count: "Community schools",
  combined_school_share: "Combined share",
  pre_k_attendance: "Pre-K attendance",
  grade_5_attendance: "Grade 5 attendance",
  grade_9_attendance: "Grade 9 attendance",
  low_ratio_school_names: "Schools with a 0–0.2 ratio",
  mean_percent_asian: "Asian",
  mean_percent_black_hispanic: "Black / Hispanic",
  mean_percent_white: "White",
  pearson_percent_asian: "Asian student percentage",
  pearson_percent_black_hispanic: "Black / Hispanic student percentage",
  pearson_percent_white: "White student percentage",
  pearson_economic_need_percent_asian: "Economic need vs. Asian",
  pearson_economic_need_percent_black_hispanic: "Economic need vs. Black / Hispanic",
  pearson_economic_need_percent_white: "Economic need vs. White",
  top_city_1: "Top city 1",
  top_city_1_school_count: "Top city 1 count",
  top_city_2: "Top city 2",
  top_city_2_school_count: "Top city 2 count",
  top_city_3: "Top city 3",
  top_city_3_school_count: "Top city 3 count",
  peak_registration_year: "Peak registration year",
  peak_registration_count: "Peak registration total",
  highest_calorie_item: "Highest-calorie burger",
  highest_calorie_count: "Highest calorie count",
  lowest_shake_shack_item: "Lowest-calorie Shake Shack burger",
  high_absenteeism_economic_need: "High-absenteeism economic need",
  high_absenteeism_income: "High-absenteeism income",
  low_absenteeism_economic_need: "Low-absenteeism economic need",
  low_absenteeism_income: "Low-absenteeism income",
  high_black_hispanic_ela: "ELA, ≥70% Black / Hispanic",
  high_black_hispanic_math: "Math, ≥70% Black / Hispanic",
  low_black_hispanic_ela: "ELA, ≤30% Black / Hispanic",
  low_black_hispanic_math: "Math, ≤30% Black / Hispanic",
  community_school_income: "Community school income",
  community_school_black_hispanic: "Community school Black / Hispanic share",
  non_community_school_income: "Non-community school income",
  non_community_school_black_hispanic: "Non-community school Black / Hispanic share",
  negative_skew_share_after_yearly_averaging: "Negatively skewed attributes",
  positive_skew_attribute_share: "Positively skewed wage attributes",
  negative_skew_attribute_share: "Negatively skewed wage attributes",
};

function artifactLabel(artifact: AnalysisArtifact): string {
  return artifactLabels[artifact.name] ?? humanizeIdentifier(artifact.name);
}

function formatNumber(value: number, artifact: AnalysisArtifact): string {
  const rendered = value.toLocaleString("en-US", {
    minimumFractionDigits: artifact.display_precision ?? 0,
    maximumFractionDigits: artifact.display_precision ?? 6,
  });
  if (!artifact.unit) return rendered;
  if (artifact.unit === "%") return `${rendered}%`;
  if (artifact.unit === "USD") {
    return new Intl.NumberFormat("en-US", {
      style: "currency",
      currency: "USD",
      maximumFractionDigits: artifact.display_precision ?? 0,
    }).format(value);
  }
  return `${rendered} ${artifact.unit}`;
}

function formatArtifact(artifact: AnalysisArtifact): string {
  if (typeof artifact.value === "number") return formatNumber(artifact.value, artifact);
  if (Array.isArray(artifact.value)) {
    if (artifact.value.length === 0) return "No matching rows";
    const first = artifact.value[0];
    if (typeof first === "object" && first !== null) {
      const fields = Object.entries(first as Record<string, unknown>).map(([key, value]) =>
        `${humanizeIdentifier(key)}: ${formatResultValue(value, artifact.display_precision)}`,
      );
      return `${fields.join(" · ")}${artifact.value.length > 1 ? ` · ${artifact.value.length} rows` : ""}`;
    }
    return artifact.value.map((value) => formatResultValue(value, artifact.display_precision)).join(" · ");
  }
  if (typeof artifact.value === "object" && artifact.value !== null) {
    return Object.entries(artifact.value as Record<string, unknown>)
      .map(([key, value]) => `${humanizeIdentifier(key)}: ${formatResultValue(value, artifact.display_precision)}`)
      .join(" · ");
  }
  return formatResultValue(artifact.value, artifact.display_precision);
}

function preferredNumericKey(record: ResultRecord): string | null {
  const numericKeys = Object.entries(record)
    .filter(([, value]) => typeof value === "number" && Number.isFinite(value))
    .map(([key]) => key);
  if (numericKeys.includes("value")) return "value";
  return (
    numericKeys.find((key) => !/(^|_)(year|rank|id|count|index_number)($|_)/i.test(key)) ??
    numericKeys[0] ??
    null
  );
}

function measureLabel(artifact: AnalysisArtifact, key: string): string {
  if (key !== "value") return humanizeIdentifier(key).toLowerCase();
  const label = artifactLabel(artifact);
  const byIndex = label.toLowerCase().lastIndexOf(" by ");
  return byIndex >= 0 ? label.slice(byIndex + 4).toLowerCase() : "computed value";
}

function artifactFinding(artifact: AnalysisArtifact | undefined): string {
  if (!artifact) return "The requested analysis completed with evidence-linked results.";
  const records = asResultRecords(artifact.value);
  if (records && records.length > 0) {
    const first = records[0];
    const numericKey = preferredNumericKey(first);
    const labelKey = Object.keys(first).find((key) => typeof first[key] === "string") ?? null;
    if (labelKey && numericKey) {
      const label = formatResultValue(first[labelKey]);
      const value = formatResultValue(first[numericKey], artifact.display_precision);
      const loweredName = artifact.name.toLowerCase();
      if (/(top|highest|maximum|largest|best)/.test(loweredName)) {
        return `${label} ranks first, with a ${measureLabel(artifact, numericKey)} of ${value}.`;
      }
      if (/(lowest|minimum|smallest)/.test(loweredName)) {
        return `${label} is the minimum result, with a ${measureLabel(artifact, numericKey)} of ${value}.`;
      }
      return `${artifactLabel(artifact)} starts with ${label}, where ${measureLabel(artifact, numericKey)} is ${value}.`;
    }
    return `${artifactLabel(artifact)} returned ${records.length} evidence-linked rows.`;
  }
  return `${artifactLabel(artifact)} is ${formatArtifact(artifact)}.`;
}

function readableClaim(claim: ReportClaim, artifacts: AnalysisArtifact[]): string {
  const linked = artifacts.find((artifact) => claim.artifact_refs.includes(artifact.artifact_id));
  const looksSerialized = claim.text.length > 240 || /:\s*\[?\{/.test(claim.text);
  return looksSerialized ? artifactFinding(linked) : claim.text;
}

interface ChartSpec {
  labelKey: string;
  valueKey: string;
  rows: ResultRecord[];
}

function chartSpec(artifact: AnalysisArtifact): ChartSpec | null {
  const records = asResultRecords(artifact.value);
  if (!records || records.length < 2) return null;
  const labelKey = Object.keys(records[0]).find((key) =>
    records.some((record) => typeof record[key] === "string"),
  );
  const valueKey = preferredNumericKey(records[0]);
  if (!labelKey || !valueKey) return null;
  const rows = records
    .filter((record) => typeof record[valueKey] === "number" && Number.isFinite(record[valueKey]))
    .slice(0, 10);
  return rows.length >= 2 ? { labelKey, valueKey, rows } : null;
}

function chartRowLabel(row: ResultRecord, labelKey: string, valueKey: string) {
  const primary = formatResultValue(row[labelKey]);
  const yearKey = Object.keys(row).find((key) => key.toLowerCase() === "year");
  if (yearKey && yearKey !== valueKey) return `${primary} · ${formatResultValue(row[yearKey])}`;
  return primary;
}

function ArtifactBarChart({ artifact }: { artifact: AnalysisArtifact }) {
  const spec = chartSpec(artifact);
  if (!spec) return null;
  const values = spec.rows.map((row) => Math.abs(Number(row[spec.valueKey])));
  const maximum = Math.max(...values, Number.EPSILON);
  return (
    <figure className="artifact-chart" aria-label={`${artifactLabel(artifact)} bar chart`}>
      <figcaption>
        <span>Visual comparison</span>
        <strong>{humanizeIdentifier(spec.valueKey)}</strong>
      </figcaption>
      <div className="artifact-bars">
        {spec.rows.map((row, index) => {
          const value = Number(row[spec.valueKey]);
          const width = Math.max(2, (Math.abs(value) / maximum) * 100);
          return (
            <div className={`artifact-bar-row ${value < 0 ? "negative" : ""}`} key={index}>
              <span title={chartRowLabel(row, spec.labelKey, spec.valueKey)}>
                {chartRowLabel(row, spec.labelKey, spec.valueKey)}
              </span>
              <div>
                <i style={{ "--bar-width": `${width}%` } as CSSProperties} />
              </div>
              <strong>{formatResultValue(value, artifact.display_precision)}</strong>
            </div>
          );
        })}
      </div>
    </figure>
  );
}

function MetricComparisonChart({ artifacts }: { artifacts: AnalysisArtifact[] }) {
  const metrics = artifacts.filter(
    (artifact): artifact is AnalysisArtifact & { value: number } =>
      typeof artifact.value === "number" && Number.isFinite(artifact.value),
  );
  if (metrics.length < 2) return null;
  // Do not draw a shared axis for unrelated scalar results (e.g. income vs. happiness).
  const sameUnit = metrics[0].unit !== null && metrics.every((item) => item.unit === metrics[0].unit);
  const correlations = metrics.every((item) => item.name.startsWith("pearson_"));
  if (!sameUnit && !correlations) return null;
  const maximum = Math.max(...metrics.map((artifact) => Math.abs(artifact.value)), Number.EPSILON);
  return (
    <figure className="metric-comparison" aria-label="Numeric result comparison chart">
      <figcaption>
        <span>Result comparison</span>
        <strong>Evidence-linked metrics</strong>
      </figcaption>
      <div>
        {metrics.map((artifact) => {
          const width = Math.max(2, (Math.abs(artifact.value) / maximum) * 100);
          return (
            <div className={`metric-comparison-row ${artifact.value < 0 ? "negative" : ""}`} key={artifact.artifact_id}>
              <span>{artifactLabel(artifact)}</span>
              <div>
                <i style={{ "--bar-width": `${width}%` } as CSSProperties} />
              </div>
              <strong>{formatNumber(artifact.value, artifact)}</strong>
            </div>
          );
        })}
      </div>
    </figure>
  );
}

function ResultSection({ artifact, index }: { artifact: AnalysisArtifact; index: number }) {
  const records = asResultRecords(artifact.value);
  if (!records) return null;
  const hasChart = chartSpec(artifact) !== null;
  return (
    <article className="report-result-section" id={`result-${artifact.artifact_id}`} tabIndex={-1}>
      <div className="result-section-heading">
        <div>
          <span>{index === 0 ? "Primary result" : `Result ${index + 1}`}</span>
          <h3>{artifactLabel(artifact)}</h3>
        </div>
        <span>{records.length} rows</span>
      </div>
      <div className={hasChart ? "report-result-layout" : "report-result-layout table-only"}>
        <ArtifactBarChart artifact={artifact} />
        <div className="report-table-wrap">
          <div className="report-table-heading">
            <span>Computed table</span>
            <small>Rendered from the persisted analysis artifact</small>
          </div>
          <StructuredDataView
            value={artifact.value}
            maxRows={20}
            precision={artifact.display_precision}
          />
        </div>
      </div>
    </article>
  );
}

export function ReportPanel({ run, catalogProvenance }: ReportPanelProps) {
  const [selectedClaimId, setSelectedClaimId] = useState<string | null>(null);
  const claimTabsId = useId();
  const claimButtonRefs = useRef<Array<HTMLButtonElement | null>>([]);
  const report = run?.report ?? null;
  const diagnosis = run?.diagnosis ?? null;
  const artifacts = run?.artifacts ?? [];
  const evidence = run?.evidence ?? {};
  const states = run?.materialized_states ?? [];
  const assets = run?.assets ?? {};

  function selectClaimByKeyboard(event: KeyboardEvent<HTMLButtonElement>, index: number) {
    if (!report || report.claims.length === 0) return;
    let nextIndex: number | null = null;
    if (event.key === "ArrowDown" || event.key === "ArrowRight") {
      nextIndex = (index + 1) % report.claims.length;
    } else if (event.key === "ArrowUp" || event.key === "ArrowLeft") {
      nextIndex = (index - 1 + report.claims.length) % report.claims.length;
    } else if (event.key === "Home") {
      nextIndex = 0;
    } else if (event.key === "End") {
      nextIndex = report.claims.length - 1;
    }
    if (nextIndex === null) return;
    event.preventDefault();
    setSelectedClaimId(report.claims[nextIndex].claim_id);
    claimButtonRefs.current[nextIndex]?.focus();
  }

  if (diagnosis) {
    return (
      <section className="report-panel diagnosis" id="final-report" aria-labelledby="diagnosis-title">
        <p className="eyebrow">{sentenceCase(diagnosis.kind)} diagnosis</p>
        <h1 id="diagnosis-title">The run stopped without a report</h1>
        <p>{diagnosis.summary}</p>
        <div className="diagnosis-stats">
          <span>{diagnosis.unresolved_obligation_ids.length} unresolved obligations</span>
          <span>{diagnosis.attempted_repairs.length} attempted repairs</span>
        </div>
      </section>
    );
  }

  if (!report || !run) {
    return (
      <section className="report-panel awaiting" id="final-report" aria-labelledby="terminal-output-title">
        <p className="eyebrow">Automatic deliverable</p>
        <h2 id="terminal-output-title">A decision-ready report will appear here</h2>
        <p>
          The report is released only after the system finds data, materializes a valid preparation
          path, executes the analysis, and links every quantitative finding to evidence.
        </p>
        <div className="awaiting-report-flow" aria-label="Report requirements">
          <span>Find data</span><i>→</i><span>Prepare</span><i>→</i><span>Analyze</span><i>→</i><span>Release report</span>
        </div>
      </section>
    );
  }

  const reportEvidence = report.evidence_refs.map((ref) => evidence[ref]).filter(Boolean);
  const tableArtifacts = artifacts.filter((artifact) => asResultRecords(artifact.value) !== null);
  const summaryArtifacts = artifacts.filter((artifact) => asResultRecords(artifact.value) === null);
  const primaryArtifact = tableArtifacts[0] ?? artifacts[0];
  const selectedClaim =
    report.claims.find((claim) => claim.claim_id === selectedClaimId) ?? report.claims[0];
  const selectedArtifacts = selectedClaim
    ? artifacts.filter((artifact) => selectedClaim.artifact_refs.includes(artifact.artifact_id))
    : [];
  const selectedStateIds = new Set(selectedArtifacts.flatMap((artifact) => artifact.source_state_ids));
  const selectedStates = states.filter((state) => selectedStateIds.has(state.state_id));
  const selectedSourceIds = new Set(selectedStates.flatMap((state) => state.source_ids));
  const selectedAssets = Object.values(assets).filter((asset) => selectedSourceIds.has(asset.asset_id));
  const selectedEvidenceIds = new Set([
    ...(selectedClaim?.evidence_refs ?? []),
    ...selectedArtifacts.flatMap((artifact) => artifact.evidence_refs),
    ...selectedStates.flatMap((state) => state.evidence_refs),
  ]);
  const selectedEvidence = [...selectedEvidenceIds].map((ref) => evidence[ref]).filter(Boolean);
  const checksummedLineageObjects =
    selectedEvidence.filter((item) => item.sha256).length +
    selectedAssets.filter((asset) => asset.sha256).length;
  // Report scope follows the executed findings, never a later unselected candidate.
  const reportArtifactIds = new Set([
    ...report.claims.flatMap((claim) => claim.artifact_refs),
    ...report.executive_artifact_refs,
    ...report.sections.flatMap((section) => section.artifact_refs),
    ...report.conclusion_artifact_refs,
  ]);
  const reportStateIds = new Set(artifacts
    .filter((artifact) => reportArtifactIds.has(artifact.artifact_id))
    .flatMap((artifact) => artifact.source_state_ids));
  const reportStates = states.filter((state) => reportStateIds.has(state.state_id));
  const reportSourceIds = new Set(reportStates.flatMap((state) => state.source_ids));
  const reportSources = Object.values(assets).filter((asset) => reportSourceIds.has(asset.asset_id));
  // Multiple materializations can overlap: do not add their rows into a fictitious cohort.
  const preparedScope = reportStates.length === 1
    ? reportStates[0].row_count.toLocaleString()
    : reportStates.length > 1 ? reportStates.length.toLocaleString() : "—";
  return (
    <section className="report-panel completed" id="final-report" aria-labelledby="report-title">
      <div className="report-cover">
        <div className="report-heading">
          <div>
            <p className="eyebrow">
              <span className="paper-callout" aria-hidden="true">D</span>
              Automatically generated analysis report
            </p>
            <h1 id="report-title">{report.title}</h1>
          </div>
          <div className="report-actions" aria-label="Portable report outputs">
            <span className="verified-badge">Evidence linked</span>
            <button type="button" onClick={() => downloadReportMarkdown(run)}>
              Download report <span aria-hidden="true">.md</span>
            </button>
            <button type="button" onClick={() => downloadEvidenceBundle(run, catalogProvenance)}>
              Export evidence <span aria-hidden="true">.json</span>
            </button>
          </div>
        </div>

        <div className="report-question">
          <span>The only user input</span>
          <p>“{run.question}”</p>
        </div>

        <ExecutiveAnswer
          key={run.run_id}
          text={report.executive_summary || (report.claims[0]
            ? readableClaim(report.claims[0], artifacts)
            : artifactFinding(primaryArtifact))}
        />

        <div className="report-scope-strip" aria-label="Report evidence scope">
          <div><strong>{reportSources.length}</strong><span>sources used</span></div>
          <div><strong>{preparedScope}</strong><span>{reportStates.length > 1 ? "prepared datasets" : "prepared rows"}</span></div>
          <div><strong>{report.claims.length}</strong><span>grounded findings</span></div>
        </div>
      </div>

      <div className="report-content">
        {report.sections.length > 0 || report.conclusion ? (
          <section className="report-narrative" aria-labelledby="report-narrative-title">
            <div className="report-section-title">
              <div>
                <span>Cross-dimensional synthesis</span>
                <h2 id="report-narrative-title">Analysis narrative</h2>
              </div>
              <p>{report.sections.length} evidence-grounded section{report.sections.length === 1 ? "" : "s"}</p>
            </div>
            {report.sections.length > 0 ? (
              <div className="report-narrative-grid">
                {report.sections.map((section, index) => (
                  <article key={`${section.title}-${index}`}>
                    <span>Analysis {index + 1}</span>
                    <h3>{section.title}</h3>
                    <p>{section.narrative}</p>
                    <div className="report-section-evidence" aria-label={`Evidence for ${section.title}`}>
                      {section.artifact_refs.map((ref) => {
                        const artifact = artifacts.find((item) => item.artifact_id === ref);
                        return artifact ? <a key={ref} href={`#result-${ref}`}>{artifactLabel(artifact)} ↗</a> : null;
                      })}
                    </div>
                  </article>
                ))}
              </div>
            ) : null}
            {report.conclusion ? (
              <div className="report-conclusion">
                <span>Integrated conclusion</span>
                <p>{report.conclusion}</p>
              </div>
            ) : null}
            {report.limitations.length > 0 ? (
              <div className="report-limitations">
                <strong>Scope and limitations</strong>
                <ul>
                  {report.limitations.map((limitation) => <li key={limitation}>{limitation}</li>)}
                </ul>
              </div>
            ) : null}
          </section>
        ) : null}

        <div className="report-section-title">
          <div>
            <span>Executed results</span>
            <h2>Evidence-backed findings</h2>
          </div>
        </div>

        {summaryArtifacts.length > 0 ? (
          <div className="metric-grid">
            {summaryArtifacts.map((artifact) => (
              <article key={artifact.artifact_id} id={`result-${artifact.artifact_id}`} tabIndex={-1}>
                <span>{artifactLabel(artifact)}</span>
                <StructuredDataView
                  value={artifact.value}
                  maxRows={10}
                  precision={artifact.display_precision}
                  compact
                />
              </article>
            ))}
          </div>
        ) : null}

        <MetricComparisonChart artifacts={summaryArtifacts} />

        <div className="report-result-stack">
          {tableArtifacts.map((artifact, index) => (
            <ResultSection artifact={artifact} index={index} key={artifact.artifact_id} />
          ))}
        </div>

        <details className="report-details">
          <summary>
            <span>
              <strong>Evidence &amp; lineage</strong>
              <small>Inspect claims, sources, checksums, and the Markdown artifact</small>
            </span>
            <span aria-hidden="true">+</span>
          </summary>
          <div className="report-details-body">
            <div className="claim-workbench">
              <div className="claim-list">
                <div className="claim-list-heading">
                  <span>Key findings</span>
                  <h3 id={`${claimTabsId}-label`}>Select a finding to inspect its lineage</h3>
                </div>
                <div role="tablist" aria-labelledby={`${claimTabsId}-label`} aria-orientation="vertical">
                  {report.claims.map((claim, index) => {
                    const selected = claim.claim_id === selectedClaim?.claim_id;
                    return (
                      <button
                        className={selected ? "claim-row selected" : "claim-row"}
                        key={claim.claim_id}
                        id={`${claimTabsId}-tab-${index}`}
                        ref={(element) => { claimButtonRefs.current[index] = element; }}
                        type="button"
                        role="tab"
                        aria-selected={selected}
                        aria-controls={`${claimTabsId}-panel`}
                        tabIndex={selected ? 0 : -1}
                        onClick={() => setSelectedClaimId(claim.claim_id)}
                        onKeyDown={(event) => selectClaimByKeyboard(event, index)}
                      >
                        <span>{String(index + 1).padStart(2, "0")}</span>
                        <p>{readableClaim(claim, artifacts)}</p>
                        <code>{claim.artifact_refs.length} artifact</code>
                      </button>
                    );
                  })}
                </div>
              </div>

              {selectedClaim ? (
                <div
                  className="claim-inspector"
                  id={`${claimTabsId}-panel`}
                  data-testid="claim-lineage"
                  role="tabpanel"
                  aria-labelledby={`${claimTabsId}-tab-${report.claims.indexOf(selectedClaim)}`}
                  tabIndex={0}
                >
                  <div className="claim-inspector-heading">
                    <div>
                      <p className="eyebrow">
                        <span className="paper-callout" aria-hidden="true">E</span>
                        Selected finding lineage
                      </p>
                      <h3>Finding → artifact → prepared state → source</h3>
                    </div>
                    <span>{checksummedLineageObjects} checksummed lineage objects</span>
                  </div>

                  <ol className="lineage-chain">
                    <li>
                      <span>Finding</span>
                      <p>{readableClaim(selectedClaim, artifacts)}</p>
                      <code>{selectedClaim.claim_id}</code>
                    </li>
                    <li>
                      <span>Executed artifact</span>
                      {selectedArtifacts.map((artifact) => (
                        <div key={artifact.artifact_id}>
                          <strong>{artifact.name.replaceAll("_", " ")}</strong>
                          <code>{formatArtifact(artifact)}</code>
                        </div>
                      ))}
                    </li>
                    <li>
                      <span>Materialized state</span>
                      {selectedStates.map((state) => (
                        <div key={state.state_id}>
                          <strong>Iteration {state.iteration} · {state.row_count.toLocaleString()} rows · {state.columns.length} columns</strong>
                          <code>{state.state_id}</code>
                        </div>
                      ))}
                    </li>
                    <li>
                      <span>Source profiles</span>
                      {selectedAssets.map((asset) => (
                        <div key={asset.asset_id}>
                          <strong>{asset.name}</strong>
                          <code>{asset.relative_path}</code>
                          <small>sha256 {asset.sha256?.slice(0, 12)}…</small>
                        </div>
                      ))}
                    </li>
                  </ol>

                  {selectedEvidence[0] ? (
                    <div className="lineage-proof">
                      <span>{sentenceCase(selectedEvidence[0].kind)}</span>
                      <code>{selectedEvidence[0].locator}</code>
                      <small>sha256 {selectedEvidence[0].sha256?.slice(0, 16)}…</small>
                    </div>
                  ) : null}
                </div>
              ) : null}
            </div>

            <section className="report-source-basis" aria-labelledby="report-source-title">
              <div className="report-section-title compact">
                <div>
                  <span>Data basis</span>
                  <h3 id="report-source-title">Sources used in this report</h3>
                </div>
                <p>Profiles and provenance only; source rows stay server-side.</p>
              </div>
              <div className="report-source-grid">
                {reportSources.map((asset) => (
                  <article key={asset.asset_id}>
                    <span>{asset.provenance?.provider ?? "Authorized catalog"}</span>
                    <strong>{asset.name}</strong>
                    <code>{asset.relative_path}</code>
                    <div>
                      <small>{asset.row_count?.toLocaleString() ?? "—"} rows</small>
                      <small>{asset.columns.length} columns</small>
                      <small>{asset.integrity_status === "verified" ? "Integrity verified" : "Profile recorded"}</small>
                    </div>
                  </article>
                ))}
              </div>
            </section>

            <details className="report-markdown-source">
              <summary>View the generated Markdown report</summary>
              <pre>{report.markdown}</pre>
            </details>

            {reportEvidence.length > 0 ? (
              <div className="report-evidence">
                <span>Report artifact</span>
                <code>{reportEvidence[0].locator}</code>
                <small>sha256 {reportEvidence[0].sha256?.slice(0, 16)}…</small>
              </div>
            ) : null}
          </div>
        </details>
      </div>
    </section>
  );
}
