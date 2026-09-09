interface StructuredDataViewProps {
  value: unknown;
  maxRows?: number;
  precision?: number | null;
  compact?: boolean;
}

export type ResultRecord = Record<string, unknown>;

export function isResultRecord(value: unknown): value is ResultRecord {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export function asResultRecords(value: unknown): ResultRecord[] | null {
  if (!Array.isArray(value) || value.length === 0 || !value.every(isResultRecord)) return null;
  return value;
}

export function humanizeIdentifier(value: string): string {
  const spaced = value.replaceAll("_", " ").replace(/([a-z])([A-Z])/g, "$1 $2").trim();
  if (!spaced) return "Result";
  return `${spaced.charAt(0).toUpperCase()}${spaced.slice(1)}`;
}

export function formatResultValue(value: unknown, precision: number | null = null): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "number") {
    if (!Number.isFinite(value)) return String(value);
    if (Number.isInteger(value)) return value.toLocaleString("en-US");
    return value.toLocaleString("en-US", {
      maximumFractionDigits: precision ?? 6,
      minimumFractionDigits: precision ?? 0,
    });
  }
  if (typeof value === "boolean") return value ? "True" : "False";
  if (typeof value === "string") return value;
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}

function recordColumns(records: ResultRecord[]): string[] {
  const seen = new Set<string>();
  for (const record of records) {
    for (const key of Object.keys(record)) seen.add(key);
  }
  return [...seen];
}

export function StructuredDataView({
  value,
  maxRows = 10,
  precision = null,
  compact = false,
}: StructuredDataViewProps) {
  const records = asResultRecords(value);
  if (records) {
    const columns = recordColumns(records);
    const visibleRows = records.slice(0, maxRows);
    return (
      <div className={compact ? "structured-table compact" : "structured-table"}>
        <table>
          <thead>
            <tr>
              {columns.map((column) => (
                <th key={column} scope="col">
                  {humanizeIdentifier(column)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {visibleRows.map((record, rowIndex) => (
              <tr key={rowIndex}>
                {columns.map((column) => (
                  <td key={column}>{formatResultValue(record[column], precision)}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
        {records.length > visibleRows.length ? (
          <p className="structured-remainder">
            Showing {visibleRows.length} of {records.length} returned rows
          </p>
        ) : null}
      </div>
    );
  }

  if (Array.isArray(value)) {
    return (
      <div className="structured-list">
        {value.slice(0, maxRows).map((item, index) => (
          <span key={`${formatResultValue(item)}-${index}`}>{formatResultValue(item, precision)}</span>
        ))}
        {value.length > maxRows ? <small>+{value.length - maxRows} more</small> : null}
      </div>
    );
  }

  if (isResultRecord(value)) {
    return (
      <dl className="structured-object">
        {Object.entries(value).map(([key, item]) => (
          <div key={key}>
            <dt>{humanizeIdentifier(key)}</dt>
            <dd>{formatResultValue(item, precision)}</dd>
          </div>
        ))}
      </dl>
    );
  }

  return <strong className="structured-scalar">{formatResultValue(value, precision)}</strong>;
}
