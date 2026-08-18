// Unicode ranges for RTL scripts: Hebrew, Arabic, Arabic Supplement,
// Arabic Extended-A, Arabic Presentation Forms A/B.
const RTL_CHAR_REGEX = new RegExp(
  '[\\u0591-\\u05F4\\u0600-\\u06FF\\u0750-\\u077F\\u08A0-\\u08FF\\uFB50-\\uFDFF\\uFE70-\\uFEFF]'
);
const LTR_CHAR_REGEX = /[A-Za-z]/;

/**
 * Detects text direction using the Unicode "first strong character" rule
 * (the same heuristic behind HTML's dir="auto"): the first letter encountered
 * that carries directional strength decides the paragraph direction. Digits,
 * punctuation and whitespace are skipped since they are direction-neutral.
 */
export function detectDirection(text: string): 'rtl' | 'ltr' {
  if (!text) return 'ltr';
  for (const ch of text) {
    if (RTL_CHAR_REGEX.test(ch)) return 'rtl';
    if (LTR_CHAR_REGEX.test(ch)) return 'ltr';
  }
  return 'ltr';
}

export function isRTL(text: string): boolean {
  return detectDirection(text) === 'rtl';
}
