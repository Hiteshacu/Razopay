import { useEffect, useState } from "react";
import { apiClient } from "../api/client";
import { CountUp } from "../components/CountUp";

type ManagedUser = {
  uid: string;
  email: string | null;
  approved: boolean;
  role: "owner" | "admin" | "member";
  created_at?: string;
  approved_by?: string;
};

type Signer = { email: string; documents: number; last_signed: string | null };

type Overview = {
  totals: {
    documents: number;
    users: number;
    approved_users: number;
    pending_users: number;
    administrators: number;
  };
  by_signer: Signer[];
  documents_scope?: "all" | "own";
};

const ROLE_LABEL: Record<string, string> = {
  owner: "Owner",
  admin: "Administrator",
  member: "Member"
};

/**
 * Who is on the system, what they may do, and what they have signed.
 *
 * Only an owner or administrator reaches this page. Role changes are the
 * owner's alone — an administrator who could promote others could quietly
 * grant themselves a replacement, which would make the distinction
 * meaningless.
 */
export function Users({
  isOwner,
  onOpenMember
}: {
  isOwner: boolean;
  onOpenMember: (uid: string) => void;
}) {
  const [users, setUsers] = useState<ManagedUser[]>([]);
  const [overview, setOverview] = useState<Overview | null>(null);
  const [ownerEmail, setOwnerEmail] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  async function load() {
    setLoading(true);
    setError("");
    try {
      const [usersResponse, overviewResponse] = await Promise.all([
        apiClient.get("/api/admin/users"),
        apiClient.get("/api/admin/overview")
      ]);
      setUsers(usersResponse.data.users);
      setOwnerEmail(usersResponse.data.owner_email ?? "");
      setOverview(overviewResponse.data);
    } catch {
      setError("Could not load users.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  async function changeRole(user: ManagedUser, role: "admin" | "member") {
    setBusy(user.uid);
    setMessage("");
    setError("");
    try {
      const { data } = await apiClient.post(`/api/admin/users/${user.uid}/role`, { role });
      setMessage(data.message);
      await load();
    } catch (exc) {
      const detail = (exc as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setError(detail ?? "Could not change that role.");
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="page">
      <header className="page-header">
        <p className="eyebrow">Administration</p>
        <h2>People and activity</h2>
      </header>

      {overview && (
        <div className="metric-grid">
          <div className="metric">
            <span><CountUp value={overview.totals.users} /></span>
            <p>Accounts</p>
          </div>
          <div className="metric">
            <span><CountUp value={overview.totals.administrators} /></span>
            <p>Administrators</p>
          </div>
          <div className="metric">
            <span><CountUp value={overview.totals.pending_users} /></span>
            <p>Awaiting approval</p>
          </div>
          <div className="metric">
            <span><CountUp value={overview.totals.documents} /></span>
            {/* Administrators are not shown other accounts' documents, so
                labelling their own count as a system total would be a lie. */}
            <p>{overview.documents_scope === "own" ? "Your documents" : "Documents signed"}</p>
          </div>
        </div>
      )}

      <section className="panel">
        <h3>Accounts</h3>
        {message && <p className="approval-ok">{message}</p>}
        {error && <p className="error-text">{error}</p>}

        {loading ? (
          <p className="loading-note">Loading...</p>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Email</th>
                  <th>Role</th>
                  <th>Status</th>
                  {isOwner && <th>Change role</th>}
                </tr>
              </thead>
              <tbody>
                {users.map((user) => (
                  <tr key={user.uid} className={isOwner ? "row-link" : undefined}>
                    <td>
                      {isOwner ? (
                        <button className="text-link" onClick={() => onOpenMember(user.uid)}>
                          {user.email ?? user.uid}
                        </button>
                      ) : (
                        user.email ?? "—"
                      )}
                    </td>
                    <td>
                      <span className={`role-pill role-${user.role}`}>
                        {ROLE_LABEL[user.role] ?? user.role}
                      </span>
                    </td>
                    <td>{user.approved ? "Active" : "Awaiting approval"}</td>
                    {isOwner && (
                      <td>
                        {user.role === "owner" ? (
                          <span className="muted">Cannot be changed</span>
                        ) : (
                          <button
                            className="ghost-button"
                            disabled={busy === user.uid || !user.approved}
                            onClick={() =>
                              changeRole(user, user.role === "admin" ? "member" : "admin")
                            }
                            title={
                              user.approved
                                ? undefined
                                : "Approve this account before giving it a role"
                            }
                          >
                            {busy === user.uid
                              ? "Saving..."
                              : user.role === "admin"
                                ? "Make member"
                                : "Make administrator"}
                          </button>
                        )}
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        <p className="loading-note" style={{ marginTop: 16 }}>
          {isOwner
            ? `Administrators can approve accounts and change nothing else. Signed documents stay private to whoever signed them — only the owner (${ownerEmail}) sees every document, and only the owner can change roles.`
            : "Administrators approve accounts. Documents stay private to whoever signed them, so this page does not show other accounts' work. Only the owner can change roles."}
        </p>
      </section>

      {overview && overview.by_signer.length > 0 && (
        <section className="panel">
          <h3>Signing activity by account</h3>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Account</th>
                  <th>Documents signed</th>
                  <th>Most recent</th>
                </tr>
              </thead>
              <tbody>
                {overview.by_signer.map((signer) => {
                  const account = users.find((user) => user.email === signer.email);
                  // Guarded on isOwner as well as on the account existing. The
                  // table above does the same, and this one did not: an
                  // administrator could click a row here and land on an
                  // owner-only endpoint, which answers 403. Offering a link
                  // that cannot work is worse than showing plain text.
                  const openable = isOwner && account;
                  return (
                  <tr key={signer.email} className={openable ? "row-link" : undefined}>
                    <td>
                      {openable ? (
                        <button className="text-link" onClick={() => onOpenMember(account!.uid)}>
                          {signer.email}
                        </button>
                      ) : (
                        signer.email
                      )}
                    </td>
                    <td>{signer.documents}</td>
                    <td>
                      {signer.last_signed
                        ? new Date(signer.last_signed).toLocaleString()
                        : "—"}
                    </td>
                  </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <p className="loading-note" style={{ marginTop: 14 }}>
            Open an account to see its authorities, keys, documents and audit
            trail. Documents signed before accounts were attributed appear as
            "unattributed".
          </p>
        </section>
      )}
    </div>
  );
}
