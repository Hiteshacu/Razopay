import { AlertTriangle, Clock, FileSearch, ScanLine } from "lucide-react";
import { motion, useReducedMotion } from "motion/react";
import { useState } from "react";
import { LatticeScene } from "../components/LatticeScene";
import { isBackgrounded, useReached } from "../hooks/useReached";
import { EASE_OUT } from "../motion";

/**
 * Three facts, in the order a judge needs them: why the fraud works, why the
 * obvious defence does not, and what is done instead. Not a feature list —
 * the product only makes sense once the settlement window is understood.
 */
const FACTS = [
  {
    icon: Clock,
    title: "The window is real",
    body: "NEFT and RTGS settle in batches, minutes to hours later. A vendor checking their own bank sees nothing — and that is exactly what a genuine payment looks like too."
  },
  {
    icon: AlertTriangle,
    title: "A soundbox cannot help",
    body: "Soundboxes announce UPI credits. These are not UPI. For a five- or six-figure transfer there is no live channel to check against at the moment goods leave the warehouse."
  },
  {
    icon: FileSearch,
    title: "So the advice proves itself",
    body: "RazorpayX signs the advice as it issues it, and records what was printed. Anyone holding one can check both, in seconds, with no account."
  }
];

/** Numbers from the held-out benchmark, quoted exactly as measured. */
const RESULTS = [
  { value: "1.000", label: "recall", note: "190 forgeries, none waved through" },
  { value: "0.000", label: "false-positive rate", note: "100 genuine copies, none accused" },
  { value: "10/10", label: "single changed digit", note: "caught after WhatsApp" }
];

export function Landing({
  onSignIn,
  onSignUp,
  onLibrary,
  onVerify
}: {
  onSignIn: () => void;
  onSignUp: () => void;
  onLibrary: () => void;
  onVerify: () => void;
}) {
  const reduceMotion = useReducedMotion();
  const [cardsRef, cardsShown] = useReached();
  const [skipEntrance] = useState(isBackgrounded);

  const rise = {
    hidden: { opacity: 0, y: reduceMotion ? 0 : 18 },
    shown: { opacity: 1, y: 0 }
  };

  return (
    <div className="landing">
      <section className="stage">
        <div className="stage-scene">
          <LatticeScene />
        </div>
        <div className="stage-veil" aria-hidden="true" />

        <motion.header
          className="stage-bar"
          initial={skipEntrance ? false : { opacity: 0, y: reduceMotion ? 0 : -12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, ease: EASE_OUT }}
        >
          <div className="landing-brand">
            <div className="brand-mark">PP</div>
            <div>
              <strong>PayProof</strong>
              <span>Payout advice verification</span>
            </div>
          </div>
          <nav className="landing-actions">
            <motion.button
              className="text-link on-dark nav-link"
              onClick={onVerify}
              whileHover={reduceMotion ? undefined : { y: -1 }}
              whileTap={reduceMotion ? undefined : { scale: 0.97 }}
            >
              Any document
            </motion.button>
            <motion.button
              className="text-link on-dark nav-link"
              onClick={onLibrary}
              whileHover={reduceMotion ? undefined : { y: -1 }}
              whileTap={reduceMotion ? undefined : { scale: 0.97 }}
            >
              Library
            </motion.button>
            <motion.button
              className="text-link on-dark nav-link"
              onClick={onSignIn}
              whileHover={reduceMotion ? undefined : { y: -1 }}
              whileTap={reduceMotion ? undefined : { scale: 0.97 }}
            >
              Sign in
            </motion.button>
            <motion.button
              className="ghost-button on-dark"
              onClick={onSignUp}
              whileHover={reduceMotion ? undefined : { y: -1 }}
              whileTap={reduceMotion ? undefined : { scale: 0.97 }}
            >
              Sign up
            </motion.button>
          </nav>
        </motion.header>

        <motion.div
          className="stage-copy"
          initial={skipEntrance ? false : "hidden"}
          animate="shown"
          transition={{ staggerChildren: 0.07, delayChildren: 0.15 }}
        >
          <motion.p className="stage-eyebrow" variants={rise} transition={{ duration: 0.55, ease: EASE_OUT }}>
            Razorpay AI Buildathon &middot; Track 02, AI Risk Manager
          </motion.p>
          <motion.h1 variants={rise} transition={{ duration: 0.55, ease: EASE_OUT }}>
            The advice says paid. The money is not there yet.
          </motion.h1>
          <motion.p className="stage-lede" variants={rise} transition={{ duration: 0.55, ease: EASE_OUT }}>
            That gap is not a bug in NEFT and RTGS — it is how batch settlement
            works, and it is where the fraud lives. A Mumbai car dealer lost
            &#8377;6.5&nbsp;lakh to an edited transfer slip. Ranka Jewellers lost
            &#8377;3.48&nbsp;lakh of gold the same way. PayProof makes a RazorpayX
            payout advice prove itself, before the goods leave.
          </motion.p>
          <motion.div className="stage-cta" variants={rise} transition={{ duration: 0.55, ease: EASE_OUT }}>
            <motion.button
              className="primary-button lg"
              onClick={onSignIn}
              whileHover={reduceMotion ? undefined : { y: -2 }}
              whileTap={reduceMotion ? undefined : { scale: 0.98 }}
            >
              Check a payout advice
            </motion.button>
            <motion.button
              className="ghost-button on-dark lg"
              onClick={onVerify}
              whileHover={reduceMotion ? undefined : { y: -2 }}
              whileTap={reduceMotion ? undefined : { scale: 0.98 }}
            >
              Verify any document
            </motion.button>
          </motion.div>
        </motion.div>

        <motion.p
          className="stage-caption"
          initial={skipEntrance ? false : { opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.8, delay: 0.7 }}
        >
          <span className="seal-dot" />
          Each lit point is a block carrying part of the signature
        </motion.p>
      </section>

      <section
        className="landing-cards"
        ref={cardsRef as React.RefObject<HTMLElement>}
        aria-labelledby="how-it-works"
      >
        <h2 className="sr-only" id="how-it-works">Why this fraud works, and what stops it</h2>
        {FACTS.map((fact, index) => {
          const Icon = fact.icon;
          return (
            <motion.article
              key={fact.title}
              initial={false}
              animate={
                cardsShown || reduceMotion
                  ? { opacity: 1, y: 0 }
                  : { opacity: 0, y: 20 }
              }
              transition={{ duration: 0.5, delay: index * 0.07, ease: EASE_OUT }}
              whileHover={reduceMotion ? undefined : { y: -4 }}
            >
              <Icon size={22} aria-hidden="true" />
              <h3>{fact.title}</h3>
              <p>{fact.body}</p>
            </motion.article>
          );
        })}
      </section>

      {/* Measured results, on the landing page rather than buried in a README.
          The track scores honest metrics, and a claim a reader has to go
          looking for reads like one that is being kept quiet. */}
      <section className="landing-results" aria-labelledby="measured">
        <h2 id="measured">Measured, on a held-out set</h2>
        <p className="results-lede">
          Ten advices, a hundred genuine copies through JPEG, resizing,
          screenshots and WhatsApp, and a hundred and ninety forgeries. The
          reader&rsquo;s thresholds were fixed on a separate development split and
          never refitted.
        </p>
        <div className="results-grid">
          {RESULTS.map((result) => (
            <div key={result.label} className="result-tile">
              <strong>{result.value}</strong>
              <span className="result-label">{result.label}</span>
              <small>{result.note}</small>
            </div>
          ))}
        </div>
        <p className="results-caveat">
          <ScanLine size={15} aria-hidden="true" />
          <span>
            What does not work is measured too: a photograph of a screen breaks
            signature recovery, so all ten genuine advices came back
            &ldquo;no signature found&rdquo;. Wrong — but it refuses rather than
            passing a fake.
          </span>
        </p>
      </section>

      <p className="landing-foot">
        <strong>Checking is open to everyone.</strong> A vendor deciding whether to
        release goods needs no account. Issuing signed advices is what the console
        behind sign-in is for.
      </p>
    </div>
  );
}
