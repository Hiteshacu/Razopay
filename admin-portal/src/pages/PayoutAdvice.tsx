import {
  AlertTriangle,
  ArrowLeft,
  CheckCircle2,
  Download,
  FileText,
  HelpCircle,
  Loader2,
  Upload,
  XCircle
} from "lucide-react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { useEffect, useRef, useState } from "react";
import {
  adviceImageUrl,
  issueAdvice,
  verifyAdvice,
  type AdviceVerdict,
  type IssuedAdvice
} from "../api/payouts";
import { EASE_OUT } from "../motion";

const TONES: Record<AdviceVerdict["status"], {
  tone: "ok" | "warn" | "bad" | "dim";
  icon: typeof CheckCircle2;
}> = {
  GENUINE: { tone: "ok", icon: CheckCircle2 },
  ALTERED: { tone: "warn", icon: AlertTriangle },
  NOT_ISSUED: { tone: "dim", icon: HelpCircle },
  WRONG_KEY: { tone: "bad", icon: XCircle },
  UNREADABLE: { tone: "dim", icon: HelpCircle }
};

const FIELD_LABELS: Record<string, string> = {
  hero_amount: "Amount (headline)",
  table_amount: "Amount (table)",
  utr: "UTR / reference",
  beneficiary: "Beneficiary",
  account: "Account number"
};

/**
 * The RazorpayX payout advice demonstration.
 *
 * Two halves, in the order the fraud happens. RazorpayX issues a signed
 * advice; a vendor receives one and has to decide whether to release goods
 * before the money has actually settled — NEFT and RTGS clear in batches, so
 * "check your bank" does not answer the question at the moment it is asked.
 */
export function PayoutAdvice({ onBack }: { onBack: () => void }) {
  const reduceMotion = useReducedMotion();
  const fileInput = useRef<HTMLInputElement | null>(null);

  const [issued, setIssued] = useState<IssuedAdvice | null>(null);
  const [issuing, setIssuing] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [verdict, setVerdict] = useState<AdviceVerdict | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!file) {
      setPreview(null);
      return;
    }
    const url = URL.createObjectURL(file);
    setPreview(url);
    return () => URL.revokeObjectURL(url);
  }, [file]);

  async function issue() {
    setIssuing(true);
    setError("");
    setVerdict(null);
    setFile(null);
    try {
      setIssued(await issueAdvice());
    } catch {
      setError("Could not issue an advice. The service may still be starting up.");
    } finally {
      setIssuing(false);
    }
  }

  async function run() {
    if (!file || !issued) return;
    setBusy(true);
    setError("");
    try {
      setVerdict(await verifyAdvice(file, issued.payout_id));
    } catch {
      setError("The check could not be completed. Try again in a moment.");
    } finally {
      setBusy(false);
    }
  }

  const shape = verdict ? TONES[verdict.status] ?? TONES.UNREADABLE : null;
  const VerdictIcon = shape?.icon ?? HelpCircle;

  return (
    <div className="verify-page">
      <header className="verify-bar">
        <button className="back-link" onClick={onBack}>
          <ArrowLeft size={15} aria-hidden="true" />
          <span>Back</span>
        </button>
        <span className="verify-badge">RazorpayX payout advice</span>
      </header>

      <div className="verify-inner">
        <motion.div
          initial={reduceMotion ? false : { opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.45, ease: EASE_OUT }}
        >
          <p className="eyebrow">Payout advice</p>
          <h1 className="verify-title">Did RazorpayX really send this money?</h1>
          <p className="verify-lede">
            NEFT and RTGS settle in batches, so a vendor asked to release goods
            against a payout advice cannot confirm it by checking their own bank —
            the credit legitimately has not arrived yet. That gap is where the
            fraud lives. This checks the advice itself.
          </p>
        </motion.div>

        {error && <p className="error-text">{error}</p>}

        {/* ---- 1. issue ---- */}
        <section className="panel">
          <h2><span className="vstep">1</span> RazorpayX issues an advice</h2>
          <p className="hint no-top">
            Signed as it is generated. The proof lives in the pixels, so it
            survives being screenshotted and forwarded.
          </p>
          <motion.button
            className="primary-button lg verify-go"
            onClick={issue}
            disabled={issuing}
            whileHover={reduceMotion || issuing ? undefined : { y: -1 }}
            whileTap={reduceMotion || issuing ? undefined : { scale: 0.99 }}
          >
            {issuing ? (
              <>
                <Loader2 size={17} className="spin" aria-hidden="true" />
                <span>Rendering and signing…</span>
              </>
            ) : (
              <>
                <FileText size={17} aria-hidden="true" />
                <span>{issued ? "Issue another advice" : "Issue a signed advice"}</span>
              </>
            )}
          </motion.button>

          {issued && (
            <motion.div
              className="advice-issued"
              initial={reduceMotion ? false : { opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.4, ease: EASE_OUT }}
            >
              <dl className="verdict-facts">
                <div><dt>Payout</dt><dd className="mono">{issued.payout_id}</dd></div>
                <div><dt>Amount</dt><dd><strong>Rs {issued.amount}</strong></dd></div>
                <div><dt>Mode</dt><dd>{issued.mode}</dd></div>
                <div><dt>To</dt><dd>{issued.beneficiary}</dd></div>
                <div><dt>UTR</dt><dd className="mono">{issued.utr}</dd></div>
              </dl>
              <img
                className="advice-preview"
                src={adviceImageUrl(issued.payout_id)}
                alt="The issued payout advice"
              />
              <a
                className="ghost-button"
                href={adviceImageUrl(issued.payout_id)}
                download={`${issued.payout_id}.png`}
              >
                <Download size={15} aria-hidden="true" />
                <span>Download it</span>
              </a>
            </motion.div>
          )}
        </section>

        {/* ---- 2. check ---- */}
        <section className="panel">
          <h2><span className="vstep">2</span> A vendor checks what they were sent</h2>
          {!issued ? (
            <p className="hint no-top">Issue an advice above first.</p>
          ) : (
            <>
              <p className="hint no-top">
                Upload the advice you received. Download the one above and send it
                straight back to see a genuine result — or edit the amount in any
                image editor first, and see what happens.
              </p>
              <input
                ref={fileInput}
                type="file"
                accept="image/png,image/jpeg"
                hidden
                onChange={(event) => {
                  setFile(event.target.files?.[0] ?? null);
                  setVerdict(null);
                }}
              />
              <button
                type="button"
                className={`dropzone${file ? " has-file" : ""}`}
                onClick={() => fileInput.current?.click()}
                onDragOver={(event) => event.preventDefault()}
                onDrop={(event) => {
                  event.preventDefault();
                  setFile(event.dataTransfer.files?.[0] ?? null);
                  setVerdict(null);
                }}
              >
                {preview ? (
                  <img src={preview} alt="" className="dropzone-preview" />
                ) : (
                  <Upload size={26} aria-hidden="true" />
                )}
                <strong>{file ? file.name : "Choose the advice, or drag it here"}</strong>
                <small>{file ? "Tap to choose a different one" : "PNG or JPG"}</small>
              </button>

              <motion.button
                className="primary-button lg verify-go"
                disabled={!file || busy}
                onClick={run}
                whileHover={reduceMotion || busy ? undefined : { y: -1 }}
                whileTap={reduceMotion || busy ? undefined : { scale: 0.99 }}
              >
                {busy ? (
                  <>
                    <Loader2 size={17} className="spin" aria-hidden="true" />
                    <span>Reading the figures…</span>
                  </>
                ) : (
                  <span>Check this advice</span>
                )}
              </motion.button>
            </>
          )}
        </section>

        <AnimatePresence>
          {verdict && shape && (
            <motion.section
              className={`verdict tone-${shape.tone}`}
              initial={reduceMotion ? { opacity: 0 } : { opacity: 0, y: 14 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.4, ease: EASE_OUT }}
            >
              <div className="verdict-head">
                <VerdictIcon size={30} aria-hidden="true" />
                <div>
                  <strong>{verdict.headline}</strong>
                  <code>{verdict.status}</code>
                </div>
              </div>
              <p className="verdict-plain">{verdict.detail}</p>

              {verdict.fields.length > 0 && (
                <div className="field-checks">
                  {verdict.fields.map((f) => (
                    <div key={f.name} className={f.matched ? "fc ok" : "fc bad"}>
                      <span className="fc-name">{FIELD_LABELS[f.name] ?? f.name}</span>
                      {f.matched ? (
                        <span className="fc-state">matches what was issued</span>
                      ) : (
                        <span className="fc-state">
                          issued as <strong>{f.expected}</strong>, document says{" "}
                          <strong>{f.read}</strong>
                        </span>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </motion.section>
          )}
        </AnimatePresence>

        <p className="verify-foot">
          The embedded signature proves RazorpayX issued the advice and survives a
          screenshot, but its page fingerprint tolerates a repainted figure — a
          measured 1.98% edit still verified. So the printed values are read back
          and compared against the issuance record. Measured on a held-out set:
          every forgery rejected, no genuine advice falsely accused, and a
          photographed screen is refused rather than guessed at.
        </p>
      </div>
    </div>
  );
}
