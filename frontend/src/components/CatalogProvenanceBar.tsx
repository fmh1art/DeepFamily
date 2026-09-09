import type { CatalogProvenance, EnvironmentSummary } from "../types";

interface CatalogProvenanceBarProps {
  provenance: CatalogProvenance | null;
  assetCount: number;
  releaseCoverage: EnvironmentSummary["release_coverage"];
}

function shortDigest(value: string) {
  return `${value.slice(0, 12)}…`;
}

export function CatalogProvenanceBar({
  provenance,
  assetCount,
  releaseCoverage,
}: CatalogProvenanceBarProps) {
  if (releaseCoverage) {
    return (
      <aside className="catalog-provenance" data-testid="catalog-provenance">
        <div>
          <span className="catalog-proof-label">
            <span className="paper-callout" aria-hidden="true">
              A
            </span>
            Pinned open release
          </span>
          <strong>CoDA-Bench · federated question-only pool</strong>
        </div>
        <dl>
          <div>
            <dt>Revision</dt>
            <dd title={releaseCoverage.revision}>{shortDigest(releaseCoverage.revision)}</dd>
          </div>
          <div>
            <dt>Open communities</dt>
            <dd
              className={
                releaseCoverage.installed_open_communities ===
                releaseCoverage.open_runtime_communities
                  ? "matched"
                  : "mismatched"
              }
            >
              {releaseCoverage.installed_open_communities} /{" "}
              {releaseCoverage.open_runtime_communities}
            </dd>
          </div>
          <div>
            <dt>Discoverable files</dt>
            <dd>{assetCount.toLocaleString()} · external, download-only</dd>
          </div>
        </dl>
        <span>
          {releaseCoverage.open_runtime_tasks} open-runtime tasks ·{" "}
          {releaseCoverage.source_datasets} source datasets ·{" "}
          {releaseCoverage.sealed_evaluation_communities} sealed community
        </span>
      </aside>
    );
  }
  if (!provenance) {
    return (
      <aside className="catalog-provenance unregistered" data-testid="catalog-provenance">
        <div>
          <span className="catalog-proof-label">
            <span className="paper-callout" aria-hidden="true">
              A
            </span>
            Catalog provenance
          </span>
          <strong>Unregistered environment</strong>
        </div>
        <p>No license is inferred. Register source metadata before publishing its reports.</p>
      </aside>
    );
  }

  return (
    <aside className="catalog-provenance" data-testid="catalog-provenance">
      <div>
        <span className="catalog-proof-label">
          <span className="paper-callout" aria-hidden="true">
            A
          </span>
          Pinned catalog
        </span>
        <strong>
          {provenance.benchmark_name} · community {provenance.community_id}
        </strong>
      </div>
      <dl>
        <div>
          <dt>Revision</dt>
          <dd title={provenance.revision}>{shortDigest(provenance.revision)}</dd>
        </div>
        <div>
          <dt>Archive SHA-256</dt>
          <dd title={provenance.archive_sha256}>{shortDigest(provenance.archive_sha256)}</dd>
        </div>
        <div>
          <dt>Registered CSVs</dt>
          <dd className={assetCount === provenance.csv_asset_count ? "matched" : "mismatched"}>
            {assetCount} / {provenance.csv_asset_count} · external, download-only
          </dd>
        </div>
      </dl>
      <a href={provenance.benchmark_url} target="_blank" rel="noreferrer">
        Upstream benchmark ↗
      </a>
    </aside>
  );
}
