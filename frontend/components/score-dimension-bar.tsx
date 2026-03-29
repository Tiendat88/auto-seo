import { Progress } from "@/components/ui/progress";
import { cn } from "@/lib/utils";

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
  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between text-sm">
        <span className="capitalize">{name.replace(/_/g, " ")}</span>
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
