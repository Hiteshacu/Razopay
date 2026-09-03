import { useState } from "react";
import { Authority, PublicKey, apiErrorMessage } from "../api/client";
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
  const [error, setError] = useState("");

  async function generate() {
    const authority = authorities.find((item) => item.authority_id === authorityId);
    if (!authority || busy) return;
    setBusy(true);
    setError("");
    setLastKey(null);
    try {
      const key = await generatePublicKey(authority.authority_id, authority.authority_name);
      setLastKey(key);
      onChanged();
    } catch (exc) {
      // Generating a 2048-bit pair is the most expensive thing this service
      // does, and the one most likely to fail for a reason worth reading:
      // MASTER_KEY absent, the key store unreachable, or the request timing
      // out on a small instance. Swallowing that left the page looking idle.
      setError(apiErrorMessage(exc, "Could not generate the key. Try again."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="page two-column">
      <section className="panel">
        <h2>Generate RSA key pair</h2>
        <p className="muted">The private key is encrypted on the backend. Firebase receives only the public key.</p>
        {authorities.length === 0 ? (
          <p className="hint">
            No authorities yet. Create one under Authorities first — a key always
            belongs to an authority.
          </p>
        ) : (
          <>
            <select value={authorityId} onChange={(event) => setAuthorityId(event.target.value)}>
              <option value="">Select authority</option>
              {authorities.map((authority) => (
                <option key={authority.authority_id} value={authority.authority_id}>{authority.authority_name}</option>
              ))}
            </select>
            <button className="primary-button" disabled={!authorityId || busy} onClick={generate}>
              {busy ? "Generating…" : "Generate key"}
            </button>
            {busy && <p className="hint">Creating a 2048-bit key pair. This can take a few seconds.</p>}
            {error && <p className="error-text">{error}</p>}
          </>
        )}
        {lastKey && (
          <div className="result-inline">
            <strong>{lastKey.key_id}</strong>
            <span>{lastKey.fingerprint_sha256}</span>
          </div>
        )}
      </section>
      <section className="panel">
        <h2>Public keys</h2>
        {keys.length === 0 ? (
          <p className="hint">No keys yet.</p>
        ) : (
          <div className="list">
            {keys.map((key) => (
              <div className="list-row" key={key.key_id}>
                <strong>{key.key_id}</strong>
                <span>{key.authority_name}</span>
                <small>{key.fingerprint_sha256}</small>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
