import { motion, useReducedMotion } from "motion/react";

/**
 * Shows what signing actually does to a document.
 *
 * The loop runs through the real sequence: the page is divided into 8x8
 * blocks, a fingerprint is taken of the visual content, that fingerprint is
 * signed, and the signature is written into the blocks themselves rather than
 * stamped on top. The final state is a document that looks untouched and
 * carries a proof — which is the idea the page has to land.
 *
 * With reduced motion the same story is told as a single static frame; nothing
 * is animated and no information is lost.
 */

const BLOCK_COLUMNS = 7;
const BLOCK_ROWS = 9;
const CARRIER_BLOCKS = [9, 17, 23, 31, 38, 44, 51, 12, 27, 40];

export function SealAnimation() {
  const reduceMotion = useReducedMotion();

  const blocks = Array.from({ length: BLOCK_COLUMNS * BLOCK_ROWS }, (_, index) => index);

  return (
    <div className="seal-figure" aria-hidden="true">
      <svg viewBox="0 0 260 300" role="presentation">
        <defs>
          <clipPath id="page-clip">
            <rect x="24" y="18" width="212" height="264" rx="10" />
          </clipPath>
        </defs>

        {/* the document */}
        <rect
          x="24"
          y="18"
          width="212"
          height="264"
          rx="10"
          className="seal-page"
        />

        {/* content lines, so it reads as a notice rather than an empty card */}
        <g className="seal-content">
          <rect x="44" y="44" width="96" height="9" rx="3" />
          <rect x="44" y="64" width="150" height="6" rx="3" />
          <rect x="44" y="78" width="132" height="6" rx="3" />
          <rect x="44" y="126" width="150" height="6" rx="3" />
          <rect x="44" y="140" width="118" height="6" rx="3" />
          <rect x="44" y="154" width="140" height="6" rx="3" />
          <rect x="44" y="212" width="70" height="6" rx="3" />
          <rect x="44" y="226" width="94" height="6" rx="3" />
        </g>

        {/* the 8x8 block grid the engine actually works on */}
        <g clipPath="url(#page-clip)">
          {blocks.map((index) => {
            const column = index % BLOCK_COLUMNS;
            const row = Math.floor(index / BLOCK_COLUMNS);
            const isCarrier = CARRIER_BLOCKS.includes(index);

            return (
              <motion.rect
                key={index}
                x={24 + column * 30.3}
                y={18 + row * 29.3}
                width={30.3}
                height={29.3}
                className={isCarrier ? "seal-block carrier" : "seal-block"}
                initial={reduceMotion ? { opacity: isCarrier ? 0.5 : 0.12 } : { opacity: 0 }}
                animate={
                  reduceMotion
                    ? undefined
                    : {
                        opacity: isCarrier ? [0, 0.14, 0.62, 0.14, 0] : [0, 0.14, 0.14, 0.1, 0]
                      }
                }
                transition={
                  reduceMotion
                    ? undefined
                    : {
                        duration: 6,
                        times: [0, 0.22, 0.46, 0.7, 1],
                        repeat: Infinity,
                        // Sweep the grid so the proof reads as being written
                        // across the page rather than appearing all at once.
                        delay: (row * BLOCK_COLUMNS + column) * 0.012,
                        ease: "easeInOut"
                      }
                }
              />
            );
          })}
        </g>

        {/* the seal that forms once the signature is embedded */}
        <motion.g
          initial={reduceMotion ? { opacity: 1, scale: 1 } : { opacity: 0, scale: 0.7 }}
          animate={reduceMotion ? undefined : { opacity: [0, 0, 1, 1, 0], scale: [0.7, 0.7, 1, 1, 0.9] }}
          transition={
            reduceMotion
              ? undefined
              : { duration: 6, times: [0, 0.4, 0.56, 0.78, 1], repeat: Infinity, ease: "easeOut" }
          }
          style={{ transformOrigin: "130px 250px" }}
        >
          <circle cx="130" cy="250" r="21" className="seal-badge" />
          <motion.path
            d="M121 250.5l6.2 6.2L140 244"
            className="seal-tick"
            fill="none"
            initial={reduceMotion ? { pathLength: 1 } : { pathLength: 0 }}
            animate={reduceMotion ? undefined : { pathLength: [0, 0, 1, 1, 1] }}
            transition={
              reduceMotion
                ? undefined
                : { duration: 6, times: [0, 0.46, 0.62, 0.9, 1], repeat: Infinity, ease: "easeOut" }
            }
          />
        </motion.g>
      </svg>

      <div className="seal-caption">
        <span className="seal-dot" />
        Proof written into the pixels, not attached to the file
      </div>
    </div>
  );
}
