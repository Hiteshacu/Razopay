import { initializeApp, type FirebaseApp } from "firebase/app";
import { getAuth, type Auth } from "firebase/auth";

/**
 * Firebase client setup for operator sign-in.
 *
 * These values are not secrets. The web config identifies the project and is
 * visible in any browser that loads the app; access is controlled by Firebase
 * security rules and by the backend verifying the ID token it receives.
 */
const config = {
  apiKey: import.meta.env.VITE_FIREBASE_API_KEY,
  authDomain: import.meta.env.VITE_FIREBASE_AUTH_DOMAIN,
  projectId: import.meta.env.VITE_FIREBASE_PROJECT_ID,
  appId: import.meta.env.VITE_FIREBASE_APP_ID
};

export const firebaseConfigured = Boolean(config.apiKey && config.authDomain && config.projectId);

let app: FirebaseApp | null = null;
let auth: Auth | null = null;

if (firebaseConfigured) {
  app = initializeApp(config);
  auth = getAuth(app);
}

/** The Auth instance, or null when the project has not been configured yet. */
export function firebaseAuth(): Auth | null {
  return auth;
}

/** Turn a Firebase error code into something worth showing a person. */
export function describeAuthError(code: string): string {
  switch (code) {
    case "auth/invalid-email":
      return "That does not look like a valid email address.";
    case "auth/missing-password":
      return "Enter your password.";
    case "auth/weak-password":
      return "Choose a password of at least six characters.";
    case "auth/email-already-in-use":
      return "An account already exists for that email. Sign in instead.";
    case "auth/invalid-credential":
    case "auth/wrong-password":
    case "auth/user-not-found":
      return "That email and password combination was not recognised.";
    case "auth/too-many-requests":
      return "Too many attempts. Wait a moment and try again.";
    case "auth/network-request-failed":
      return "Could not reach the authentication service. Check your connection.";
    case "auth/operation-not-allowed":
      return "Email sign-in is not enabled for this Firebase project yet.";
    default:
      return "Sign-in failed. Please try again.";
  }
}
