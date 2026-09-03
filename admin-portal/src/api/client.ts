import axios from "axios";
import { firebaseAuth } from "../firebase";

/**
 * The message to show a person when a request fails.
 *
 * FastAPI reports errors two different ways and the console has to read both.
 * A raised HTTPException puts a plain string in `detail`; a request that fails
 * schema validation puts a *list* of field errors there instead. Reading only
 * the string case meant every validation failure — a malformed address, a name
 * one character too short — arrived as the generic fallback, which tells the
 * operator nothing about which field to fix.
 */
export function apiErrorMessage(exc: unknown, fallback: string): string {
  if (!axios.isAxiosError(exc)) return fallback;

  if (exc.code === "ECONNABORTED") {
    return "The server took too long to answer. It may be waking up — try again.";
  }
  if (!exc.response) {
    return "Could not reach the server. Check your connection and try again.";
  }

  const detail = exc.response.data?.detail;
  if (typeof detail === "string" && detail.trim()) return detail;

  if (Array.isArray(detail)) {
    // ["body", "email"] -> "email"; the last segment is the field itself.
    const parts = detail
      .map((item) => {
        const field = Array.isArray(item?.loc) ? String(item.loc[item.loc.length - 1]) : "";
        const message = String(item?.msg ?? "").replace(/^Value error, /, "");
        return field && message ? `${field}: ${message}` : message;
      })
      .filter(Boolean);
    if (parts.length) return parts.join(" · ");
  }

  return fallback;
}

export const apiClient = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000",
  timeout: 120000
});

/**
 * Attach the signed-in operator's Firebase ID token to every request.
 *
 * getIdToken() returns the cached token and refreshes it automatically when
 * it is close to expiry, so a long session does not start failing an hour in.
 */
apiClient.interceptors.request.use(async (config) => {
  const user = firebaseAuth()?.currentUser;
  if (user) {
    const token = await user.getIdToken();
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

/**
 * Nudge the service awake without waiting for the answer.
 *
 * An idle instance sleeps and needs the better part of a minute to serve its
 * first request. Sending this the moment the page opens means the wake-up
 * overlaps with the operator reading the login screen and typing, instead of
 * happening afterwards while they stare at an empty dashboard.
 */
export function wakeService(): void {
  const origin = (apiClient.defaults.baseURL ?? "").replace(/\/+$/, "");
  if (!origin) return;
  void fetch(`${origin}/api/health`).catch(() => {
    /* the point is to start the wake-up, not to read the reply */
  });
}

/**
 * Download a signed document.
 *
 * The file is fetched rather than linked to. A signed document is only
 * visible to the account that signed it (or to an administrator), and that
 * check lives behind an Authorization header the browser will not attach to
 * a plain <a href>. So the bytes are pulled with the session's token and
 * handed to the browser as a blob.
 *
 * Documents are ~1.6 MB, small enough that holding one in memory briefly is
 * not worth the complexity of a streaming save.
 */
export async function downloadSignedFile(document: {
  document_id: string;
  signed_filename?: string;
}): Promise<void> {
  const response = await apiClient.get(
    `/api/documents/${encodeURIComponent(document.document_id)}/file`,
    { responseType: "blob" }
  );

  const href = URL.createObjectURL(response.data as Blob);
  const anchor = window.document.createElement("a");
  anchor.href = href;
  anchor.download = document.signed_filename ?? `${document.document_id}.png`;
  window.document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  // Revoking immediately can cancel the save in some browsers; one turn of
  // the event loop is enough for the click to have been taken.
  window.setTimeout(() => URL.revokeObjectURL(href), 0);
}

export type Authority = {
  authority_id: string;
  authority_name: string;
  department: string;
  email: string;
  created_at: string;
  status: string;
};

export type PublicKey = {
  key_id: string;
  authority_id: string;
  authority_name: string;
  public_key_pem: string;
  algorithm: string;
  key_size: number;
  created_at: string;
  active: boolean;
  fingerprint_sha256: string;
};

export type SignedDocument = {
  document_id: string;
  authority_id: string;
  authority_name: string;
  public_key_id?: string;
  key_id: string;
  original_filename: string;
  signed_filename?: string;
  file_type: string;
  visual_fingerprint_hash?: string;
  signed_by_email?: string;
  signed_by_uid?: string;
  storage_type?: string;
  download_url?: string;
  signed_file_download_url: string;
  signed_file_storage_path: string;
  created_at: string;
  signature_status?: string;
  status: string;
};

export type AuditLog = {
  event_type: string;
  actor?: string;
  authority_id?: string;
  key_id?: string;
  document_id?: string;
  timestamp: string;
  details?: Record<string, unknown>;
  previous_hash?: string;
  current_hash?: string;
};
