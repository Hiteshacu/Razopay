import {
  ArrowLeft,
  Check,
  Copy,
  Download,
  KeyRound,
  ScanLine,
  ShieldCheck,
  Terminal
} from "lucide-react";
import { motion, useReducedMotion } from "motion/react";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { EASE_OUT } from "../motion";

const WHEEL = "/lib/trustshield-0.2.0-py3-none-any.whl";
const GIT_URL = "git+https://github.com/Hiteshacu/trust-shield.git#subdirectory=library";

/** Copyable code, with the language on the rail and a copy button that confirms itself. */
function Snippet({ label = "python", code }: { label?: string; code: string }) {
  const [copied, setCopied] = useState(false);

  async function copy() {
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1600);
    } catch {
      // Clipboard permission can be refused; the text stays selectable either way.
      setCopied(false);
    }
  }

  return (
    <div className="snippet">
      <div className="snippet-bar">
        <span>{label}</span>
        <button type="button" onClick={copy} aria-label={copied ? "Copied" : "Copy to clipboard"}>
          {copied ? <Check size={13} aria-hidden="true" /> : <Copy size={13} aria-hidden="true" />}
          <span>{copied ? "Copied" : "Copy"}</span>
        </button>
      </div>
      <pre><code>{code}</code></pre>
    </div>
  );
}

/**
 * Has this element been reached yet?
 *
 * Not whileInView. That reveals on *intersection*, and an element can get from
 * below the fold to above it without ever intersecting — a fast flick, an
 * anchor jump, restoring a scroll position. When that happens the section stays
 * at opacity 0 for good, and a page that can permanently hide its own content
 * is worse than a page with no animation at all.
 *
 * This asks a question that cannot get stuck instead: is the top of the element
 * above the bottom of the viewport? True while it is on screen, and true
 * forever after it has passed. Each element stops listening the moment it
 * answers yes, so the work disappears as the reader moves down the page.
 */
function useReached(margin = 0.9) {
  const ref = useRef<HTMLElement | null>(null);
  const [reached, setReached] = useState(false);

  useEffect(() => {
    const element = ref.current;
    if (!element) return;

    let frame = 0;
    let done = false;

    const check = () => {
      if (done) return true;
      if (element.getBoundingClientRect().top < window.innerHeight * margin) {
        done = true;
        setReached(true);
        window.removeEventListener("scroll", onScroll);
        window.removeEventListener("resize", onScroll);
        return true;
      }
      return false;
    };

    function onScroll() {
      if (frame) return;              // one measurement per frame, not per event
      frame = requestAnimationFrame(() => {
        frame = 0;
        check();
      });
    }

    if (!check()) {
      window.addEventListener("scroll", onScroll, { passive: true });
      window.addEventListener("resize", onScroll, { passive: true });
    }

    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("resize", onScroll);
    };
  }, [margin]);

  return [ref, reached] as const;
}

/**
 * A section that arrives as you reach it.
 *
 * One reveal per section and a small offset, deliberately. A page where every
 * element makes its own entrance reads as a slideshow, and documentation is
 * something people scan under pressure.
 */
function Section({
  icon,
  title,
  children
}: {
  icon?: ReactNode;
  title: string;
  children: ReactNode;
}) {
  const reduceMotion = useReducedMotion();
  const [ref, reached] = useReached();
  const shown = reached || reduceMotion;

  return (
    <motion.section
      ref={ref as React.RefObject<HTMLElement>}
      className="panel"
      initial={false}
      animate={shown ? { opacity: 1, y: 0 } : { opacity: 0, y: 14 }}
      transition={{ duration: 0.42, ease: EASE_OUT }}
    >
      <h2>{icon}{title}</h2>
      {children}
    </motion.section>
  );
}


/**
 * One numbered step of the walkthrough.
 *
 * Numbered because this genuinely is a sequence — the install has to precede
 * the restart, the restart has to precede the import, and a key has to exist
 * before anything can be signed. Every step that produces output shows what
 * that output should be, so a reader can tell whether they are still on track
 * without running the next one to find out.
 */
function Step({
  n,
  title,
  note,
  label,
  code,
  output,
  action
}: {
  n: string;
  title: string;
  note?: ReactNode;
  label?: string;
  code?: string;
  output?: string;
  action?: string;
}) {
  return (
    <li className="step">
      <div className="step-rail" aria-hidden="true">
        <span className="step-n">{n}</span>
      </div>
      <div className="step-body">
        <h3>{title}</h3>
        {note && <p className="step-note">{note}</p>}
        {action && <p className="step-action">{action}</p>}
        {code && <Snippet label={label} code={code} />}
        {output && (
          <div className="step-out">
            <span>you should see</span>
            <pre>{output}</pre>
          </div>
        )}
      </div>
    </li>
  );
}

const STATUSES: Array<[string, string, string]> = [
  ["AUTHENTIC", "Signed by that key, and unchanged since.", "ok"],
  ["TAMPERED", "Genuinely signed — and edited afterwards.", "warn"],
  ["SIGNATURE_INVALID", "A proof is present, but this key did not validate it. Usually the wrong key.", "bad"],
  ["WATERMARK_NOT_FOUND", "No proof at all: never signed, or damaged past recovery.", "dim"]
];

const SURVIVES: Array<[string, boolean, string]> = [
  ["Screenshotting", true, "the proof is in the pixels, and a screenshot keeps pixels"],
  ["JPEG and PNG recompression", true, "verified down to quality 50"],
  ["Resizing and moderate rescaling", true, ""],
  ["Forwarding through messaging apps", true, ""],
  ["Metadata being stripped", true, "irrelevant — nothing is kept there"],
  ["Heavy cropping", false, "the blocks carrying the signature are cut away"],
  ["Photographing a screen", false, "moiré and perspective exceed recovery"],
  ["Very small or very blank images", false, "too few textured blocks to carry 2,272 bits"]
];

/**
 * The developer-facing page: install, make a key pair, sign, verify.
 *
 * Public and reachable without an account — whether to build on this is a
 * question a developer has long before they would consider signing up.
 */
export function Library({ onBack }: { onBack: () => void }) {
  const reduceMotion = useReducedMotion();

  const rise = {
    hidden: { opacity: 0, y: reduceMotion ? 0 : 12 },
    shown: { opacity: 1, y: 0 }
  };

  return (
    <div className="library-page">
      <div className="library-glow" aria-hidden="true" />

      <header className="library-bar">
        <button className="back-link" onClick={onBack}>
          <ArrowLeft size={15} aria-hidden="true" />
          <span>Back</span>
        </button>
        <motion.a
          className="download-button sm"
          href={WHEEL}
          download
          whileHover={reduceMotion ? undefined : { y: -1 }}
          whileTap={reduceMotion ? undefined : { scale: 0.97 }}
        >
          <Download size={15} aria-hidden="true" />
          <span>Download the wheel</span>
        </motion.a>
      </header>

      <div className="library-inner">
        <motion.div
          className="library-hero"
          initial="hidden"
          animate="shown"
          transition={{ staggerChildren: 0.05 }}
        >
          <motion.p className="eyebrow" variants={rise} transition={{ duration: 0.45, ease: EASE_OUT }}>
            For developers
          </motion.p>
          <motion.h1 className="library-title" variants={rise} transition={{ duration: 0.45, ease: EASE_OUT }}>
            <code>trustshield</code>
            <span className="version-pill">v0.2.0</span>
          </motion.h1>
          <motion.p className="library-lede" variants={rise} transition={{ duration: 0.45, ease: EASE_OUT }}>
            The signing engine behind this console, as an installable Python package.
            Generate a key pair, sign an image, verify it anywhere. The signature goes
            into the pixels rather than the metadata, so it is still there after a
            screenshot.
          </motion.p>
          <motion.div className="library-stats" variants={rise} transition={{ duration: 0.45, ease: EASE_OUT }}>
            <div><strong>RSA-2048</strong><span>PSS / SHA-256</span></div>
            <div><strong>284 bytes</strong><span>embedded per document</span></div>
            <div><strong>4 tiers</strong><span>of recovery on verify</span></div>
          </motion.div>
        </motion.div>

        <Section title="Start to finish, in order" icon={<Terminal size={17} aria-hidden="true" />}>
          <p>
            Every command, in the order they have to run. The first four are
            one-time setup; from step 5 on is the work.
          </p>

          <p className="rail-label">In a notebook</p>
          <ol className="steps-list">
            <Step
              n="1"
              title="Remove any older copy"
              note={
                <>
                  A half-updated install is the hardest failure to read, because the
                  version can report new while the code is old. Removing first makes
                  that impossible.
                </>
              }
              label="jupyter"
              code="!pip uninstall -y trustshield"
              output="Successfully uninstalled trustshield-0.2.0"
            />
            <Step
              n="2"
              title="Install"
              label="jupyter"
              code={`!pip install --no-cache-dir --force-reinstall --no-deps "${GIT_URL}"`}
              output="Successfully installed trustshield-0.2.0"
            />
            <Step
              n="3"
              title="Restart the kernel"
              action="Kernel → Restart Kernel"
              note={
                <>
                  <strong>Not optional.</strong> Python keeps the old module in memory
                  until you restart, so without this you get the previous version&rsquo;s
                  errors no matter what pip just did.
                </>
              }
            />
            <Step
              n="4"
              title="Check what you actually have"
              note="Checks the code, not just the version label — those can disagree."
              code={`import trustshield, inspect
from trustshield import api

src = inspect.getsource(api)
print("version:", trustshield.__version__)
print("has the fix:", "_signing_failure_message" in src)`}
              output={`version: 0.2.0
has the fix: True`}
            />
            <Step
              n="5"
              title="Make a key pair, or load the one you have"
              note="Keys are made once and reused. Regenerating would sign every document with a different key, and nothing signed earlier would verify."
              code={`import trustshield
from pathlib import Path

if Path("./keys/private_key.pem").exists():
    keys = trustshield.KeyPair.load("./keys")
else:
    keys = trustshield.KeyPair.generate().save("./keys")

print("key", keys.fingerprint[:16])`}
              output="key 7ca83b0c1cc2fac6"
            />
            <Step
              n="6"
              title="Sign a document"
              note={
                <>
                  Use raw strings (<code>r&quot;...&quot;</code>) for Windows paths —
                  <code> \U</code> in <code>C:\Users</code> is an escape sequence
                  otherwise. Takes about ten seconds on a large page.
                </>
              }
              code={`result = trustshield.sign(
    r"C:\Users\HP\Pictures\research papers sih.png",
    r"C:\Users\HP\Pictures\signed.png",
    private_key="./keys",
)
print("signed ->", result.output_path)`}
              output="signed -> C:\Users\HP\Pictures\signed.png"
            />
            <Step
              n="7"
              title="Verify the signed file"
              code={`check = trustshield.verify(
    r"C:\Users\HP\Pictures\signed.png", public_key="./keys"
)
print("verify ->", check.status)`}
              output="verify -> AUTHENTIC"
            />
            <Step
              n="8"
              title="Verify the original, to prove it is not just saying yes"
              note="The single most convincing thing to show anyone. The same command on the unsigned file has to come back negative, or the positive means nothing."
              code={`check = trustshield.verify(
    r"C:\Users\HP\Pictures\research papers sih.png", public_key="./keys"
)
print("verify ->", check.status)`}
              output="verify -> WATERMARK_NOT_FOUND"
            />
          </ol>
        </Section>

        <Section title="The same thing outside a notebook">
          <p>
            No <code>!</code> prefix, and no kernel to restart. Otherwise identical.
          </p>
          <p className="rail-label">Terminal</p>
          <Snippet
            label="bash"
            code={`pip install "${GIT_URL}"

trustshield keygen -o ./keys
trustshield sign notice.png -o signed.png -k ./keys
trustshield verify signed.png -k ./keys      # AUTHENTIC, exit 0
trustshield verify notice.png -k ./keys      # WATERMARK_NOT_FOUND, exit 1`}
          />
          <p className="rail-label">A Python script</p>
          <Snippet
            label="python"
            code={`import trustshield
from pathlib import Path

keys = (
    trustshield.KeyPair.load("./keys")
    if Path("./keys/private_key.pem").exists()
    else trustshield.KeyPair.generate().save("./keys")
)

trustshield.sign("notice.png", "signed.png", private_key="./keys")

print(trustshield.verify("signed.png", public_key="./keys"))
# AUTHENTIC: Signature valid and content unchanged.

print(trustshield.verify("notice.png", public_key="./keys"))
# WATERMARK_NOT_FOUND: No hidden proof was found in this image.`}
          />
          <p className="hint">
            Signing a 12-megapixel page takes about ten seconds. It will look like
            nothing is happening. It is.
          </p>
        </Section>

        <Section title="Keys" icon={<KeyRound size={17} aria-hidden="true" />}>
          <p>
            Two halves, two jobs, not interchangeable. The same pair has to be on both
            sides: a document signed with one private key verifies only against its own
            public key.
          </p>
          <div className="key-split">
            <motion.div whileHover={reduceMotion ? undefined : { y: -2 }}>
              <code>private_key.pem</code>
              <strong>Signs</strong>
              <p>Never share it. Anyone holding it can sign in your name.</p>
            </motion.div>
            <motion.div whileHover={reduceMotion ? undefined : { y: -2 }}>
              <code>public_key.pem</code>
              <strong>Verifies</strong>
              <p>Share freely. It cannot sign, and verification is impossible without it.</p>
            </motion.div>
          </div>
          <p className="hint">
            Written as plain PEM so they travel — to a colleague, into a container, onto
            the machine that will verify. Protect the private key like a password.
          </p>
        </Section>

        <Section title="The four answers" icon={<ShieldCheck size={17} aria-hidden="true" />}>
          <p>
            Verification does not return a boolean, because "not authentic" covers two
            very different situations.
          </p>
          <div className="status-list">
            {STATUSES.map(([name, meaning, tone], index) => (
              <motion.div
                key={name}
                className={`status-row tone-${tone}`}
                initial={reduceMotion ? false : { opacity: 0, x: -8 }}
                whileInView={{ opacity: 1, x: 0 }}
                viewport={{ once: true, amount: 0 }}
                transition={{ duration: 0.32, delay: index * 0.04, ease: EASE_OUT }}
              >
                <code>{name}</code>
                <p>{meaning}</p>
              </motion.div>
            ))}
          </div>
          <Snippet
            code={`result = trustshield.verify("signed.png", public_key="./keys")

if result:                                  # truthy only when AUTHENTIC
    print("genuine")
elif result.status == trustshield.TAMPERED:
    print("issued by that authority, then altered")`}
          />
          <p className="hint">
            <strong>TAMPERED</strong> is the one a plain signature cannot produce: the
            signature is valid, but the picture no longer matches what was signed. That is
            someone editing a real notice and re-sharing it.
          </p>
        </Section>

        <Section title="Command line" icon={<Terminal size={17} aria-hidden="true" />}>
          <p>So signing can be a build step or a cron job with no Python around it.</p>
          <Snippet
            label="bash"
            code={`trustshield keygen -o ./keys
trustshield sign notice.png -o signed.png -k ./keys
trustshield verify signed.png -k ./keys`}
          />
          <p>Exit codes let a pipeline branch on the answer.</p>
          <Snippet
            label="bash"
            code={`if trustshield verify incoming.png -k ./public; then
  echo "genuine"        # exit 0
else
  echo "rejected"       # 1 = not authentic, 2 = could not run
fi`}
          />
        </Section>

        <Section title="What survives" icon={<ScanLine size={17} aria-hidden="true" />}>
          <ul className="survives">
            {SURVIVES.map(([what, ok, why], index) => (
              <motion.li
                key={what}
                className={ok ? "yes" : "no"}
                initial={reduceMotion ? false : { opacity: 0, y: 8 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true, amount: 0 }}
                transition={{ duration: 0.3, delay: index * 0.035, ease: EASE_OUT }}
              >
                <span className="mark" aria-hidden="true">{ok ? "survives" : "fails"}</span>
                <span className="what">{what}</span>
                {why && <span className="why">{why}</span>}
              </motion.li>
            ))}
          </ul>
        </Section>

        <Section title="On the visible carrier">
          <p>
            Zoom into a signed document and you will find faint diagonal texture in flat
            areas. That is the carrier, and it is deliberate.
          </p>
          <p>
            A screenshot keeps exactly what you can see. A mark quiet enough to vanish
            from a white margin is a mark closer to vanishing from the screenshot — so the
            strength that makes it faintly visible is the strength that makes it survive.
            Weakening it was measured, and it costs survival before it buys much
            invisibility.
          </p>
          <p className="hint">
            <code>DTS_SUBTLE_EMBEDDING=1</code> trades some of that for a cleaner look on
            blank paper, if a particular document needs it. Off by default, on purpose.
          </p>
        </Section>

        <Section title="Two limits, stated plainly">
          <ul>
            <li>
              <strong>Key trust is not solved here.</strong> Verification proves that
              <em> a</em> key signed the document — not who owns that key. A directory or
              certificate chain is yours to provide.
            </li>
            <li>
              <strong>This is provenance, not detection.</strong> It proves what is
              genuine; it does not analyse an unknown image for signs of synthesis.
            </li>
          </ul>
        </Section>
      </div>
    </div>
  );
}
