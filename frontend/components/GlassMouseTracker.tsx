"use client";

import { useEffect } from "react";

const GLASS_SELECTORS = ".card, .sidebar, .modal";
const CLICK_SELECTORS = "button, .card";

export default function GlassMouseTracker() {
  useEffect(() => {
    const onMove = (e: MouseEvent) => {
      const els = document.querySelectorAll<HTMLElement>(GLASS_SELECTORS);
      els.forEach((el) => {
        const r = el.getBoundingClientRect();
        const cx = r.left + r.width / 2;
        const cy = r.top + r.height / 2;
        const angle =
          ((Math.atan2(e.clientY - cy, e.clientX - cx) * 180) / Math.PI + 360) %
          360;
        el.style.setProperty("--rim-angle", `${angle.toFixed(1)}deg`);
        const mx = ((e.clientX - r.left) / r.width) * 100;
        const my = ((e.clientY - r.top) / r.height) * 100;
        el.style.setProperty("--mx", `${mx.toFixed(1)}%`);
        el.style.setProperty("--my", `${my.toFixed(1)}%`);
      });
    };

    const onClick = (e: MouseEvent) => {
      const target = (e.target as HTMLElement)?.closest<HTMLElement>(
        CLICK_SELECTORS
      );
      if (!target) return;

      // Squish animation
      target.classList.remove("glass-squish");
      void target.offsetWidth; // force reflow to restart
      target.classList.add("glass-squish");
      setTimeout(() => target.classList.remove("glass-squish"), 750);

      // Ripple
      const r = target.getBoundingClientRect();
      const ripple = document.createElement("span");
      ripple.className = "glass-ripple-el";
      ripple.style.left = `${e.clientX - r.left}px`;
      ripple.style.top = `${e.clientY - r.top}px`;
      target.style.position = "relative";
      target.appendChild(ripple);
      setTimeout(() => ripple.remove(), 800);
    };

    window.addEventListener("mousemove", onMove, { passive: true });
    window.addEventListener("click", onClick, { passive: true });
    return () => {
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("click", onClick);
    };
  }, []);

  return null;
}
