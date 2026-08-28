/**
 * One motion vocabulary for the whole console.
 *
 * Sharing these keeps every screen moving at the same rhythm — the thing
 * that separates an interface that feels considered from one where each
 * page animates to its own taste. Entrances only ever change transform and
 * opacity, so nothing triggers layout work mid-animation.
 */

export const EASE_OUT = [0.22, 1, 0.36, 1] as const;

/** Page and panel entrances. */
export const rise = {
  hidden: { opacity: 0, y: 12 },
  shown: { opacity: 1, y: 0 }
};

/** For a container whose children should arrive in sequence. */
export const stagger = (delay = 0.04) => ({
  hidden: {},
  shown: { transition: { staggerChildren: delay } }
});

export const pageTransition = {
  initial: { opacity: 0, y: 10 },
  animate: { opacity: 1, y: 0 },
  exit: { opacity: 0, y: -6 },
  transition: { duration: 0.24, ease: EASE_OUT }
};

/** Buttons and cards under the pointer. Small enough to feel physical. */
export const press = {
  whileHover: { y: -2 },
  whileTap: { scale: 0.98 }
};
