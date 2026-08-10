"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState, useEffect } from "react";

const links = [
  { href: "/", label: "Dashboard" },
  { href: "/calls", label: "Calls" },
  { href: "/analytics", label: "Analytics" },
  { href: "/batches", label: "Batches" },
  { href: "/phone-numbers", label: "Phone Numbers" },
  { href: "/clients", label: "Clients" },
  { href: "/agents", label: "Agents" },
];

export default function Nav() {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const [theme, setTheme] = useState<"light" | "dark">("dark");

  // Read initial theme from the attribute set by the FOUC-prevention script
  useEffect(() => {
    const stored = document.documentElement.getAttribute("data-theme") as "light" | "dark" | null;
    setTheme(stored ?? "dark");
  }, []);

  // Close nav when route changes
  useEffect(() => { setOpen(false); }, [pathname]);

  // Close nav when clicking outside on mobile
  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent) => {
      const aside = document.querySelector(".sidebar");
      if (aside && !aside.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [open]);

  function toggleTheme() {
    const next = theme === "dark" ? "light" : "dark";
    setTheme(next);
    document.documentElement.setAttribute("data-theme", next);
    localStorage.setItem("theme", next);
  }

  return (
    <aside className={`sidebar${open ? " open" : ""}`}>
      <div className="brand">
        turing
        <small>voice gateway · dev console</small>
      </div>

      <button
        className="menu-toggle"
        aria-label={open ? "Close menu" : "Open menu"}
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
      >
        <span />
        <span />
        <span />
      </button>

      <nav className="nav" onClick={() => setOpen(false)}>
        {links.map((l) => {
          const active =
            l.href === "/" ? pathname === "/" : pathname.startsWith(l.href);
          return (
            <Link key={l.href} href={l.href} className={active ? "active" : ""}>
              {l.label}
            </Link>
          );
        })}
      </nav>

      <div className="nav-footer">
        <button
          className="theme-toggle"
          onClick={toggleTheme}
          title={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
          aria-label={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
        >
          {theme === "dark" ? "☀" : "◑"}
        </button>
      </div>
    </aside>
  );
}
