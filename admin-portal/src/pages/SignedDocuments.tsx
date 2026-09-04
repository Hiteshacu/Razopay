import { SignedDocument } from "../api/client";
import { DocumentTable } from "../components/DocumentTable";

export function SignedDocuments({
  documents,
  isOwner = false
}: {
  documents: SignedDocument[];
  isOwner?: boolean;
}) {
  return (
    <div className="page">
      <header className="page-header">
        <p className="eyebrow">Firebase archive</p>
        <h2>Signed documents</h2>
        {/* This list is every account's own work, the owner's included. The
            owner can read and download anybody's, but from that account's
            page rather than from here — a single merged list made it
            impossible to tell at a glance which documents were yours. That
            is a good rule and an invisible one, so it is worth saying where
            the rest are rather than leaving it to be discovered. */}
        <p className="hint">
          {isOwner
            ? "Documents you signed. To read or download another account's, open it under People."
            : "Documents you signed. Each account sees only its own."}
        </p>
      </header>
      <section className="panel">
        <DocumentTable documents={documents} />
      </section>
    </div>
  );
}

