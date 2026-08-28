import axios from "axios";
import { firebaseAuth } from "../firebase";

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
