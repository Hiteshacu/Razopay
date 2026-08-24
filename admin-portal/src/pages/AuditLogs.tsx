import { AuditLog } from "../api/client";

export function AuditLogs({ logs }: { logs: AuditLog[] }) {
  return (
    <div className="page">
      <header className="page-header">
        <p className="eyebrow">Hash chained events</p>
        <h2>Audit logs</h2>
      </header>
      <section className="panel">
        <div className="list">
          {logs.map((log, index) => (
            <div className="list-row" key={`${log.current_hash}-${index}`}>
              <strong>{log.event_type}</strong>
              <span>{new Date(log.timestamp).toLocaleString()}</span>
              <small>{log.current_hash}</small>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}

