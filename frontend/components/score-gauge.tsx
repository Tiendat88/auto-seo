"use client";

import { cn } from "@/lib/utils";

function scoreColor(score: number): string {
  if (score < 40) return "text-destructive";
  if (score < 70) return "text-muted-foreground";
  return "text-primary";
}

export function ScoreGauge({
  score,
  size = 100,
  label,
  className,
}: {
  score: number;
  size?: number;
  label?: string;
  className?: string;
}) {
  const radius = 40;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference - (score / 100) * circumference;

  return (
    <div className={cn("flex flex-col items-center gap-1", className)}>
      <svg width={size} height={size} viewBox="0 0 100 100" className="-rotate-90">
        <circle
          cx="50"
          cy="50"
          r={radius}
          fill="none"
          strokeWidth="8"
          className="stroke-muted"
        />
        <circle
          cx="50"
          cy="50"
          r={radius}
          fill="none"
          strokeWidth="8"
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          className={cn("transition-all duration-500", scoreColor(score).replace("text-", "stroke-"))}
        />
      </svg>
      <span className={cn("text-2xl font-bold tabular-nums", scoreColor(score))}>
        {Math.round(score)}
      </span>
      {label && <span className="text-xs text-muted-foreground">{label}</span>}
    </div>
  );
}
