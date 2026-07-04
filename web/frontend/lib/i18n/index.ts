"use client";

import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import en from "./en.json";
import ko from "./ko.json";

export type Lang = "en" | "ko";

const STORAGE_KEY = "gaitlab.lang";

function readStoredLanguage(): Lang | null {
  if (typeof window === "undefined") return null;
  const stored = window.localStorage.getItem(STORAGE_KEY);
  if (stored === "ko" || stored === "en") return stored;
  return null;
}

if (!i18n.isInitialized) {
  i18n.use(initReactI18next).init({
    resources: {
      en: { translation: en },
      ko: { translation: ko },
    },
    // Keep SSR and the first client render identical. A stored browser
    // preference is applied after hydration by applyStoredLanguage().
    lng: "en",
    fallbackLng: "en",
    interpolation: { escapeValue: false },
  });
}

export function setLanguage(lang: Lang) {
  i18n.changeLanguage(lang);
  if (typeof window !== "undefined") {
    window.localStorage.setItem(STORAGE_KEY, lang);
  }
}

export function getLanguage(): Lang {
  return (i18n.language as Lang) || "en";
}

export function applyStoredLanguage(): Lang {
  const stored = readStoredLanguage();
  if (stored && stored !== i18n.language) {
    i18n.changeLanguage(stored);
    return stored;
  }
  return getLanguage();
}

export default i18n;
