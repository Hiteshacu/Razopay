import {
  AlertTriangle,
  ArrowLeft,
  CheckCircle2,
  HelpCircle,
  Loader2,
  Upload,
  XCircle
} from "lucide-react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { useEffect, useMemo, useRef, useState } from "react";
import { verifyAdvice, type AdviceVerdict } from "../api/payouts";
import {
  listPublishedKeys,
  verifyDocument,
  wakePublicApi,
  type PublicKey,
  type VerifyResult
} from "../api/verify";
import { EASE_OUT } from "../motion";

/** How each verdict should be presented. */
const VERDICTS: Record<
  string,
  { tone: "ok" | "warn" | "bad" | "dim"; icon: typeof CheckCircle2; headline: string; plain: string }
> = {
  AUTHENTIC: {
    tone: "ok",
    icon: CheckCircle2,
    headline: "Genuine",
    // Says what was actually checked. It used to claim "nothing in it has
    // changed since", which is more than this test establishes: the content
    // check compares a perceptual fingerprint, and a measured 1% edit — an
    // account number — does not move that fingerprint past its tolerance.
    // Claiming more than the mathematics supports is the one thing a trust
    // product cannot do.
    plain:
      "This document carries that authority's signature, and its content matches the version they signed."
  },
  TAMPERED: {
    tone: "warn",
    icon: AlertTriangle,
    headline: "Issued, then altered",
    plain:
      "The signature is real — this authority did issue this document. But the picture no longer matches what they signed. Something in it has been edited."
  },
  SIGNATURE_INVALID: {
    tone: "bad",
    icon: XCircle,
    headline: "Not signed by this authority",
    plain:
      "A proof is present, but it does not belong to the authority you chose. Either the wrong one was selected, or this document is not what it claims to be."
  },
  WATERMARK_NOT_FOUND: {
    tone: "dim",
    icon: HelpCircle,
    headline: "No proof found",
    plain:
      "This document carries no PayProof signature. It was either never signed, or damaged past recovery — a heavy crop, or a photo of a screen."
  },
  ERROR: {
    tone: "dim",
    icon: HelpCircle,
    headline: "Could not check this file",
    plain: "Something went wrong while reading the document."
  }
};

/**
 * Public verification, in a browser.
 *
 * The same three steps as the app — the file, who signed it, which of their
 * authorities — because the order matters. Checking against a key nobody chose
 * produces a failure that reads exactly like a forgery, so naming the signer
 * first is what makes a negative answer mean anything.
 *
 * No account, no install. Someone handed a suspicious notice should be able to
 * check it from the link they were sent.
 */
export function Verify({ onBack }: { onBack: () => void }) {
  const reduceMotion = useReducedMotion();
  const fileInput = useRef<HTMLInputElement | null>(null);

  const [keys, setKeys] = useState<PublicKey[]>([]);
  const [loadError, setLoadError] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [signer, setSigner] = useState("");
  const [selectedKeyId, setSelectedKeyId] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<VerifyResult | null>(null);
  const [failed, setFailed] = useState("");
  // RazorpayX mode. A payout advice is checked against the record RazorpayX
  // kept when it issued it, which is a different question from "did this key
  // sign this file" and needs no key chosen: RazorpayX signs its own advices,
  // so naming a signer would be asking the reader something already known.
  const [razorpayMode, setRazorpayMode] = useState(false);
  const [payoutId, setPayoutId] = useState("");
  const [adviceVerdict, setAdviceVerdict] = useState<AdviceVerdict | null>(null);

  useEffect(() => {
    wakePublicApi();
    listPublishedKeys()
      .then(setKeys)
      .catch(() =>
        setLoadError("Could not reach the verification service. It may be starting up — try again in a moment.")
      );
  }, []);

  // Revoke the object URL when the picture changes, or the tab leaks memory
  // one image at a time.
  useEffect(() => {
    if (!file) {
      setPreview(null);
      return;
    }
    const url = URL.createObjectURL(file);
    setPreview(url);
    return () => URL.revokeObjectURL(url);
  }, [file]);

  /**
   * Keys held by whoever the typed name matches.
   *
   * A blank name matches nothing, deliberately: a document checked against an
   * arbitrary key tells you nothing, and a failure would look like a forgery.
   */
  const matches = useMemo(() => {
    const query = signer.trim().toLowerCase();
    if (!query) return [];
    return keys.filter((key) => (key.owner_username ?? "").includes(query));
  }, [keys, signer]);

  const signers = useMemo(
    () => [...new Set(matches.map((k) => k.owner_username).filter(Boolean))] as string[],
    [matches]
  );

  // Settle on a key only when there is no choice to make.
  useEffect(() => {
    setSelectedKeyId(matches.length === 1 ? matches[0].key_id : "");
    setResult(null);
  }, [matches]);

  function pick(next: File | null) {
    setFile(next);
    setResult(null);
    setAdviceVerdict(null);
    setFailed("");
    // An issued advice downloads as <payout_id>.png, so the id is usually
    // already in the reader's hand. Filling it saves them copying a string
    // off the page, and it stays editable because a file can be renamed.
    const stem = (next?.name ?? "").replace(/\.[^.]+$/, "");
    if (/^[A-Za-z0-9_]{6,}$/.test(stem)) setPayoutId(stem);
  }

  async function runAdvice() {
    if (!file || !payoutId.trim()) return;
    setBusy(true);
    setResult(null);
    setAdviceVerdict(null);
    setFailed("");
    try {
      setAdviceVerdict(await verifyAdvice(file, payoutId.trim()));
    } catch (exc) {
      const detail = (exc as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setFailed(detail ?? "The check could not be completed. Try again.");
    } finally {
      setBusy(false);
    }
  }

  async function run() {
    if (!file || !selectedKeyId) return;
    setBusy(true);
    setResult(null);
    setAdviceVerdict(null);
    setFailed("");
    try {
      setResult(await verifyDocument(file, selectedKeyId));
    } catch {
      setFailed("The check could not be completed. The service may be waking up — try again.");
    } finally {
      setBusy(false);
    }
  }

  const verdict = result ? VERDICTS[result.result] ?? VERDICTS.ERROR : null;
  const VerdictIcon = verdict?.icon ?? HelpCircle;
  const autoDetected = Boolean(result?.details?.auto_detected_key);

  return (
    <div className="verify-page">
      <header className="verify-bar">
        <button className="back-link" onClick={onBack}>
          <ArrowLeft size={15} aria-hidden="true" />
          <span>Back</span>
        </button>
        <span className="verify-badge">No account needed</span>
      </header>

      <div className="verify-inner">
        <motion.div
          initial={reduceMotion ? false : { opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.45, ease: EASE_OUT }}
        >
          <p className="eyebrow">Verify a document</p>
          <h1 className="verify-title">Is this notice genuine?</h1>
          <p className="verify-lede">
            Upload the image you were sent, say who it claims to be from, and check
            it. Nothing is stored, and you do not need an account.
          </p>
        </motion.div>

        {loadError && <p className="error-text">{loadError}</p>}

        {/* The one switch that changes what question is being asked. */}
        <div className="rzp-switch">
          <label>
            <input
              type="checkbox"
              checked={razorpayMode}
              onChange={(event) => {
                setRazorpayMode(event.target.checked);
                setResult(null);
                setAdviceVerdict(null);
                setFailed("");
              }}
            />
            <span className="rzp-track" aria-hidden="true"><i /></span>
            <span className="rzp-label">
              <strong>RazorpayX payout advice</strong>
              <small>
                Checks it against the record RazorpayX kept when it issued it, using
                RazorpayX's own key. No signer or key to choose.
              </small>
            </span>
          </label>
        </div>

        {/* ---- 1. the document ---- */}
        <section className="panel">
          <h2><span className="vstep">1</span> The document</h2>
          <input
            ref={fileInput}
            type="file"
            accept="image/png,image/jpeg,application/pdf"
            hidden
            onChange={(event) => pick(event.target.files?.[0] ?? null)}
          />
          <button
            type="button"
            className={`dropzone${file ? " has-file" : ""}`}
            onClick={() => fileInput.current?.click()}
            onDragOver={(event) => event.preventDefault()}
            onDrop={(event) => {
              event.preventDefault();
              pick(event.dataTransfer.files?.[0] ?? null);
            }}
          >
            {preview && file?.type.startsWith("image/") ? (
              <img src={preview} alt="" className="dropzone-preview" />
            ) : (
              <Upload size={26} aria-hidden="true" />
            )}
            <strong>{file ? file.name : "Choose an image, or drag one here"}</strong>
            <small>{file ? "Tap to choose a different one" : "PNG, JPG or PDF"}</small>
          </button>
        </section>

        {razorpayMode && (
          <section className="panel">
            <h2><span className="vstep">2</span> Which payout?</h2>
            <p className="hint no-top">
              The payout id printed on the advice. An advice downloaded from the
              console is named after it, so choosing the file usually fills this in.
            </p>
            <input
              className="verify-input"
              type="text"
              value={payoutId}
              placeholder="e.g. pout_4f2c9a1b"
              autoComplete="off"
              spellCheck={false}
              onChange={(event) => setPayoutId(event.target.value)}
            />
          </section>
        )}

        {/* Both steps belong to the generic path only: in RazorpayX mode
            the key is RazorpayX's own and there is nothing to pick. */}
        {!razorpayMode && (
          <>
          {/* ---- 2. who signed it ---- */}
          <section className="panel">
            <h2><span className="vstep">2</span> Who signed it?</h2>
            <p className="hint no-top">
              The name of the office or person it claims to be from. Checking against
              the wrong authority looks the same as a forgery, so this has to be named.
            </p>
            <input
              className="verify-input"
              type="text"
              value={signer}
              placeholder="e.g. pramila"
              autoComplete="off"
              spellCheck={false}
              onChange={(event) => setSigner(event.target.value)}
              disabled={keys.length === 0}
            />
            {signer.trim() && (
              <p className={signers.length ? "match-found" : "match-none"}>
                {signers.length
                  ? `${signers.join(", ")} — ${matches.length} key${matches.length === 1 ? "" : "s"}`
                  : `No signer named "${signer.trim()}"`}
              </p>
            )}
          </section>

          {/* ---- 3. which authority ---- */}
          <section className="panel">
            <h2><span className="vstep">3</span> Which authority?</h2>
            {matches.length === 0 ? (
              <p className="hint no-top">
                {signer.trim() ? "Nothing to choose — no keys for that name." : "Enter a name above first."}
              </p>
            ) : (
              <div className="authority-list">
                {matches.map((key) => (
                  <label key={key.key_id} className={selectedKeyId === key.key_id ? "authority sel" : "authority"}>
                    <input
                      type="radio"
                      name="authority"
                      checked={selectedKeyId === key.key_id}
                      onChange={() => {
                        setSelectedKeyId(key.key_id);
                        setResult(null);
                      }}
                    />
                    <span>
                      <strong>{key.authority_name}</strong>
                      <small>{key.key_id} · {key.algorithm}</small>
                    </span>
                  </label>
                ))}
              </div>
            )}
          </section>
          </>
        )}

        <motion.button
          className="primary-button lg verify-go"
          disabled={busy || !file || (razorpayMode ? !payoutId.trim() : !selectedKeyId)}
          onClick={razorpayMode ? runAdvice : run}
          whileHover={reduceMotion || busy ? undefined : { y: -1 }}
          whileTap={reduceMotion || busy ? undefined : { scale: 0.99 }}
        >
          {busy ? (
            <>
              <Loader2 size={17} className="spin" aria-hidden="true" />
              <span>Checking the pixels…</span>
            </>
          ) : (
            <span>{razorpayMode ? "Check this payout advice" : "Verify this document"}</span>
          )}
        </motion.button>

        {busy && (
          <p className="hint centered">
            Reading the signature out of the image. This can take up to half a minute.
          </p>
        )}
        {failed && <p className="error-text">{failed}</p>}

        {/* The advice verdict is its own shape: it carries per-field evidence,
            which the generic result has no equivalent for. */}
        <AnimatePresence>
          {adviceVerdict && (
            <motion.section
              className={`verdict tone-${
                adviceVerdict.status === "GENUINE"
                  ? "ok"
                  : adviceVerdict.status === "ALTERED"
                    ? "warn"
                    : adviceVerdict.status === "NOT_ISSUED"
                      ? "bad"
                      : "dim"
              }`}
              initial={reduceMotion ? { opacity: 0 } : { opacity: 0, y: 14 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.4, ease: EASE_OUT }}
            >
              <div className="verdict-head">
                {adviceVerdict.status === "GENUINE" ? (
                  <CheckCircle2 size={30} aria-hidden="true" />
                ) : adviceVerdict.status === "ALTERED" ? (
                  <AlertTriangle size={30} aria-hidden="true" />
                ) : (
                  <XCircle size={30} aria-hidden="true" />
                )}
                <div>
                  <strong>{adviceVerdict.headline}</strong>
                  <code>{adviceVerdict.status}</code>
                </div>
              </div>
              <p className="verdict-plain">{adviceVerdict.detail}</p>

              {adviceVerdict.fields.length > 0 && (
                <div className="table-wrap">
                  <table className="field-check">
                    <thead>
                      <tr><th>Field</th><th>Issued as</th><th>Printed now</th></tr>
                    </thead>
                    <tbody>
                      {adviceVerdict.fields.map((check) => (
                        <tr key={check.name} className={check.matched ? undefined : "mismatch"}>
                          <td>{check.name.replace(/_/g, " ")}</td>
                          <td className="mono">{check.expected}</td>
                          <td className="mono">{check.read}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </motion.section>
          )}
        </AnimatePresence>

        <AnimatePresence>
          {verdict && result && (
            <motion.section
              className={`verdict tone-${verdict.tone}`}
              initial={reduceMotion ? { opacity: 0 } : { opacity: 0, y: 14 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.4, ease: EASE_OUT }}
            >
              <div className="verdict-head">
                <VerdictIcon size={30} aria-hidden="true" />
                <div>
                  <strong>{verdict.headline}</strong>
                  <code>{result.result}</code>
                </div>
              </div>
              <p className="verdict-plain">{verdict.plain}</p>

              {autoDetected && (
                <p className="verdict-note">
                  You picked a different authority, but this document does verify —
                  it was signed by <strong>{result.authority_name}</strong>.
                </p>
              )}

              <dl className="verdict-facts">
                {result.authority_name && (
                  <div><dt>Authority</dt><dd>{result.authority_name}</dd></div>
                )}
                <div><dt>Checked</dt><dd>{new Date().toLocaleString()}</dd></div>
              </dl>
            </motion.section>
          )}
        </AnimatePresence>

        <p className="verify-foot">
          The proof lives in the pixels rather than the file's metadata, so it
          survives a screenshot. Verification proves which key signed a document,
          not who owns that key — and it detects substantial alterations rather
          than every possible one.
        </p>
      </div>
    </div>
  );
}
