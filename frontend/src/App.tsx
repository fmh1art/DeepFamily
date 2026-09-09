import { type FormEvent, type KeyboardEvent, useEffect, useRef, useState } from "react";

import { createRun, deleteRun, getEnvironment, getRun } from "./api";
import { AboutNotice } from "./components/AboutNotice";
import { CatalogProvenanceBar } from "./components/CatalogProvenanceBar";
import { ContractPanel } from "./components/ContractPanel";
import { LifecyclePanel } from "./components/LifecyclePanel";
import { RepairImpactPanel } from "./components/RepairImpactPanel";
import { ReportPanel } from "./components/ReportPanel";
import { ResearchWorkflowPanel } from "./components/ResearchWorkflowPanel";
import { SourcesPanel } from "./components/SourcesPanel";
import { sentenceCase } from "./displayText";
import type { EnvironmentSummary, RunState } from "./types";

const fallbackPilotQuestion =
  "What are the Pearson correlation coefficients between the number of students who took the " +
  "SHSAT and the percentage of Asian, Black/Hispanic, and White students for Grade 8 in 2016, " +
  "using SHSAT registration and tester data that includes grade level information?";

const waitForProgress = (milliseconds: number) =>
  new Promise<void>((resolve) => window.setTimeout(resolve, milliseconds));

function App() {
  const [question, setQuestion] = useState(fallbackPilotQuestion);
  const [environment, setEnvironment] = useState<EnvironmentSummary | null>(null);
  const [run, setRun] = useState<RunState | null>(null);
  const [loading, setLoading] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [deletionMessage, setDeletionMessage] = useState<string | null>(null);
  const [focusResult, setFocusResult] = useState(false);
  const [auditOpen, setAuditOpen] = useState(false);
  const [composerOpen, setComposerOpen] = useState(true);
  const resultSummaryRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let active = true;
    getEnvironment()
      .then((result) => {
        if (active) {
          setEnvironment(result);
          if (result.planner_mode !== "registry" && result.example_questions.length === 0) {
            setQuestion("");
          }
        }
      })
      .catch((requestError: unknown) => {
        if (active) {
          setError(
            requestError instanceof Error ? requestError.message : "The API is unavailable.",
          );
        }
      });
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    if (!loading && focusResult) {
      resultSummaryRef.current?.focus();
      setFocusResult(false);
    }
  }, [focusResult, loading]);

  useEffect(() => {
    if (run?.report || run?.diagnosis) setComposerOpen(false);
  }, [run?.diagnosis, run?.report]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmed = question.trim();
    if (trimmed.length < 10 || loading || environment?.available !== true) return;
    setFocusResult(false);
    setLoading(true);
    setError(null);
    setDeletionMessage(null);
    setRun(null);
    try {
      let current = await createRun(trimmed);
      setRun(current);
      while (current.status === "pending" || current.status === "running") {
        await waitForProgress(600);
        current = await getRun(current.run_id);
        setRun(current);
      }
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "The analysis failed.");
    } finally {
      setLoading(false);
      setFocusResult(true);
    }
  }

  function runFromQuestionField(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (
      event.key === "Enter" &&
      (event.ctrlKey || event.metaKey) &&
      question.trim().length >= 10 &&
      !loading &&
      environment?.available === true
    ) {
      event.preventDefault();
      event.currentTarget.form?.requestSubmit();
    }
  }

  async function deleteStoredRun() {
    if (!run || deleting) return;
    const confirmed = window.confirm(
      "Delete this run from the active server, including its materialized tables, analysis artifacts, and report? This cannot be undone here; download anything you need first.",
    );
    if (!confirmed) return;

    setDeleting(true);
    setError(null);
    setDeletionMessage(null);
    try {
      await deleteRun(run.run_id);
      setRun(null);
      setComposerOpen(true);
      setDeletionMessage(
        "Run deleted from the active server, including its generated tables, analysis artifacts, and report.",
      );
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Run deletion failed.");
    } finally {
      setDeleting(false);
    }
  }

  const status = loading ? "running" : (run?.status ?? "ready");
  const questionDescriptionIds = [
    "question-help",
    "data-handling-summary",
    "question-count",
  ].join(" ");
  const hasTerminalOutput = Boolean(run?.report || run?.diagnosis);

  return (
    <main>
      <a className="skip-link" href="#analysis-question">
        Skip to analytical question
      </a>
      <header className="topbar">
        <a className="brand" href="#top" aria-label="Ask, Don't Upload home">
          <span className="brand-mark">A/DU</span>
          <span>
            <strong>Ask, Don&apos;t Upload</strong>
            <small>Closed-loop agentic analytics</small>
          </span>
        </a>
        <div className="topbar-meta">
          <div className="environment-status" role="status" aria-live="polite" aria-atomic="true">
            <span
              className={environment?.available ? "online-dot" : "offline-dot"}
              aria-hidden="true"
            />
            <span className="sr-only">
              Environment status: {environment ? (environment.available ? "available" : "unavailable") : "connecting"}.
            </span>
            <span>
              {environment ? `${environment.asset_count.toLocaleString()} files` : "Connecting"}
            </span>
            {environment && (
              <small>
                {environment.planner_mode === "agentic"
                  ? "Agentic mode"
                  : `${sentenceCase(environment.planner_mode)} mode`}
              </small>
            )}
          </div>
        </div>
      </header>

      {!run && (
        <section className="hero" id="top">
          <div className="hero-copy">
            <p className="kicker">Question-only data analysis</p>
            <h1>
              Ask a question. <span>Get a grounded report.</span>
            </h1>
            <p className="hero-description">
              The system finds data, prepares it, runs the analysis, and explains the result. No
              upload, table selection, or pipeline configuration is required.
            </p>
          </div>
        </section>
      )}

      <section className="workspace">
        <details
          className={`question-shell ${hasTerminalOutput ? "has-result" : ""}`}
          open={composerOpen}
          onToggle={(event) => setComposerOpen(event.currentTarget.open)}
        >
          <summary>
            <span>
              <strong>Ask another question</strong>
              <small>{run?.question}</small>
            </span>
            <span aria-hidden="true">+</span>
          </summary>
          <form className="question-composer" onSubmit={submit} aria-busy={loading}>
          <div className="composer-heading">
            <label htmlFor="analysis-question">Your analytical question</label>
            <span>No upload required</span>
          </div>
          {(environment?.example_questions.length ?? 0) > 0 && (
            <div className="example-questions" aria-label="Verified pilot questions">
              <span>Verified pilots</span>
              {(environment?.example_questions ?? []).map((example) => (
                <button
                  key={example.task_id}
                  type="button"
                  onClick={() => setQuestion(example.question)}
                  disabled={loading}
                  aria-pressed={question === example.question}
                >
                  <strong>{example.task_id}</strong>
                  {example.label}
                </button>
              ))}
            </div>
          )}
          <textarea
            id="analysis-question"
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            rows={3}
            minLength={10}
            maxLength={4000}
            required
            disabled={loading}
            aria-describedby={questionDescriptionIds}
            aria-keyshortcuts="Control+Enter Meta+Enter"
            onKeyDown={runFromQuestionField}
          />
          <details className="data-handling-disclosure">
            <summary id="data-handling-summary">
              <strong>Privacy &amp; model use</strong>
              <span>Do not submit secrets or confidential data</span>
            </summary>
            <div>
              <p
                className="storage-disclosure"
                id="run-storage-disclosure"
                role="note"
                data-testid="run-storage-disclosure"
              >
                <strong>Run storage.</strong>{" "}
                {environment === null
                  ? "Loading this server's retention policy."
                  : environment.run_retention_hours > 0
                    ? `Finished runs expire after ${environment.run_retention_hours} hours without an update; you can delete them sooner.`
                    : "Automatic expiry is disabled on this server; after a run finishes, you can delete its question and generated artifacts from the active runtime."}
              </p>
              {environment !== null && environment.planner_mode !== "registry" && (
                <p
                  className="model-processing-disclosure"
                  id="model-processing-disclosure"
                  role="note"
                  data-testid="model-processing-disclosure"
                >
                  <strong>External model planning is active.</strong> The provider receives your
                  question, authorized catalog metadata, bounded previews, and execution
                  observations. Complete files and server credentials are not sent.
                </p>
              )}
            </div>
          </details>
          <div className="question-help">
            <span id="question-help">
              Describe the analytical goal only. Press Ctrl/⌘ + Enter to run.
            </span>
            <span id="question-count">{question.length.toLocaleString()} / 4,000</span>
          </div>
          <div className="composer-footer">
            <button
              type="button"
              onClick={() =>
                setQuestion(
                  environment?.example_questions[0]?.question ??
                    (environment?.planner_mode !== "registry" ? "" : fallbackPilotQuestion),
                )
              }
              disabled={loading}
            >
              {environment?.planner_mode !== "registry"
                ? "Clear question"
                : "Restore pilot question"}
            </button>
            <button
              className="primary-action"
              type="submit"
              disabled={
                loading || environment?.available !== true || question.trim().length < 10
              }
            >
              {loading ? (
                <>
                  <span className="spinner" aria-hidden="true" /> Running closed loop
                </>
              ) : (
                "Run hands-off analysis →"
              )}
            </button>
          </div>
          </form>
        </details>

        {(loading || run) && (
          <div
            className="run-meta"
            id="analysis-results"
            ref={resultSummaryRef}
            tabIndex={-1}
            aria-live="polite"
            aria-atomic="true"
          >
            <span className="sr-only">Analysis status:</span>
            <span className={`run-status ${status}`}>{sentenceCase(status)}</span>
            {run && <code>{run.run_id}</code>}
            {run &&
              environment?.run_deletion_supported &&
              run.status !== "pending" &&
              run.status !== "running" && (
              <button
                className="delete-run"
                type="button"
                onClick={deleteStoredRun}
                disabled={deleting || loading}
              >
                {deleting ? "Deleting…" : "Delete run"}
              </button>
              )}
          </div>
        )}

        {deletionMessage && (
          <div className="success-banner" role="status">
            {deletionMessage}
          </div>
        )}

        {run?.error && (
          <div className="error-banner" role="alert">
            {run.error}
          </div>
        )}

        {error && (
          <div className="error-banner" role="alert">
            {error}
          </div>
        )}

        {hasTerminalOutput && (
          <ReportPanel run={run} catalogProvenance={environment?.catalog_provenance ?? null} />
        )}

        {environment?.planner_mode === "agentic" && run && <ResearchWorkflowPanel run={run} />}

        {run && (
          <details
            className="technical-audit"
            open={auditOpen}
            onToggle={(event) => setAuditOpen(event.currentTarget.open)}
          >
            <summary>
              <span>
                <strong>Technical details</strong>
                <small>Catalog, contract, lifecycle, sources, and repairs</small>
              </span>
              <span aria-hidden="true">+</span>
            </summary>
            <div className="technical-audit-body">
              {environment && (
                <CatalogProvenanceBar
                  provenance={environment.catalog_provenance}
                  assetCount={environment.asset_count}
                  releaseCoverage={environment.release_coverage}
                />
              )}
              <div className="system-grid">
                <ContractPanel contract={run.contract ?? null} />
                <LifecyclePanel
                  events={run.events ?? []}
                  violations={run.violations ?? []}
                  repairGoals={run.repair_goals ?? []}
                  agentTraces={run.agent_traces ?? []}
                />
                <SourcesPanel
                  assets={run.assets ?? {}}
                  decisions={run.source_decisions ?? []}
                  states={run.materialized_states ?? []}
                />
              </div>

              <RepairImpactPanel
                decisions={run.source_decisions ?? []}
                states={run.materialized_states ?? []}
                violations={run.violations ?? []}
                repairGoals={run.repair_goals ?? []}
                artifacts={run.artifacts ?? []}
                reportReleased={Boolean(run.report)}
              />
            </div>
          </details>
        )}
      </section>

      <AboutNotice />

      <footer>
        <span>VLDB 2027 demonstration research prototype</span>
      </footer>
    </main>
  );
}

export default App;
