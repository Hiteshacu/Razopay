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
 * It follows the cursor. Moving the mouse turns the lattice and brightens the
 * blocks nearest the pointer, which is what makes it read as an object with
 * depth rather than a looping video — you can tell it is responding to you.
 *
 * Drawn on a canvas with its own perspective projection rather than through a
 * 3D engine. WebGL is a hard dependency that fails visibly when a driver
 * disagrees with it, and a scene this simple does not need a renderer that
 * costs three times the rest of the application.
 */

const COLUMNS = 9;
const ROWS = 9;
const LAYERS = 4;
const SPACING = 58;
const FOCAL = 900;
const LINK_DISTANCE = 92;
// How close the pointer has to be, in pixels, to brighten a block.
const CURSOR_REACH = 190;

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
          z: (layer - (LAYERS - 1) / 2) * SPACING * 1.5,
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
    const stage = canvas.parentElement;

    const nodes = buildLattice();
    let width = 0;
    let height = 0;
    let zoom = 1;
    let centreX = 0;
    let centreY = 0;
    let frame = 0;
    let running = true;
    let start = performance.now();

    // Where the pointer is, and where the scene has caught up to. The eased
    // pair is what gets drawn, so the lattice leans after the cursor instead
    // of snapping to it.
    let pointerX = 0;
    let pointerY = 0;
    let easedX = 0;
    let easedY = 0;
    let cursor: { x: number; y: number } | null = null;
    let cursorFade = 0;

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

      // Fill the space it is given. A lattice sized in fixed pixels looks
      // like a small object dropped into a large hero; sizing it against the
      // stage keeps it the same relative object on a laptop and a monitor.
      const fit = Math.min(width / 980, height / 660);
      zoom = Math.max(0.85, Math.min(2.1, fit)) * 1.55;

      // Nudged right of centre on wide screens so the mass of the lattice
      // sits beside the headline rather than under it.
      centreX = width > 900 ? width * 0.63 : width * 0.5;
      centreY = height * (width > 900 ? 0.5 : 0.42);
    }

    function draw(now: number) {
      const time = reduceMotion ? 2.2 : (now - start) / 1000;

      if (!reduceMotion) {
        easedX += (pointerX - easedX) * 0.055;
        easedY += (pointerY - easedY) * 0.055;
        cursorFade += ((cursor ? 1 : 0) - cursorFade) * 0.07;
      }

      // The drift continues underneath, so the scene still moves when the
      // pointer is still — and on a touch screen, which never has one.
      const spin = reduceMotion
        ? -0.5
        : Math.sin(time * 0.16) * 0.4 - 0.25 + easedX * 0.55;
      const tilt = reduceMotion
        ? 0.32
        : 0.3 + Math.sin(time * 0.11) * 0.06 - easedY * 0.32;
      // The wave sweeps front to back on a loop, which is what makes the
      // lattice read as something being written rather than merely spinning.
      const wave = ((time * 0.42) % 2.2) - 0.6;

      context!.clearRect(0, 0, width, height);

      const cosSpin = Math.cos(spin);
      const sinSpin = Math.sin(spin);
      const cosTilt = Math.cos(tilt);
      const sinTilt = Math.sin(tilt);

      const projected = nodes.map((node) => {
        const x1 = node.x * cosSpin - node.z * sinSpin;
        const z1 = node.x * sinSpin + node.z * cosSpin;
        const y1 = node.y * cosTilt - z1 * sinTilt;
        const z2 = node.y * sinTilt + z1 * cosTilt;
        const scale = (FOCAL / (FOCAL + z2 + 420)) * zoom;
        const sx = centreX + x1 * scale;
        const sy = centreY + y1 * scale;
        // Distance from the wave front, so the glow travels through depth.
        const lit = Math.max(0, 1 - Math.abs((z1 / 200) - wave) * 1.9);
        let near = 0;
        if (cursor && cursorFade > 0.01) {
          const px = sx - cursor.x;
          const py = sy - cursor.y;
          const gap = px * px + py * py;
          if (gap < CURSOR_REACH * CURSOR_REACH) {
            near = (1 - Math.sqrt(gap) / CURSOR_REACH) * cursorFade;
          }
        }
        return {
          sx,
          sy,
          scale,
          depth: z2,
          // What the block is currently worth to the picture: whichever of
          // the wave and the pointer is reaching it more.
          energy: Math.max(lit, near),
          near,
          carrier: node.carrier,
          pulse: 0.6 + Math.sin(time * 1.6 + node.phase) * 0.4
        };
      });

      projected.sort((a, b) => b.depth - a.depth);

      // Links first, so nodes sit on top of their own connections. Anything
      // the wave or the pointer has reached can carry one.
      //
      // This pass is every pair of blocks, so it is the one place in the
      // scene where constant factors matter. It compares squared distances
      // and takes the root only for the few pairs close enough to draw —
      // Math.hypot on every pair costs more than the drawing does.
      const reach = LINK_DISTANCE * zoom;
      const reachSquared = reach * reach;
      context!.lineWidth = 1;
      for (let i = 0; i < projected.length; i += 1) {
        const a = projected[i];
        if (a.energy < 0.08) continue;
        for (let j = i + 1; j < projected.length; j += 1) {
          const b = projected[j];
          if (b.energy < 0.08) continue;
          const dx = a.sx - b.sx;
          const dy = a.sy - b.sy;
          const gap = dx * dx + dy * dy;
          if (gap > reachSquared) continue;
          const strength =
            (1 - Math.sqrt(gap) / reach) * (a.energy < b.energy ? a.energy : b.energy);
          context!.strokeStyle = `rgba(45, 212, 191, ${strength * 0.5})`;
          context!.beginPath();
          context!.moveTo(a.sx, a.sy);
          context!.lineTo(b.sx, b.sy);
          context!.stroke();
        }
      }

      for (const point of projected) {
        const energy = point.energy;
        const base = point.carrier ? 3.1 : 1.7;
        const radius = base * point.scale * (0.85 + energy * 0.95);
        // Depth fog: distant blocks recede rather than crowding the front.
        const fog = Math.max(0.12, Math.min(1, point.scale * 1.05));

        if (energy > 0.12 && (point.carrier || point.near > 0.35)) {
          const glow = context!.createRadialGradient(
            point.sx, point.sy, 0,
            point.sx, point.sy, radius * 7
          );
          glow.addColorStop(0, `rgba(94, 234, 212, ${0.4 * energy * fog})`);
          glow.addColorStop(1, "rgba(94, 234, 212, 0)");
          context!.fillStyle = glow;
          context!.beginPath();
          context!.arc(point.sx, point.sy, radius * 7, 0, Math.PI * 2);
          context!.fill();
        }

        const alpha = point.carrier
          ? (0.3 + energy * 0.7) * fog
          : (0.16 + energy * 0.45) * fog * point.pulse;
        context!.fillStyle = point.carrier
          ? `rgba(153, 246, 228, ${alpha})`
          : `rgba(125, 176, 170, ${alpha})`;
        context!.beginPath();
        context!.arc(point.sx, point.sy, radius, 0, Math.PI * 2);
        context!.fill();
      }

      // A soft halo under the pointer. Without it the brightening reads as
      // the lattice flickering rather than as the cursor doing something.
      if (cursor && cursorFade > 0.01) {
        const halo = context!.createRadialGradient(
          cursor.x, cursor.y, 0,
          cursor.x, cursor.y, CURSOR_REACH
        );
        halo.addColorStop(0, `rgba(45, 212, 191, ${0.09 * cursorFade})`);
        halo.addColorStop(1, "rgba(45, 212, 191, 0)");
        context!.fillStyle = halo;
        context!.beginPath();
        context!.arc(cursor.x, cursor.y, CURSOR_REACH, 0, Math.PI * 2);
        context!.fill();
      }

      if (running && !reduceMotion) frame = requestAnimationFrame(draw);
    }

    function onPointerMove(event: PointerEvent) {
      // A finger dragging the page should scroll it, not steer a background.
      if (event.pointerType === "touch") return;
      const bounds = canvas!.getBoundingClientRect();
      const x = event.clientX - bounds.left;
      const y = event.clientY - bounds.top;
      cursor = { x, y };
      pointerX = (x / bounds.width) * 2 - 1;
      pointerY = (y / bounds.height) * 2 - 1;
    }

    function onPointerLeave() {
      cursor = null;
      pointerX = 0;
      pointerY = 0;
    }

    resize();
    frame = requestAnimationFrame(draw);
    window.addEventListener("resize", resize);
    if (!reduceMotion && stage) {
      // Listened for on the stage, not the canvas: the copy and the veil sit
      // above the canvas, so the canvas itself never sees the pointer.
      stage.addEventListener("pointermove", onPointerMove);
      stage.addEventListener("pointerleave", onPointerLeave);
    }

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
      if (stage) {
        stage.removeEventListener("pointermove", onPointerMove);
        stage.removeEventListener("pointerleave", onPointerLeave);
      }
    };
  }, [reduceMotion]);

  return <canvas ref={canvasRef} className="lattice-canvas" aria-hidden="true" />;
}
