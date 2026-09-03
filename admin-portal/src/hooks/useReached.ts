import { useEffect, useRef, useState } from "react";

/**
 * Has this element been reached yet?
 *
 * Not `whileInView`. That reveals on *intersection*, and an element can get
 * from below the fold to above it without ever intersecting — a fast flick, an
 * anchor jump, a restored scroll position, or a headless browser whose viewport
 * measures zero height. When that happens the element stays at opacity 0 for
 * good. A page that can permanently hide its own content is worse than a page
 * with no animation at all, and it is not hypothetical: an automated audit of
 * the landing page reported the feature cards as empty boxes with no icons,
 * because that is exactly what it was shown.
 *
 * This asks a question that cannot get stuck instead: is the top of the element
 * above the bottom of the viewport? True while it is on screen, and true
 * forever after it has passed. A zero-height viewport answers yes rather than
 * never answering. Each element stops listening the moment it answers, so the
 * work disappears as the reader moves down the page.
 */
export function isBackgrounded() {
  return typeof document !== "undefined" && document.visibilityState === "hidden";
}

export function useReached(margin = 0.9) {
  const ref = useRef<HTMLElement | null>(null);
  // A hidden tab never animates: motion suspends entrance animations while
  // visibilityState is "hidden", so anything whose resting state is opacity 0
  // stays invisible for good. That is not a corner case — it is every crawler,
  // link-preview bot and screenshot service. Start revealed for them.
  const [reached, setReached] = useState(isBackgrounded);

  useEffect(() => {
    const element = ref.current;
    if (!element) return;

    let frame = 0;
    let done = false;

    const check = () => {
      if (done) return true;
      // innerHeight of 0 means we cannot measure; reveal rather than hide.
      if (isBackgrounded()) { done = true; setReached(true); return true; }
      const limit = window.innerHeight ? window.innerHeight * margin : Infinity;
      if (element.getBoundingClientRect().top < limit) {
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
