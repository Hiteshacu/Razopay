import type { Authority, PublicKey } from "../api/client";

export function KeySelector({
  authorities,
  keys,
  authorityId,
  keyId,
  onAuthority,
  onKey
}: {
  authorities: Authority[];
  keys: PublicKey[];
  authorityId: string;
  keyId: string;
  onAuthority: (value: string) => void;
  onKey: (value: string) => void;
}) {
  const visibleKeys = keys.filter((key) => !authorityId || key.authority_id === authorityId);
  return (
    <div className="selector-grid">
      <label>
        Authority
        <select value={authorityId} onChange={(event) => onAuthority(event.target.value)}>
          <option value="">Select authority</option>
          {authorities.map((authority) => (
            <option key={authority.authority_id} value={authority.authority_id}>
              {authority.authority_name}
            </option>
          ))}
        </select>
      </label>
      <label>
        Public key
        <select value={keyId} onChange={(event) => onKey(event.target.value)}>
          <option value="">Select key</option>
          {visibleKeys.map((key) => (
            <option key={key.key_id} value={key.key_id}>
              {key.key_id} - {key.fingerprint_sha256.slice(0, 10)}
            </option>
          ))}
        </select>
      </label>
    </div>
  );
}
