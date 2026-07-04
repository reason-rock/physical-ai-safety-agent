"use client";

type Color = "safe" | "warn" | "danger" | "brand";

const COLOR_HEX: Record<Color, string> = {
  safe: "#1c7a4f",
  warn: "#a8660f",
  danger: "#a83232",
  brand: "#2f5f9f",
};

export function Gauge({
  value,
  label,
  rightLabel,
  color,
}: {
  value: number;
  label: string;
  rightLabel: string;
  color: Color;
}) {
  const pct = Math.max(0, Math.min(100, value));
  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex justify-between text-[11px] font-semibold">
        <span className="uppercase tracking-wider text-faint">{label}</span>
        <span className="font-mono text-muted">{rightLabel}</span>
      </div>
      <div className="h-2 w-full overflow-hidden rounded-full bg-line">
        <div
          className="h-full rounded-full transition-all"
          style={{
            width: `${pct}%`,
            background: COLOR_HEX[color],
            transitionDuration: "300ms",
          }}
        />
      </div>
    </div>
  );
}

export function gaugeColor(pct: number): Color {
  if (pct < 70) return "safe";
  if (pct < 90) return "warn";
  return "danger";
}
