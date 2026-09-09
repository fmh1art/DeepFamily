export type Stage =
  | "question"
  | "discovery"
  | "preparation"
  | "analysis"
  | "validation"
  | "report"
  | "stopped";

export type RunStatus = "pending" | "running" | "completed" | "insufficient" | "failed";
export type ObligationStatus = "pending" | "satisfied" | "violated";

export interface EvidenceRef {
  ref_id: string;
  kind: string;
  locator: string;
  sha256: string | null;
  description: string;
}

export interface AnalyticalObligation {
  obligation_id: string;
  type: string;
  description: string;
  required: boolean;
  status: ObligationStatus;
  check: string;
  expected: Record<string, unknown>;
  evidence_refs: string[];
}

export interface AnalyticalContract {
  contract_id: string;
  question: string;
  task_family: string;
  search_terms: string[];
  obligations: AnalyticalObligation[];
  analysis_plan: DeclarativeAnalysisPlan | null;
  compilation: {
    kind: "registry" | "model";
    attempts: number;
    request_sha256s: string[];
    response_sha256s: string[];
    plan_schema_version: string | null;
  };
}

export interface DeclarativeAnalysisPlan {
  schema_version: "1.0";
  summary: string;
  sources: Array<{
    alias: string;
    asset_id: string;
    required_columns: string[];
    purpose: string;
  }>;
  preparation: Array<{
    type: string;
    output_table: string;
  }>;
  analyses: Array<{
    type: string;
    name: string;
    table: string;
  }>;
  primary_table: string;
  report_title: string;
}

export interface DataAsset {
  asset_id: string;
  relative_path: string;
  name: string;
  columns: string[];
  byte_size: number;
  file_format: string;
  tabular: boolean;
  row_count: number | null;
  sha256: string | null;
  expected_sha256: string | null;
  integrity_status: "unregistered" | "unverified" | "verified";
  provenance: SourceProvenance | null;
}

export interface SourceProvenance {
  dataset_key: string;
  title: string;
  provider: string;
  creator: string;
  source_url: string;
  license_label: string;
  license_status: "declared" | "unknown";
  license_url: string | null;
  redistribution_policy: "download_only";
}

export interface CatalogProvenance {
  benchmark_name: string;
  benchmark_url: string;
  revision: string;
  community_id: number;
  archive_sha256: string;
  archive_bytes: number;
  asset_manifest: string;
  asset_manifest_sha256: string;
  csv_asset_count: number;
  audit_date: string;
  data_access_policy: "download_only";
  source_data_bundled: false;
}

export interface SourceDecision {
  decision_id: string;
  iteration: number;
  selected_source_ids: string[];
  newly_selected_source_ids: string[];
  candidate_scores: Record<string, number>;
  reason: string;
  trigger_violation_id: string | null;
  evidence_refs: string[];
}

export interface AgentTrace {
  trace_id: string;
  agent: "discovery" | "preparation" | "analysis";
  turn: number;
  action: string;
  status: "accepted" | "rejected" | "observed";
  request_sha256: string;
  response_sha256: string;
  summary: string;
  parent_state_ids: string[];
}

export interface DiscoveryCandidate {
  asset_id: string | null;
  relative_path: string;
  name: string;
  kind: "directory" | "file";
  community: string | null;
  file_format: string | null;
  byte_size: number | null;
  score: number | null;
}

export interface DiscoveryHop {
  hop_id: string;
  iteration: number;
  turn: number;
  parent_hop_id: string | null;
  action: string;
  status: "accepted" | "rejected" | "observed";
  scope: string;
  destination: string | null;
  query_terms: string[];
  candidates: DiscoveryCandidate[];
  inspected_asset_id: string | null;
  inspected_path: string | null;
  inspected_schema: Record<string, string>;
  selected_asset_ids: string[];
  summary: string;
  error: string | null;
}

export interface PreparationOperatorTrace {
  operator_id: string;
  position: number;
  operator_type: string;
  operator_family:
    | "data_cleaning"
    | "column_transformation"
    | "table_transformation"
    | "other";
  input_tables: string[];
  output_table: string;
  parameters: Record<string, unknown>;
  input_rows: number[];
  output_rows: number | null;
  output_columns: string[];
  added_columns: string[];
  removed_columns: string[];
  summary: string;
}

export interface PreparationAttempt {
  attempt_id: string;
  turn: number;
  candidate_id: string | null;
  parent_candidate_id: string | null;
  status: "materialized" | "rejected" | "selected";
  reason: string;
  source_aliases: string[];
  operators: PreparationOperatorTrace[];
  state_id: string | null;
  output_table: string | null;
  output_rows: number | null;
  output_columns: string[];
  observation: string;
  violation_type: string | null;
  error: string | null;
  request_sha256: string;
  response_sha256: string;
}

export interface AnalysisNotebookStep {
  step_id: string;
  sequence: number;
  turn: number;
  phase: "analyze" | "understand" | "code" | "execute" | "debug" | "answer" | "report";
  status: "planned" | "running" | "completed" | "failed";
  title: string;
  summary: string;
  analysis_name: string | null;
  language: "markdown" | "python" | "sql" | "json" | "text";
  source_code: string | null;
  parameters: Record<string, unknown>;
  output: unknown;
  runtime: string | null;
  duration_ms: number | null;
  state_refs: string[];
  artifact_refs: string[];
  evidence_refs: string[];
}

export interface MaterializedState {
  state_id: string;
  iteration: number;
  parent_state_ids: string[];
  source_ids: string[];
  row_count: number;
  columns: string[];
  schema: Record<string, string>;
  preview_rows: Array<Record<string, unknown>>;
  metrics: Record<string, unknown>;
  evidence_refs: string[];
}

export interface AnalysisArtifact {
  artifact_id: string;
  kind: string;
  name: string;
  value: unknown;
  unit: string | null;
  display_precision: number | null;
  source_state_ids: string[];
  evidence_refs: string[];
}

export interface SufficiencyViolation {
  violation_id: string;
  obligation_ids: string[];
  type: string;
  observed: Record<string, unknown>;
  expected: Record<string, unknown>;
  detected_stage: Stage;
  responsible_stage: Stage;
  evidence_refs: string[];
  resolved: boolean;
}

export interface RepairGoal {
  repair_goal_id: string;
  violation_id: string;
  target_stage: Stage;
  instruction: string;
  search_terms: string[];
  status: "pending" | "completed" | "failed";
  selected_source_ids: string[];
}

export interface LifecycleEvent {
  event_id: string;
  sequence: number;
  from_stage: Stage;
  to_stage: Stage;
  edge_kind: "forward" | "repair" | "terminal";
  summary: string;
  object_refs: string[];
}

export interface ReportClaim {
  claim_id: string;
  text: string;
  value: unknown;
  artifact_refs: string[];
  evidence_refs: string[];
}

export interface Report {
  report_id: string;
  title: string;
  markdown: string;
  claims: ReportClaim[];
  evidence_refs: string[];
  executive_summary: string;
  executive_artifact_refs: string[];
  sections: Array<{
    title: string;
    narrative: string;
    artifact_refs: string[];
  }>;
  conclusion: string;
  conclusion_artifact_refs: string[];
  limitations: string[];
}

export interface InsufficiencyDiagnosis {
  diagnosis_id: string;
  kind: "capability_gap" | "data_gap" | "budget_exhausted";
  summary: string;
  unresolved_obligation_ids: string[];
  attempted_repairs: string[];
  evidence_refs: string[];
}

export interface RunState {
  run_id: string;
  environment_id: string;
  question: string;
  status: RunStatus;
  current_stage: Stage;
  contract: AnalyticalContract | null;
  evidence: Record<string, EvidenceRef>;
  assets: Record<string, DataAsset>;
  agent_traces: AgentTrace[];
  discovery_hops: DiscoveryHop[];
  preparation_attempts: PreparationAttempt[];
  analysis_notebook: AnalysisNotebookStep[];
  source_decisions: SourceDecision[];
  materialized_states: MaterializedState[];
  artifacts: AnalysisArtifact[];
  violations: SufficiencyViolation[];
  repair_goals: RepairGoal[];
  events: LifecycleEvent[];
  report: Report | null;
  diagnosis: InsufficiencyDiagnosis | null;
  error: string | null;
}

export interface EnvironmentSummary {
  environment_id: string;
  available: boolean;
  csv_assets: number;
  asset_count: number;
  tabular_assets: number;
  file_formats: Record<string, number>;
  planner_mode: "registry" | "model" | "agentic";
  run_retention_hours: number;
  run_deletion_supported: true;
  catalog_provenance: CatalogProvenance | null;
  release_coverage: {
    revision: string;
    published_communities: number;
    open_runtime_communities: number;
    installed_open_communities: number;
    published_tasks: number;
    open_runtime_tasks: number;
    source_datasets: number;
    sealed_evaluation_communities: number;
  } | null;
  example_questions: Array<{
    task_id: number;
    label: string;
    question: string;
  }>;
}
