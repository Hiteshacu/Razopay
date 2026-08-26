import { ShieldCheck } from "lucide-react";
import { motion } from "motion/react";
import { useEffect, useState } from "react";
import { apiClient } from "../api/client";

type Request = { email: string; requested_at?: string; state: string };

/**
 * Landing page for the link in an approval email.
 *
 * Nothing is granted by arriving here. The page describes the request and
 * waits for a deliberate click, because mail clients fetch links in messages
 * before anyone opens them — approving on page load would mean an unread
 * email could hand out authority by itself.
 */
export function ApprovalPage({ token, onDone }: { token: string; onDone: () => void }) {
  const [request, setRequest] = useState<Request | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState("");

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const { data } = await apiClient.get(`/api/auth/approval/${token}`);
        if (!cancelled) setRequest(data);
      } catch {
        if (!cancelled) setError("This approval link is not valid, or it has already been used.");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [token]);

  async function approve() {
    setBusy(true);
    setError("");
    try {
      const { data } = await apiClient.post(`/api/auth/approval/${token}`);
      setDone(data.message);
    } catch (exc) {
      const detail = (exc as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setError(detail ?? "Could not approve this request. The link may have expired.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="login-shell">
      <motion.section
        className="login-panel"
        initial={{ opacity: 0, y: 14 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, ease: [0.22, 1, 0.36, 1] }}
      >
        <div className="login-icon">
          <ShieldCheck size={34} />
        </div>
        <p className="eyebrow">Digital Trust Shield</p>

        {done ? (
          <>
            <h1>Approved</h1>
            <p className="loading-note">{done} They can sign in now.</p>
            <button className="primary-button" onClick={onDone}>
              Go to the console
            </button>
          </>
        ) : error ? (
          <>
            <h1>Link not valid</h1>
            <p className="loading-note">{error}</p>
            <button className="primary-button" onClick={onDone}>
              Go to the console
            </button>
          </>
        ) : !request ? (
          <p className="loading-note">Checking this request...</p>
        ) : request.state === "already_approved" ? (
          <>
            <h1>Already approved</h1>
            <p className="loading-note">{request.email} can already sign documents.</p>
            <button className="primary-button" onClick={onDone}>
              Go to the console
            </button>
          </>
        ) : request.state === "expired" ? (
          <>
            <h1>Link expired</h1>
            <p className="loading-note">
              This request is older than seven days. Ask {request.email} to sign in again,
              which sends a fresh request.
            </p>
            <button className="primary-button" onClick={onDone}>
              Go to the console
            </button>
          </>
        ) : (
          <>
            <h1>Approve this account?</h1>
            <p className="loading-note">
              <strong>{request.email}</strong> is asking to act as an issuing authority.
            </p>
            <p className="approval-warning">
              Approving lets this account <strong>sign documents in your authority's name</strong>.
              Only continue if you recognise this address.
            </p>
            <button className="primary-button" onClick={approve} disabled={busy}>
              {busy ? "Approving..." : "Approve access"}
            </button>
            <p className="auth-switch">
              <button type="button" onClick={onDone}>
                Not now
              </button>
            </p>
          </>
        )}
      </motion.section>
    </main>
  );
}
