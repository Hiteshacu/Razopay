import type { FormEvent } from "react";
import { useState } from "react";
import { Authority, apiErrorMessage } from "../api/client";
import { createAuthority } from "../api/keys";

export function Authorities({ authorities, onChanged }: { authorities: Authority[]; onChanged: () => void }) {
  const [form, setForm] = useState({ authority_name: "", department: "", email: "" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [created, setCreated] = useState("");

  // The backend requires two characters in each name and a real address. It is
  // better to say so beside the field than to send a request that comes back
  // 422 — and the button was previously live with the form empty.
  const name = form.authority_name.trim();
  const department = form.department.trim();
  const email = form.email.trim();
  const ready = name.length >= 2 && department.length >= 2 && email.includes("@");

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!ready || busy) return;
    setBusy(true);
    setError("");
    setCreated("");
    try {
      const authority = await createAuthority({
        authority_name: name,
        department,
        email
      });
      setForm({ authority_name: "", department: "", email: "" });
      setCreated(authority.authority_name);
      onChanged();
    } catch (exc) {
      // This used to be a bare try/finally. Any failure — an expired session,
      // a rejected field, the service still waking — was swallowed, the form
      // simply sat there, and there was no way to tell a refused request from
      // one that never left the page.
      setError(apiErrorMessage(exc, "Could not create the authority. Try again."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="page two-column">
      <section className="panel">
        <h2>Create authority</h2>
        <form onSubmit={submit} className="stack-form">
          <input
            placeholder="Authority name"
            value={form.authority_name}
            onChange={(event) => setForm({ ...form, authority_name: event.target.value })}
          />
          <input
            placeholder="Department"
            value={form.department}
            onChange={(event) => setForm({ ...form, department: event.target.value })}
          />
          <input
            type="email"
            placeholder="Email"
            value={form.email}
            onChange={(event) => setForm({ ...form, email: event.target.value })}
          />
          <button className="primary-button" disabled={!ready || busy}>
            {busy ? "Creating…" : "Create authority"}
          </button>
          {error && <p className="error-text">{error}</p>}
          {created && <p className="match-found">Created “{created}”.</p>}
        </form>
      </section>
      <section className="panel">
        <h2>Authorities</h2>
        {authorities.length === 0 ? (
          <p className="hint">
            No authorities yet. Create one on the left, then generate a key for it
            under Keys.
          </p>
        ) : (
          <div className="list">
            {authorities.map((authority) => (
              <div className="list-row" key={authority.authority_id}>
                <strong>{authority.authority_name}</strong>
                <span>{authority.department}</span>
                <small>{authority.email}</small>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
