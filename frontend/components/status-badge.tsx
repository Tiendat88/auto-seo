import { Badge } from "@/components/ui/badge";
import { JOB_STATUS_VARIANT, TERMINAL_STATUSES } from "@/lib/constants";
import type { JobStatus } from "@/lib/types";

const STATUS_VI: Record<string, string> = {
  pending: "Chờ xử lý",
  researching: "Đang nghiên cứu",
  planning: "Lập dàn ý",
  generating: "Đang viết",
  scoring: "Chấm điểm",
  reviewing: "Kiểm duyệt",
  editing: "Chỉnh sửa",
  completed: "Hoàn thành",
  failed: "Thất bại",
};

export function StatusBadge({
  status,
  currentStep,
}: {
  status: JobStatus;
  currentStep?: string | null;
}) {
  const variant = JOB_STATUS_VARIANT[status];
  const isActive = !TERMINAL_STATUSES.includes(status) && status !== "pending";

  const baseLabel = STATUS_VI[status] || status;
  const label = currentStep
    ? `${baseLabel} (${currentStep.split(":").pop()})`
    : baseLabel;

  const completedClass =
    status === "completed"
      ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-500/20 dark:text-emerald-400 border-transparent"
      : "";

  return (
    <Badge variant={variant} className={`gap-1.5 capitalize font-medium ${completedClass}`}>
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
