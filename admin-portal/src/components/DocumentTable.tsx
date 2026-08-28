import { Check, Copy, Download } from "lucide-react";
import { motion } from "motion/react";
import { useState } from "react";
import { SignedDocument, signedFileUrl } from "../api/client";
import { EASE_OUT } from "../motion";

function Fingerprint({ hash }: { hash?: string }) {
  const [copied, setCopied] = useState(false);

  if (!hash) return <span className="hash-empty">—</span>;

  async function copy() {
    try {
      await navigator.clipboard.writeText(hash!);
      setCopied(true);
      setTimeout(() => setCopied(false), 1600);
    } catch {
      setCopied(false);
    }
  }

  return (
    <button type="button" className="hash-cell" onClick={copy} title={`Copy ${hash}`}>
      <code>{hash.slice(0, 10)}…{hash.slice(-4)}</code>
      <span className="hash-icon" aria-hidden="true">
        {copied ? <Check size={13} /> : <Copy size={13} />}
      </span>
      <span className="sr-only">{copied ? "Copied" : "Copy fingerprint"}</span>
    </button>
  );
}

export function DocumentTable({ documents }: { documents: SignedDocument[] }) {
  if (documents.length === 0) {
    return <p className="loading-note">Nothing signed yet. Documents appear here once signed.</p>;
  }

  return (
    <div className="table-wrap">
      <table className="data-table">
        <thead>
          <tr>
            <th>Document</th>
            <th>Authority</th>
            <th>Visual fingerprint</th>
            <th>Signed</th>
            <th aria-label="Download" />
          </tr>
        </thead>
        <tbody>
          {documents.map((document, index) => (
            <motion.tr
              key={document.document_id}
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              // Capped so a long list does not take seconds to finish arriving.
              transition={{ duration: 0.25, delay: Math.min(index, 12) * 0.02, ease: EASE_OUT }}
            >
              <td className="cell-name" title={document.original_filename}>
                <strong>{document.original_filename}</strong>
                {document.signed_by_email && <small>{document.signed_by_email}</small>}
              </td>
              <td>
                <span className="authority-tag">{document.authority_name}</span>
              </td>
              <td>
                <Fingerprint hash={document.visual_fingerprint_hash} />
              </td>
              <td className="cell-date">
                {new Date(document.created_at).toLocaleDateString()}
                <small>{new Date(document.created_at).toLocaleTimeString()}</small>
              </td>
              <td className="cell-action">
                <a
                  className="icon-link"
                  href={signedFileUrl(document)}
                  target="_blank"
                  rel="noreferrer"
                  download
                >
                  <Download size={15} aria-hidden="true" />
                  <span>Download</span>
                </a>
              </td>
            </motion.tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
