"use client";

import { useEffect, useRef, useState } from "react";

/**
 * Lightweight dropdown menu. Click the trigger to open; click anywhere
 * outside (or Esc) to close. The trigger is whatever children you pass,
 * so the visual style is fully controlled by the caller.
 *
 * Usage:
 *   <Dropdown trigger={<button>⋯</button>}>
 *     <DropdownItem>...</DropdownItem>
 *   </Dropdown>
 */
export function Dropdown({
  trigger,
  children,
  align = "right",
}: {
  trigger: React.ReactNode;
  children: React.ReactNode;
  align?: "left" | "right";
}) {
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    function onDoc(e: MouseEvent) {
      if (!containerRef.current?.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", onDoc);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDoc);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  return (
    <div ref={containerRef} className="relative">
      <button
        type="button"
        onClick={(e) => {
          e.stopPropagation();
          setOpen((v) => !v);
        }}
        className="inline-flex items-center justify-center rounded p-1 text-faint transition hover:bg-line/60 hover:text-ink"
        aria-haspopup="menu"
        aria-expanded={open}
      >
        {trigger}
      </button>
      {open && (
        <div
          role="menu"
          className={`absolute z-30 mt-1 min-w-[240px] max-w-[320px] rounded-md border border-line bg-panel p-3 shadow-card-hover animate-fade-in ${
            align === "right" ? "right-0" : "left-0"
          }`}
          onClick={(e) => e.stopPropagation()}
        >
          {children}
        </div>
      )}
    </div>
  );
}

export function DropdownRow({
  label,
  value,
  mono = true,
}: {
  label: string;
  value: React.ReactNode;
  mono?: boolean;
}) {
  return (
    <div className="flex flex-col gap-0.5 py-1">
      <span className="text-[9px] font-bold uppercase tracking-wider text-faint">
        {label}
      </span>
      <span
        className={`break-all text-[11px] leading-snug text-ink-soft ${
          mono ? "font-mono" : ""
        }`}
      >
        {value}
      </span>
    </div>
  );
}
