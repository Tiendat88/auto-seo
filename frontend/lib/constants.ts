import type { JobStatus, BrandStreamStage } from "./types";

export const TERMINAL_STATUSES: JobStatus[] = ["completed", "failed"];

export const JOB_STATUS_VARIANT: Record<
  JobStatus,
  "default" | "secondary" | "destructive" | "outline"
> = {
  pending: "secondary",
  researching: "outline",
  planning: "outline",
  generating: "outline",
  scoring: "outline",
  reviewing: "outline",
  editing: "outline",
  completed: "default",
  failed: "destructive",
};

export const PIPELINE_STEPS = [
  { key: "researching", label: "Nghiên cứu" },
  { key: "planning", label: "Lập dàn ý" },
  { key: "generating", label: "Viết bài" },
  { key: "scoring", label: "Chấm điểm" },
  { key: "reviewing", label: "Kiểm duyệt" },
  { key: "editing", label: "Chỉnh sửa" },
] as const;

export const BRAND_STREAM_STAGES: { key: BrandStreamStage; label: string }[] = [
  { key: "scraping", label: "Đọc & Phân tích Website" },
  { key: "identifying-competitors", label: "Xác định Đối thủ cạnh tranh" },
  { key: "generating-prompts", label: "Tạo Kịch bản câu hỏi" },
  { key: "fetching-responses", label: "Truy vấn các Mô hình AI" },
  { key: "analyzing", label: "Phân tích Kết quả đề cập" },
  { key: "scoring", label: "Tính toán Điểm số" },
  { key: "finalizing", label: "Hoàn thiện Báo cáo" },
];

export const SUB_QUERY_TYPE_LABELS: Record<string, string> = {
  comparative: "So sánh",
  feature_specific: "Tính năng cụ thể",
  use_case: "Tình huống sử dụng",
  trust_signals: "Tín hiệu Uy tín",
  how_to: "Hướng dẫn",
  definitional: "Định nghĩa / Giải thích",
};

// Bảng dịch tên tiêu chí AEO (từ API backend)
export const AEO_CHECK_NAME_VI: Record<string, string> = {
  "Direct Answer Detection": "Phát hiện Câu trả lời Trực tiếp",
  "H-tag Hierarchy": "Cấu trúc Thẻ Tiêu đề (H-tag)",
  "Snippet Readability": "Khả năng đọc cho Snippet",
  "Direct Answer": "Câu trả lời Trực tiếp",
  "Heading Structure": "Cấu trúc Tiêu đề",
  "Readability": "Khả năng đọc",
};

// Bảng dịch tên thứ nguyên điểm chất lượng bài viết (từ API backend)
export const SCORE_DIMENSION_VI: Record<string, string> = {
  keyword_usage: "Sử dụng Từ khóa",
  heading_structure: "Cấu trúc Tiêu đề",
  word_count_target: "Số từ mục tiêu",
  readability_metrics: "Chỉ số Khả năng đọc",
  humanity: "Tính Người thật",
  keyword_distribution: "Phân bổ Từ khóa",
  differentiation_delivery: "Điểm Khác biệt",
  content_depth: "Chiều sâu Nội dung",
  differentiation: "Sự khác biệt",
  accuracy: "Độ chính xác",
  consistency: "Tính nhất quán",
  readability: "Khả năng đọc",
  actionability: "Tính Hữu dụng",
};

