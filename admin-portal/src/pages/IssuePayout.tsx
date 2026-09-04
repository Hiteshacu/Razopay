import { Banknote, Download, Loader2, ShieldCheck } from "lucide-react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { useState } from "react";
import {
  adviceImageUrl,
  downloadAdvice,
  issueAdvice,
  type IssuedAdvice
} from "../api/payouts";
import { EASE_OUT } from "../motion";

const MODES = ["NEFT", "RTGS", "IMPS"] as const;

/**
 * Issue a payout advice, the way RazorpayX would.
 *
 * Laid out as the counterfoil it stands in for, because that is what the
 * reader is being asked to trust: the point of the demo is that the piece of
 * paper proves itself, and a form that looks like a form makes the signed
 * output look like a different document than the one that was filled in.
 *
 * Signing is not a second button. An advice that exists unsigned for even one
 * step is a document somebody can be handed, and the whole claim here is that
 * RazorpayX signs at the moment of issue — so the amount is typed, and what
 * comes back is already signed.
 */
export function IssuePayout() {
  const reduceMotion = useReducedMotion();

  const [amount, setAmount] = useState("");
  const [beneficiary, setBeneficiary] = useState("");
  const [mode, setMode] = useState<string>("NEFT");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [issued, setIssued] = useState<IssuedAdvice | null>(null);
  const [saving, setSaving] = useState(false);

  async function submit() {
    setError("");
    if (!amount.trim()) {
      setError("Enter the amount to pay.");
      return;
    }
    setBusy(true);
    setIssued(null);
    try {
      setIssued(await issueAdvice({ amount, beneficiary, mode }));
    } catch (exc) {
      const detail = (exc as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setError(detail ?? "Could not issue the advice. The service may be waking up — try again.");
    } finally {
      setBusy(false);
    }
  }

  async function save() {
    if (!issued) return;
    setSaving(true);
    try {
      await downloadAdvice(issued.payout_id);
    } catch {
      setError("The advice was issued, but the download failed. Try again.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="page">
      <header className="page-header">
        <p className="eyebrow">RazorpayX payouts</p>
        <h2>Issue a payout advice</h2>
        <p className="hint">
          Fill it in as a payer would. RazorpayX signs the advice as it prints it,
          so what you get back already carries its proof — there is no separate
          signing step, and no moment where an unsigned copy exists.
        </p>
      </header>

      <section className="panel">
        {/* The counterfoil. Deliberately not a plain form: the mode sits on
            the stub where it does on a real advice, because NEFT and RTGS
            settling in batches is the whole reason this document gets
            forged. */}
        <div className="cheque">
          <div className="cheque-stub">
            <span className="cheque-brand">RazorpayX</span>
            <div className="cheque-modes" role="radiogroup" aria-label="Settlement mode">
              {MODES.map((option) => (
                <button
                  key={option}
                  type="button"
                  role="radio"
                  aria-checked={mode === option}
                  className={mode === option ? "cheque-mode on" : "cheque-mode"}
                  onClick={() => setMode(option)}
                >
                  {option}
                </button>
              ))}
            </div>
            <small>
              {mode === "IMPS"
                ? "Settles instantly, around the clock."
                : "Settles in batches — minutes to hours after this advice is issued."}
            </small>
          </div>

          <div className="cheque-body">
            <label className="cheque-line">
              <span>Pay</span>
              <input
                type="text"
                value={beneficiary}
                placeholder="Beneficiary name (leave blank for a sample)"
                onChange={(event) => setBeneficiary(event.target.value)}
              />
            </label>

            <label className="cheque-line amount">
              <span>Amount</span>
              <div className="cheque-amount">
                <em>₹</em>
                <input
                  type="text"
                  inputMode="decimal"
                  value={amount}
                  placeholder="803626.45"
                  onChange={(event) => setAmount(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter") submit();
                  }}
                />
              </div>
            </label>

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
                    <Banknote size={16} aria-hidden="true" />
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
            Rendering the advice, then weaving the signature through its pixels.
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
              <div>
                <dt>Payout id</dt>
                <dd className="mono">{issued.payout_id}</dd>
              </div>
              <div>
                <dt>Amount</dt>
                <dd>₹{issued.amount}</dd>
              </div>
              <div>
                <dt>Mode</dt>
                <dd>{issued.mode}</dd>
              </div>
              <div>
                <dt>Beneficiary</dt>
                <dd>{issued.beneficiary}</dd>
              </div>
              <div>
                <dt>UTR</dt>
                <dd className="mono">{issued.utr}</dd>
              </div>
            </dl>

            <img
              className="advice-preview"
              src={adviceImageUrl(issued.payout_id)}
              alt={`Signed payout advice ${issued.payout_id}`}
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
                  <span>Download the signed advice</span>
                </>
              )}
            </motion.button>

            <p className="hint">
              Keep the payout id. Checking this advice compares what is printed on
              it against the record kept here when it was issued, and the id is how
              that record is found.
            </p>
          </motion.section>
        )}
      </AnimatePresence>
    </div>
  );
}
