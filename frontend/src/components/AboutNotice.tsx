const inventoryPath = "/notices/dependency-license-inventory-v0.4.0.json";

export function AboutNotice() {
  return (
    <details className="about-notice" id="about" data-testid="about-notice">
      <summary>
        <span>
          <strong>Data &amp; software notice</strong>
          <small>External data stays server-side · research preview</small>
        </span>
        <span aria-hidden="true">+</span>
      </summary>
      <div className="about-notice-body">
        <div className="about-heading">
          <div>
            <p className="eyebrow">Transparency boundary</p>
            <h2>Data &amp; software notice</h2>
          </div>
          <span className="release-state">Research preview · code license pending</span>
        </div>

        <p className="about-lead">
          This prototype analyzes authorized server-side data. It exposes provenance, not raw-data
          download routes, and does not grant reuse rights for project code or third-party data.
        </p>

        <div className="notice-grid">
          <article>
            <h3>Project code</h3>
            <p>A root license must be selected before a public source release.</p>
          </article>
          <article>
            <h3>External evidence</h3>
            <p>Source bytes stay server-side; reports expose origins and verified digests.</p>
          </article>
          <article>
            <h3>Dependencies</h3>
            <p>
              License metadata covers 45 Python and three shipped Web dependencies; container
              packages remain subject to final legal review.
            </p>
          </article>
        </div>

        <nav className="notice-links" aria-label="Transparency records">
          <a href={inventoryPath} target="_blank" rel="noreferrer">
            Dependency inventory ↗
          </a>
          <a href="/api/v1/environments/current" target="_blank" rel="noreferrer">
            Environment provenance ↗
          </a>
        </nav>
      </div>
    </details>
  );
}
