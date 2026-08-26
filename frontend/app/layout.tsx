import type { Metadata } from "next";
import "./globals.css";
import GlassMouseTracker from "../components/GlassMouseTracker";

export const metadata: Metadata = {
  title: "turing · Bolna gateway",
  description: "Development console for turing_service",
  icons: { icon: "data:," },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        {/* Blocking theme script — runs synchronously before first paint.
            1. Adds theme-init to kill transitions during apply.
            2. Sets data-theme from localStorage or OS preference.
            3. Removes theme-init after two rAF cycles (first painted frame). */}
        <script dangerouslySetInnerHTML={{ __html: `(function(){
          var stored = localStorage.getItem('theme');
          var prefer = window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark';
          var theme = stored || prefer;
          var el = document.documentElement;
          el.classList.add('theme-init');
          el.setAttribute('data-theme', theme);
          requestAnimationFrame(function(){
            requestAnimationFrame(function(){
              el.classList.remove('theme-init');
            });
          });
        })();`}} />
      </head>
      <body>
        {/* Hidden SVG filter — liquid glass distortion used by .glass-squish */}
        <svg style={{ position: "absolute", width: 0, height: 0, overflow: "hidden" }} aria-hidden="true">
          <defs>
            <filter id="lg-dist" x="-30%" y="-30%" width="160%" height="160%" colorInterpolationFilters="sRGB">
              <feTurbulence type="fractalNoise" baseFrequency="0.007 0.007" numOctaves="4" seed="42" result="noise" />
              <feGaussianBlur in="noise" stdDeviation="1.5" result="blurred" />
              <feDisplacementMap in="SourceGraphic" in2="blurred" scale="55" xChannelSelector="R" yChannelSelector="G" />
            </filter>
          </defs>
        </svg>
        <GlassMouseTracker />
        {children}
      </body>
    </html>
  );
}
