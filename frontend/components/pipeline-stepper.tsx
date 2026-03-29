import { Check } from "lucide-react";
import { cn } from "@/lib/utils";
import { PIPELINE_STEPS } from "@/lib/constants";
import type { JobStatus } from "@/lib/types";

export function PipelineStepper({
  status,
  currentStep,
}: {
  status: JobStatus;
  currentStep: string | null;
}) {
  const stepKeys: string[] = PIPELINE_STEPS.map((s) => s.key);
  const activeKey = currentStep?.split(":")[0] ?? "";
  const subStep = currentStep?.includes(":") ? currentStep.split(":")[1] : null;
  const activeIdx = stepKeys.indexOf(activeKey);
  const isCompleted = status === "completed";
  const isFailed = status === "failed";

  return (
    <div className="flex items-center gap-1">
      {PIPELINE_STEPS.map((step, i) => {
        const done = isCompleted || i < activeIdx;
        const active = !isCompleted && !isFailed && step.key === activeKey;
        const failed = isFailed && step.key === activeKey;

        return (
          <div key={step.key} className="flex items-center gap-1">
            {i > 0 && (
              <div
                className={cn(
                  "h-0.5 w-6",
                  done ? "bg-primary" : "bg-muted",
                )}
              />
            )}
            <div className="flex flex-col items-center gap-0.5">
              <div
                className={cn(
                  "flex h-7 w-7 items-center justify-center rounded-full text-xs font-medium",
                  done && "bg-primary text-primary-foreground",
                  active && "bg-primary/20 text-primary ring-2 ring-primary",
                  failed && "bg-destructive/20 text-destructive ring-2 ring-destructive",
                  !done && !active && !failed && "bg-muted text-muted-foreground",
                )}
              >
                {done ? <Check className="h-3.5 w-3.5" /> : i + 1}
              </div>
              <span
                className={cn(
                  "text-[10px]",
                  active || done ? "text-foreground font-medium" : "text-muted-foreground",
                )}
              >
                {step.label}
              </span>
              {active && subStep && (
                <span className="text-[9px] text-muted-foreground">{subStep}</span>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}
