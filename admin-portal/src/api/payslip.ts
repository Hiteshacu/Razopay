import axios from "axios";
import { apiBaseUrl } from "./baseUrl";
import { apiClient } from "./client";
import type { AdviceVerdict } from "./payouts";

/**
 * The public half of the payslip flow.
 *
 * Its own instance with no token, like the payout verifier: the party who
 * needs to know whether a salary is real — a lender, a landlord, a background
 * check — is exactly the party with no account here. Issuing goes through
 * apiClient instead, because what it signs is filed against an account.
 */
const publicClient = axios.create({
  baseURL: apiBaseUrl(),
  timeout: 120000
});

export type IssuedPayslip = {
  slip_id: string;
  employee: string;
  employee_id: string;
  period: string;
  employer: string;
  net: string;
  gross: string;
  deductions: string;
  printed: Record<string, string>;
  image_url: string;
  document_id?: string | null;
};

/**
 * A payslip verdict is an advice verdict.
 *
 * Both come from the same adjudicator over a different field set, so they are
 * the same shape by construction rather than by coincidence. Declaring it once
 * and re-exporting keeps the verdict renderer able to take either without a
 * cast, and means a change to one cannot silently diverge from the other.
 */
export type { AdviceVerdict as PayslipVerdict } from "./payouts";

export type PayslipRequest = {
  employee: string;
  net?: string;
  period?: string;
  employer?: string;
};

export function payslipImageUrl(slipId: string): string {
  const base = (publicClient.defaults.baseURL ?? "").replace(/\/+$/, "");
  return `${base}/api/payslip/image/${slipId}`;
}

export async function issuePayslip(request: PayslipRequest): Promise<IssuedPayslip> {
  const form = new FormData();
  form.append("employee", request.employee);
  if (request.net) form.append("net", request.net);
  if (request.period) form.append("period", request.period);
  if (request.employer) form.append("employer", request.employer);
  const { data } = await apiClient.post<IssuedPayslip>("/api/payslip/issue", form);
  return data;
}

export async function verifyPayslip(file: File, slipId: string): Promise<AdviceVerdict> {
  const form = new FormData();
  form.append("file", file);
  form.append("slip_id", slipId);
  const { data } = await publicClient.post<AdviceVerdict>("/api/payslip/verify", form);
  return data;
}
