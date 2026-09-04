import axios from "axios";
import { apiClient } from "./client";
import { apiBaseUrl } from "./baseUrl";

/**
 * The public half of the payout advice flow.
 *
 * Its own axios instance, with no auth token attached, for the same reason
 * the citizen verifier has one: a vendor deciding whether to release goods
 * has no RazorpayX account, and the whole argument is that they should not
 * need one to find out whether they are being defrauded.
 *
 * Issuing does not belong on it. That signs a document and files it against
 * the account that asked, so it goes through apiClient, which attaches the
 * caller's token. Sending an unauthenticated request to it fails as
 * "Sign in to continue" while the sidebar still shows you signed in, which
 * reads as a broken console rather than a missing header.
 */
const client = axios.create({
  baseURL: apiBaseUrl(),
  // Issuing renders and signs a document; verification runs the engine's
  // recovery tiers and then reads five fields. Both are slower than a
  // typical request and neither should be cut off mid-flight.
  timeout: 120000
});

export type IssuedAdvice = {
  /**
   * Set when the advice was filed as a signed document.
   *
   * Absent if the bookkeeping failed, which does not invalidate the advice —
   * it was still rendered and signed. The console falls back to the demo
   * image route so a download is still offered rather than withheld over a
   * missing record.
   */
  document_id?: string | null;
  payout_id: string;
  amount: string;
  mode: string;
  beneficiary: string;
  utr: string;
  printed: Record<string, string>;
  image_url: string;
};

export type AdviceVerdict = {
  status: "GENUINE" | "ALTERED" | "NOT_ISSUED" | "WRONG_KEY" | "UNREADABLE";
  headline: string;
  detail: string;
  /** Pixels of the file that was uploaded, so a region can be drawn on it. */
  image_width: number;
  image_height: number;
  /** False when the payload could not be read back — no claim either way. */
  measurable: boolean;
  /** Largest torn patch of carrier, in blocks. */
  blob: number;
  /**
   * Every torn patch, largest first, in the coordinates above.
   *
   * Plural because a forger who changes two figures leaves two, and showing
   * one of them points the reader away from half of what is wrong.
   */
  regions: Array<{
    left: number;
    top: number;
    right: number;
    bottom: number;
    blocks: number;
  }>;
};

export function adviceImageUrl(payoutId: string): string {
  const base = (client.defaults.baseURL ?? "").replace(/\/+$/, "");
  return `${base}/api/payout-advice/image/${payoutId}`;
}

export type AdviceRequest = {
  /** Rupees, as typed. Commas and a rupee sign are tolerated by the server. */
  amount?: string;
  beneficiary?: string;
  mode?: string;
};

/**
 * Issue a signed advice.
 *
 * Anything left out is filled from a seeded sample, so naming only the amount
 * still produces a complete document — a half-filled advice would not be a
 * fair test of a reader that has to find every field.
 */
export async function issueAdvice(request: AdviceRequest = {}): Promise<IssuedAdvice> {
  const form = new FormData();
  if (request.amount) form.append("amount", request.amount);
  if (request.beneficiary) form.append("beneficiary", request.beneficiary);
  if (request.mode) form.append("mode", request.mode);
  const { data } = await apiClient.post<IssuedAdvice>("/api/payout-advice/issue", form);
  return data;
}

/** Download an issued advice as a file, rather than opening it in a tab. */
export async function downloadAdvice(payoutId: string): Promise<void> {
  const response = await apiClient.get(`/api/payout-advice/image/${payoutId}`, {
    responseType: "blob"
  });
  const href = URL.createObjectURL(response.data as Blob);
  const anchor = window.document.createElement("a");
  anchor.href = href;
  anchor.download = `${payoutId}.png`;
  window.document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(href);
}

export async function verifyAdvice(file: File, payoutId: string): Promise<AdviceVerdict> {
  const form = new FormData();
  form.append("file", file);
  form.append("payout_id", payoutId);
  const { data } = await client.post<AdviceVerdict>("/api/payout-advice/verify", form);
  return data;
}
