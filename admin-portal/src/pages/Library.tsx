import { ArrowLeft, Check, Copy, Download, KeyRound, ShieldCheck, Terminal } from "lucide-react";
import { motion, useReducedMotion } from "motion/react";
import { useState } from "react";
import { EASE_OUT } from "../motion";

const WHEEL = "/lib/trustshield-0.1.0-py3-none-any.whl";

function Snippet({ label, code }: { label?: string; code: string }) {
  const [copied, setCopied] = useState(false);

  async function copy() {
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1600);
    } catch {
      // Clipboard access can be refused; the code is selectable either way.
      setCopied(false);
    }
  }

  return (
    <div className="snippet">
      <div className="snippet-bar">
        <span>{label ?? "python"}</span>
        <button type="button" onClick={copy} aria-label="Copy to clipboard">
          {copied ? <Check size={13} aria-hidden="true" /> : <Copy size={13} aria-hidden="true" />}
          <span>{copied ? "Copied" : "Copy"}</span>
        </button>
      </div>
      <pre><code>{code}</code></pre>
    </div>
  );
}

const STATUSES = [
  ["AUTHENTIC", "Signed by that key, and unchanged since.", "ok"],
  ["TAMPERED", "Genuinely signed — and edited afterwards.", "warn"],
  ["SIGNATURE_INVALID", "A proof is present, but this key did not validate it. Usually the wrong key.", "bad"],
  ["WATERMARK_NOT_FOUND", "No proof at all: never signed, or damaged past recovery.", "dim"]
];

/**
 * The developer-facing page: install the library, make a key pair, sign,
 * verify.
 *
 * Public, and reachable without an account. Someone deciding whether to build
 * on this needs to read it before they would ever think about signing up.
 */
export function Library({ onBack }: { onBack: () => void }) {
  const reduceMotion = useReducedMotion();

  const rise = {
    hidden: { opacity: 0, y: reduceMotion ? 0 : 14 },
    shown: { opacity: 1, y: 0 }
  };

  return (
    <div className="library-page">
      <header className="library-bar">
        <button className="back-link" onClick={onBack}>
          <ArrowLeft size={15} aria-hidden="true" />
          <span>Back</span>
        </button>
        <a className="download-button sm" href={WHEEL} download>
          <Download size={15} aria-hidden="true" />
          <span>Download the wheel</span>
        </a>
      </header>

      <motion.div
        className="library-inner"
        initial="hidden"
        animate="shown"
        transition={{ staggerChildren: 0.06 }}
      >
        <motion.div variants={rise} transition={{ duration: 0.5, ease: EASE_OUT }}>
          <p className="eyebrow">For developers</p>
          <h1 className="library-title">
            <code>trustshield</code>
          </h1>
          <p className="library-lede">
            The signing engine behind this console, as an installable Python package.
            Make a key pair, sign an image, verify it anywhere — the proof lives in
            the pixels, so it survives a screenshot.
          </p>
        </motion.div>

        <motion.section className="panel" variants={rise} transition={{ duration: 0.5, ease: EASE_OUT }}>
          <h2>Install</h2>
          <Snippet label="bash" code={"pip install trustshield"} />
          <p className="hint">
            Python 3.10 or newer. PDF signing needs a renderer, which is large, so
            it is optional: <code>pip install "trustshield[pdf]"</code>
          </p>
          <p className="hint">
            Not on PyPI yet — use the wheel above:{" "}
            <code>pip install trustshield-0.1.0-py3-none-any.whl</code>
          </p>
        </motion.section>

        <motion.section className="panel" variants={rise} transition={{ duration: 0.5, ease: EASE_OUT }}>
          <h2>The whole thing, in five lines</h2>
          <Snippet
            code={`import trustshield

keys = trustshield.KeyPair.generate().save("./keys")
trustshield.sign("notice.png", "signed.png", private_key="./keys")

print(trustshield.verify("signed.png", public_key="./keys"))
# AUTHENTIC: Signature valid and content unchanged.`}
          />
        </motion.section>

        <motion.section className="panel" variants={rise} transition={{ duration: 0.5, ease: EASE_OUT }}>
          <h2><KeyRound size={17} aria-hidden="true" /> Keys</h2>
          <p>
            Two halves, two jobs. They are not interchangeable, and the same pair
            has to be on both sides — a document signed with one private key
            verifies only against its own public key.
          </p>
          <div className="key-split">
            <div>
              <code>private_key.pem</code>
              <strong>Signs</strong>
              <p>Never share it. Anyone holding it can sign in your name.</p>
            </div>
            <div>
              <code>public_key.pem</code>
              <strong>Verifies</strong>
              <p>Share freely. It cannot sign, and verification is impossible without it.</p>
            </div>
          </div>
          <Snippet
            code={`keys = trustshield.KeyPair.generate().save("./keys")
print(keys.fingerprint[:16])   # "is this the key I think it is?"

later = trustshield.KeyPair.load("./keys")`}
          />
          <p className="hint">
            Keys are written as plain PEM so they travel — to a colleague, into a
            container, onto the machine that will verify. Protect the private key
            the way you would a password.
          </p>
        </motion.section>

        <motion.section className="panel" variants={rise} transition={{ duration: 0.5, ease: EASE_OUT }}>
          <h2><ShieldCheck size={17} aria-hidden="true" /> The four answers</h2>
          <p>
            Verification does not return a boolean, because "not authentic" covers
            two very different situations.
          </p>
          <div className="status-list">
            {STATUSES.map(([name, meaning, tone]) => (
              <div key={name} className={`status-row tone-${tone}`}>
                <code>{name}</code>
                <p>{meaning}</p>
              </div>
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
            <strong>TAMPERED</strong> is the one a plain signature cannot produce:
            the signature is valid, but the picture no longer matches what was
            signed. That is someone editing a real notice and re-sharing it.
          </p>
        </motion.section>

        <motion.section className="panel" variants={rise} transition={{ duration: 0.5, ease: EASE_OUT }}>
          <h2><Terminal size={17} aria-hidden="true" /> Command line</h2>
          <p>So signing can be a step in a build or a cron job with no Python around it.</p>
          <Snippet
            label="bash"
            code={`trustshield keygen -o ./keys
trustshield sign notice.png -o signed.png -k ./keys
trustshield verify signed.png -k ./keys`}
          />
          <p>Exit codes let a pipeline branch on the answer — 0 authentic, 1 not, 2 could not run.</p>
          <Snippet
            label="bash"
            code={`if trustshield verify incoming.png -k ./public; then
  echo "genuine"
else
  echo "rejected"
fi`}
          />
        </motion.section>

        <motion.section className="panel" variants={rise} transition={{ duration: 0.5, ease: EASE_OUT }}>
          <h2>What survives, and what does not</h2>
          <div className="table-wrap">
            <table>
              <tbody>
                <tr><td>Screenshotting</td><td className="ok-cell">survives</td></tr>
                <tr><td>JPEG and PNG recompression</td><td className="ok-cell">survives</td></tr>
                <tr><td>Resizing and moderate rescaling</td><td className="ok-cell">survives</td></tr>
                <tr><td>Forwarding through messaging apps</td><td className="ok-cell">survives</td></tr>
                <tr><td>Metadata being stripped</td><td className="ok-cell">irrelevant — nothing is kept there</td></tr>
                <tr><td>Heavy cropping</td><td className="bad-cell">fails — the blocks carrying the signature are cut away</td></tr>
                <tr><td>Photographing a screen</td><td className="bad-cell">fails — moiré and perspective exceed recovery</td></tr>
                <tr><td>Very small images</td><td className="bad-cell">fails — too few blocks to carry 2,272 bits</td></tr>
              </tbody>
            </table>
          </div>
          <p className="hint">
            Two limits worth stating plainly: verification proves that <em>a</em> key
            signed the document, not who owns that key — a directory or certificate
            chain is yours to provide. And this is provenance, not detection: it
            proves what is genuine rather than analysing an unknown image for signs
            of synthesis.
          </p>
        </motion.section>
      </motion.div>
    </div>
  );
}
