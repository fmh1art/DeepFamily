import type { AnalyticalContract } from "../types";
import { sentenceCase } from "../displayText";

interface ContractPanelProps {
  contract: AnalyticalContract | null;
}

const typeLabels: Record<string, string> = {
  measure: "Measure",
  dimension: "Dimension",
  coverage: "Coverage",
  grain: "Grain",
  join: "Join",
  statistical: "Statistical",
  evidence: "Evidence",
};

export function ContractPanel({ contract }: ContractPanelProps) {
  return (
    <section className="panel contract-panel" aria-labelledby="contract-title">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">Execution contract</p>
          <h2 id="contract-title">Analytical sufficiency</h2>
        </div>
        {contract && (
          <span className="count-badge">
            <span aria-hidden="true">{contract.obligations.length}</span>
            <span className="sr-only">
              {contract.obligations.length} analytical obligations
            </span>
          </span>
        )}
      </div>

      {!contract ? (
        <div className="empty-state">
          The question will be compiled into measures, dimensions, coverage, join, and evidence
          obligations.
        </div>
      ) : (
        <>
          {contract.analysis_plan && (
            <div className="plan-summary">
              <div className="plan-summary-heading">
                <span>Validated plan v{contract.analysis_plan.schema_version}</span>
                <code>
                  {contract.compilation.kind} · {contract.compilation.attempts} attempt
                  {contract.compilation.attempts === 1 ? "" : "s"}
                </code>
              </div>
              <p>{contract.analysis_plan.summary}</p>
              <div className="plan-stages" aria-label="Declarative plan stages">
                <span>{contract.analysis_plan.sources.length} sources</span>
                <b>→</b>
                <span>{contract.analysis_plan.preparation.length} transforms</span>
                <b>→</b>
                <span>{contract.analysis_plan.analyses.length} analyses</span>
              </div>
            </div>
          )}
          <div
            className="obligation-list"
            role="region"
            tabIndex={0}
            aria-label="Analytical obligations"
          >
            {contract.obligations.map((obligation) => (
              <article className="obligation" key={obligation.obligation_id}>
                <span className={`status-dot ${obligation.status}`} aria-hidden="true" />
                <div>
                  <div className="obligation-meta">
                    <span>{typeLabels[obligation.type] ?? obligation.type}</span>
                    <code>{obligation.check}</code>
                    <span className={`obligation-status ${obligation.status}`}>
                      {sentenceCase(obligation.status)}
                    </span>
                  </div>
                  <p>{obligation.description}</p>
                </div>
              </article>
            ))}
          </div>
        </>
      )}
    </section>
  );
}
