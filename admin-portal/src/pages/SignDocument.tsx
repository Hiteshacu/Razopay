import axios from "axios";
import { AnimatePresence, motion } from "motion/react";
import { useState } from "react";
import { Authority, PublicKey } from "../api/client";
import { signDocument } from "../api/signing";
import { FileUploader } from "../components/FileUploader";
import { KeySelector } from "../components/KeySelector";
import { DownloadButton } from "../components/DownloadButton";
import { ResultCard } from "../components/ResultCard";
import { Modal } from "../components/Modal";
import { SigningProgress } from "../components/SigningProgress";
import { EASE_OUT, press } from "../motion";

export function SignDocument({
  authorities,
  keys,
  onSigned
}: {
  authorities: Authority[];
  keys: PublicKey[];
  onSigned: () => void;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [authorityId, setAuthorityId] = useState("");
  const [keyId, setKeyId] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<Awaited<ReturnType<typeof signDocument>> | null>(null);
  const [error, setError] = useState("");

  async function submit() {
    if (!file || !authorityId || !keyId) return;
    setBusy(true);
    setError("");
    setResult(null);
    try {
      const response = await signDocument(file, authorityId, keyId);
      setResult(response);
      onSigned();
    } catch (exc) {
      const detail = axios.isAxiosError(exc)
        ? (typeof exc.response?.data?.detail === "string" ? exc.response?.data?.detail : undefined)
        : undefined;
      setError(detail ?? "Signing failed. Check Firebase/backend setup and selected key.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="page">
      <header className="page-header">
        <p className="eyebrow">Signing engine</p>
        <h2>Sign a poster or PDF</h2>
      </header>
      <section className="panel">
        <FileUploader file={file} onFile={setFile} />
        <KeySelector
          authorities={authorities}
          keys={keys}
          authorityId={authorityId}
          keyId={keyId}
          onAuthority={(value) => {
            setAuthorityId(value);
            setKeyId("");
          }}
          onKey={setKeyId}
        />
        <motion.button
          className="primary-button"
          disabled={!file || !authorityId || !keyId || busy}
          onClick={submit}
          {...(busy ? {} : press)}
        >
          {busy ? "Signing..." : "Sign document"}
        </motion.button>
        {error && <p className="error-text">{error}</p>}
      </section>

      {/* A dialog rather than a panel further down the page: the wait is
          long enough that the work needs to be the only thing on screen,
          and it stops a second signature being started mid-flight.
          Not dismissable while running — the request cannot be cancelled,
          so offering a close button would be a lie. */}
      <Modal
        open={busy || Boolean(result)}
        dismissable={Boolean(result)}
        wide
        onClose={() => setResult(null)}
        labelledBy="signing-heading"
      >
        <SigningProgress done={Boolean(result)} />
        {result && (
          <div className="modal-actions">
            <DownloadButton
              document={result}
              className="download-button"
              label="Download signed document"
            />
            <button className="ghost-button" onClick={() => setResult(null)}>
              Close
            </button>
          </div>
        )}
      </Modal>

      {result && (
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.35, ease: EASE_OUT }}
        >
        <ResultCard title="Document signed successfully" tone="success">
          <p>Document ID: {result.document_id}</p>
          <p>Storage: {result.signed_file_storage_path}</p>
          <DownloadButton
            document={result}
            className="download-button"
            label="Download signed document"
          />
          <p className="hint">
            Share this file to demonstrate verification. Signed files are held on the
            server temporarily, so download it now rather than relying on this link later.
          </p>
        </ResultCard>
        </motion.div>
      )}
    </div>
  );
}
