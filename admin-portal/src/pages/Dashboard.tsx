import { AuditLog, Authority, PublicKey, SignedDocument } from "../api/client";

function Metric({ value, label, loading }: { value: number; label: string; loading: boolean }) {
  return (
    <div className="metric">
      {/* A zero while data is still in flight reads as "nothing here" rather
          than "not counted yet", which is alarming on a first load. */}
      <span className={loading ? "metric-pending" : undefined}>{loading ? "–" : value}</span>
      <p>{label}</p>
    </div>
  );
}

export function Dashboard({
  authorities,
  keys,
  documents,
  auditLogs,
  loading = false
}: {
  authorities: Authority[];
  keys: PublicKey[];
  documents: SignedDocument[];
  auditLogs: AuditLog[];
  loading?: boolean;
}) {
  return (
    <div className="page">
      <header className="page-header">
        <p className="eyebrow">Live overview</p>
        <h2>Trust operations dashboard</h2>
      </header>
      <div className="metric-grid">
        <Metric value={authorities.length} label="Authorities" loading={loading} />
        <Metric value={keys.length} label="Public keys" loading={loading} />
        <Metric value={documents.length} label="Signed documents" loading={loading} />
        <Metric value={auditLogs.length} label="Audit events" loading={loading} />
      </div>
      <section className="panel">
        <h3>Recent signing events</h3>
        {loading ? (
          <p className="loading-note">
            Loading activity. The service sleeps when idle, so the first request after a
            quiet spell can take up to a minute.
          </p>
        ) : auditLogs.length === 0 ? (
          <p className="loading-note">No signing activity recorded yet.</p>
        ) : (
          <div className="timeline">
            {auditLogs.slice(0, 6).map((log, index) => (
              <div key={`${log.current_hash}-${index}`} className="timeline-row">
                <strong>{log.event_type}</strong>
                <span>{new Date(log.timestamp).toLocaleString()}</span>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
