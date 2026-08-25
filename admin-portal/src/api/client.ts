import axios from "axios";

export const apiClient = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000",
  timeout: 120000
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
 * Build a download link that works from this browser.
 *
 * Records signed before the backend knew its own public address carry a
 * hardcoded 127.0.0.1 origin, which only resolves on the machine that signed
 * them. Where that is the case, rebuild the link from the API origin and the
 * stored path so old documents stay downloadable.
 */
export function signedFileUrl(document: {
  download_url?: string;
  signed_file_download_url?: string;
  signed_file_storage_path?: string;
}): string {
  const stored = document.download_url ?? document.signed_file_download_url ?? "";
  const isLoopback = /^https?:\/\/(127\.0\.0\.1|localhost)\b/i.test(stored);
  if (stored && !isLoopback) return stored;

  const path = (document.signed_file_storage_path ?? "").replace(/^\/+/, "");
  if (!path) return stored;

  const origin = (apiClient.defaults.baseURL ?? "").replace(/\/+$/, "");
  return `${origin}/uploads/${path}`;
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
