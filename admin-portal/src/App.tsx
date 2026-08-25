import { useEffect, useState } from "react";
import { AuditLog, Authority, PublicKey, SignedDocument, wakeService } from "./api/client";
import { listAuditLogs, listDocuments } from "./api/documents";
import { listAuthorities, listPublicKeys } from "./api/keys";
import { Navbar, View } from "./components/Navbar";
import { AuditLogs } from "./pages/AuditLogs";
import { Authorities } from "./pages/Authorities";
import { Dashboard } from "./pages/Dashboard";
import { KeyManagement } from "./pages/KeyManagement";
import { Login } from "./pages/Login";
import { SignDocument } from "./pages/SignDocument";
import { SignedDocuments } from "./pages/SignedDocuments";

export default function App() {
  const [authenticated, setAuthenticated] = useState(Boolean(localStorage.getItem("dts_admin_token")));
  const [view, setView] = useState<View>("dashboard");
  const [authorities, setAuthorities] = useState<Authority[]>([]);
  const [keys, setKeys] = useState<PublicKey[]>([]);
  const [documents, setDocuments] = useState<SignedDocument[]>([]);
  const [auditLogs, setAuditLogs] = useState<AuditLog[]>([]);
  const [loadError, setLoadError] = useState("");
  const [loading, setLoading] = useState(true);

  async function loadAll() {
    const [authorityData, keyData, documentData, auditData] = await Promise.all([
      listAuthorities(),
      listPublicKeys(),
      listDocuments(),
      listAuditLogs()
    ]);
    setAuthorities(authorityData);
    setKeys(keyData);
    setDocuments(documentData);
    setAuditLogs(auditData);
  }

  async function refresh() {
    setLoadError("");
    setLoading(true);
    try {
      await loadAll();
    } catch {
      // An idle server sleeps and takes up to a minute to answer its first
      // request, which is indistinguishable from an outage on the first try.
      // Say so plainly and retry once before reporting a real failure.
      setLoadError("Waking the server up. This can take up to a minute on the first request.");
      try {
        await new Promise((resolve) => setTimeout(resolve, 6000));
        await loadAll();
        setLoadError("");
      } catch {
        setLoadError("Could not reach the Trust Shield service. Check that it is running, then reload.");
      }
    } finally {
      setLoading(false);
    }
  }

  // Start waking the service as the page opens, before anyone signs in, so the
  // spin-up runs while the login screen is on show rather than afterwards.
  useEffect(() => {
    wakeService();
  }, []);

  useEffect(() => {
    if (authenticated) {
      void refresh();
    }
  }, [authenticated]);

  if (!authenticated) {
    return <Login onLogin={() => setAuthenticated(true)} />;
  }

  return (
    <main className="app-shell">
      <Navbar view={view} onChange={setView} />
      <section className="workspace">
        {loadError && <div className="status-banner">{loadError}</div>}
        {view === "dashboard" && <Dashboard authorities={authorities} keys={keys} documents={documents} auditLogs={auditLogs} loading={loading} />}
        {view === "authorities" && <Authorities authorities={authorities} onChanged={refresh} />}
        {view === "keys" && <KeyManagement authorities={authorities} keys={keys} onChanged={refresh} />}
        {view === "sign" && <SignDocument authorities={authorities} keys={keys} onSigned={refresh} />}
        {view === "documents" && <SignedDocuments documents={documents} />}
        {view === "audit" && <AuditLogs logs={auditLogs} />}
      </section>
    </main>
  );
}

