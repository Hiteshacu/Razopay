import { motion, useReducedMotion } from "motion/react";
import { AuditLog, Authority, PublicKey, SignedDocument } from "../api/client";
import { EASE_OUT } from "../motion";

function Metric({
  value,
  label,
  loading,
  index
}: {
  value: number;
  label: string;
  loading: boolean;
  index: number;
}) {
  const reduceMotion = useReducedMotion();
  return (
    <motion.div
      className="metric"
      initial={reduceMotion ? false : { opacity: 0, y: 14 }}
      animate={{ opacity: 1, y: 0 }}
      // 50ms apart: reads as a sequence without the last card arriving late.
      transition={{ duration: 0.4, delay: index * 0.05, ease: EASE_OUT }}
      whileHover={reduceMotion ? undefined : { y: -3 }}
    >
      {/* A zero while data is still in flight reads as "nothing here" rather
          than "not counted yet", which is alarming on a first load. */}
      <span className={loading ? "metric-pending" : undefined}>{loading ? "–" : value}</span>
      <p>{label}</p>
    </motion.div>
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
        <Metric value={authorities.length} label="Authorities" loading={loading} index={0} />
        <Metric value={keys.length} label="Public keys" loading={loading} index={1} />
        <Metric value={documents.length} label="Signed documents" loading={loading} index={2} />
        <Metric value={auditLogs.length} label="Audit events" loading={loading} index={3} />
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
              <motion.div
                key={`${log.current_hash}-${index}`}
                className="timeline-row"
                initial={{ opacity: 0, x: -8 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ duration: 0.3, delay: index * 0.04, ease: EASE_OUT }}
              >
                <strong>{log.event_type}</strong>
                <span>{new Date(log.timestamp).toLocaleString()}</span>
              </motion.div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
