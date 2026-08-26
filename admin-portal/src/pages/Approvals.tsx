import { useEffect, useState } from "react";
import { apiClient } from "../api/client";

type Pending = {
  uid: string;
  email: string | null;
  requested_at?: string;
  notified: boolean;
};

/**
 * The approval queue.
 *
 * Approving by emailed link cannot be the only route: free hosting blocks
 * outbound SMTP, so the message may never leave the server. Everything
 * needed to make the decision is here instead, and the emailed link stays
 * as a convenience for when mail does work.
 */
export function Approvals() {
  const [pending, setPending] = useState<Pending[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  async function load() {
    setLoading(true);
    setError("");
    try {
      const { data } = await apiClient.get("/api/auth/pending");
      setPending(data);
    } catch {
      setError("Could not load the approval queue.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  async function act(uid: string, approve: boolean) {
    setBusy(uid);
    setError("");
    setMessage("");
    try {
      const { data } = approve
        ? await apiClient.post(`/api/auth/pending/${uid}/approve`)
        : await apiClient.delete(`/api/auth/pending/${uid}`);
      setMessage(data.message);
      await load();
    } catch (exc) {
      const detail = (exc as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setError(detail ?? "That action did not complete.");
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="page">
      <header className="page-header">
        <p className="eyebrow">Access control</p>
        <h2>Approval requests</h2>
      </header>

      <section className="panel">
        {message && <p className="approval-ok">{message}</p>}
        {error && <p className="error-text">{error}</p>}

        {loading ? (
          <p className="loading-note">Loading requests...</p>
        ) : pending.length === 0 ? (
          <p className="loading-note">
            No one is waiting. Accounts appear here the first time someone signs in.
          </p>
        ) : (
          <div className="list">
            {pending.map((request) => (
              <div key={request.uid} className="approval-row">
                <div>
                  <strong>{request.email ?? "account with no email"}</strong>
                  <small>
                    Requested{" "}
                    {request.requested_at
                      ? new Date(request.requested_at).toLocaleString()
                      : "recently"}
                    {!request.notified && " · no email could be sent"}
                  </small>
                </div>
                <div className="approval-actions">
                  <button
                    className="primary-button"
                    disabled={busy === request.uid}
                    onClick={() => act(request.uid, true)}
                  >
                    {busy === request.uid ? "Working..." : "Approve"}
                  </button>
                  <button
                    className="ghost-button"
                    disabled={busy === request.uid}
                    onClick={() => act(request.uid, false)}
                  >
                    Reject
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}

        <p className="loading-note" style={{ marginTop: 18 }}>
          Approving lets an account sign documents in your authority's name. Only approve
          addresses you recognise.
        </p>
      </section>
    </div>
  );
}
