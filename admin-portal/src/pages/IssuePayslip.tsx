import { Download, FileBadge, Loader2, ShieldCheck } from "lucide-react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { useState } from "react";
import { downloadSignedFile } from "../api/client";
import {
  issuePayslip,
  payslipImageUrl,
  type IssuedPayslip
} from "../api/payslip";
import { EASE_OUT } from "../motion";

/**
 * Issue a payslip, the way RazorpayX Payroll would.
 *
 * Only the name is required. A payslip is checked by somebody the employee is
 * asking for something — a lender, a landlord, a background check — and the
 * name is what ties the document to the person standing in front of them, so
 * it is the one field the issuer must be told. Everything else is filled from
 * a sample, because a half-filled payslip is not a fair test of a reader that
 * has to find every field.
 */
export function IssuePayslip() {
  const reduceMotion = useReducedMotion();

  const [employee, setEmployee] = useState("");
  const [net, setNet] = useState("");
  const [period, setPeriod] = useState("");
  const [employer, setEmployer] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [issued, setIssued] = useState<IssuedPayslip | null>(null);
  const [saving, setSaving] = useState(false);

  async function submit() {
    setError("");
    if (!employee.trim()) {
      setError("Enter the employee's name.");
      return;
    }
    setBusy(true);
    setIssued(null);
    try {
      setIssued(await issuePayslip({ employee, net, period, employer }));
    } catch (exc) {
      const detail = (exc as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setError(detail ?? "Could not issue the payslip. The service may be waking up — try again.");
    } finally {
      setBusy(false);
    }
  }

  async function save() {
    if (!issued) return;
    setSaving(true);
    try {
      // Through the document route when it was filed, so the same per-account
      // rule decides who may take it as for everything else signed here.
      if (issued.document_id) {
        await downloadSignedFile({
          document_id: issued.document_id,
          signed_filename: `${issued.slip_id}.png`
        });
      } else {
        window.open(payslipImageUrl(issued.slip_id), "_blank", "noopener");
      }
    } catch {
      setError("The payslip was issued, but the download failed. Try again.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="page">
      <header className="page-header">
        <p className="eyebrow">RazorpayX Payroll</p>
        <h2>Issue a payslip</h2>
        <p className="hint">
          A lender, a landlord or a background check has no channel to a payroll
          system — Account Aggregator carries data from regulated financial
          institutions, and an employer is not one. So a payslip is trusted on
          sight, or not at all. RazorpayX Payroll signs this one as it prints it.
        </p>
      </header>

      <section className="panel">
        <div className="cheque">
          <div className="cheque-stub">
            <span className="cheque-brand">RazorpayX</span>
            <span className="slip-kind">Payroll</span>
            <small>
              Net pay is the number a lender multiplies to decide what someone
              can borrow, so it is the number a forger changes first.
            </small>
          </div>

          <div className="cheque-body">
            <label className="cheque-line">
              <span>Employee</span>
              <input
                type="text"
                value={employee}
                placeholder="Full name, as printed"
                onChange={(event) => setEmployee(event.target.value)}
              />
            </label>

            <label className="cheque-line amount">
              <span>Net pay</span>
              <div className="cheque-amount">
                <em>₹</em>
                <input
                  type="text"
                  inputMode="decimal"
                  value={net}
                  placeholder="53387.10"
                  onChange={(event) => setNet(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter") submit();
                  }}
                />
              </div>
            </label>

            <div className="slip-row">
              <label className="cheque-line">
                <span>Pay period</span>
                <input
                  type="text"
                  value={period}
                  placeholder="March 2026"
                  onChange={(event) => setPeriod(event.target.value)}
                />
              </label>
              <label className="cheque-line">
                <span>Employer</span>
                <input
                  type="text"
                  value={employer}
                  placeholder="Leave blank for a sample"
                  onChange={(event) => setEmployer(event.target.value)}
                />
              </label>
            </div>

            <div className="cheque-foot">
              <span className="cheque-specimen">SPECIMEN</span>
              <motion.button
                className="primary-button"
                onClick={submit}
                disabled={busy}
                whileHover={reduceMotion || busy ? undefined : { y: -1 }}
                whileTap={reduceMotion || busy ? undefined : { scale: 0.98 }}
              >
                {busy ? (
                  <>
                    <Loader2 size={16} className="spin" aria-hidden="true" />
                    <span>Signing…</span>
                  </>
                ) : (
                  <>
                    <FileBadge size={16} aria-hidden="true" />
                    <span>Issue and sign</span>
                  </>
                )}
              </motion.button>
            </div>
          </div>
        </div>

        {error && <p className="error-text">{error}</p>}
        {busy && (
          <p className="hint centered">
            Rendering the payslip, then weaving the signature through its pixels.
            This takes a few seconds on the free tier.
          </p>
        )}
      </section>

      <AnimatePresence>
        {issued && (
          <motion.section
            className="panel"
            initial={reduceMotion ? { opacity: 0 } : { opacity: 0, y: 14 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.4, ease: EASE_OUT }}
          >
            <h3>
              <ShieldCheck size={17} aria-hidden="true" /> Issued and signed
            </h3>

            <dl className="verdict-facts">
              <div><dt>Slip id</dt><dd className="mono">{issued.slip_id}</dd></div>
              <div><dt>Employee</dt><dd>{issued.employee}</dd></div>
              <div><dt>Employee ID</dt><dd className="mono">{issued.employee_id}</dd></div>
              <div><dt>Pay period</dt><dd>{issued.period}</dd></div>
              <div><dt>Net pay</dt><dd>₹{issued.net}</dd></div>
              <div><dt>Gross</dt><dd>₹{issued.gross}</dd></div>
              <div><dt>Deductions</dt><dd>₹{issued.deductions}</dd></div>
              <div><dt>Employer</dt><dd>{issued.employer}</dd></div>
            </dl>

            <img
              className="advice-preview"
              src={payslipImageUrl(issued.slip_id)}
              alt={`Signed payslip ${issued.slip_id}`}
            />

            <motion.button
              className="primary-button"
              onClick={save}
              disabled={saving}
              whileHover={reduceMotion || saving ? undefined : { y: -1 }}
              whileTap={reduceMotion || saving ? undefined : { scale: 0.98 }}
            >
              {saving ? (
                <>
                  <Loader2 size={16} className="spin" aria-hidden="true" />
                  <span>Preparing…</span>
                </>
              ) : (
                <>
                  <Download size={16} aria-hidden="true" />
                  <span>Download the signed payslip</span>
                </>
              )}
            </motion.button>

            <p className="hint">
              Keep the slip id. Checking this payslip compares what is printed on
              it against the record kept here when it was issued, and the id is
              how that record is found.
            </p>
          </motion.section>
        )}
      </AnimatePresence>
    </div>
  );
}
