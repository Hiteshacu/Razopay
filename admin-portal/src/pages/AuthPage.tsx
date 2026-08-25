import { ShieldCheck } from "lucide-react";
import type { FormEvent } from "react";
import { useState } from "react";
import {
  createUserWithEmailAndPassword,
  signInWithEmailAndPassword
} from "firebase/auth";
import { describeAuthError, firebaseAuth, firebaseConfigured } from "../firebase";

export type AuthMode = "signin" | "signup";

export function AuthPage({
  mode,
  onModeChange,
  onBack
}: {
  mode: AuthMode;
  onModeChange: (mode: AuthMode) => void;
  onBack: () => void;
}) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const signingUp = mode === "signup";

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError("");

    if (!email.trim()) {
      setError("Enter your email address.");
      return;
    }
    if (!password) {
      setError("Enter your password.");
      return;
    }
    if (signingUp && password !== confirmation) {
      setError("The two passwords do not match.");
      return;
    }

    const auth = firebaseAuth();
    if (!auth) {
      setError("Authentication is not configured for this deployment yet.");
      return;
    }

    setBusy(true);
    try {
      if (signingUp) {
        await createUserWithEmailAndPassword(auth, email.trim(), password);
      } else {
        await signInWithEmailAndPassword(auth, email.trim(), password);
      }
      // App watches Firebase for the session and swaps the screen itself.
    } catch (exc) {
      const code = (exc as { code?: string })?.code ?? "";
      setError(describeAuthError(code));
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="login-shell">
      <section className="login-panel">
        <div className="login-icon">
          <ShieldCheck size={34} />
        </div>
        <p className="eyebrow">Digital Trust Shield</p>
        <h1>{signingUp ? "Create an authority account" : "Sign in to the console"}</h1>

        {!firebaseConfigured && (
          <p className="error-text">
            Firebase authentication is not configured. Set the VITE_FIREBASE_* variables
            and rebuild.
          </p>
        )}

        <form onSubmit={handleSubmit}>
          <label>
            Email
            <input
              type="email"
              autoComplete="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
            />
          </label>
          <label>
            Password
            <input
              type="password"
              autoComplete={signingUp ? "new-password" : "current-password"}
              value={password}
              onChange={(event) => setPassword(event.target.value)}
            />
          </label>
          {signingUp && (
            <label>
              Confirm password
              <input
                type="password"
                autoComplete="new-password"
                value={confirmation}
                onChange={(event) => setConfirmation(event.target.value)}
              />
            </label>
          )}

          {error && <p className="error-text">{error}</p>}

          <button className="primary-button" type="submit" disabled={busy || !firebaseConfigured}>
            {busy
              ? signingUp
                ? "Creating account..."
                : "Signing in..."
              : signingUp
                ? "Create account"
                : "Sign in"}
          </button>
        </form>

        <p className="auth-switch">
          {signingUp ? "Already have an account?" : "Need an account?"}{" "}
          <button type="button" onClick={() => onModeChange(signingUp ? "signin" : "signup")}>
            {signingUp ? "Sign in" : "Sign up"}
          </button>
        </p>
        <p className="auth-switch">
          <button type="button" onClick={onBack}>
            Back to home
          </button>
        </p>
      </section>
    </main>
  );
}
