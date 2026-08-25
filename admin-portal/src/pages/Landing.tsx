import { FileSignature, ScanLine, ShieldCheck } from "lucide-react";

export function Landing({
  onSignIn,
  onSignUp
}: {
  onSignIn: () => void;
  onSignUp: () => void;
}) {
  return (
    <div className="landing">
      <header className="landing-bar">
        <div className="landing-brand">
          <div className="brand-mark">DTS</div>
          <div>
            <strong>Digital Trust Shield</strong>
            <span>Authority signing &amp; verification</span>
          </div>
        </div>
        <nav className="landing-actions">
          <button className="ghost-button" onClick={onSignIn}>
            Sign in
          </button>
          <button className="primary-button" onClick={onSignUp}>
            Sign up
          </button>
        </nav>
      </header>

      <main className="landing-hero">
        <p className="eyebrow">Proof that travels with the document</p>
        <h1>Know whether a notice, receipt or poster is genuine.</h1>
        <p className="landing-lede">
          An issuing authority signs a document once. The proof is hidden inside the
          image itself, so it survives being forwarded, compressed and screenshotted —
          and anyone can check it in seconds.
        </p>

        <div className="landing-cards">
          <article>
            <ShieldCheck size={22} />
            <h3>Signed by an authority</h3>
            <p>
              Each document is signed with an RSA key that never leaves the backend.
              Only a registered authority can issue one.
            </p>
          </article>
          <article>
            <FileSignature size={22} />
            <h3>Invisible, not attached</h3>
            <p>
              The proof lives in the pixels rather than in metadata, so it is still
              there after a screenshot or a trip through a messaging app.
            </p>
          </article>
          <article>
            <ScanLine size={22} />
            <h3>Anyone can verify</h3>
            <p>
              Citizens check a document in the mobile app without an account. Signing
              needs an approved authority; verifying does not.
            </p>
          </article>
        </div>

        <p className="landing-foot">
          Verifying is open to everyone. This console is for issuing authorities.
        </p>
      </main>
    </div>
  );
}
