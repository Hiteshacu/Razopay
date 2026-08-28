import { animate, useReducedMotion } from "motion/react";
import { useEffect, useRef, useState } from "react";

/**
 * A number that counts up to its value.
 *
 * Only on the way in and only from zero: re-animating on every refresh would
 * make a figure that has not changed look like it did. Reduced motion, and
 * anything above the threshold, renders the final value immediately — nobody
 * wants to watch four thousand tick past.
 */
export function CountUp({ value, max = 500 }: { value: number; max?: number }) {
  const reduceMotion = useReducedMotion();
  const [shown, setShown] = useState(reduceMotion || value > max ? value : 0);
  const animated = useRef(false);

  useEffect(() => {
    if (reduceMotion || value > max || animated.current) {
      setShown(value);
      return;
    }
    animated.current = true;
    const controls = animate(0, value, {
      duration: Math.min(1.1, 0.35 + value * 0.02),
      ease: [0.22, 1, 0.36, 1],
      onUpdate: (latest) => setShown(Math.round(latest))
    });
    return () => controls.stop();
  }, [value, max, reduceMotion]);

  return <>{shown}</>;
}
