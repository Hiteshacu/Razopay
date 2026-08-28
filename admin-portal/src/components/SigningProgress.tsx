import { Check, Loader2 } from "lucide-react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { useEffect, useState } from "react";
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
    <div className="signing-progress" role="status" aria-live="polite">
      <p className="signing-progress-title">
        {done ? "Signed" : "Signing in progress"}
      </p>

      <ol className="signing-stages">
        {STAGES.map((item, index) => {
          const complete = done || index < stage;
          const active = !done && index === stage;

          return (
            <motion.li
              key={item.label}
              className={complete ? "stage complete" : active ? "stage active" : "stage"}
              initial={reduceMotion ? false : { opacity: 0, x: -6 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ duration: 0.3, delay: index * 0.05, ease: EASE_OUT }}
            >
              <span className="stage-marker" aria-hidden="true">
                <AnimatePresence mode="wait" initial={false}>
                  {complete ? (
                    <motion.span
                      key="done"
                      initial={reduceMotion ? false : { scale: 0.5, opacity: 0 }}
                      animate={{ scale: 1, opacity: 1 }}
                      transition={{ duration: 0.22, ease: EASE_OUT }}
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
                    <motion.span key="idle" className="stage-dot" />
                  )}
                </AnimatePresence>
              </span>
              <span className="stage-text">
                <strong>{item.label}</strong>
                <small>{item.detail}</small>
              </span>
            </motion.li>
          );
        })}
      </ol>

      {!done && (
        <p className="signing-note">
          This takes around half a minute on the free tier — the server has a
          fraction of a processor. The document is not held up by anything else.
        </p>
      )}
    </div>
  );
}
