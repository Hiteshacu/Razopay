import { useState } from "react";
import { SignedDocument, signedFileUrl } from "../api/client";

function FingerprintCell({ hash }: { hash?: string }) {
  const [copied, setCopied] = useState(false);

  if (!hash) {
    return <span className="hash-empty">—</span>;
  }

  async function copy() {
    try {
      await navigator.clipboard.writeText(hash!);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      setCopied(false);
    }
  }

  return (
    <button type="button" className="hash-cell" onClick={copy} title={hash}>
      <code>{hash.slice(0, 12)}…{hash.slice(-6)}</code>
      <span className="hash-action">{copied ? "Copied" : "Copy"}</span>
    </button>
  );
}

export function DocumentTable({ documents }: { documents: SignedDocument[] }) {
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Document</th>
            <th>Authority</th>
            <th>Key</th>
            <th>Visual fingerprint</th>
            <th>Signed At</th>
            <th>Output</th>
          </tr>
        </thead>
        <tbody>
          {documents.map((document) => (
            <tr key={document.document_id}>
              <td>{document.original_filename}</td>
              <td>{document.authority_name}</td>
              <td>{document.key_id}</td>
              <td>
                <FingerprintCell hash={document.visual_fingerprint_hash} />
              </td>
              <td>{new Date(document.created_at).toLocaleString()}</td>
              <td>
                <a href={signedFileUrl(document)} target="_blank" rel="noreferrer" download>
                  Download
                </a>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
