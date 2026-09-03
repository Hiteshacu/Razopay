import axios from "axios";
import { apiBaseUrl } from "./baseUrl";

/**
 * The public verification API.
 *
 * Deliberately a separate axios instance from `apiClient`. That one attaches
 * the signed-in operator's token to every request, and these two endpoints are
 * open to anyone — a citizen checking a notice has no account. Sending a
 * stale or irrelevant token with a public request only invites confusion when
 * one expires.
 */
const publicClient = axios.create({
  baseURL: apiBaseUrl(),
  // Verification runs up to four recovery tiers and is deadline-bounded at 35s
  // on the server. Leave room for that plus the upload itself.
  timeout: 120000
});

export type PublicKey = {
  key_id: string;
  authority_id: string;
  authority_name: string;
  algorithm: string;
  key_size: number;
  created_at: string;
  active: boolean;
  fingerprint_sha256: string;
  /** The part of the signer's account address before the @. */
  owner_username?: string | null;
};

export type VerifyResult = {
  success: boolean;
  result: "AUTHENTIC" | "TAMPERED" | "SIGNATURE_INVALID" | "WATERMARK_NOT_FOUND" | "ERROR";
  reason: string;
  authority_name?: string | null;
  authority_id?: string | null;
  key_id?: string | null;
  details?: {
    auto_detected_key?: boolean;
    selected_key_id?: string;
    [key: string]: unknown;
  };
};

/** Every published key. Open on purpose — see the note on the endpoint. */
export async function listPublishedKeys(): Promise<PublicKey[]> {
  const { data } = await publicClient.get<PublicKey[]>("/api/keys/public");
  return data.filter((key) => key.active);
}

export async function verifyDocument(file: File, keyId: string): Promise<VerifyResult> {
  const form = new FormData();
  form.append("file", file);
  form.append("key_id", keyId);
  const { data } = await publicClient.post<VerifyResult>("/api/verify", form);
  return data;
}

/**
 * Wake the service before anyone waits on it.
 *
 * The API can be cold, and a first request that takes a minute reads as a
 * broken page. Firing this when the verifier opens overlaps the wake-up with
 * the person choosing a file.
 */
export function wakePublicApi(): void {
  const origin = (publicClient.defaults.baseURL ?? "").replace(/\/+$/, "");
  if (!origin) return;
  void fetch(`${origin}/api/ping`).catch(() => {
    /* the point is to start the wake-up, not to read the reply */
  });
}
