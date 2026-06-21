import { Progress } from "@/components/ui/progress";
import { cn } from "@/lib/utils";
import { SCORE_DIMENSION_VI } from "@/lib/constants";

function barColor(score: number): string {
  if (score < 0.5) return "[&>div]:bg-destructive";
  if (score < 0.7) return "[&>div]:bg-muted-foreground";
  return "[&>div]:bg-primary";
}

export function ScoreDimensionBar({
  name,
  score,
  feedback,
}: {
  name: string;
  score: number;
  feedback?: string;
}) {
  const displayName = SCORE_DIMENSION_VI[name] ?? name.replace(/_/g, " ");

  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between text-sm">
        <span className="capitalize font-medium">{displayName}</span>
        <span className="font-mono text-xs text-muted-foreground">
          {(score * 100).toFixed(0)}%
        </span>
      </div>
      <Progress value={score * 100} className={cn("h-2", barColor(score))} />
      {feedback && (
        <p className="text-xs text-muted-foreground">{feedback}</p>
      )}
    </div>
  );
}

