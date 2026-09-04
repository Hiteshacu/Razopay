import { useEffect, useState } from "react";
import { onAuthStateChanged, signOut, type User } from "firebase/auth";
import { AnimatePresence, motion } from "motion/react";
import {
  AuditLog,
  Authority,
  PublicKey,
  SignedDocument,
  apiClient,
  wakeService
} from "./api/client";
import { listAuditLogs, listDocuments } from "./api/documents";
import { listAuthorities, listPublicKeys } from "./api/keys";
import { Navbar, type Role, View } from "./components/Navbar";
import { firebaseAuth, firebaseConfigured } from "./firebase";
import { pageTransition } from "./motion";
import { AuditLogs } from "./pages/AuditLogs";
import { ApprovalPage } from "./pages/ApprovalPage";
import { AuthPage, type AuthMode } from "./pages/AuthPage";
import { Approvals } from "./pages/Approvals";
import { Authorities } from "./pages/Authorities";
import { Dashboard } from "./pages/Dashboard";
import { KeyManagement } from "./pages/KeyManagement";
import { Landing } from "./pages/Landing";
import { Library } from "./pages/Library";
import { PayoutAdvice } from "./pages/PayoutAdvice";
import { Verify } from "./pages/Verify";
import { SignDocument } from "./pages/SignDocument";
import { SignedDocuments } from "./pages/SignedDocuments";
import { MemberActivity } from "./pages/MemberActivity";
import { Users } from "./pages/Users";

type Screen = "landing" | "auth" | "library" | "verify" | "console";

type Approval = { approved: boolean; email: string | null; reason?: string; role: Role } | null;

export default function App() {
  const [screen, setScreen] = useState<Screen>("landing");
  const [authMode, setAuthMode] = useState<AuthMode>("signin");
  const [user, setUser] = useState<User | null>(null);
  const [approval, setApproval] = useState<Approval>(null);
  const [checkingSession, setCheckingSession] = useState(firebaseConfigured);
  // An approval link arrives as ?approve=<token>. It is handled before any
  // sign-in check, because the person clicking it is usually not the person
  // whose account is waiting.
  const [approvalToken, setApprovalToken] = useState<string | null>(() =>
    new URLSearchParams(window.location.search).get("approve")
  );

  const [view, setView] = useState<View>("dashboard");
  // Which account's page is open, if any. Held here rather than in Users so
  // that leaving People and coming back does not reopen somebody's page.
  const [openMember, setOpenMember] = useState<string | null>(null);
  const [authorities, setAuthorities] = useState<Authority[]>([]);
  const [keys, setKeys] = useState<PublicKey[]>([]);
  const [documents, setDocuments] = useState<SignedDocument[]>([]);
  const [auditLogs, setAuditLogs] = useState<AuditLog[]>([]);
  const [loadError, setLoadError] = useState("");
  const [loading, setLoading] = useState(true);

  // Start waking the service as the page opens, so the spin-up overlaps with
  // reading the landing page rather than running after sign-in.
  useEffect(() => {
    wakeService();
  }, []);

  // Firebase restores an existing session asynchronously, so wait for its
  // first callback before deciding which screen to show. Rendering the
  // landing page first would sign the operator out visually on every reload.
  useEffect(() => {
    const auth = firebaseAuth();
    if (!auth) {
      setCheckingSession(false);
      return;
    }
    return onAuthStateChanged(auth, (nextUser) => {
      setUser(nextUser);
      setCheckingSession(false);
      if (!nextUser) {
        setApproval(null);
        setScreen("landing");
      }
    });
  }, []);

  // Signing in proves who someone is; it does not make them an authority.
  // Ask the backend whether this account is approved before showing the
  // console, so an unapproved operator gets an explanation instead of a
  // screen full of failed requests.
  useEffect(() => {
    if (!user) return;
    let cancelled = false;

    void (async () => {
      try {
        const { data } = await apiClient.get("/api/auth/me");
        if (cancelled) return;
        setApproval({
          approved: Boolean(data.approved),
          email: data.email,
          reason: data.reason,
          role: (data.role as Role) ?? "member"
        });
        if (data.approved) setScreen("console");
      } catch {
        if (!cancelled) {
          setApproval({ approved: false, email: user.email, reason: "unreachable", role: "member" });
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [user]);

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
        setLoadError("Could not reach the PayProof service. Check that it is running, then reload.");
      }
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (screen === "console") {
      void refresh();
    }
  }, [screen]);

  async function handleSignOut() {
    const auth = firebaseAuth();
    if (auth) await signOut(auth);
    setUser(null);
    setApproval(null);
    setScreen("landing");
  }

  if (approvalToken) {
    return (
      <ApprovalPage
        token={approvalToken}
        onDone={() => {
          window.history.replaceState({}, "", window.location.pathname);
          setApprovalToken(null);
        }}
      />
    );
  }

  if (checkingSession) {
    return (
      <main className="login-shell">
        <section className="login-panel">
          <p className="loading-note">Checking your session...</p>
        </section>
      </main>
    );
  }

  if (!user) {
    if (screen === "auth") {
      return (
        <AuthPage mode={authMode} onModeChange={setAuthMode} onBack={() => setScreen("landing")} />
      );
    }
    if (screen === "library") {
      return <Library onBack={() => setScreen("landing")} />;
    }
    if (screen === "verify") {
      return <Verify onBack={() => setScreen("landing")} />;
    }
    return (
      <Landing
        onSignIn={() => {
          setAuthMode("signin");
          setScreen("auth");
        }}
        onSignUp={() => {
          setAuthMode("signup");
          setScreen("auth");
        }}
        onLibrary={() => setScreen("library")}
        onVerify={() => setScreen("verify")}
      />
    );
  }

  if (approval && !approval.approved) {
    const unreachable = approval.reason === "unreachable";
    return (
      <main className="login-shell">
        <section className="login-panel">
          <p className="eyebrow">PayProof</p>
          <h1>{unreachable ? "Cannot reach the service" : "Account awaiting approval"}</h1>
          <p className="loading-note">
            {unreachable
              ? "Signed in as " +
                (approval.email ?? "this account") +
                ", but the PayProof service did not respond. It may still be waking up — wait a moment and try again."
              : "Signed in as " +
                (approval.email ?? "this account") +
                ". Creating an account does not grant authority to sign documents. An existing administrator needs to approve this account first."}
          </p>
          <button className="primary-button" onClick={() => window.location.reload()}>
            Try again
          </button>
          <p className="auth-switch">
            <button type="button" onClick={handleSignOut}>
              Sign out
            </button>
          </p>
        </section>
      </main>
    );
  }

  if (!approval) {
    return (
      <main className="login-shell">
        <section className="login-panel">
          <p className="loading-note">Checking your access...</p>
        </section>
      </main>
    );
  }

  const administers = approval.role === "owner" || approval.role === "admin";

  return (
    <main className="app-shell">
      <Navbar
        view={view}
        onChange={(next) => {
          setOpenMember(null);
          setView(next);
        }}
        email={approval.email}
        role={approval.role}
        onSignOut={handleSignOut}
      />
      <section className="workspace">
        {loadError && <div className="status-banner">{loadError}</div>}
        {/* Keyed on the view so switching pages crossfades rather than
            snapping, which makes the console feel like one surface. */}
        <AnimatePresence mode="wait" initial={false}>
          <motion.div key={view} {...pageTransition}>
        {view === "dashboard" && (
          <Dashboard
            authorities={authorities}
            keys={keys}
            documents={documents}
            auditLogs={auditLogs}
            loading={loading}
          />
        )}
        {view === "authorities" && <Authorities authorities={authorities} onChanged={refresh} />}
        {view === "keys" && <KeyManagement authorities={authorities} keys={keys} onChanged={refresh} />}
        {view === "sign" && <SignDocument authorities={authorities} keys={keys} onSigned={refresh} />}
        {view === "advice" && <PayoutAdvice onBack={() => setView("dashboard")} />}
        {view === "documents" && (
          <SignedDocuments documents={documents} isOwner={approval.role === "owner"} />
        )}
        {view === "audit" && <AuditLogs logs={auditLogs} />}
        {/* Guarded here as well as in the sidebar: hiding a link is a
            courtesy, not a control. The backend refuses these calls from a
            member regardless. */}
        {view === "approvals" && administers && <Approvals />}
        {view === "users" && administers && openMember === null && (
          <Users
            isOwner={approval.role === "owner"}
            onOpenMember={(uid) => setOpenMember(uid)}
          />
        )}
        {view === "users" && administers && openMember !== null && (
          <MemberActivity uid={openMember} onBack={() => setOpenMember(null)} />
        )}
          </motion.div>
        </AnimatePresence>
      </section>
    </main>
  );
}
