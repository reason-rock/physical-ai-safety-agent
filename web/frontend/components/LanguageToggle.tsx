"use client";

import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { applyStoredLanguage, setLanguage, type Lang } from "@/lib/i18n";

/** Small language toggle. */
export function LanguageToggle() {
  const { i18n: i18nInstance } = useTranslation();
  const [lang, setLang] = useState<Lang>("en");

  useEffect(() => {
    const handler = (nextLang: string) => setLang(nextLang as Lang);
    i18nInstance.on("languageChanged", handler);
    setLang(applyStoredLanguage());
    return () => {
      i18nInstance.off("languageChanged", handler);
    };
  }, [i18nInstance]);

  function toggle() {
    const next: Lang = lang === "ko" ? "en" : "ko";
    setLang(next);
    setLanguage(next);
  }

  return (
    <button
      type="button"
      onClick={toggle}
      className="rounded-md border border-line bg-panel px-2 py-1 text-[11px] font-bold text-ink-soft transition hover:bg-bg"
      title={lang === "ko" ? "Switch to English" : "Switch to Korean"}
    >
      {lang === "ko" ? "KO" : "EN"}
    </button>
  );
}
