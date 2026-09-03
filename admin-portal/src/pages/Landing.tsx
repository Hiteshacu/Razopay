import { FileSignature, ScanLine, ShieldCheck } from "lucide-react";
import { motion, useReducedMotion } from "motion/react";
import { useState } from "react";
import { LatticeScene } from "../components/LatticeScene";
import { isBackgrounded, useReached } from "../hooks/useReached";
import { EASE_OUT } from "../motion";

const FEATURES = [
  {
    icon: ShieldCheck,
    title: "Signed by an authority",
    body: "Each document is signed with an RSA key that never leaves the backend. Only a registered authority can issue one."
  },
  {
    icon: FileSignature,
    title: "Invisible, not attached",
    body: "The proof lives in the pixels rather than in metadata, so it is still there after a screenshot or a trip through a messaging app."
  },
  {
    icon: ScanLine,
    title: "Anyone can verify",
    body: "Citizens check a document in the mobile app without an account. Signing needs an approved authority; verifying does not."
  }
];

export function Landing({
  onSignIn,
  onSignUp,
  onLibrary,
  onVerify,
  onPayouts
}: {
  onSignIn: () => void;
  onSignUp: () => void;
  onLibrary: () => void;
  onVerify: () => void;
  onPayouts: () => void;
}) {
  const reduceMotion = useReducedMotion();
  // One flag for the whole row: hooks cannot be called per item inside a map,
  // and three cards side by side should arrive together anyway.
  const [cardsRef, cardsShown] = useReached();
  // Same reason as the cards: skip the entrance entirely when the page is
  // being rendered somewhere nobody is watching, so the headline is never a
  // blank space in a screenshot.
  const [skipEntrance] = useState(isBackgrounded);

  const rise = {
    hidden: { opacity: 0, y: reduceMotion ? 0 : 18 },
    shown: { opacity: 1, y: 0 }
  };

  return (
    <div className="landing">
      {/* The hero is its own dark stage. The lattice needs depth to read, and
          glow only reads as glow against something dark. */}
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
            <div className="brand-mark">DTS</div>
            <div>
              <strong>Digital Trust Shield</strong>
              <span>Authority signing &amp; verification</span>
            </div>
          </div>
          <nav className="landing-actions">
            {/* Developers come here to decide whether to build on this, which
                is a question they have before they would ever sign up. So the
                library sits beside the account buttons, not behind them. */}
            {/* Verifying is the public half of this product and needs no
                account, so it sits in the nav rather than behind sign-in. */}
            <motion.button
              className="text-link on-dark nav-link"
              onClick={onVerify}
              whileHover={reduceMotion ? undefined : { y: -1 }}
              whileTap={reduceMotion ? undefined : { scale: 0.97 }}
            >
              Verify a document
            </motion.button>
            <motion.button
              className="text-link on-dark nav-link"
              onClick={onPayouts}
              whileHover={reduceMotion ? undefined : { y: -1 }}
              whileTap={reduceMotion ? undefined : { scale: 0.97 }}
            >
              Payout advice
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
            Proof that travels with the document
          </motion.p>
          <motion.h1 variants={rise} transition={{ duration: 0.55, ease: EASE_OUT }}>
            Know whether a notice, receipt or poster is genuine.
          </motion.h1>
          <motion.p className="stage-lede" variants={rise} transition={{ duration: 0.55, ease: EASE_OUT }}>
            An issuing authority signs a document once. The proof is written into the
            image itself — across the blocks the picture is already made of — so it
            survives being forwarded, compressed and screenshotted.
          </motion.p>
          <motion.div className="stage-cta" variants={rise} transition={{ duration: 0.55, ease: EASE_OUT }}>
            <motion.button
              className="primary-button lg"
              onClick={onSignUp}
              whileHover={reduceMotion ? undefined : { y: -2 }}
              whileTap={reduceMotion ? undefined : { scale: 0.98 }}
            >
              Create an authority account
            </motion.button>
            <motion.button
              className="ghost-button on-dark lg"
              onClick={onVerify}
              whileHover={reduceMotion ? undefined : { y: -2 }}
              whileTap={reduceMotion ? undefined : { scale: 0.98 }}
            >
              Verify a document
            </motion.button>
            <a className="text-link on-dark" href="/apk">
              Or get the Android app
            </a>
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
        <h2 className="sr-only" id="how-it-works">How Trust Shield works</h2>
        {FEATURES.map((feature, index) => {
          const Icon = feature.icon;
          return (
            <motion.article
              key={feature.title}
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
              <h3>{feature.title}</h3>
              <p>{feature.body}</p>
            </motion.article>
          );
        })}
      </section>

      <p className="landing-foot">
        <strong>Verifying is open to everyone.</strong> This console is for
        issuing authorities.
      </p>
    </div>
  );
}
