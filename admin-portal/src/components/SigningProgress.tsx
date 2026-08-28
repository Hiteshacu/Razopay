import { Check, Loader2 } from "lucide-react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { useEffect, useState } from "react";
import { LatticeScene } from "./LatticeScene";
import { EASE_OUT } from "../motion";

/**
 * What the engine is doing while a signature is produced.
 *
 * Signing takes the better part of half a minute on a small instance, and a
 * spinner for that long reads as a hang. These are the real stages the engine
 * works through, and the estimates come from measured timings.
 *
 * The last stage deliberately has no estimate: it holds until the response
 * actually arrives, so the display can never claim to have finished work that
 * is still running. Nothing here reports true progress — the server answers
 * once — so the steps describe the work rather than pretending to measure it.
 *
 * Laid out landscape, with the lattice from the landing page running beside
 * the steps. It is the same picture of the same mechanism: blocks of the
 * document lighting up as the proof is written across them. Seeing it here
 * while that is genuinely happening is the point of showing it at all.
 */

const STAGES = [
  { label: "Reading the document", detail: "Decoding and preparing the image", seconds: 2 },
  { label: "Taking a visual fingerprint", detail: "128 bits describing how the page looks", seconds: 4 },
  { label: "Signing the fingerprint", detail: "RSA-PSS with the authority's private key", seconds: 2 },
  { label: "Weaving the proof into the pixels", detail: "Across every 8×8 block of the image", seconds: 8 },
  { label: "Checking the signed file verifies", detail: "Confirming the proof can be read back", seconds: null }
];

export function SigningProgress({ done }: { done: boolean }) {
  const reduceMotion = useReducedMotion();
  const [stage, setStage] = useState(0);

  useEffect(() => {
    if (done) {
      setStage(STAGES.length);
      return;
    }
    let cancelled = false;
    let index = 0;

    function advance() {
      const seconds = STAGES[index]?.seconds;
      if (seconds == null || cancelled) return; // hold on the last stage
      window.setTimeout(() => {
        if (cancelled) return;
        index += 1;
        setStage(index);
        advance();
      }, seconds * 1000);
    }
    advance();

    return () => {
      cancelled = true;
    };
  }, [done]);

  return (
    <div className="signing" role="status" aria-live="polite">
      <div className="signing-visual" aria-hidden="true">
        <LatticeScene />

        <AnimatePresence>
          {done && (
            <motion.div
              key="veil"
              className="signing-visual-veil"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ duration: 0.4 }}
            />
          )}
        </AnimatePresence>

        <AnimatePresence>
          {done && (
            <motion.div
              key="seal"
              className="signing-seal"
              initial={reduceMotion ? { opacity: 1 } : { opacity: 0, scale: 0.82 }}
              animate={{ opacity: 1, scale: 1 }}
              transition={{ duration: 0.45, ease: EASE_OUT }}
            >
              {/* The ring closes, then the tick draws through it — the same
                  order the engine works in: embed, then confirm. */}
              <svg viewBox="0 0 120 120" role="presentation">
                <motion.circle
                  cx="60"
                  cy="60"
                  r="36"
                  className="signing-seal-ring"
                  initial={reduceMotion ? { pathLength: 1 } : { pathLength: 0, rotate: -90 }}
                  animate={{ pathLength: 1, rotate: -90 }}
                  transition={{ duration: 0.55, ease: EASE_OUT }}
                  style={{ transformOrigin: "60px 60px" }}
                />
                <motion.path
                  d="M43 61.5 L54.5 73 L78 47"
                  className="signing-seal-tick"
                  initial={reduceMotion ? { pathLength: 1 } : { pathLength: 0 }}
                  animate={{ pathLength: 1 }}
                  transition={{ duration: 0.35, delay: reduceMotion ? 0 : 0.4, ease: EASE_OUT }}
                />
              </svg>
            </motion.div>
          )}
        </AnimatePresence>

        {!done && (
          <p className="signing-visual-caption">
            Each lit point is a block of your document carrying part of the signature.
          </p>
        )}
      </div>

      <div className="signing-body">
        <p className="signing-title" id="signing-heading">
          {done ? <span className="signing-title-done">Signed</span> : "Signing in progress"}
        </p>

        <ol className="signing-steps">
          {STAGES.map((item, index) => {
            const complete = done || index < stage;
            const active = !done && index === stage;

            return (
              <motion.li
                key={item.label}
                className={
                  complete
                    ? "signing-step complete"
                    : active
                      ? "signing-step active"
                      : "signing-step"
                }
                initial={reduceMotion ? false : { opacity: 0, x: -6 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ duration: 0.3, delay: index * 0.05, ease: EASE_OUT }}
              >
                <span className="signing-step-marker" aria-hidden="true">
                  <AnimatePresence mode="wait" initial={false}>
                    {complete ? (
                      <motion.span
                        key="done"
                        initial={reduceMotion ? false : { scale: 0.5, opacity: 0 }}
                        animate={{ scale: 1, opacity: 1 }}
                        transition={{
                          duration: 0.22,
                          // On completion the steps tick over in sequence
                          // rather than all at once, which reads as the work
                          // finishing instead of the display resetting.
                          delay: done && !reduceMotion ? index * 0.08 : 0,
                          ease: EASE_OUT
                        }}
                      >
                        <Check size={13} />
                      </motion.span>
                    ) : active ? (
                      <motion.span
                        key="busy"
                        animate={reduceMotion ? undefined : { rotate: 360 }}
                        transition={
                          reduceMotion
                            ? undefined
                            : { duration: 1.1, repeat: Infinity, ease: "linear" }
                        }
                      >
                        <Loader2 size={13} />
                      </motion.span>
                    ) : (
                      <motion.span key="idle" className="signing-step-dot" />
                    )}
                  </AnimatePresence>
                </span>
                <span className="signing-step-text">
                  <strong>{item.label}</strong>
                  <small>{item.detail}</small>
                </span>
              </motion.li>
            );
          })}
        </ol>

        <p className="signing-note">
          {done
            ? "The proof is in the image itself. It survives a screenshot, a forward and a re-compression — download it below."
            : "This takes around half a minute on the free tier — the server has a fraction of a processor. The document is not held up by anything else."}
        </p>
      </div>
    </div>
  );
}
