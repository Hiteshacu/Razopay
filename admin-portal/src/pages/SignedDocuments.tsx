import { SignedDocument } from "../api/client";
import { DocumentTable } from "../components/DocumentTable";

export function SignedDocuments({ documents }: { documents: SignedDocument[] }) {
  return (
    <div className="page">
      <header className="page-header">
        <p className="eyebrow">Firebase archive</p>
        <h2>Signed documents</h2>
      </header>
      <section className="panel">
        <DocumentTable documents={documents} />
      </section>
    </div>
  );
}

