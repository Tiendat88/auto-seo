import { Badge } from "@/components/ui/badge";
import { JOB_STATUS_VARIANT, TERMINAL_STATUSES } from "@/lib/constants";
import type { JobStatus } from "@/lib/types";

export function StatusBadge({
  status,
  currentStep,
}: {
  status: JobStatus;
  currentStep?: string | null;
}) {
  const variant = JOB_STATUS_VARIANT[status];
  const isActive = !TERMINAL_STATUSES.includes(status) && status !== "pending";
  const label = currentStep
    ? `${status} (${currentStep.split(":").pop()})`
    : status;

  return (
    <Badge variant={variant} className="gap-1.5 capitalize">
      {isActive && (
        <span className="relative flex h-2 w-2">
          <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-current opacity-75" />
          <span className="relative inline-flex h-2 w-2 rounded-full bg-current" />
        </span>
      )}
      {label}
    </Badge>
  );
}
