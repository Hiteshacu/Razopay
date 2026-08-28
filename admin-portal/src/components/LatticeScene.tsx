import { useEffect, useRef } from "react";
import { useReducedMotion } from "motion/react";

/**
 * The signing lattice: the document's 8x8 block grid, in three dimensions.
 *
 * A signature is not stamped on top of a document — it is written across the
 * blocks the image is already made of. So the hero shows exactly that: a
 * lattice of blocks with a wave travelling through it, lighting the carriers
 * that hold the proof and drawing the links between them.
 *
 * Drawn on a canvas with its own perspective projection rather than through a
 * 3D engine. WebGL is a hard dependency that fails visibly when a driver
 * disagrees with it, and a scene this simple does not need a renderer that
 * costs three times the rest of the application.
 */

const COLUMNS = 7;
const ROWS = 7;
const LAYERS = 3;
const SPACING = 52;
const FOCAL = 620;
const LINK_DISTANCE = 78;

type Node = { x: number; y: number; z: number; carrier: boolean; phase: number };

function buildLattice(): Node[] {
  const nodes: Node[] = [];
  for (let layer = 0; layer < LAYERS; layer += 1) {
    for (let row = 0; row < ROWS; row += 1) {
      for (let column = 0; column < COLUMNS; column += 1) {
        const index = layer * ROWS * COLUMNS + row * COLUMNS + column;
        nodes.push({
          x: (column - (COLUMNS - 1) / 2) * SPACING,
          y: (row - (ROWS - 1) / 2) * SPACING,
          z: (layer - (LAYERS - 1) / 2) * SPACING * 1.6,
          // A scattered minority carry the payload, as they do in the engine:
          // the proof is spread across the grid, not written in a block.
          carrier: index % 7 === 3 || index % 11 === 5,
          phase: (column + row * 1.7 + layer * 3.1) * 0.35
        });
      }
    }
  }
  return nodes;
}

export function LatticeScene() {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const reduceMotion = useReducedMotion();

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const context = canvas.getContext("2d");
    if (!context) return;

    const nodes = buildLattice();
    let width = 0;
    let height = 0;
    let frame = 0;
    let running = true;
    let start = performance.now();

    function resize() {
      const parent = canvas!.parentElement;
      if (!parent) return;
      const ratio = Math.min(window.devicePixelRatio || 1, 2);
      width = parent.clientWidth;
      height = parent.clientHeight;
      canvas!.width = width * ratio;
      canvas!.height = height * ratio;
      canvas!.style.width = `${width}px`;
      canvas!.style.height = `${height}px`;
      context!.setTransform(ratio, 0, 0, ratio, 0, 0);
    }

    function draw(now: number) {
      const time = reduceMotion ? 2.2 : (now - start) / 1000;
      const spin = reduceMotion ? -0.5 : Math.sin(time * 0.16) * 0.55 - 0.25;
      const tilt = reduceMotion ? 0.32 : 0.3 + Math.sin(time * 0.11) * 0.07;
      // The wave sweeps front to back on a loop, which is what makes the
      // lattice read as something being written rather than merely spinning.
      const wave = ((time * 0.42) % 2.2) - 0.6;

      context!.clearRect(0, 0, width, height);

      const cosSpin = Math.cos(spin);
      const sinSpin = Math.sin(spin);
      const cosTilt = Math.cos(tilt);
      const sinTilt = Math.sin(tilt);
      const centreX = width / 2;
      const centreY = height / 2;

      const projected = nodes.map((node) => {
        const x1 = node.x * cosSpin - node.z * sinSpin;
        const z1 = node.x * sinSpin + node.z * cosSpin;
        const y1 = node.y * cosTilt - z1 * sinTilt;
        const z2 = node.y * sinTilt + z1 * cosTilt;
        const scale = FOCAL / (FOCAL + z2 + 320);
        // Distance from the wave front, so the glow travels through depth.
        const lit = Math.max(0, 1 - Math.abs((z1 / 200) - wave) * 1.9);
        return {
          sx: centreX + x1 * scale,
          sy: centreY + y1 * scale,
          scale,
          depth: z2,
          lit,
          carrier: node.carrier,
          pulse: 0.6 + Math.sin(time * 1.6 + node.phase) * 0.4
        };
      });

      projected.sort((a, b) => b.depth - a.depth);

      // Links first, so nodes sit on top of their own connections.
      for (let i = 0; i < projected.length; i += 1) {
        const a = projected[i];
        if (a.lit < 0.08) continue;
        for (let j = i + 1; j < projected.length; j += 1) {
          const b = projected[j];
          if (b.lit < 0.08) continue;
          const dx = a.sx - b.sx;
          const dy = a.sy - b.sy;
          const distance = Math.hypot(dx, dy);
          if (distance > LINK_DISTANCE) continue;
          const strength = (1 - distance / LINK_DISTANCE) * Math.min(a.lit, b.lit);
          context!.strokeStyle = `rgba(45, 212, 191, ${strength * 0.5})`;
          context!.lineWidth = 1;
          context!.beginPath();
          context!.moveTo(a.sx, a.sy);
          context!.lineTo(b.sx, b.sy);
          context!.stroke();
        }
      }

      for (const point of projected) {
        const base = point.carrier ? 3.1 : 1.7;
        const radius = base * point.scale * (0.85 + point.lit * 0.9);
        // Depth fog: distant blocks recede rather than crowding the front.
        const fog = Math.max(0.12, Math.min(1, point.scale * 1.35));

        if (point.carrier && point.lit > 0.12) {
          const glow = context!.createRadialGradient(
            point.sx, point.sy, 0,
            point.sx, point.sy, radius * 7
          );
          glow.addColorStop(0, `rgba(94, 234, 212, ${0.4 * point.lit * fog})`);
          glow.addColorStop(1, "rgba(94, 234, 212, 0)");
          context!.fillStyle = glow;
          context!.beginPath();
          context!.arc(point.sx, point.sy, radius * 7, 0, Math.PI * 2);
          context!.fill();
        }

        const alpha = point.carrier
          ? (0.3 + point.lit * 0.7) * fog
          : (0.16 + point.lit * 0.4) * fog * point.pulse;
        context!.fillStyle = point.carrier
          ? `rgba(153, 246, 228, ${alpha})`
          : `rgba(125, 176, 170, ${alpha})`;
        context!.beginPath();
        context!.arc(point.sx, point.sy, radius, 0, Math.PI * 2);
        context!.fill();
      }

      if (running && !reduceMotion) frame = requestAnimationFrame(draw);
    }

    resize();
    frame = requestAnimationFrame(draw);
    window.addEventListener("resize", resize);

    // Stop entirely when the tab is hidden. An animation nobody is looking at
    // is just a drain on a laptop battery.
    //
    // Restarting cannot be conditional on having stopped: browsers suspend
    // requestAnimationFrame in a hidden tab, so a page opened in the
    // background never paints its first frame even though nothing marked it
    // as stopped. Becoming visible always schedules a frame.
    function onVisibility() {
      if (document.hidden) {
        running = false;
        cancelAnimationFrame(frame);
        return;
      }
      running = true;
      start = performance.now() - 2200;
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(draw);
    }
    document.addEventListener("visibilitychange", onVisibility);

    return () => {
      running = false;
      cancelAnimationFrame(frame);
      window.removeEventListener("resize", resize);
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, [reduceMotion]);

  return <canvas ref={canvasRef} className="lattice-canvas" aria-hidden="true" />;
}
