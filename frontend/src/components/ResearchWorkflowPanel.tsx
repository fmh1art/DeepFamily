import { useEffect, useId, useMemo, useRef, useState } from "react";

import { sentenceCase } from "../displayText";
import type {
  AnalysisNotebookStep,
  DiscoveryCandidate,
  DiscoveryHop,
  MaterializedState,
  PreparationAttempt,
  PreparationOperatorTrace,
  RunState,
  Stage,
} from "../types";
import { StructuredDataView } from "./StructuredDataView";

interface ResearchWorkflowPanelProps {
  run: RunState | null;
}

type WorkbenchStage = "discovery" | "preparation" | "analysis";
type StageDisplayStatus = "waiting" | "active" | "complete" | "stopped";

const stageOrder: Stage[] = [
  "question",
  "discovery",
  "preparation",
  "analysis",
  "validation",
  "report",
  "stopped",
];

const stageMetadata: Array<{
  id: WorkbenchStage;
  index: number;
  title: string;
  paper: string;
}> = [
  {
    id: "discovery",
    index: 1,
    title: "Discover",
    paper: "CoDA-Bench",
  },
  {
    id: "preparation",
    index: 2,
    title: "Prepare",
    paper: "DeepPrep",
  },
  {
    id: "analysis",
    index: 3,
    title: "Analyze",
    paper: "DeepAnalyze",
  },
];

function stageProgress(run: RunState | null, stage: WorkbenchStage): StageDisplayStatus {
  if (run === null) return "waiting";
  if (run.status === "failed" || run.status === "insufficient") {
    const hasWork =
      stage === "discovery"
        ? run.discovery_hops.length > 0
        : stage === "preparation"
          ? run.preparation_attempts.length > 0
          : run.analysis_notebook.length > 0;
    return hasWork ? "stopped" : "waiting";
  }
  const current = stageOrder.indexOf(run.current_stage);
  const target = stageOrder.indexOf(stage);
  if (current === target) return "active";
  return current > target || run.status === "completed" ? "complete" : "waiting";
}

function activeWorkbenchStage(run: RunState | null): WorkbenchStage {
  if (!run || run.current_stage === "question" || run.current_stage === "discovery") {
    return "discovery";
  }
  if (run.current_stage === "preparation") return "preparation";
  if (run.current_stage === "analysis") return "analysis";
  if (run.analysis_notebook.length > 0) return "analysis";
  if (run.preparation_attempts.length > 0) return "preparation";
  return "discovery";
}

function stageCount(run: RunState | null, stage: WorkbenchStage) {
  if (!run) return 0;
  if (stage === "discovery") return run.discovery_hops.length;
  if (stage === "preparation") return run.preparation_attempts.length;
  return run.analysis_notebook.length;
}

function formatBytes(bytes: number | null) {
  if (bytes === null) return null;
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function renderJson(value: unknown) {
  if (typeof value === "string") return value;
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

function shortPath(value: string) {
  const segments = value.split("/").filter(Boolean);
  if (segments.length <= 2) return value;
  return `${segments.at(-2)}/${segments.at(-1)}`;
}

function truncate(value: string, length = 34) {
  return value.length <= length ? value : `${value.slice(0, length - 1)}…`;
}

function SchemaList({
  columns,
  schema = {},
  limit = 12,
}: {
  columns: string[];
  schema?: Record<string, string>;
  limit?: number;
}) {
  const [expanded, setExpanded] = useState(false);
  return (
    <div className="stage-schema-list">
      {columns.slice(0, expanded ? columns.length : limit).map((column) => (
        <span key={column} title={column}>
          <strong>{column}</strong>
          <small>{schema[column] ?? "type not recorded"}</small>
        </span>
      ))}
      {columns.length > limit ? (
        <button type="button" aria-expanded={expanded} onClick={() => setExpanded(!expanded)}>
          {expanded ? "Show fewer fields" : `Show all ${columns.length} fields`}
        </button>
      ) : null}
    </div>
  );
}

function PreparedTablePreview({ state }: { state: MaterializedState | null }) {
  if (!state) {
    return <p className="stage-output-pending">Waiting for a materialized table.</p>;
  }
  return (
    <div className="prepared-table-preview">
      <div className="prepared-table-shape">
        <strong>{state.row_count.toLocaleString()} rows</strong>
        <span>{state.columns.length} columns</span>
      </div>
      <SchemaList columns={state.columns} schema={state.schema} />
      {state.preview_rows.length > 0 ? (
        <div className="prepared-preview-table">
          <span>Executed data preview</span>
          <StructuredDataView value={state.preview_rows} maxRows={5} compact />
        </div>
      ) : (
        <p className="stage-output-pending">Preview unavailable for this earlier persisted run.</p>
      )}
    </div>
  );
}

interface DiscoveryGraphNode {
  id: string;
  label: string;
  kind: "root" | "community" | "directory" | "file";
  x: number;
  y: number;
  assetId: string | null;
  community: string | null;
  path: string;
}

interface DiscoveryGraphEdge {
  id: string;
  from: string;
  to: string;
}

function pathCommunity(path: string): string | null {
  return path.match(/community_\d+/i)?.[0] ?? null;
}

function DiscoveryNetwork({
  hops,
  activeIndex,
}: {
  hops: DiscoveryHop[];
  activeIndex: number;
}) {
  const arrowId = useId().replaceAll(":", "");
  const { nodes, edges, visited, current, frontier, selected, transitions } = useMemo(() => {
    const communities = new Set<string>();
    const files = new Map<string, DiscoveryCandidate>();
    const directories = new Set<string>();
    const visibleHops = hops.slice(0, activeIndex + 1);
    for (const hop of visibleHops) {
      if (hop.status === "rejected") continue;
      const destinationCommunity = hop.destination ? pathCommunity(hop.destination) : null;
      if (destinationCommunity) communities.add(destinationCommunity);
      if (hop.action === "list_directory" && hop.destination && hop.destination !== "authorized_root") {
        directories.add(hop.destination);
      }
      for (const candidate of hop.candidates) {
        const community = candidate.community ?? pathCommunity(candidate.relative_path);
        if (community) communities.add(community);
        if (candidate.kind === "directory") directories.add(candidate.relative_path);
        if (candidate.kind === "file") {
          files.set(candidate.asset_id ?? candidate.relative_path, candidate);
        }
      }
      if (hop.inspected_path) {
        const community = pathCommunity(hop.inspected_path);
        if (community) communities.add(community);
        if (!files.has(hop.inspected_asset_id ?? hop.inspected_path)) files.set(
          hop.inspected_asset_id ?? hop.inspected_path,
          {
            asset_id: hop.inspected_asset_id,
            relative_path: hop.inspected_path,
            name: shortPath(hop.inspected_path),
            kind: "file",
            community,
            file_format: "csv",
            byte_size: null,
            score: null,
          },
        );
      }
    }
    // Membership is a hierarchy, not an invented semantic community graph.
    // Only the root's community overview is global; file nodes arrive with observations.
    for (const path of [...directories, ...[...files.values()].map((file) => file.relative_path)]) {
      const parts = path.split("/");
      for (let depth = 1; depth < parts.length; depth += 1) {
        directories.add(parts.slice(0, depth).join("/"));
      }
    }
    const communityList = [...communities].sort((a, b) => a.localeCompare(b, undefined, { numeric: true }));
    const fileList = [...files.entries()];
    const directoryList = [...directories].filter((path) => !communities.has(path)).sort();
    const graphNodes: DiscoveryGraphNode[] = [
      {
        id: "root",
        label: "Authorized catalog",
        kind: "root",
        x: 380,
        y: 220,
        assetId: null,
        community: null,
        path: "/",
      },
      ...communityList.map((community, index) => {
        const angle = (Math.PI * 2 * index) / Math.max(communityList.length, 1) - Math.PI / 2;
        return {
          id: `community:${community}`,
          label: community.replace("community_", "Community "),
          kind: "community" as const,
          x: 380 + Math.cos(angle) * 190,
          y: 220 + Math.sin(angle) * 130,
          assetId: null,
          community,
          path: community,
        };
      }),
      ...directoryList.map((path, index) => {
        const community = pathCommunity(path);
        const communityIndex = community ? communityList.indexOf(community) : index;
        const angle = (Math.PI * 2 * communityIndex) / Math.max(communityList.length, 1) - Math.PI / 2;
        const peers = directoryList.filter((item) => pathCommunity(item) === community);
        const offset = (peers.indexOf(path) - (peers.length - 1) / 2) * 0.07;
        return {
          id: `directory:${path}`, label: shortPath(path), kind: "directory" as const,
          x: 380 + Math.cos(angle + offset) * 255,
          y: 220 + Math.sin(angle + offset) * 158,
          assetId: null, community, path,
        };
      }),
      ...fileList.map(([key, candidate], index) => {
        const community = candidate.community ?? pathCommunity(candidate.relative_path);
        const communityIndex = community ? communityList.indexOf(community) : index;
        const peers = fileList.filter(([, file]) => (file.community ?? pathCommunity(file.relative_path)) === community);
        const peerIndex = peers.findIndex(([id]) => id === key);
        const spread = Math.min(1.4, Math.max(0.2, peers.length * 0.06));
        const offset = peers.length > 1 ? (peerIndex / (peers.length - 1) - 0.5) * spread : 0;
        const angle = (Math.PI * 2 * communityIndex) / Math.max(communityList.length, 1) - Math.PI / 2 + offset;
        return {
          id: `file:${key}`,
          label: candidate.name,
          kind: "file" as const,
          x: 380 + Math.cos(angle) * 325,
          y: 220 + Math.sin(angle) * 190,
          assetId: candidate.asset_id,
          community,
          path: candidate.relative_path,
        };
      }),
    ];
    const byId = new Map(graphNodes.map((node) => [node.id, node]));
    const byAsset = new Map(
      graphNodes.filter((node) => node.assetId).map((node) => [node.assetId as string, node.id]),
    );
    const byPath = new Map(graphNodes.map((node) => [node.path, node.id]));
    const destinationId = (destination: string | null): string | null => {
      if (!destination || destination === "selected_evidence_set") return null;
      if (destination === "authorized_root" || destination === "/") return "root";
      if (byPath.has(destination)) return byPath.get(destination) ?? null;
      const community = pathCommunity(destination);
      if (community && byId.has(`community:${community}`) && destination === community) {
        return `community:${community}`;
      }
      const file = graphNodes.find(
        (node) => node.kind === "file" && (node.path.endsWith(destination) || destination.endsWith(node.path)),
      );
      return file?.id ?? (community ? `community:${community}` : null);
    };
    const graphEdges: DiscoveryGraphEdge[] = [];
    for (const community of communityList) {
      graphEdges.push({ id: `root-${community}`, from: "root", to: `community:${community}` });
    }
    for (const node of graphNodes.filter((candidate) => candidate.kind === "file" || candidate.kind === "directory")) {
      const parentPath = node.path.split("/").slice(0, -1).join("/");
      const parent = byPath.get(parentPath) ?? (node.community && byId.has(`community:${node.community}`)
        ? `community:${node.community}`
        : "root");
      graphEdges.push({ id: `${parent}-${node.id}`, from: parent, to: node.id });
    }
    const historical = new Set<string>(["root"]);
    const currentNodes = new Set<string>();
    const frontierNodes = new Set<string>();
    const selectedNodes = new Set<string>();
    const navigations: Array<DiscoveryGraphEdge & { active: boolean }> = [];
    const focusByHop = new Map<string, string[]>();
    visibleHops.forEach((hop, index) => {
      if (hop.status === "rejected") return;
      const destination = destinationId(hop.destination);
      const targets = hop.action === "select_sources"
        ? hop.selected_asset_ids.flatMap((id) => byAsset.get(id) ? [byAsset.get(id)!] : [])
        : hop.action === "search_catalog" && !destination
          ? [...new Set(hop.candidates.flatMap((candidate) => {
            const community = candidate.community ?? pathCommunity(candidate.relative_path);
            return community ? [`community:${community}`] : [];
          }))]
          : destination ? [destination] : [];
      focusByHop.set(hop.hop_id, targets);
      const parentFocus = hop.parent_hop_id ? focusByHop.get(hop.parent_hop_id) : null;
      const origin = hop.action === "search_catalog" ? "root"
        : parentFocus?.length === 1 ? parentFocus[0] : destinationId(hop.scope) ?? "root";
      for (const target of targets) {
        historical.add(target);
        if (index === activeIndex) currentNodes.add(target);
        if (target !== origin) navigations.push({
          id: `${hop.hop_id}:${target}`, from: origin, to: target, active: index === activeIndex,
        });
      }
      if (destination) historical.add(destination);
      if (hop.inspected_asset_id && byAsset.has(hop.inspected_asset_id)) {
        historical.add(byAsset.get(hop.inspected_asset_id) as string);
      }
      if (hop.action === "select_sources") selectedNodes.clear();
      hop.selected_asset_ids.forEach((assetId) => {
        if (byAsset.has(assetId)) selectedNodes.add(byAsset.get(assetId) as string);
      });
      if (index === activeIndex) {
        if (destination) currentNodes.add(destination);
        if (hop.inspected_asset_id && byAsset.has(hop.inspected_asset_id)) {
          currentNodes.add(byAsset.get(hop.inspected_asset_id) as string);
        }
        hop.candidates.forEach((candidate) => {
          const id = candidate.kind === "directory"
            ? byPath.get(candidate.relative_path) ?? ""
            : `file:${candidate.asset_id ?? candidate.relative_path}`;
          if (byId.has(id)) frontierNodes.add(id);
        });
        hop.selected_asset_ids.forEach((assetId) => {
          if (byAsset.has(assetId)) currentNodes.add(byAsset.get(assetId) as string);
        });
      }
    });
    return {
      nodes: graphNodes,
      edges: graphEdges,
      visited: historical,
      current: currentNodes,
      frontier: frontierNodes,
      selected: selectedNodes,
      transitions: navigations,
    };
  }, [activeIndex, hops]);
  const byId = new Map(nodes.map((node) => [node.id, node]));
  return (
    <div className="discovery-network" aria-label="Complete community discovery network">
      <div className="discovery-network-heading">
        <div>
          <span>Community network</span>
          <strong>Community overview · step {activeIndex + 1}</strong>
        </div>
        <small>{nodes.filter((node) => node.kind === "community").length} communities · {nodes.filter((node) => node.kind === "file").length} encountered files</small>
      </div>
      <svg viewBox="0 0 760 440" role="img" aria-label="Data communities and files explored by the discovery agent">
        <defs>
          <marker id={arrowId} viewBox="0 0 10 10" refX="14" refY="5" markerWidth="5" markerHeight="5" orient="auto-start-reverse">
            <path d="M 0 0 L 10 5 L 0 10 z" fill="#a94e00" />
          </marker>
        </defs>
        <g className="network-edges">
          {edges.map((edge) => {
            const from = byId.get(edge.from);
            const to = byId.get(edge.to);
            if (!from || !to) return null;
            const edgeVisited = visited.has(edge.to) || selected.has(edge.to);
            return (
              <line
                key={edge.id}
                className={edgeVisited ? "visited" : ""}
                x1={from.x}
                y1={from.y}
                x2={to.x}
                y2={to.y}
              />
            );
          })}
        </g>
        <g className="network-transitions">
          {transitions.map((edge) => {
            const from = byId.get(edge.from);
            const to = byId.get(edge.to);
            if (!from || !to) return null;
            return <path key={edge.id} data-from={from.path} data-to={to.path}
              className={edge.active ? "current" : "visited"}
              d={`M ${from.x} ${from.y} Q ${(from.x + to.x) / 2 + 16} ${(from.y + to.y) / 2 - 18} ${to.x} ${to.y}`}
              markerEnd={edge.active ? `url(#${arrowId})` : undefined}>
              <title>{from.path} → {to.path}</title>
            </path>;
          })}
        </g>
        <g className="network-nodes">
          {nodes.map((node) => {
            const className = [
              node.kind,
              visited.has(node.id) ? "visited" : "",
              frontier.has(node.id) ? "frontier" : "",
              selected.has(node.id) ? "selected" : "",
              current.has(node.id) ? "current" : "",
            ].filter(Boolean).join(" ");
            const showLabel = node.kind === "root" || current.has(node.id) || selected.has(node.id);
            return (
              <g className={className} key={node.id} data-path={node.path} transform={`translate(${node.x} ${node.y})`}>
                <title>{node.path}</title>
                <circle r={node.kind === "root" ? 22 : node.kind === "community" ? 8 : 6} />
                {showLabel ? <text y={node.kind === "root" ? 38 : -13}>{truncate(node.label, 27)}</text>
                  : node.kind === "community" ? <text y={-13}>{node.community?.replace("community_", "")}</text> : null}
              </g>
            );
          })}
        </g>
      </svg>
      <div className="discovery-network-legend" aria-label="Network legend">
        <span className="current">Current hop</span>
        <span className="visited">History</span>
        <span className="frontier">Current frontier</span>
        <span>Unvisited community</span>
      </div>
      <p className="network-scope-note">Communities in full; files expand as encountered. Arrows show tool-focus transitions, not semantic similarity.</p>
    </div>
  );
}

function StageHeader({
  index,
  title,
  framework,
  status,
  count,
  novelty,
}: {
  index: number;
  title: string;
  framework: string;
  status: StageDisplayStatus;
  count: number;
  novelty: string;
}) {
  return (
    <div className="research-stage-intro">
      <div className="research-stage-heading">
        <span className="research-stage-number">{index}</span>
        <div>
          <p>{framework}</p>
          <h3>{title}</h3>
        </div>
        <span className={`research-stage-status ${status}`}>
          {status === "active" ? <span className="live-pulse" aria-hidden="true" /> : null}
          {sentenceCase(status)} · {count}
        </span>
      </div>
      <div className="research-novelty">
        <span>Core mechanism</span>
        <strong>{novelty}</strong>
      </div>
    </div>
  );
}

function StageStats({ children }: { children: React.ReactNode }) {
  return <div className="research-stage-stats">{children}</div>;
}

function StageStat({ value, label }: { value: string | number; label: string }) {
  return (
    <div>
      <strong>{typeof value === "number" ? value.toLocaleString() : value}</strong>
      <span>{label}</span>
    </div>
  );
}

function CandidateRows({ candidates }: { candidates: DiscoveryCandidate[] }) {
  if (candidates.length === 0) return null;
  return (
    <div className="discovery-frontier" aria-label="Discovery frontier">
      <div className="frontier-heading">
        <span>Ranked frontier</span>
        <small>{candidates.length} candidates visible to this hop</small>
      </div>
      <div className="frontier-grid">
        {candidates.slice(0, 5).map((candidate) => (
          <div
            className="frontier-row"
            key={`${candidate.relative_path}-${candidate.asset_id ?? "dir"}`}
          >
            <span className={`frontier-kind ${candidate.kind}`} aria-hidden="true">
              {candidate.kind === "directory" ? "↳" : "▤"}
            </span>
            <span title={candidate.relative_path}>{candidate.relative_path}</span>
            <small>
              {candidate.score !== null ? `score ${candidate.score.toFixed(1)}` : candidate.kind}
              {candidate.file_format ? ` · ${candidate.file_format}` : null}
              {formatBytes(candidate.byte_size) ? ` · ${formatBytes(candidate.byte_size)}` : null}
            </small>
          </div>
        ))}
      </div>
      {candidates.length > 5 ? <small>+ {candidates.length - 5} more candidates</small> : null}
    </div>
  );
}

function DiscoveryView({ run }: ResearchWorkflowPanelProps) {
  const hops = run?.discovery_hops ?? [];
  const [activeHopIndex, setActiveHopIndex] = useState(0);
  const [followHops, setFollowHops] = useState(true);
  const latestSelection = hops.slice(0, activeHopIndex + 1).reverse()
    .find((hop) => hop.action === "select_sources" && hop.status === "accepted");
  const selectedAssetIds = new Set(latestSelection?.selected_asset_ids ?? []);
  const inspected = hops.slice(0, activeHopIndex + 1)
    .filter((hop) => hop.status !== "rejected" && hop.inspected_asset_id !== null).length;
  const selectedAssets = Object.values(run?.assets ?? {}).filter((asset) =>
    selectedAssetIds.has(asset.asset_id),
  );
  useEffect(() => {
    setFollowHops(true);
  }, [run?.run_id]);
  useEffect(() => {
    if (followHops) setActiveHopIndex(Math.max(0, hops.length - 1));
  }, [followHops, hops.length, run?.run_id]);
  function showHop(index: number) {
    setFollowHops(false);
    setActiveHopIndex(index);
  }

  const activeHop = hops[activeHopIndex] ?? null;
  const activeSelectedAssets = activeHop
    ? (activeHop.status === "rejected" ? [] : activeHop.selected_asset_ids.map((assetId) => run?.assets[assetId]).filter(Boolean))
    : [];

  return (
    <section className="research-stage discovery-stage" aria-label="Data discovery workflow">
      <StageHeader
        index={1}
        title="Data discovery"
        framework="CoDA-Bench · path walk"
        status={stageProgress(run, "discovery")}
        count={hops.length}
        novelty="Walks the catalog hop by hop and selects only evidence it actually inspected."
      />

      <StageStats>
        <StageStat value={hops.length ? `${activeHopIndex + 1} / ${hops.length}` : 0} label="navigation hops" />
        <StageStat value={inspected} label="files inspected" />
        <StageStat value={selectedAssetIds.size} label="sources selected" />
      </StageStats>

      <div className="stage-io stage-io-discovery" aria-label="Discovery input and output">
        <article className="stage-io-card input">
          <span>Input · data need</span>
          <strong>{run?.question ?? "Analytical question"}</strong>
          <div className="term-list">
            {(run?.contract?.search_terms ?? activeHop?.query_terms ?? []).slice(0, 8).map((term) => (
              <code key={term}>{term}</code>
            ))}
          </div>
        </article>
        <div className="stage-io-arrow" aria-hidden="true">→</div>
        <article className="stage-io-card output">
          <span>Output · relevant CSV files</span>
          {selectedAssets.length > 0 ? (
            <div className="discovery-output-files">
              {selectedAssets.map((asset) => (
                <div key={asset.asset_id}>
                  <strong>{asset.name}</strong>
                  <small>{asset.row_count?.toLocaleString() ?? "—"} rows · {asset.columns.length} columns</small>
                  <code>{asset.relative_path}</code>
                </div>
              ))}
            </div>
          ) : (
            <p className="stage-output-pending">The selected source set will appear after inspection.</p>
          )}
        </article>
      </div>

      {hops.length === 0 ? (
        <div className="research-empty">
          <strong>Waiting for the first community hop</strong>
          <span>Search, directory traversal, schema inspection, and source selection appear here live.</span>
        </div>
      ) : (
        <div className="discovery-network-workbench">
          <section className="discovery-step-inspector" aria-live="polite">
            <div className="discovery-step-nav">
              <button
                type="button"
                disabled={activeHopIndex === 0}
                onClick={() => showHop(Math.max(0, activeHopIndex - 1))}
                aria-label="Previous discovery hop"
              >
                ←
              </button>
              <div>
                <span>Current hop</span>
                <strong>{activeHopIndex + 1} / {hops.length}</strong>
              </div>
              <button
                type="button"
                disabled={activeHopIndex === hops.length - 1}
                onClick={() => showHop(Math.min(hops.length - 1, activeHopIndex + 1))}
                aria-label="Next discovery hop"
              >
                →
              </button>
            </div>
            <div className="discovery-step-timeline" aria-label="Discovery hop history">
              {hops.map((hop, index) => (
                <button
                  key={hop.hop_id}
                  type="button"
                  className={index === activeHopIndex ? "current" : index < activeHopIndex ? "visited" : ""}
                  aria-label={`Show hop ${index + 1}: ${sentenceCase(hop.action)}`}
                  aria-pressed={index === activeHopIndex}
                  onClick={() => showHop(index)}
                >
                  {index + 1}
                </button>
              ))}
            </div>
            {!followHops && run?.status === "running" ? (
              <button className="follow-live-action" type="button" onClick={() => setFollowHops(true)}>
                Follow latest hop
              </button>
            ) : null}
            {activeHop ? (
              <div className="discovery-step-content">
                <div className="discovery-step-title">
                  <div>
                    <span>{sentenceCase(activeHop.action)}</span>
                    <strong>{shortPath(activeHop.destination ?? activeHop.scope)}</strong>
                  </div>
                  <span className={`trace-state ${activeHop.status}`}>{sentenceCase(activeHop.status)}</span>
                </div>
                <p>{activeHop.summary}</p>
                <dl className="hop-io">
                  <div>
                    <dt>Hop input</dt>
                    <dd>{activeHop.query_terms.length > 0 ? activeHop.query_terms.join(" · ") : activeHop.scope}</dd>
                  </div>
                  <div>
                    <dt>Hop output</dt>
                    <dd>
                      {activeHop.status === "rejected" ? "No output · action rejected" : activeSelectedAssets.length > 0
                        ? `${activeSelectedAssets.length} CSV file(s) selected`
                        : activeHop.inspected_path
                          ? `Schema inspected: ${Object.keys(activeHop.inspected_schema).length} columns`
                          : `${activeHop.candidates.length} candidate node(s)`}
                    </dd>
                  </div>
                </dl>
                {activeHop.query_terms.length > 0 ? (
                  <div className="term-list hop-terms">
                    {activeHop.query_terms.map((term) => <code key={term}>{term}</code>)}
                  </div>
                ) : null}
                <CandidateRows candidates={activeHop.candidates} />
                {activeHop.inspected_path ? (
                  <div className="inspected-schema">
                    <div>
                      <strong>Inspected schema</strong>
                      <code>{activeHop.inspected_path}</code>
                    </div>
                    <SchemaList
                      columns={Object.keys(activeHop.inspected_schema)}
                      schema={activeHop.inspected_schema}
                      limit={9}
                    />
                  </div>
                ) : null}
                {activeSelectedAssets.length > 0 ? (
                  <div className="selected-source-callout">
                    <strong>Selected output</strong>
                    <span>{activeSelectedAssets.map((asset) => asset?.name).join(" · ")}</span>
                  </div>
                ) : null}
                {activeHop.error ? (
                  <details className="inline-debug" open>
                    <summary>Rejected tool feedback</summary>
                    <pre>{activeHop.error}</pre>
                  </details>
                ) : null}
              </div>
            ) : null}
          </section>
          <DiscoveryNetwork hops={hops} activeIndex={activeHopIndex} />
        </div>
      )}
    </section>
  );
}

interface PreparationTreeNode {
  id: string;
  signature: string;
  operator: PreparationOperatorTrace;
  children: PreparationTreeNode[];
  attemptIds: Set<string>;
  turns: Set<number>;
  statuses: Set<PreparationAttempt["status"]>;
  selectedPath: boolean;
}

interface PreparationTree {
  roots: PreparationTreeNode[];
  nodes: Map<string, PreparationTreeNode>;
  selectedLeafId: string | null;
}

function stableJson(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(stableJson).join(",")}]`;
  if (value && typeof value === "object") {
    return `{${Object.entries(value as Record<string, unknown>)
      .sort(([left], [right]) => left.localeCompare(right))
      .map(([key, item]) => `${JSON.stringify(key)}:${stableJson(item)}`)
      .join(",")}}`;
  }
  return JSON.stringify(value);
}

function operatorSignature(operator: PreparationOperatorTrace) {
  return stableJson({
    type: operator.operator_type,
    inputs: operator.input_tables,
    output: operator.output_table,
    parameters: operator.parameters,
  });
}

function buildPreparationTree(attempts: PreparationAttempt[]): PreparationTree {
  const roots: PreparationTreeNode[] = [];
  const nodes = new Map<string, PreparationTreeNode>();
  let selectedLeafId: string | null = null;
  const chosenAttempt = [...attempts].reverse().find((attempt) => attempt.status === "selected");

  for (const attempt of attempts) {
    let siblings = roots;
    let leaf: PreparationTreeNode | null = null;
    for (const operator of attempt.operators) {
      const signature = operatorSignature(operator);
      let node = siblings.find((candidate) => candidate.signature === signature);
      if (!node) {
        node = {
          id: operator.operator_id,
          signature,
          operator,
          children: [],
          attemptIds: new Set(),
          turns: new Set(),
          statuses: new Set(),
          selectedPath: false,
        };
        siblings.push(node);
        nodes.set(node.id, node);
      }
      node.attemptIds.add(attempt.attempt_id);
      node.turns.add(attempt.turn);
      node.statuses.add(attempt.status);
      if (!node.selectedPath) node.operator = operator;
      if (attempt.attempt_id === chosenAttempt?.attempt_id) {
        node.selectedPath = true;
        node.operator = operator;
      }
      leaf = node;
      siblings = node.children;
    }
    if (attempt.attempt_id === chosenAttempt?.attempt_id && leaf) selectedLeafId = leaf.id;
  }

  return { roots, nodes, selectedLeafId };
}

function operatorRowDelta(operator: PreparationOperatorTrace) {
  const input = operator.input_rows[0];
  if (input === undefined || operator.output_rows === null) return null;
  return `${input.toLocaleString()} → ${operator.output_rows.toLocaleString()} rows`;
}

function PreparationTreeBranch({
  node,
  selectedNodeId,
  onSelect,
}: {
  node: PreparationTreeNode;
  selectedNodeId: string | null;
  onSelect: (nodeId: string) => void;
}) {
  const rejectedOnly = node.statuses.size === 1 && node.statuses.has("rejected");
  const stateClass = node.selectedPath ? "solution" : rejectedOnly ? "rejected" : "explored";
  return (
    <li>
      <button
        className={`prep-tree-node ${stateClass} ${selectedNodeId === node.id ? "selected" : ""}`}
        type="button"
        aria-pressed={selectedNodeId === node.id}
        onClick={() => onSelect(node.id)}
      >
        <span className={`operator-family-dot ${node.operator.operator_family}`} aria-hidden="true" />
        <span>
          <strong>{node.operator.operator_type}</strong>
          <small>{node.operator.output_table}</small>
        </span>
        <span className="tree-node-turns">
          {node.selectedPath ? "Final path" : `Turn ${[...node.turns].join(", ")}`}
        </span>
      </button>
      {node.children.length > 0 ? (
        <ul>
          {node.children.map((child) => (
            <PreparationTreeBranch
              key={child.id}
              node={child}
              selectedNodeId={selectedNodeId}
              onSelect={onSelect}
            />
          ))}
        </ul>
      ) : null}
    </li>
  );
}

function OperatorInspector({ node }: { node: PreparationTreeNode | null }) {
  if (!node) {
    return (
      <div className="operator-inspector empty">
        <strong>Select an operator node</strong>
        <p>Its external execution observation, tables, row counts, and bounded arguments appear here.</p>
      </div>
    );
  }
  const operator = node.operator;
  return (
    <aside className="operator-inspector" aria-live="polite">
      <div className="operator-inspector-heading">
        <div>
          <span>Selected operator</span>
          <h4>{operator.operator_type}</h4>
        </div>
        <span className={`operator-family-label ${operator.operator_family}`}>
          {sentenceCase(operator.operator_family)}
        </span>
      </div>
      <p>{operator.summary}</p>
      <dl className="operator-shape">
        <div>
          <dt>Input table</dt>
          <dd>{operator.input_tables.join(" + ") || "—"}</dd>
        </div>
        <div>
          <dt>Output table</dt>
          <dd>{operator.output_table}</dd>
        </div>
        <div>
          <dt>Observed shape</dt>
          <dd>{operatorRowDelta(operator) ?? `${operator.output_columns.length} columns`}</dd>
        </div>
        <div>
          <dt>Explored in</dt>
          <dd>Turn {[...node.turns].join(", ")}</dd>
        </div>
      </dl>
      {operator.added_columns.length > 0 || operator.removed_columns.length > 0 ? (
        <div className="schema-delta">
          {operator.added_columns.length > 0 ? (
            <span>+ {operator.added_columns.join(", ")}</span>
          ) : null}
          {operator.removed_columns.length > 0 ? (
            <span>− {operator.removed_columns.join(", ")}</span>
          ) : null}
        </div>
      ) : null}
      <details className="operator-parameters">
        <summary>Bounded operator arguments</summary>
        <pre>{renderJson(operator.parameters)}</pre>
      </details>
    </aside>
  );
}

function PreparationView({ run }: ResearchWorkflowPanelProps) {
  const attempts = run?.preparation_attempts ?? [];
  const tree = useMemo(() => buildPreparationTree(attempts), [attempts]);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const selectedAttempt = [...attempts].reverse().find((attempt) => attempt.status === "selected") ?? null;
  const rejectedCount = attempts.filter((attempt) => attempt.status === "rejected").length;
  const sourceAliases = [...new Set(attempts.flatMap((attempt) => attempt.source_aliases))];
  const selectedState = selectedAttempt?.state_id
    ? (run?.materialized_states.find((state) => state.state_id === selectedAttempt.state_id) ?? null)
    : (run?.materialized_states.at(-1) ?? null);
  const latestDecision = run?.source_decisions.at(-1) ?? null;
  const inputAssetIds = selectedState?.source_ids ?? latestDecision?.selected_source_ids ?? [];
  const inputAssets = inputAssetIds.map((assetId) => run?.assets[assetId]).filter(Boolean);
  const inspectedSchemas = new Map(
    (run?.discovery_hops ?? [])
      .filter((hop) => hop.inspected_asset_id)
      .map((hop) => [hop.inspected_asset_id as string, hop.inspected_schema]),
  );
  const inputColumns = new Set(inputAssets.flatMap((asset) => asset?.columns ?? []));
  const addedColumns = selectedState?.columns.filter((column) => !inputColumns.has(column)) ?? [];
  const removedColumns = [...inputColumns].filter((column) => selectedState && !selectedState.columns.includes(column));
  const typeDifferences = (selectedState?.columns ?? []).flatMap((column) => {
    const inputTypes = [...new Set(inputAssets.flatMap((asset) => {
      const type = asset ? inspectedSchemas.get(asset.asset_id)?.[column] : undefined;
      return type ? [type] : [];
    }))];
    const outputType = selectedState?.schema[column];
    return outputType && inputTypes.some((type) => type !== outputType)
      ? [{ column, inputTypes, outputType }] : [];
  });

  useEffect(() => {
    if (tree.selectedLeafId && selectedNodeId === null) setSelectedNodeId(tree.selectedLeafId);
    if (selectedNodeId && !tree.nodes.has(selectedNodeId)) setSelectedNodeId(tree.selectedLeafId);
  }, [selectedNodeId, tree]);

  const selectedNode = selectedNodeId ? (tree.nodes.get(selectedNodeId) ?? null) : null;

  return (
    <section className="research-stage preparation-stage" aria-label="Data preparation workflow">
      <StageHeader
        index={2}
        title="Data preparation"
        framework="DeepPrep · Tree-based Agentic Reasoning"
        status={stageProgress(run, "preparation")}
        count={attempts.length}
        novelty="Executes candidate operator paths, observes results, and backtracks from bad branches."
      />

      <StageStats>
        <StageStat value={attempts.length} label="candidate branches" />
        <StageStat value={tree.nodes.size} label="unique operator nodes" />
        <StageStat value={rejectedCount} label="branches rejected" />
      </StageStats>

      <div className="stage-io prep-data-io" aria-label="Preparation input and output">
        <article className="stage-io-card input prep-input-data">
          <span>Input · discovered CSV schemas</span>
          {inputAssets.length > 0 ? (
            <div className="prep-input-sources">
              {inputAssets.map((asset) => asset ? (
                <section key={asset.asset_id}>
                  <div>
                    <strong>{asset.name}</strong>
                    <small>{asset.row_count?.toLocaleString() ?? "—"} rows · {asset.columns.length} columns</small>
                  </div>
                  <SchemaList
                    columns={asset.columns}
                    schema={inspectedSchemas.get(asset.asset_id)}
                    limit={8}
                  />
                </section>
              ) : null)}
            </div>
          ) : (
            <p className="stage-output-pending">Waiting for Discovery to select input files.</p>
          )}
        </article>
        <div className="prep-transform-bridge" aria-label="Selected preparation operators">
          <span>Selected operator path</span>
          {selectedAttempt?.operators.map((operator, index) => (
            <div key={operator.operator_id}>
              <i>{index + 1}</i>
              <strong>{operator.operator_type}</strong>
            </div>
          )) ?? <small>Waiting for tree search</small>}
        </div>
        <article className="stage-io-card output prep-output-data">
          <span>{selectedAttempt ? "Output · analysis-ready table" : "Candidate preview · not yet selected"}</span>
          <strong>{selectedAttempt?.output_table ?? "Prepared dataset"}</strong>
          <PreparedTablePreview state={selectedState} />
          {selectedState && inputAssets.length > 0 ? (
            <details className="schema-change-details">
              <summary>Schema changes · {addedColumns.length} added · {removedColumns.length} removed · {typeDifferences.length} type differences</summary>
              <p>Compares input field names and recorded types with the output, not field-level lineage. Type labels may differ between runtimes.</p>
              {addedColumns.length > 0 ? <div><strong>Added / renamed</strong><SchemaList columns={addedColumns} schema={selectedState.schema} /></div> : null}
              {removedColumns.length > 0 ? <div><strong>Removed / renamed</strong><SchemaList columns={removedColumns} /></div> : null}
              {typeDifferences.length > 0 ? (
                <div>
                  <strong>Recorded types · input → output</strong>
                  <div className="stage-schema-list">
                    {typeDifferences.map(({ column, inputTypes, outputType }) => (
                      <span key={column} title={column}>
                        <strong>{column}</strong>
                        <small>{inputTypes.join(" / ")} → {outputType}</small>
                      </span>
                    ))}
                  </div>
                </div>
              ) : null}
            </details>
          ) : null}
        </article>
      </div>

      {attempts.length === 0 ? (
        <div className="research-empty">
          <strong>Waiting for the first operator branch</strong>
          <span>Executed candidate paths will merge into a shared-prefix tree here.</span>
        </div>
      ) : (
        <>
          <div className="prep-tree-workbench">
            <div className="prep-tree-board">
              <div className="prep-tree-board-heading">
                <div>
                  <span>Operator tree</span>
                  <strong>Shared prefixes are drawn once</strong>
                </div>
                <div className="prep-tree-legend" aria-label="Operator tree legend">
                  <span className="solution">Final path</span>
                  <span className="explored">Explored</span>
                  <span className="rejected">Rejected</span>
                </div>
              </div>
              <div className="prep-tree-scroll">
                <ul className="prep-operator-tree">
                  <li className="prep-root-item">
                    <div className="prep-source-node">
                      <span>Root</span>
                      <strong>{sourceAliases.join(" + ") || "Selected source tables"}</strong>
                      <small>Every exploration starts from the authorized inputs</small>
                    </div>
                    {tree.roots.length > 0 ? (
                      <ul>
                        {tree.roots.map((node) => (
                          <PreparationTreeBranch
                            key={node.id}
                            node={node}
                            selectedNodeId={selectedNodeId}
                            onSelect={setSelectedNodeId}
                          />
                        ))}
                      </ul>
                    ) : null}
                  </li>
                </ul>
              </div>
            </div>
            <OperatorInspector node={selectedNode} />
          </div>

          <details className="prep-exploration-ledger">
            <summary className="ledger-heading">
              <div>
                <span>Search history</span>
                <strong>{attempts.length} attempts with observations</strong>
              </div>
              <small>View branches</small>
            </summary>
            <div className="prep-ledger-body">
              <ol>
                {attempts.map((attempt) => (
                  <li className={`prep-turn-card ${attempt.status}`} key={attempt.attempt_id}>
                    <div className="prep-turn-index">{String(attempt.turn).padStart(2, "0")}</div>
                    <div className="prep-turn-content">
                      <div className="prep-turn-heading">
                        <div>
                          <span>Exploration {attempt.turn}</span>
                          <strong>{attempt.candidate_id ?? "Rejected before execution"}</strong>
                        </div>
                        <span className={`branch-status ${attempt.status}`}>
                          {sentenceCase(attempt.status)}
                        </span>
                      </div>
                      <p>{attempt.reason}</p>
                      <div className="branch-parent">
                        {attempt.parent_candidate_id
                          ? `Backtrack / expand from ${attempt.parent_candidate_id}`
                          : "Expand from the original source tables"}
                      </div>
                      {attempt.operators.length > 0 ? (
                        <div className="ledger-operator-chain">
                          {attempt.operators.map((operator, index) => (
                            <span key={operator.operator_id}>
                              {index > 0 ? <i aria-hidden="true">→</i> : null}
                              {operator.operator_type}
                            </span>
                          ))}
                        </div>
                      ) : null}
                      <div className="branch-observation">
                        <strong>Executor observation</strong>
                        <span>{attempt.observation}</span>
                      </div>
                      {attempt.error ? (
                        <details className="inline-debug">
                          <summary>Rejection feedback</summary>
                          <pre>{attempt.error}</pre>
                        </details>
                      ) : null}
                    </div>
                  </li>
                ))}
              </ol>
            </div>
          </details>
        </>
      )}
    </section>
  );
}

function NotebookOutput({ step }: { step: AnalysisNotebookStep }) {
  if (step.output === null || step.output === undefined) return null;
  if (step.phase === "answer" && Array.isArray(step.output)) {
    return (
      <div className="notebook-output answer-output">
        <span>Accepted findings</span>
        <div>
          <strong>{step.output.length} evidence-linked findings passed the release gate</strong>
          <p>The readable findings, charts, and computed tables are assembled in the final report below.</p>
          <details>
            <summary>Inspect persisted claim payloads</summary>
            <pre>{renderJson(step.output)}</pre>
          </details>
        </div>
      </div>
    );
  }
  if (step.phase === "report" && typeof step.output === "object" && !Array.isArray(step.output)) {
    const output = step.output as Record<string, unknown>;
    const sections = Array.isArray(output.sections) ? output.sections : [];
    const limitations = Array.isArray(output.limitations) ? output.limitations : [];
    return (
      <div className="notebook-output report-output">
        <span>Generated report</span>
        <div>
          <strong>{String(output.title ?? "Analysis report")}</strong>
          <p>{String(output.executive_summary ?? "Evidence-grounded report released.")}</p>
          {sections.length > 0 ? (
            <div className="report-output-sections">
              {sections.slice(0, 6).map((section, index) => {
                const block = typeof section === "object" && section !== null
                  ? section as Record<string, unknown>
                  : {};
                return (
                  <section key={`${String(block.title ?? "section")}-${index}`}>
                    <strong>{String(block.title ?? `Section ${index + 1}`)}</strong>
                    <p>{String(block.narrative ?? "")}</p>
                  </section>
                );
              })}
            </div>
          ) : null}
          {output.conclusion ? (
            <div className="report-output-conclusion">
              <span>Integrated conclusion</span>
              <p>{String(output.conclusion)}</p>
            </div>
          ) : null}
          {limitations.length > 0 ? (
            <small>{limitations.length} scope limitation{limitations.length === 1 ? "" : "s"} recorded</small>
          ) : null}
        </div>
      </div>
    );
  }
  return (
    <div className="notebook-output">
      <span>Execution output</span>
      <StructuredDataView value={step.output} maxRows={10} compact />
    </div>
  );
}

function AnalysisView({ run }: ResearchWorkflowPanelProps) {
  const steps = run?.analysis_notebook ?? [];
  const executed = steps.filter((step) => step.phase === "execute" && step.status === "completed");
  const debugged = steps.filter((step) => step.phase === "debug").length;
  const consumedStateId = [...steps].reverse().find((step) =>
    step.status === "completed" && (step.phase === "execute" || step.phase === "understand") && step.state_refs.length > 0,
  )?.state_refs[0];
  const selectedStateId = [...(run?.preparation_attempts ?? [])].reverse()
    .find((attempt) => attempt.status === "selected")?.state_id;
  const inputState = run?.materialized_states.find((state) => state.state_id === (consumedStateId ?? selectedStateId)) ?? null;
  const report = run?.report ?? null;

  return (
    <section className="research-stage analysis-stage" aria-label="Data analysis workflow">
      <StageHeader
        index={3}
        title="Data analysis"
        framework="DeepAnalyze · agentic notebook loop"
        status={stageProgress(run, "analysis")}
        count={steps.length}
        novelty="Writes and executes SQL or Python, keeps debug feedback, then grounds the report."
      />

      <StageStats>
        <StageStat value={steps.length} label="notebook steps" />
        <StageStat value={executed.length} label="analyses executed" />
        <StageStat value={debugged} label="debug retries" />
      </StageStats>

      <div className="stage-io analysis-data-io" aria-label="Analysis input and output">
        <article className="stage-io-card input analysis-input-data">
          <span>Input · prepared dataset</span>
          <PreparedTablePreview state={inputState} />
        </article>
        <div className="stage-io-arrow" aria-hidden="true">→</div>
        <article className="stage-io-card output analysis-report-card">
          <span>Output · decision-ready report</span>
          {report ? (
            <>
              <strong>{report.title}</strong>
              <p>{report.executive_summary || report.claims[0]?.text}</p>
              {report.sections.length > 0 ? (
                <div className="analysis-report-dimensions">
                  {report.sections.slice(0, 6).map((section, index) => (
                    <span key={`${section.title}-${index}`}>{section.title}</span>
                  ))}
                </div>
              ) : null}
              {report.conclusion ? (
                <div className="analysis-integrated-conclusion">
                  <span>Integrated conclusion</span>
                  <p>{report.conclusion}</p>
                </div>
              ) : null}
              <a href="#final-report">Open the complete report ↑</a>
            </>
          ) : (
            <p className="stage-output-pending">
              The report appears after every executed finding passes the evidence gate.
            </p>
          )}
        </article>
      </div>

      {steps.length === 0 ? (
        <div className="research-empty">
          <strong>Waiting for the analysis notebook</strong>
          <span>Code, execution, debug feedback, accepted answers, and report release appear here live.</span>
        </div>
      ) : (
        <ol className="analysis-notebook" aria-label="DeepAnalyze-style execution notebook">
          {steps.map((step) => (
            <li className={`notebook-cell ${step.phase} ${step.status}`} key={step.step_id}>
              <div className="notebook-gutter">
                <span>{String(step.sequence).padStart(2, "0")}</span>
                <i aria-hidden="true" />
              </div>
              <article>
                <div className="notebook-cell-heading">
                  <span className={`notebook-phase ${step.phase}`}>{sentenceCase(step.phase)}</span>
                  <strong>{step.title.split(" · ").at(-1)}</strong>
                  <span className={`notebook-status ${step.status}`}>{sentenceCase(step.status)}</span>
                  {step.runtime ? (
                    <small>
                      {sentenceCase(step.runtime)}
                      {step.duration_ms !== null ? ` · ${step.duration_ms.toFixed(1)} ms` : ""}
                    </small>
                  ) : null}
                </div>
                <p>{step.summary}</p>
                {step.source_code ||
                Object.keys(step.parameters).length > 0 ||
                (step.output !== null && step.output !== undefined) ||
                step.artifact_refs.length > 0 ? (
                  <details
                    className="notebook-cell-details"
                    open={step.phase === "debug" || step.phase === "report"}
                  >
                    <summary>
                      {step.source_code ? `View ${step.language} and output` : "View execution details"}
                    </summary>
                    {step.source_code ? (
                      <div className="notebook-code-wrap">
                        <div>
                          <span>{step.language}</span>
                          <small>Bounded execution</small>
                        </div>
                        <pre className={`source-cell language-${step.language}`}>
                          <code>{step.source_code}</code>
                        </pre>
                      </div>
                    ) : null}
                    {Object.keys(step.parameters).length > 0 ? (
                      <details className="cell-parameters">
                        <summary>Bound parameters</summary>
                        <pre>{renderJson(step.parameters)}</pre>
                      </details>
                    ) : null}
                    <NotebookOutput step={step} />
                    {step.artifact_refs.length > 0 ? (
                      <div className="cell-lineage">
                        <span>✓</span>
                        {step.artifact_refs.length} artifact link
                        {step.artifact_refs.length === 1 ? "" : "s"} · {step.evidence_refs.length}{" "}
                        evidence link{step.evidence_refs.length === 1 ? "" : "s"}
                      </div>
                    ) : null}
                  </details>
                ) : null}
              </article>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}

export function ResearchWorkflowPanel({ run }: ResearchWorkflowPanelProps) {
  const [selectedStage, setSelectedStage] = useState<WorkbenchStage>("discovery");
  const [followLive, setFollowLive] = useState(true);
  const previousRunId = useRef<string | null>(null);
  const liveStage = activeWorkbenchStage(run);

  useEffect(() => {
    const runId = run?.run_id ?? null;
    if (runId !== previousRunId.current) {
      previousRunId.current = runId;
      setFollowLive(true);
      setSelectedStage(activeWorkbenchStage(run));
      return;
    }
    if (followLive && (run?.status === "pending" || run?.status === "running")) {
      setSelectedStage(liveStage);
    }
  }, [followLive, liveStage, run]);

  function selectStage(stage: WorkbenchStage) {
    setFollowLive(false);
    setSelectedStage(stage);
  }

  return (
    <section
      className="research-workflow"
      data-testid="research-workflow"
      aria-labelledby="research-workflow-title"
    >
      <div className="research-workflow-heading">
        <div>
          <p className="eyebrow">Automatic workflow</p>
          <h2 id="research-workflow-title">How the answer was produced</h2>
        </div>
        <p className="workflow-question">{run?.question}</p>
      </div>

      <div className="research-stage-switcher" role="tablist" aria-label="Agent workflow stages">
        {stageMetadata.map((stage) => {
          const status = stageProgress(run, stage.id);
          const selected = selectedStage === stage.id;
          return (
            <button
              key={stage.id}
              id={`workflow-tab-${stage.id}`}
              className={`${stage.id} ${selected ? "selected" : ""} ${status}`}
              type="button"
              role="tab"
              aria-selected={selected}
              aria-controls={`workflow-panel-${stage.id}`}
              tabIndex={selected ? 0 : -1}
              onClick={() => selectStage(stage.id)}
            >
              <span className="stage-switch-index">
                {status === "complete" ? "✓" : String(stage.index).padStart(2, "0")}
              </span>
              <span>
                <small>{stage.paper}</small>
                <strong>{stage.title}</strong>
              </span>
              <span className={`stage-switch-state ${status}`}>
                {status === "active" ? <i className="live-pulse" aria-hidden="true" /> : null}
                {stageCount(run, stage.id)}
              </span>
            </button>
          );
        })}
        <div className={`report-stage-marker ${run?.report ? "complete" : "waiting"}`}>
          <span>{run?.report ? "✓" : "04"}</span>
          <div>
            <small>Output</small>
            <strong>Report</strong>
          </div>
        </div>
      </div>

      {(run?.status === "pending" || run?.status === "running") && !followLive ? (
        <button
          className="follow-live-action"
          type="button"
          onClick={() => {
            setFollowLive(true);
            setSelectedStage(liveStage);
          }}
        >
          <span className="live-pulse" aria-hidden="true" /> Follow the live agent
        </button>
      ) : null}

      <div className="research-stage-viewport">
        <div
          id={`workflow-panel-${selectedStage}`}
          role="tabpanel"
          aria-labelledby={`workflow-tab-${selectedStage}`}
        >
          {selectedStage === "discovery" ? <DiscoveryView run={run} /> : null}
          {selectedStage === "preparation" ? <PreparationView run={run} /> : null}
          {selectedStage === "analysis" ? <AnalysisView run={run} /> : null}
        </div>
      </div>
    </section>
  );
}
