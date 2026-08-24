import type { FormEvent } from "react";
import { useState } from "react";
import { Authority } from "../api/client";
import { createAuthority } from "../api/keys";

export function Authorities({ authorities, onChanged }: { authorities: Authority[]; onChanged: () => void }) {
  const [form, setForm] = useState({ authority_name: "", department: "", email: "" });
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    try {
      await createAuthority(form);
      setForm({ authority_name: "", department: "", email: "" });
      onChanged();
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="page two-column">
      <section className="panel">
        <h2>Create authority</h2>
        <form onSubmit={submit} className="stack-form">
          <input placeholder="Authority name" value={form.authority_name} onChange={(event) => setForm({ ...form, authority_name: event.target.value })} />
          <input placeholder="Department" value={form.department} onChange={(event) => setForm({ ...form, department: event.target.value })} />
          <input placeholder="Email" value={form.email} onChange={(event) => setForm({ ...form, email: event.target.value })} />
          <button className="primary-button" disabled={busy}>Create authority</button>
        </form>
      </section>
      <section className="panel">
        <h2>Authorities</h2>
        <div className="list">
          {authorities.map((authority) => (
            <div className="list-row" key={authority.authority_id}>
              <strong>{authority.authority_name}</strong>
              <span>{authority.department}</span>
              <small>{authority.email}</small>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
