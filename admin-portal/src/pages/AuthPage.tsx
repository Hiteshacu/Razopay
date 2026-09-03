import { ShieldCheck } from "lucide-react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
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
  const reduceMotion = useReducedMotion();
  const ease = [0.22, 1, 0.36, 1] as const;

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
      <motion.section
        className="login-panel"
        initial={{ opacity: 0, y: reduceMotion ? 0 : 16, scale: reduceMotion ? 1 : 0.98 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        transition={{ duration: 0.45, ease }}
      >
        <motion.div
          className="login-icon"
          initial={{ opacity: 0, scale: reduceMotion ? 1 : 0.6 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: 0.5, delay: 0.08, ease }}
        >
          <ShieldCheck size={34} />
        </motion.div>
        <p className="eyebrow">PayProof</p>
        <AnimatePresence mode="wait" initial={false}>
          <motion.h1
            key={mode}
            initial={{ opacity: 0, y: reduceMotion ? 0 : 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: reduceMotion ? 0 : -8 }}
            transition={{ duration: 0.22, ease }}
          >
            {signingUp ? "Create an authority account" : "Sign in to the console"}
          </motion.h1>
        </AnimatePresence>

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
          <AnimatePresence initial={false}>
            {signingUp && (
              <motion.label
                key="confirm"
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: "auto" }}
                exit={{ opacity: 0, height: 0 }}
                transition={{ duration: reduceMotion ? 0 : 0.24, ease }}
                style={{ overflow: "hidden" }}
              >
                Confirm password
                <input
                  type="password"
                  autoComplete="new-password"
                  value={confirmation}
                  onChange={(event) => setConfirmation(event.target.value)}
                />
              </motion.label>
            )}
          </AnimatePresence>

          <AnimatePresence>
            {error && (
              <motion.p
                className="error-text"
                role="alert"
                initial={{ opacity: 0, y: reduceMotion ? 0 : -6 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.2, ease }}
              >
                {error}
              </motion.p>
            )}
          </AnimatePresence>

          <motion.button
            className="primary-button"
            type="submit"
            disabled={busy || !firebaseConfigured}
            whileHover={reduceMotion || busy ? undefined : { y: -2 }}
            whileTap={reduceMotion || busy ? undefined : { scale: 0.98 }}
          >
            {busy
              ? signingUp
                ? "Creating account..."
                : "Signing in..."
              : signingUp
                ? "Create account"
                : "Sign in"}
          </motion.button>
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
      </motion.section>
    </main>
  );
}
