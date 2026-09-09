import type {
  AgentTrace,
  LifecycleEvent,
  RepairGoal,
  SufficiencyViolation,
} from "../types";
import { sentenceCase } from "../displayText";

interface LifecyclePanelProps {
  events: LifecycleEvent[];
  violations: SufficiencyViolation[];
  repairGoals: RepairGoal[];
  agentTraces: AgentTrace[];
}

function stageLabel(stage: string) {
  return stage.charAt(0).toUpperCase() + stage.slice(1);
}

export function LifecyclePanel({
  events,
  violations,
  repairGoals,
  agentTraces,
}: LifecyclePanelProps) {
  const violationById = new Map(violations.map((item) => [item.violation_id, item]));

  return (
    <section className="panel lifecycle-panel" aria-labelledby="lifecycle-title">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">Materialized state graph</p>
          <h2 id="lifecycle-title">Lifecycle trace</h2>
        </div>
        {events.length > 0 && (
          <span className="count-badge">
            <span aria-hidden="true">{events.length}</span>
            <span className="sr-only">{events.length} lifecycle events</span>
          </span>
        )}
      </div>

      {events.length === 0 ? (
        <div className="empty-state">
          Forward execution and backward repair edges will appear here as verifiable events.
        </div>
      ) : (
        <ol className="event-list" tabIndex={0} aria-label="Persisted lifecycle events">
          {events.map((event) => (
            <li className={`event ${event.edge_kind}`} key={event.event_id}>
              <div className="event-index">{String(event.sequence).padStart(2, "0")}</div>
              <div className="event-content">
                <div className="event-edge">
                  <span>{stageLabel(event.from_stage)}</span>
                  <span className="edge-arrow" aria-label="to">
                    {event.edge_kind === "repair" ? "↶" : "→"}
                  </span>
                  <span>{stageLabel(event.to_stage)}</span>
                  <span className={`edge-kind ${event.edge_kind}`}>
                    {sentenceCase(event.edge_kind)}
                  </span>
                </div>
                <p>{event.summary}</p>
              </div>
            </li>
          ))}
        </ol>
      )}

      {repairGoals.length > 0 && (
        <div className="repair-summary">
          <p className="eyebrow">Closed-loop repair</p>
          {repairGoals.map((goal) => {
            const violation = violationById.get(goal.violation_id);
            return (
              <article key={goal.repair_goal_id}>
                <div className="repair-title">
                  <span>{sentenceCase(violation?.type ?? "sufficiency_violation")}</span>
                  <span className={`repair-status ${goal.status}`}>
                    {sentenceCase(goal.status)}
                  </span>
                </div>
                <p>{goal.instruction}</p>
                <div className="term-list">
                  {goal.search_terms.map((term) => (
                    <code key={term}>{term}</code>
                  ))}
                </div>
              </article>
            );
          })}
        </div>
      )}

      {agentTraces.length > 0 && (
        <div className="agent-trace-summary">
          <div className="agent-trace-heading">
            <div>
              <p className="eyebrow">Bounded model decisions</p>
              <h3>Agent turns</h3>
            </div>
            <span className="count-badge">{agentTraces.length}</span>
          </div>
          <ol className="agent-trace-list" aria-label="Persisted agent decision trace">
            {agentTraces.map((trace) => (
              <li key={trace.trace_id}>
                <div className="agent-trace-meta">
                  <span>{stageLabel(trace.agent)}</span>
                  <span>Turn {trace.turn}</span>
                  <span>{sentenceCase(trace.action)}</span>
                  <span className={`agent-turn-status ${trace.status}`}>
                    {sentenceCase(trace.status)}
                  </span>
                </div>
                <p>{trace.summary}</p>
                <small>
                  Request {trace.request_sha256.slice(0, 10)} · Response{" "}
                  {trace.response_sha256.slice(0, 10)}
                </small>
              </li>
            ))}
          </ol>
        </div>
      )}
    </section>
  );
}
