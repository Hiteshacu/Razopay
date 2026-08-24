import axios from "axios";
import { useState } from "react";
import { Authority, PublicKey } from "../api/client";
import { signDocument } from "../api/signing";
import { FileUploader } from "../components/FileUploader";
import { KeySelector } from "../components/KeySelector";
import { ResultCard } from "../components/ResultCard";

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
        <button className="primary-button" disabled={!file || !authorityId || !keyId || busy} onClick={submit}>
          {busy ? "Signing..." : "Sign document"}
        </button>
        {error && <p className="error-text">{error}</p>}
      </section>
      {result && (
        <ResultCard title="Document signed successfully" tone="success">
          <p>Document ID: {result.document_id}</p>
          <p>Storage mode: {result.storage_type}</p>
          <p>Storage: {result.signed_file_storage_path}</p>
          <p>URL: {result.download_url}</p>
          <a href={result.download_url} target="_blank" rel="noreferrer">Download Signed Document</a>
        </ResultCard>
      )}
    </div>
  );
}
