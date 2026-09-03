import axios from "axios";

/**
 * The payout advice demonstration.
 *
 * Its own axios instance, with no auth token attached, for the same reason
 * the citizen verifier has one: a vendor deciding whether to release goods
 * has no RazorpayX account, and the whole argument is that they should not
 * need one to find out whether they are being defrauded.
 */
const client = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000",
  // Issuing renders and signs a document; verification runs the engine's
  // recovery tiers and then reads five fields. Both are slower than a
  // typical request and neither should be cut off mid-flight.
  timeout: 120000
});

export type IssuedAdvice = {
  payout_id: string;
  amount: string;
  mode: string;
  beneficiary: string;
  utr: string;
  printed: Record<string, string>;
  image_url: string;
};

export type FieldCheck = {
  name: string;
  expected: string;
  read: string;
  matched: boolean;
  confidence: number;
};

export type AdviceVerdict = {
  status: "GENUINE" | "ALTERED" | "NOT_ISSUED" | "WRONG_KEY" | "UNREADABLE";
  headline: string;
  detail: string;
  watermark_ok: boolean;
  fields: FieldCheck[];
};

export function adviceImageUrl(payoutId: string): string {
  const base = (client.defaults.baseURL ?? "").replace(/\/+$/, "");
  return `${base}/api/payout-advice/image/${payoutId}`;
}

export async function issueAdvice(): Promise<IssuedAdvice> {
  const { data } = await client.post<IssuedAdvice>(
    "/api/payout-advice/issue",
    new FormData()
  );
  return data;
}

export async function verifyAdvice(file: File, payoutId: string): Promise<AdviceVerdict> {
  const form = new FormData();
  form.append("file", file);
  form.append("payout_id", payoutId);
  const { data } = await client.post<AdviceVerdict>("/api/payout-advice/verify", form);
  return data;
}
