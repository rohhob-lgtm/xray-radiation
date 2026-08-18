// Central language registry for the Translation Studio frontend — mirrors
// backend/api/languages.py. Adding a new language means adding one entry
// here (and to the backend registry); no other component should hard-code
// language metadata.

export type Direction = 'ltr' | 'rtl';

export interface LanguageConfig {
  code: string;
  label: string;
  nativeLabel: string;
  flag: string;
  direction: Direction;
}

export const SUPPORTED_LANGUAGES: Record<string, LanguageConfig> = {
  en: { code: 'en', label: 'English', nativeLabel: 'English', flag: '🇬🇧', direction: 'ltr' },
  ar: { code: 'ar', label: 'Arabic',  nativeLabel: 'العربية',  flag: '🇸🇦', direction: 'rtl' },
  ru: { code: 'ru', label: 'Russian', nativeLabel: 'Русский',  flag: '🇷🇺', direction: 'ltr' },
  fr: { code: 'fr', label: 'French',  nativeLabel: 'Français', flag: '🇫🇷', direction: 'ltr' },
  es: { code: 'es', label: 'Spanish', nativeLabel: 'Español',  flag: '🇪🇸', direction: 'ltr' },
};

// Selectable as a translation target. English is a target too (AR→EN etc.).
export const TARGET_LANGUAGES: LanguageConfig[] = ['ar', 'en', 'ru', 'fr', 'es'].map(
  (c) => SUPPORTED_LANGUAGES[c]
);

// Selectable as a translation source ("auto" triggers server-side detection).
export const SOURCE_LANGUAGES: Array<LanguageConfig | { code: 'auto'; label: string; nativeLabel: string; flag: string; direction: Direction }> = [
  { code: 'auto', label: 'Auto Detect', nativeLabel: 'Auto Detect', flag: '🌐', direction: 'ltr' },
  SUPPORTED_LANGUAGES.en,
  SUPPORTED_LANGUAGES.ar,
  SUPPORTED_LANGUAGES.ru,
  SUPPORTED_LANGUAGES.fr,
  SUPPORTED_LANGUAGES.es,
];

export function getLanguage(code: string | null | undefined): LanguageConfig | undefined {
  if (!code) return undefined;
  return SUPPORTED_LANGUAGES[code.toLowerCase().split('-')[0]];
}

export function langDisplayName(code: string | null | undefined): string {
  return getLanguage(code)?.label ?? (code ? code.toUpperCase() : '');
}

export function langFlag(code: string | null | undefined): string {
  return getLanguage(code)?.flag ?? '🏳️';
}

export function isRtlLang(code: string | null | undefined): boolean {
  return getLanguage(code)?.direction === 'rtl';
}
