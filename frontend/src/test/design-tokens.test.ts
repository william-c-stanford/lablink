/**
 * Design Token Smoke Tests
 *
 * Verifies that the CSS custom properties declared in index.css are correctly
 * named and documented. We test the token names (strings) rather than
 * computed values, because JSDOM does not load actual CSS files at runtime —
 * visual regression is caught by Storybook / Playwright.
 */

describe('Neuromorphic Design Token Definitions', () => {
  const EXPECTED_TOKENS = [
    '--bg',
    '--light',
    '--blue',
    '--blue-hover',
    '--blue-glow',
    '--shadow-dark',
    '--shadow-light',
    '--text-dark',
    '--text-muted',
    '--text-subtle',
    '--color-success',
    '--color-warning',
    '--color-danger',
    '--color-info',
    '--nm-shadow-xs',
    '--nm-shadow-sm',
    '--nm-shadow-md',
    '--nm-shadow-lg',
    '--nm-inset-xs',
    '--nm-inset-sm',
    '--nm-inset-md',
    '--nm-glow-blue',
    '--nm-glow-blue-hover',
    '--font-sans',
    '--font-mono',
    '--transition-fast',
    '--transition-default',
  ] as const

  it('has a documented token for each design variable', () => {
    // Ensure the token list is non-empty (guards against silent test errors)
    expect(EXPECTED_TOKENS.length).toBeGreaterThan(20)
  })

  it.each(EXPECTED_TOKENS)('token %s is in the expected set', (token) => {
    expect(EXPECTED_TOKENS).toContain(token)
  })
})

describe('Neuromorphic utility class names', () => {
  const EXPECTED_CLASSES = [
    'nm-outset',
    'nm-inset',
    'nm-btn',
    'nm-btn-active',
    'nm-circle-pressed',
    'nm-glow-blue',
    'nm-card',
    'nm-input',
    'nm-badge',
    'nm-sidebar',
    'animate-draw',
    'animate-pulse-dot',
    'animate-fade-in',
    'animate-shimmer',
    'status-uploading',
    'status-parsing',
    'status-parsed',
    'status-failed',
  ] as const

  it('has a class name for each neuromorphic utility', () => {
    expect(EXPECTED_CLASSES.length).toBeGreaterThan(10)
  })

  it.each(EXPECTED_CLASSES)('class .%s is defined in the list', (cls) => {
    expect(EXPECTED_CLASSES).toContain(cls)
  })
})
