import { ArrowLeft, FileSignature, KeyRound, ShieldCheck } from "lucide-react";
import { motion } from "motion/react";
import { useEffect, useState } from "react";
import { apiClient } from "../api/client";
import { CountUp } from "../components/CountUp";
import { DownloadButton } from "../components/DownloadButton";
import { EASE_OUT } from "../motion";

type Activity = {
  user: { uid: string; email: string | null; role: string; approved: boolean; created_at?: string };
  totals: { authorities: number; keys: number; documents: number };
  authorities: Array<{
    authority_id: string;
    authority_name: string;
    department?: string;
    created_at?: string;
    status?: string;
  }>;
  keys: Array<{
    key_id: string;
    authority_name: string;
    algorithm?: string;
    key_size?: number;
    fingerprint_sha256?: string;
    created_at?: string;
    active?: boolean;
  }>;
  documents: Array<{
    document_id: string;
    original_filename?: string;
    signed_filename?: string;
    authority_name?: string;
    visual_fingerprint_hash?: string;
    created_at?: string;
  }>;
  audit: Array<{
    event_type: string;
    actor?: string;
    timestamp?: string;
    authority_id?: string;
    key_id?: string;
    document_id?: string;
  }>;
};

/**
 * One account's whole history, opened from People.
 *
 * Every other page in the console shows you your own work. This is the one
 * place another account's is shown, and you get here by naming whose you
 * want — so "whose is this?" is answered once, at the top, instead of being
 * a question you have to ask of every row.
 */
export function MemberActivity({ uid, onBack }: { uid: string; onBack: () => void }) {
  const [data, setData] = useState<Activity | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError("");
    apiClient
      .get(`/api/admin/users/${encodeURIComponent(uid)}/activity`)
      .then(({ data: payload }) => {
        if (!cancelled) setData(payload);
      })
      .catch(() => {
        if (!cancelled) setError("Could not load this account's activity.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [uid]);

  const when = (value?: string) => (value ? new Date(value).toLocaleString() : "—");

  return (
    <motion.div
      className="page"
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, ease: EASE_OUT }}
    >
      <header className="page-header">
        <button className="back-link" onClick={onBack}>
          <ArrowLeft size={15} aria-hidden="true" />
          <span>Back to People</span>
        </button>
        <p className="eyebrow">Account activity</p>
        <h2>{data?.user.email ?? "Loading..."}</h2>
      </header>

      {error && <p className="error-text">{error}</p>}
      {loading && <p className="loading-note">Loading...</p>}

      {data && (
        <>
          <div className="metric-grid">
            <div className="metric">
              <span><CountUp value={data.totals.authorities} /></span>
              <p>Authorities</p>
            </div>
            <div className="metric">
              <span><CountUp value={data.totals.keys} /></span>
              <p>Keys</p>
            </div>
            <div className="metric">
              <span><CountUp value={data.totals.documents} /></span>
              <p>Documents signed</p>
            </div>
          </div>

          <section className="panel">
            <h3><ShieldCheck size={17} aria-hidden="true" /> Authorities</h3>
            {data.authorities.length === 0 ? (
              <p className="loading-note">This account has not created an authority.</p>
            ) : (
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr><th>Authority</th><th>Department</th><th>Status</th><th>Created</th></tr>
                  </thead>
                  <tbody>
                    {data.authorities.map((authority) => (
                      <tr key={authority.authority_id}>
                        <td className="cell-name"><strong>{authority.authority_name}</strong></td>
                        <td>{authority.department ?? "—"}</td>
                        <td>{authority.status ?? "—"}</td>
                        <td className="cell-date">{when(authority.created_at)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>

          <section className="panel">
            <h3><KeyRound size={17} aria-hidden="true" /> Keys</h3>
            {data.keys.length === 0 ? (
              <p className="loading-note">This account has not generated a key.</p>
            ) : (
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr><th>Authority</th><th>Algorithm</th><th>Fingerprint</th><th>Created</th></tr>
                  </thead>
                  <tbody>
                    {data.keys.map((key) => (
                      <tr key={key.key_id}>
                        <td className="cell-name"><strong>{key.authority_name}</strong><small>{key.key_id}</small></td>
                        <td>{key.algorithm ?? "—"}{key.key_size ? ` · ${key.key_size}` : ""}</td>
                        {/* Public fingerprint only. Private key material is
                            never served by the API, to anyone. */}
                        <td className="hash-cell">{key.fingerprint_sha256?.slice(0, 24) ?? "—"}</td>
                        <td className="cell-date">{when(key.created_at)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>

          <section className="panel">
            <h3><FileSignature size={17} aria-hidden="true" /> Signed documents</h3>
            {data.documents.length === 0 ? (
              <p className="loading-note">This account has not signed anything.</p>
            ) : (
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr><th>Document</th><th>Authority</th><th>Signed</th><th aria-label="Download" /></tr>
                  </thead>
                  <tbody>
                    {data.documents.map((document) => (
                      <tr key={document.document_id}>
                        <td className="cell-name">
                          <strong>{document.original_filename ?? document.document_id}</strong>
                        </td>
                        <td><span className="authority-tag">{document.authority_name ?? "—"}</span></td>
                        <td className="cell-date">{when(document.created_at)}</td>
                        <td className="cell-action">
                          <DownloadButton document={document} />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>

          <section className="panel">
            <h3>Audit trail</h3>
            {data.audit.length === 0 ? (
              <p className="loading-note">No recorded events for this account.</p>
            ) : (
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr><th>Event</th><th>When</th><th>Reference</th></tr>
                  </thead>
                  <tbody>
                    {data.audit.map((entry, index) => (
                      <tr key={`${entry.timestamp}-${index}`}>
                        <td className="cell-name"><strong>{entry.event_type}</strong></td>
                        <td className="cell-date">{when(entry.timestamp)}</td>
                        <td className="hash-cell">
                          {entry.document_id ?? entry.key_id ?? entry.authority_id ?? "—"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        </>
      )}
    </motion.div>
  );
}
