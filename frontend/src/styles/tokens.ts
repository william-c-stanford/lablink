/**
 * LabLink Neuromorphic Design Tokens
 *
 * All values extracted directly from LandingPage.html.
 * Light-only design — no dark mode variants.
 *
 * Shadow system:
 *   "raised" (nm-outset) — element appears to float above the surface
 *   "inset"  (nm-inset)  — element appears pressed into the surface
 *   "btn"    (nm-btn)    — interactive button resting state
 *   "btnHover"           — button hover state (reduced shadow + translateY)
 *   "btnActive"          — button active/pressed state
 *   "circle"             — circle pressed (step indicators, avatars)
 *   "glowBlue"           — raised + blue glow ring (primary CTAs, logo)
 *   "glowBlueHover"      — hover variant of glowBlue
 */

// ---------------------------------------------------------------------------
// Raw shadow component values (reused to compose shadow strings)
// ---------------------------------------------------------------------------

/** Dark shadow colour used in all neuromorphic shadows */
const SHADOW_DARK = "rgba(174, 185, 201, 0.4)" as const;

/** Light shadow colour used in all neuromorphic shadows */
const SHADOW_LIGHT = "rgba(255, 255, 255, 0.9)" as const;

/** Blue glow colour for primary interactive elements */
const GLOW_BLUE_BASE = "rgba(59, 130, 246, 0.4)" as const;

/** Blue glow colour for hovered primary interactive elements */
const GLOW_BLUE_HOVER = "rgba(59, 130, 246, 0.6)" as const;

// ---------------------------------------------------------------------------
// Color palette
// ---------------------------------------------------------------------------

export const colors = {
  // Core neuromorphic surface
  bg: "#f5f7fa",         // --bg  : base grey surface (all neuromorphic elements share this bg)
  surface: "#ffffff",    // --light: pure white surface (popovers, modals)

  // Brand
  blue: {
    DEFAULT: "#3b82f6",  // --blue / blue-500  : primary accent
    dark:    "#2563eb",  // blue-600           : deeper accent, chart strokes
    glow:    GLOW_BLUE_BASE,
    glowHover: GLOW_BLUE_HOVER,
  },

  // Text scale
  text: {
    primary:   "#0f172a", // slate-900 : headings, hero text
    secondary: "#1e293b", // slate-800 : body (--text-dark)
    muted:     "#64748b", // slate-500 : secondary body, descriptions
    subtle:    "#94a3b8", // slate-400 : placeholders, metadata
    disabled:  "#cbd5e1", // slate-300 : disabled / decorative
  },

  // Semantic / status colors
  error:   "#ef4444", // red-500
  warning: "#f97316", // orange-500
  caution: "#fbbf24", // amber-400
  info:    "#6366f1", // indigo-500

  // Border / divider
  border: {
    DEFAULT: "#e2e8f0", // slate-200
    dark:    "#cbd5e1", // slate-300
  },

  // Shadow primitives (used in boxShadow compositions)
  shadow: {
    dark:  SHADOW_DARK,
    light: SHADOW_LIGHT,
  },

  // Footer / dark surface (footer bg only — no dark mode)
  footerBg:    "#0f172a", // slate-900
  footerCard:  "#1e293b", // slate-800
  footerText:  "#64748b", // slate-500
  footerLink:  "#cbd5e1", // slate-300
  footerDivider: "#1e293b", // slate-800

  // Accent overlays (DMTA cycle nodes)
  indigoTint: "rgba(99,  102, 241, 0.05)", // indigo-50/50 approx
  blueTint:   "rgba(59,  130, 246, 0.05)", // blue-50/50   approx
  blueBorder: "rgba(59,  130, 246, 0.20)", // blue/20 border on glow btn
} as const;

// ---------------------------------------------------------------------------
// Typography
// ---------------------------------------------------------------------------

export const typography = {
  fontFamily: {
    sans: "'Plus Jakarta Sans', sans-serif",
    mono: "'JetBrains Mono', monospace",
  },

  /** Google Fonts URL — include in <head> or @import in global CSS */
  googleFontsUrl:
    "https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500&display=swap",

  fontWeight: {
    regular:    400,
    medium:     500,
    semibold:   600,
    bold:       700,
    extrabold:  800,
  },

  /** Heading scale extracted from the landing page */
  fontSize: {
    "2xs": "0.625rem",  // 10px — uppercase labels / chip text
    xs:    "0.75rem",   // 12px — metadata, mono stamps
    sm:    "0.875rem",  // 14px — small body, captions
    base:  "1rem",      // 16px — default body
    lg:    "1.125rem",  // 18px
    xl:    "1.25rem",   // 20px — sub-headings
    "2xl": "1.5rem",    // 24px — card headings
    "3xl": "1.875rem",  // 30px — section sub-heads
    "4xl": "2.25rem",   // 36px — stat numbers, section headings
    "5xl": "3rem",      // 48px — hero sub-heading
    "6xl": "3.75rem",   // 60px — hero heading (lg)
    "7xl": "4.5rem",    // 72px — largest hero text
  },

  letterSpacing: {
    tight:    "-0.025em",
    tighter:  "-0.05em",
    normal:   "0em",
    wide:     "0.025em",
    wider:    "0.05em",
    widest:   "0.1em",  // uppercase tracking-widest labels
  },

  lineHeight: {
    none:    "1",
    tight:   "1.25",
    snug:    "1.375",
    normal:  "1.5",
    relaxed: "1.625", // used extensively in body copy
    loose:   "2",
  },
} as const;

// ---------------------------------------------------------------------------
// Neuromorphic shadow system
// ---------------------------------------------------------------------------

export const shadows = {
  /**
   * nm-outset — raised card / panel
   * box-shadow: 8px 8px 16px <dark>, -8px -8px 16px <light>
   */
  raised: `8px 8px 16px ${SHADOW_DARK}, -8px -8px 16px ${SHADOW_LIGHT}`,

  /**
   * nm-inset — pressed / recessed surface
   * box-shadow: inset 6px 6px 12px <dark>, inset -6px -6px 12px <light>
   */
  inset: `inset 6px 6px 12px ${SHADOW_DARK}, inset -6px -6px 12px ${SHADOW_LIGHT}`,

  /**
   * nm-btn resting state
   * box-shadow: 4px 4px 8px <dark>, -4px -4px 8px <light>
   */
  btn: `4px 4px 8px ${SHADOW_DARK}, -4px -4px 8px ${SHADOW_LIGHT}`,

  /**
   * nm-btn hover state (slightly reduced — gives "push in" feel)
   * box-shadow: 2px 2px 4px <dark>, -2px -2px 4px <light>
   */
  btnHover: `2px 2px 4px ${SHADOW_DARK}, -2px -2px 4px ${SHADOW_LIGHT}`,

  /**
   * nm-btn-active / fully pressed
   * box-shadow: inset 2px 2px 4px <dark>, inset -2px -2px 4px <light>
   */
  btnActive: `inset 2px 2px 4px ${SHADOW_DARK}, inset -2px -2px 4px ${SHADOW_LIGHT}`,

  /**
   * nm-circle-pressed — step indicator circles, avatar wells
   * box-shadow: inset 5px 5px 10px <dark>, inset -5px -5px 10px <light>
   */
  circle: `inset 5px 5px 10px ${SHADOW_DARK}, inset -5px -5px 10px ${SHADOW_LIGHT}`,

  /**
   * nm-glow-blue — raised + blue ambient glow (primary CTAs, logo icon)
   * box-shadow: 0 0 25px <glow-blue>, 8px 8px 16px <dark>, -8px -8px 16px <light>
   */
  glowBlue: `0 0 25px ${GLOW_BLUE_BASE}, 8px 8px 16px ${SHADOW_DARK}, -8px -8px 16px ${SHADOW_LIGHT}`,

  /**
   * nm-glow-blue:hover
   * box-shadow: 0 0 40px <glow-blue-hover>, 4px 4px 8px <dark>, -4px -4px 8px <light>
   */
  glowBlueHover: `0 0 40px ${GLOW_BLUE_HOVER}, 4px 4px 8px ${SHADOW_DARK}, -4px -4px 8px ${SHADOW_LIGHT}`,

  /**
   * Semantic status glows (used on pain-point icons in the landing page)
   */
  glowRed:    "0 0 20px rgba(239, 68,  68,  0.4)",
  glowOrange: "0 0 20px rgba(249, 115, 22,  0.4)",
  glowIndigo: "0 0 20px rgba(99,  102, 241, 0.4)",
  glowAmber:  "0 0 20px rgba(251, 191, 36,  0.4)",

  /** Utility — no elevation, no shadow */
  none: "none",
} as const;

// ---------------------------------------------------------------------------
// Border radius
// ---------------------------------------------------------------------------

export const borderRadius = {
  none:   "0",
  sm:     "0.25rem",   // 4px
  DEFAULT:"0.375rem",  // 6px — Tailwind default
  md:     "0.5rem",    // 8px
  lg:     "0.75rem",   // 12px  (rounded-lg)
  xl:     "0.75rem",   // 12px  (rounded-xl) — logo icon box
  "2xl":  "1rem",      // 16px  (rounded-2xl) — icon badge squares
  "3xl":  "1.5rem",    // 24px  (rounded-3xl) — large buttons / CTAs
  "4xl":  "2.5rem",    // 40px  (rounded-[40px]) — cards
  "5xl":  "3.75rem",   // 60px  (rounded-[60px]) — hero CTA section
  full:   "9999px",    // pill / circle
} as const;

// ---------------------------------------------------------------------------
// Spacing scale
// Tailwind-compatible 4px base unit.
// ---------------------------------------------------------------------------

export const spacing = {
  px:   "1px",
  0:    "0",
  0.5:  "0.125rem",  //  2px
  1:    "0.25rem",   //  4px
  1.5:  "0.375rem",  //  6px
  2:    "0.5rem",    //  8px
  2.5:  "0.625rem",  // 10px
  3:    "0.75rem",   // 12px
  3.5:  "0.875rem",  // 14px
  4:    "1rem",      // 16px
  5:    "1.25rem",   // 20px
  6:    "1.5rem",    // 24px
  7:    "1.75rem",   // 28px
  8:    "2rem",      // 32px
  9:    "2.25rem",   // 36px
  10:   "2.5rem",    // 40px
  11:   "2.75rem",   // 44px
  12:   "3rem",      // 48px
  14:   "3.5rem",    // 56px
  16:   "4rem",      // 64px
  20:   "5rem",      // 80px
  24:   "6rem",      // 96px
  28:   "7rem",      // 112px
  32:   "8rem",      // 128px
  36:   "9rem",      // 144px
  40:   "10rem",     // 160px
  48:   "12rem",     // 192px
  56:   "14rem",     // 224px
  64:   "16rem",     // 256px
  80:   "20rem",     // 320px

  // Named semantic spacing tokens used by landing page sections
  navHeight:      "6rem",   // h-24 (96px)
  sectionY:       "8rem",   // py-32 (128px)
  heroTopLg:      "14rem",  // pt-56 (224px)
  cardPad:        "3rem",   // p-12 (48px)
  cardPadSm:      "2.5rem", // p-10 (40px)
  iconBox:        "3.5rem", // w-14 / h-14 (56px)
  iconBoxLg:      "4rem",   // w-16 / h-16 (64px)
} as const;

// ---------------------------------------------------------------------------
// Animation / transition tokens
// ---------------------------------------------------------------------------

export const animation = {
  transition: {
    fast:   "0.15s ease",
    base:   "0.2s ease",
    slow:   "0.3s ease",
  },

  /** Button hover: slight sink to reinforce "push" metaphor */
  btnHoverTranslate: "translateY(1px)",

  /** Card hover: slight float above surface */
  cardHoverTranslate: "translateY(-4px)",

  /** Card hover scale variant */
  cardHoverScale: "scale(1.02)",

  /** Hero SVG line draw keyframe duration */
  drawLineDuration: "3s ease-out forwards",

  /** Stroke-dasharray value for animated SVG paths */
  dasharray: 1000,

  /** Pulsing dot animation (ping keyframe) */
  ping: "ping 1s cubic-bezier(0, 0, 0.2, 1) infinite",
} as const;

// ---------------------------------------------------------------------------
// Z-index scale
// ---------------------------------------------------------------------------

export const zIndex = {
  hide:     -1,
  auto:     "auto",
  base:     0,
  raised:   10,
  dropdown: 20,
  sticky:   40,
  nav:      50,  // fixed navigation z-50
  modal:    60,
  toast:    70,
  tooltip:  80,
} as const;

// ---------------------------------------------------------------------------
// Breakpoints (Tailwind defaults, documented here for reference)
// ---------------------------------------------------------------------------

export const breakpoints = {
  sm:  "640px",
  md:  "768px",
  lg:  "1024px",
  xl:  "1280px",
  "2xl": "1536px",
} as const;

// ---------------------------------------------------------------------------
// Composite helper — CSS custom properties object
// Useful for injecting into a <style> tag or :root via a globalStyles utility.
// ---------------------------------------------------------------------------

export const cssVariables = {
  "--bg":           colors.bg,
  "--blue":         colors.blue.DEFAULT,
  "--light":        colors.surface,
  "--shadow-dark":  colors.shadow.dark,
  "--shadow-light": colors.shadow.light,
  "--text-dark":    colors.text.secondary,
} as const;

// ---------------------------------------------------------------------------
// Default export — full token map
// ---------------------------------------------------------------------------

const tokens = {
  colors,
  typography,
  shadows,
  borderRadius,
  spacing,
  animation,
  zIndex,
  breakpoints,
  cssVariables,
} as const;

export default tokens;

// ---------------------------------------------------------------------------
// Type exports for use in component prop types
// ---------------------------------------------------------------------------

export type ColorToken       = typeof colors;
export type ShadowToken      = typeof shadows;
export type BorderRadiusToken = typeof borderRadius;
export type SpacingToken     = typeof spacing;
export type TokenMap         = typeof tokens;
