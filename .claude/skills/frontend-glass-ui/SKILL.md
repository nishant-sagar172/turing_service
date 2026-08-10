---
name: frontend-glass-ui
description: Liquid Glass UI/UX system for the turing frontend — Apple-grade premium glass morphism. Load before writing or editing any frontend file.
---

## Stack context
Next.js 14 App Router · TypeScript · plain CSS (globals.css) · no Tailwind · no component library.
All styles live in `frontend/app/globals.css` via CSS custom properties and class selectors.

---

## Design philosophy — Liquid Glass (Apple iOS 26 / macOS 26 grade)

Three layers on every surface:
1. **Specular** — bright top-left corner highlight (`::before` gradient + inset box-shadow top edge)
2. **Glass body** — semi-transparent with deep backdrop-filter blur + brightness + saturate
3. **Depth** — layered drop shadows + subtle inner rim

---

## CSS variables (`:root`)

```css
/* Glass surfaces */
--glass-bg: rgba(255, 255, 255, 0.05);
--glass-bg-hover: rgba(255, 255, 255, 0.09);
--glass-bg-active: rgba(79, 140, 255, 0.14);
--glass-border: rgba(255, 255, 255, 0.10);
--glass-border-hover: rgba(255, 255, 255, 0.20);
--glass-border-active: rgba(79, 140, 255, 0.45);

/* Liquid Glass shadows — layered for depth */
--glass-shadow:
  inset 0 1px 0 rgba(255,255,255,0.18),   /* specular top rim */
  inset 0 0 0 0.5px rgba(255,255,255,0.08), /* inner border */
  0 4px 16px rgba(0,0,0,0.30),
  0 16px 48px rgba(0,0,0,0.22);
--glass-shadow-hover:
  inset 0 1px 0 rgba(255,255,255,0.28),
  inset 0 0 0 0.5px rgba(255,255,255,0.12),
  0 8px 24px rgba(0,0,0,0.36),
  0 24px 64px rgba(0,0,0,0.28);
--glass-shadow-active: 0 0 0 2px rgba(79,140,255,0.35), 0 0 20px rgba(79,140,255,0.15);

/* Blur strength */
--blur-sm: 12px;
--blur-md: 24px;
--blur-lg: 40px;
--blur-xl: 56px;

/* Specular highlight */
--specular-corner: linear-gradient(135deg, rgba(255,255,255,0.22) 0%, rgba(255,255,255,0.04) 40%, transparent 60%);
--specular-edge: linear-gradient(180deg, rgba(255,255,255,0.14) 0%, transparent 100%);

/* Ambient glow — stronger for premium feel */
--glow-accent: rgba(79, 140, 255, 0.28);
--glow-accent-strong: rgba(79, 140, 255, 0.45);
--glow-green: rgba(55, 201, 120, 0.28);
--glow-red: rgba(255, 95, 109, 0.28);
--glow-amber: rgba(245, 181, 68, 0.28);

/* Background — rich multi-orb mesh */
--bg-gradient:
  radial-gradient(ellipse 90% 70% at 15% 5%,  rgba(79,140,255,0.12) 0%, transparent 55%),
  radial-gradient(ellipse 60% 50% at 85% 80%,  rgba(55,201,120,0.08) 0%, transparent 50%),
  radial-gradient(ellipse 50% 40% at 70% 15%,  rgba(120,80,255,0.06) 0%, transparent 45%),
  radial-gradient(ellipse 40% 30% at 20% 85%,  rgba(0,180,220,0.05) 0%, transparent 40%),
  #080c14;

/* Motion */
--ease-glass: cubic-bezier(0.16, 1, 0.3, 1);
--ease-spring: cubic-bezier(0.34, 1.56, 0.64, 1);
--duration-fast: 150ms;
--duration-normal: 250ms;
--duration-slow: 400ms;
```

---

## Liquid Glass surface recipe

Apply to any floating element:

```css
.liquid-glass {
  background: var(--glass-bg);
  border: 1px solid var(--glass-border);
  backdrop-filter: blur(var(--blur-md)) saturate(200%) brightness(1.06);
  -webkit-backdrop-filter: blur(var(--blur-md)) saturate(200%) brightness(1.06);
  box-shadow: var(--glass-shadow);
  border-radius: var(--radius);
  position: relative;
  overflow: hidden;
}
/* Specular corner highlight */
.liquid-glass::before {
  content: '';
  position: absolute;
  inset: 0;
  background: var(--specular-corner);
  pointer-events: none;
  border-radius: inherit;
  z-index: 1;
}
/* Color absorption tint from accent */
.liquid-glass::after {
  content: '';
  position: absolute;
  inset: 0;
  background: radial-gradient(ellipse 80% 50% at 20% 0%, rgba(79,140,255,0.06) 0%, transparent 60%);
  pointer-events: none;
  border-radius: inherit;
  z-index: 0;
}
```

---

## Component rules

### Cards
- Use `var(--glass-shadow)` for layered inset rim + drop shadow.
- `::before` = `var(--specular-corner)` — bright top-left specular.
- `::after` = accent tint absorption.
- Hover: `translateY(-3px)` + `var(--glass-shadow-hover)` + `border-color: var(--glass-border-hover)`.
- Card `h2`: `border-bottom: 1px solid var(--glass-border); padding-bottom: 12px; margin-bottom: 16px`.

### Sidebar
- `backdrop-filter: blur(var(--blur-lg)) saturate(200%) brightness(1.04)`.
- Background: `rgba(8, 12, 20, 0.55)` — more transparent so bg-gradient shows through.
- Right border: `1px solid var(--glass-border)`.
- Inset right glow: `box-shadow: inset -1px 0 0 rgba(255,255,255,0.05)`.
- Nav link hover: liquid glass pill `background: var(--glass-bg-hover)` + `translateX(4px)` + inner rim.
- Active link: `background: var(--glass-bg-active)` + `border-left: 3px solid var(--accent)` + accent glow `box-shadow: inset 0 0 12px rgba(79,140,255,0.08)`.

### Buttons
- Primary: `background: rgba(79,140,255,0.18)` + `border: 1px solid rgba(79,140,255,0.38)` + `box-shadow: inset 0 1px 0 rgba(255,255,255,0.25), 0 0 0 0 var(--glow-accent)`.
  - Hover: `box-shadow: inset 0 1px 0 rgba(255,255,255,0.30), 0 0 20px var(--glow-accent), 0 4px 16px rgba(79,140,255,0.20)` + `translateY(-2px)`.
  - Active: `scale(0.96)` + shadow collapses.
- Secondary: pure liquid glass — `var(--glass-bg)` + inset rim only.
- Danger: red tint + `box-shadow: inset 0 1px 0 rgba(255,120,120,0.20)`.

### Inputs / Selects / Textareas
- `background: rgba(255,255,255,0.03)` + `border: 1px solid var(--glass-border)`.
- `box-shadow: inset 0 2px 4px rgba(0,0,0,0.20)` — recessed, not floating.
- Focus: `border-color: var(--glass-border-active)` + `box-shadow: inset 0 2px 4px rgba(0,0,0,0.20), 0 0 0 3px rgba(79,140,255,0.15)`.

### Modal
- `background: rgba(8,14,26,0.78)` + `backdrop-filter: blur(var(--blur-xl)) saturate(200%) brightness(1.08)`.
- `box-shadow: var(--glass-shadow-hover), 0 0 80px rgba(0,0,0,0.5)`.
- `::before` = bright specular corner.
- Backdrop: `background: rgba(0,0,0,0.55)` + `backdrop-filter: blur(8px)`.
- Entrance: `scale(0.94) → scale(1)` with `--ease-spring`.

### Badges
- `backdrop-filter: blur(8px) saturate(180%)`.
- Inset `box-shadow: inset 0 1px 0 rgba(255,255,255,0.15)` — specular on pill.
- Colors: green badge = `box-shadow: 0 0 8px rgba(55,201,120,0.25)`, red = `0 0 8px rgba(255,95,109,0.25)`.

### Filter strip / Tabs
- Inactive: liquid glass pill with specular inset.
- Active: `background: var(--glass-bg-active)` + `box-shadow: 0 0 16px var(--glow-accent), inset 0 1px 0 rgba(255,255,255,0.20)`.

---

## Responsive layout

### Breakpoints
```
Mobile  : ≤ 640px
Tablet  : 641px – 1024px
Desktop : ≥ 1025px
```

### Mobile sidebar
Sidebar = `display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between`.
Brand + hamburger on row 1. Nav on row 2 (`flex-basis: 100%`). `max-height: 56px` collapsed → `800px` open.
`brand small` hidden on mobile. Transition: `max-height var(--duration-slow) var(--ease-glass)`.

---

## Background
```css
body { background: var(--bg-gradient); }
/* Animated ambient orbs */
@keyframes orb-drift {
  0%, 100% { transform: translate(0, 0) scale(1); }
  50%       { transform: translate(20px, -15px) scale(1.05); }
}
```

## Performance
- `backdrop-filter` only on sidebar, cards, modals, floating elements — NOT on inline text or icons.
- All animations on `transform` + `opacity` only (GPU composited).
- Mobile: `@supports (backdrop-filter: blur(1px))` guard with opaque fallback.

## Checklist
- [ ] `box-shadow` uses layered inset rim + drop shadow (not just drop shadow)
- [ ] `::before` specular corner on every floating surface
- [ ] `backdrop-filter` includes `saturate(200%) brightness(1.06)`
- [ ] Hover lifts with `translateY(-2px)` or `-3px`
- [ ] Active press uses `scale(0.96)`
- [ ] Focus uses `box-shadow` ring, not outline
- [ ] Tested at 375px / 768px / 1280px
