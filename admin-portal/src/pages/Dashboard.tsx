import { AuditLog, Authority, PublicKey, SignedDocument } from "../api/client";

export function Dashboard({
  authorities,
  keys,
  documents,
  auditLogs
}: {
  authorities: Authority[];
  keys: PublicKey[];
  documents: SignedDocument[];
  auditLogs: AuditLog[];
}) {
  return (
    <div className="page">
      <header className="page-header">
        <p className="eyebrow">Live overview</p>
        <h2>Trust operations dashboard</h2>
      </header>
      <div className="metric-grid">
        <div className="metric"><span>{authorities.length}</span><p>Authorities</p></div>
        <div className="metric"><span>{keys.length}</span><p>Public keys</p></div>
        <div className="metric"><span>{documents.length}</span><p>Signed documents</p></div>
        <div className="metric"><span>{auditLogs.length}</span><p>Audit events</p></div>
      </div>
      <section className="panel">
        <h3>Recent signing events</h3>
        <div className="timeline">
          {auditLogs.slice(0, 6).map((log, index) => (
            <div key={`${log.current_hash}-${index}`} className="timeline-row">
              <strong>{log.event_type}</strong>
              <span>{new Date(log.timestamp).toLocaleString()}</span>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}

