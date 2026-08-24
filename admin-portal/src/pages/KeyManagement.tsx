import { useState } from "react";
import { Authority, PublicKey } from "../api/client";
import { generatePublicKey } from "../api/keys";

export function KeyManagement({
  authorities,
  keys,
  onChanged
}: {
  authorities: Authority[];
  keys: PublicKey[];
  onChanged: () => void;
}) {
  const [authorityId, setAuthorityId] = useState("");
  const [lastKey, setLastKey] = useState<PublicKey | null>(null);
  const [busy, setBusy] = useState(false);

  async function generate() {
    const authority = authorities.find((item) => item.authority_id === authorityId);
    if (!authority) return;
    setBusy(true);
    try {
      const key = await generatePublicKey(authority.authority_id, authority.authority_name);
      setLastKey(key);
      onChanged();
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="page two-column">
      <section className="panel">
        <h2>Generate RSA key pair</h2>
        <p className="muted">The private key is encrypted on the backend. Firebase receives only the public key.</p>
        <select value={authorityId} onChange={(event) => setAuthorityId(event.target.value)}>
          <option value="">Select authority</option>
          {authorities.map((authority) => (
            <option key={authority.authority_id} value={authority.authority_id}>{authority.authority_name}</option>
          ))}
        </select>
        <button className="primary-button" disabled={!authorityId || busy} onClick={generate}>Generate key</button>
        {lastKey && (
          <div className="result-inline">
            <strong>{lastKey.key_id}</strong>
            <span>{lastKey.fingerprint_sha256}</span>
          </div>
        )}
      </section>
      <section className="panel">
        <h2>Public keys</h2>
        <div className="list">
          {keys.map((key) => (
            <div className="list-row" key={key.key_id}>
              <strong>{key.key_id}</strong>
              <span>{key.authority_name}</span>
              <small>{key.fingerprint_sha256}</small>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}

