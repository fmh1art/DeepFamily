import type {
  AnalysisArtifact,
  MaterializedState,
  RepairGoal,
  SourceDecision,
  SufficiencyViolation,
} from "../types";
import { sentenceCase } from "../displayText";

interface RepairImpactPanelProps {
  decisions: SourceDecision[];
  states: MaterializedState[];
  violations: SufficiencyViolation[];
  repairGoals: RepairGoal[];
  artifacts: AnalysisArtifact[];
  reportReleased: boolean;
}

function stringArray(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];
}

function countLabel(count: number, singular: string, plural = `${singular}s`) {
  return `${count} ${count === 1 ? singular : plural}`;
}

export function RepairImpactPanel({
  decisions,
  states,
  violations,
  repairGoals,
  artifacts,
  reportReleased,
}: RepairImpactPanelProps) {
  const completedGoals = repairGoals.filter((goal) => goal.status === "completed");
  const repairedViolationIds = new Set(completedGoals.map((goal) => goal.violation_id));
  const repairedViolations = violations.filter(
    (violation) => violation.resolved && repairedViolationIds.has(violation.violation_id),
  );
  const initialState = states[0];
  const acceptedState = states.at(-1);

  if (!initialState || !acceptedState || repairedViolations.length === 0) return null;

  const requiredColumns = [
    ...new Set(
      repairedViolations.flatMap((violation) =>
        stringArray(violation.expected.required_columns),
      ),
    ),
  ];
  const requiredCategories = [
    ...new Set(
      repairedViolations.flatMap((violation) =>
        stringArray(violation.expected.required_categories),
      ),
    ),
  ];
  const fallbackTargets = [...new Set(completedGoals.flatMap((goal) => goal.search_terms))];
  const targets =
    requiredColumns.length > 0
      ? requiredColumns
      : requiredCategories.length > 0
        ? requiredCategories
        : fallbackTargets;
  const targetSingular = requiredColumns.length > 0 ? "required variable" : "requested category";
  const targetPlural = requiredColumns.length > 0 ? "required variables" : "requested categories";
  const recoveredTargetCount =
    requiredColumns.length > 0
      ? requiredColumns.filter((column) => acceptedState.columns.includes(column)).length
      : requiredCategories.length > 0
        ? requiredCategories.filter((category) =>
            stringArray(acceptedState.metrics.restaurant_coverage)
              .map((value) => value.toLowerCase())
              .includes(category.toLowerCase()),
          ).length
        : targets.length;
  const repairSourceIds = new Set(
    decisions
      .filter((decision) => decision.trigger_violation_id)
      .flatMap((decision) => decision.newly_selected_source_ids),
  );
  const joinCoverage = acceptedState.metrics.join_coverage;
  const initialSourceCount = initialState.source_ids.length;
  const acceptedSourceCount = acceptedState.source_ids.length;

  return (
    <section className="repair-impact-panel" aria-labelledby="repair-impact-title" data-testid="repair-impact">
      <div className="repair-impact-heading">
        <div>
          <p className="eyebrow">
            <span className="paper-callout" aria-hidden="true">
              C
            </span>
            Why the loop mattered
          </p>
          <h2 id="repair-impact-title">Repair impact</h2>
        </div>
        <span className="impact-badge">
          {countLabel(completedGoals.length, "backward edge")} · {countLabel(repairSourceIds.size, "new source")}
        </span>
      </div>

      <div className="repair-impact-flow">
        <article className="impact-state blocked">
          <div className="impact-state-label">
            <span>Initial pass</span>
            <strong>Report gated</strong>
          </div>
          <dl>
            <div>
              <dt>Evidence</dt>
              <dd>{countLabel(initialSourceCount, "source")}</dd>
            </div>
            <div>
              <dt>Prepared schema</dt>
              <dd>{countLabel(initialState.columns.length, "column")}</dd>
            </div>
            <div>
              <dt>Violation</dt>
              <dd>
                {countLabel(targets.length, targetSingular, targetPlural)} missing
              </dd>
            </div>
          </dl>
        </article>

        <div className="impact-repair" aria-label="Repair from Analysis back to Discovery">
          <span>Analysis ↶ Discovery</span>
          <strong>{sentenceCase(repairedViolations[0].type)}</strong>
          <div className="impact-terms">
            {targets.map((target) => (
              <code key={target}>{target}</code>
            ))}
          </div>
        </div>

        <article className="impact-state accepted">
          <div className="impact-state-label">
            <span>Replayed state</span>
            <strong>{reportReleased ? "Report released" : "Repair completed"}</strong>
          </div>
          <dl>
            <div>
              <dt>Evidence</dt>
              <dd>
                {countLabel(acceptedSourceCount, "source")} (+{acceptedSourceCount - initialSourceCount})
              </dd>
            </div>
            <div>
              <dt>Recovered</dt>
              <dd>
                {recoveredTargetCount}/{targets.length} {targetPlural}
              </dd>
            </div>
            <div>
              <dt>Acceptance proof</dt>
              <dd>
                {typeof joinCoverage === "number"
                  ? `${(joinCoverage * 100).toFixed(1)}% join`
                  : countLabel(artifacts.length, "artifact")}
              </dd>
            </div>
          </dl>
        </article>
      </div>
    </section>
  );
}
