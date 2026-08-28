import { Download, Loader2 } from "lucide-react";
import { useState } from "react";
import { downloadSignedFile } from "../api/client";

/**
 * Fetches a signed document and hands it to the browser.
 *
 * A button rather than a link, because the file is only released to the
 * account that signed it and that check needs the session's token — which a
 * browser will not put on a plain <a href>. The trade-off is that a download
 * now has a pending state and can fail, so both are shown.
 */
export function DownloadButton({
  document,
  className = "icon-link",
  label = "Download"
}: {
  document: { document_id: string; signed_filename?: string };
  className?: string;
  label?: string;
}) {
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);

  async function run() {
    setBusy(true);
    setFailed(false);
    try {
      await downloadSignedFile(document);
    } catch {
      setFailed(true);
    } finally {
      setBusy(false);
    }
  }

  return (
    <button
      type="button"
      className={className}
      onClick={run}
      disabled={busy}
      title={failed ? "Could not fetch this file. Try again." : undefined}
    >
      {busy ? (
        <Loader2 size={15} aria-hidden="true" className="spin" />
      ) : (
        <Download size={15} aria-hidden="true" />
      )}
      <span>{busy ? "Preparing..." : failed ? "Retry download" : label}</span>
    </button>
  );
}
