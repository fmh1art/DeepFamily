import type { DataAsset, MaterializedState, SourceDecision } from "../types";

interface SourcesPanelProps {
  assets: Record<string, DataAsset>;
  decisions: SourceDecision[];
  states: MaterializedState[];
}

function formatBytes(bytes: number) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KiB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MiB`;
}

export function SourcesPanel({ assets, decisions, states }: SourcesPanelProps) {
  const latestState = states.at(-1);
  const joinCoverage = latestState?.metrics.join_coverage;
  const selectedAssets = decisions.flatMap((decision) =>
    decision.newly_selected_source_ids.map((assetId) => ({
      asset: assets[assetId],
      decision,
    })),
  );

  return (
    <section className="panel sources-panel" aria-labelledby="sources-title">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">
            <span className="paper-callout" aria-hidden="true">
              B
            </span>
            Progressive discovery
          </p>
          <h2 id="sources-title">Selected evidence</h2>
        </div>
        {decisions.length > 0 && (
          <span className="count-badge">
            <span aria-hidden="true">{decisions.length}</span>
            <span className="sr-only">{decisions.length} source decisions</span>
          </span>
        )}
      </div>

      {decisions.length === 0 ? (
        <div className="empty-state">
          No dataset is supplied with the task. The system will inspect the authorized environment
          on demand.
        </div>
      ) : (
        <div
          className="source-list"
          role="region"
          tabIndex={0}
          aria-label="Selected evidence sources"
        >
          {selectedAssets.map(({ asset, decision }, sourceIndex) => {
            const provenance = asset?.provenance;
            return (
              <article className="source-card" key={`${decision.decision_id}-${asset?.asset_id}`}>
                <div className="source-step">Decision {decision.iteration + 1}</div>
                <h3>{asset?.name ?? "Unknown source"}</h3>
                {provenance && <p className="source-title">{provenance.title}</p>}
                <p className="source-path">{asset?.relative_path}</p>
                <dl>
                  <div>
                    <dt>Rows</dt>
                    <dd>{asset?.row_count?.toLocaleString() ?? "—"}</dd>
                  </div>
                  <div>
                    <dt>Columns</dt>
                    <dd>{asset?.columns.length ?? "—"}</dd>
                  </div>
                  <div>
                    <dt>Size</dt>
                    <dd>{asset ? formatBytes(asset.byte_size) : "—"}</dd>
                  </div>
                </dl>
                {asset?.sha256 && (
                  <p className="source-digest" title={asset.sha256}>
                    SHA-256 {asset.sha256.slice(0, 12)}…
                  </p>
                )}
                {provenance ? (
                  <div className="source-provenance" data-testid={`source-provenance-${sourceIndex}`}>
                    <div className="provenance-badges">
                      <span className={provenance.license_status}>
                        {provenance.license_status === "declared"
                          ? `Metadata · ${provenance.license_label}`
                          : "License unknown"}
                      </span>
                      <span>Download-only</span>
                      <span className={asset.integrity_status}>
                        Integrity {asset.integrity_status}
                      </span>
                    </div>
                    <p>
                      {provenance.provider} · {provenance.creator}
                    </p>
                    <div className="provenance-links">
                      <a href={provenance.source_url} target="_blank" rel="noreferrer">
                        Upstream record ↗
                      </a>
                      {provenance.license_url && (
                        <a href={provenance.license_url} target="_blank" rel="noreferrer">
                          License text ↗
                        </a>
                      )}
                    </div>
                  </div>
                ) : (
                  <div className="source-provenance unknown">
                    Provenance unregistered · no license inferred
                  </div>
                )}
                {decision.trigger_violation_id && (
                  <span className="repair-trigger">Added by downstream repair</span>
                )}
              </article>
            );
          })}
        </div>
      )}

      {latestState && (
        <div className="state-summary">
          <div>
            <span>Materialized rows</span>
            <strong>{latestState.row_count.toLocaleString()}</strong>
          </div>
          <div>
            <span>Join coverage</span>
            <strong>
              {typeof joinCoverage === "number" ? `${(joinCoverage * 100).toFixed(1)}%` : "—"}
            </strong>
          </div>
        </div>
      )}
    </section>
  );
}
