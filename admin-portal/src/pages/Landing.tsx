import { FileSignature, ScanLine, ShieldCheck } from "lucide-react";
import { motion, useReducedMotion } from "motion/react";
import { SealAnimation } from "../components/SealAnimation";

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
  onSignUp
}: {
  onSignIn: () => void;
  onSignUp: () => void;
}) {
  const reduceMotion = useReducedMotion();

  // One shared rhythm for the whole page. Entrances move a short distance and
  // only ever animate transform and opacity, so nothing triggers layout work.
  const rise = {
    hidden: { opacity: 0, y: reduceMotion ? 0 : 14 },
    shown: { opacity: 1, y: 0 }
  };

  const ease = [0.22, 1, 0.36, 1] as const;

  return (
    <div className="landing">
      <motion.header
        className="landing-bar"
        initial={{ opacity: 0, y: reduceMotion ? 0 : -10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, ease }}
      >
        <div className="landing-brand">
          <div className="brand-mark">DTS</div>
          <div>
            <strong>Digital Trust Shield</strong>
            <span>Authority signing &amp; verification</span>
          </div>
        </div>
        <nav className="landing-actions">
          <motion.button
            className="ghost-button"
            onClick={onSignIn}
            whileHover={reduceMotion ? undefined : { y: -1 }}
            whileTap={reduceMotion ? undefined : { scale: 0.97 }}
          >
            Sign in
          </motion.button>
          <motion.button
            className="primary-button"
            onClick={onSignUp}
            whileHover={reduceMotion ? undefined : { y: -1 }}
            whileTap={reduceMotion ? undefined : { scale: 0.97 }}
          >
            Sign up
          </motion.button>
        </nav>
      </motion.header>

      <main className="landing-hero">
        <motion.div
          className="landing-copy"
          initial="hidden"
          animate="shown"
          // 60ms between children: enough to read as a sequence, short enough
          // that the whole block has settled before the eye finishes the line.
          transition={{ staggerChildren: 0.06, delayChildren: 0.08 }}
        >
          <motion.p className="eyebrow" variants={rise} transition={{ duration: 0.5, ease }}>
            Proof that travels with the document
          </motion.p>
          <motion.h1 variants={rise} transition={{ duration: 0.5, ease }}>
            Know whether a notice, receipt or poster is genuine.
          </motion.h1>
          <motion.p className="landing-lede" variants={rise} transition={{ duration: 0.5, ease }}>
            An issuing authority signs a document once. The proof is hidden inside the
            image itself, so it survives being forwarded, compressed and screenshotted —
            and anyone can check it in seconds.
          </motion.p>
          <motion.div className="landing-cta" variants={rise} transition={{ duration: 0.5, ease }}>
            <motion.button
              className="primary-button"
              onClick={onSignUp}
              whileHover={reduceMotion ? undefined : { y: -2 }}
              whileTap={reduceMotion ? undefined : { scale: 0.97 }}
            >
              Create an authority account
            </motion.button>
            <a className="text-link" href="/apk">
              Get the verifier app
            </a>
          </motion.div>
        </motion.div>

        <motion.div
          className="landing-figure"
          initial={{ opacity: 0, scale: reduceMotion ? 1 : 0.96 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: 0.6, delay: 0.15, ease }}
        >
          <SealAnimation />
        </motion.div>
      </main>

      <section className="landing-cards">
        {FEATURES.map((feature, index) => {
          const Icon = feature.icon;
          return (
            <motion.article
              key={feature.title}
              initial={{ opacity: 0, y: reduceMotion ? 0 : 18 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, amount: 0.4 }}
              transition={{ duration: 0.45, delay: index * 0.06, ease }}
              whileHover={reduceMotion ? undefined : { y: -3 }}
            >
              <Icon size={22} aria-hidden="true" />
              <h3>{feature.title}</h3>
              <p>{feature.body}</p>
            </motion.article>
          );
        })}
      </section>

      <p className="landing-foot">
        Verifying is open to everyone. This console is for issuing authorities.
      </p>
    </div>
  );
}
