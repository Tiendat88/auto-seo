"use client";

import { useEffect, useState, useCallback } from "react";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import { Skeleton } from "@/components/ui/skeleton";
import { listPublishJobs, cancelPublishJob } from "@/lib/api";
import type { PublishJob, PublishJobStatus } from "@/lib/types";
import { cn } from "@/lib/utils";
import { toast } from "sonner";
import {
  Send, Calendar, Clock, RotateCcw, ExternalLink, CheckCircle2,
  AlertCircle, Loader2, XCircle, CircleDashed,
} from "lucide-react";

const PAGE_SIZE = 30;

const STATUS_META: Record<PublishJobStatus, { label: string; className: string; icon: typeof Send }> = {
  pending: { label: "Chờ xử lý", className: "bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300", icon: CircleDashed },
  sent: { label: "Đang gửi", className: "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300", icon: Loader2 },
  success: { label: "Thành công", className: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400", icon: CheckCircle2 },
  failed: { label: "Thất bại", className: "bg-rose-100 text-rose-700 dark:bg-rose-900/30 dark:text-rose-400", icon: AlertCircle },
  cancelled: { label: "Đã hủy", className: "bg-muted text-muted-foreground", icon: XCircle },
};

const FILTERS: { value: string; label: string }[] = [
  { value: "all", label: "Tất cả trạng thái" },
  { value: "pending", label: "Chờ xử lý" },
  { value: "sent", label: "Đang gửi" },
  { value: "success", label: "Thành công" },
  { value: "failed", label: "Thất bại" },
  { value: "cancelled", label: "Đã hủy" },
];

export default function PublishHistoryPage() {
  const [jobs, setJobs] = useState<PublishJob[]>([]);
  const [total, setTotal] = useState(0);
  const [statusFilter, setStatusFilter] = useState("all");
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);

  const fetchJobs = useCallback(async () => {
    try {
      const res = await listPublishJobs({
        limit: PAGE_SIZE,
        offset,
        status: statusFilter === "all" ? undefined : statusFilter,
      });
      setJobs(res.jobs);
      setTotal(res.total);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Không tải được lịch sử đăng");
    } finally {
      setLoading(false);
    }
  }, [offset, statusFilter]);

  useEffect(() => {
    setLoading(true);
    fetchJobs();
  }, [fetchJobs]);

  // Auto-refresh while any job is still in flight.
  useEffect(() => {
    const active = jobs.some((j) => j.status === "pending" || j.status === "sent");
    if (!active) return;
    const t = setInterval(fetchJobs, 3000);
    return () => clearInterval(t);
  }, [jobs, fetchJobs]);

  const handleCancel = async (job: PublishJob) => {
    try {
      await cancelPublishJob(job.id);
      toast.success("Đã hủy lệnh đăng");
      fetchJobs();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Hủy thất bại");
    }
  };

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const currentPage = Math.floor(offset / PAGE_SIZE) + 1;

  return (
    <div className="space-y-6 max-w-7xl mx-auto pb-10">
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-3xl font-extrabold tracking-tight text-blue-900 dark:text-blue-100 flex items-center gap-3">
            Lịch sử Đăng bài
          </h1>
          <p className="text-muted-foreground mt-1">
            Theo dõi các lần AutoSEO gửi bài viết tới website đích.
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={() => { setLoading(true); fetchJobs(); }}>
          <RotateCcw className="mr-2 h-4 w-4" />
          Làm mới
        </Button>
      </div>

      <Card className="border-blue-500/10 shadow-sm overflow-hidden bg-card/50 backdrop-blur-sm">
        <div className="p-4 flex flex-col sm:flex-row items-center justify-between gap-4 border-b border-blue-500/10 bg-blue-50/50 dark:bg-blue-900/10">
          <div className="w-full sm:max-w-xs">
            <Select value={statusFilter} onValueChange={(v) => { if (v) { setStatusFilter(v); setOffset(0); } }}>
              <SelectTrigger className="bg-background border-blue-200 dark:border-blue-800">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {FILTERS.map((f) => (
                  <SelectItem key={f.value} value={f.value}>{f.label}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="flex items-center gap-2 text-sm text-blue-600 dark:text-blue-400 font-medium bg-blue-100 dark:bg-blue-900/30 px-3 py-1.5 rounded-full whitespace-nowrap">
            <Send className="h-4 w-4" />
            <span>Tổng số: {total} lượt đăng</span>
          </div>
        </div>

        <div className="overflow-x-auto">
          <Table>
            <TableHeader className="bg-muted/30">
              <TableRow className="hover:bg-transparent">
                <TableHead className="font-semibold text-blue-900 dark:text-blue-200">Bài viết</TableHead>
                <TableHead className="font-semibold text-blue-900 dark:text-blue-200">Đích đăng</TableHead>
                <TableHead className="font-semibold text-blue-900 dark:text-blue-200">Chế độ</TableHead>
                <TableHead className="font-semibold text-blue-900 dark:text-blue-200">Trạng thái</TableHead>
                <TableHead className="font-semibold text-blue-900 dark:text-blue-200">Kết quả</TableHead>
                <TableHead className="font-semibold text-blue-900 dark:text-blue-200">Thời gian</TableHead>
                <TableHead className="text-right font-semibold text-blue-900 dark:text-blue-200">Hành động</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {loading ? (
                Array.from({ length: 5 }).map((_, i) => (
                  <TableRow key={i}>
                    {Array.from({ length: 7 }).map((_, j) => (
                      <TableCell key={j}><Skeleton className="h-5 w-full" /></TableCell>
                    ))}
                  </TableRow>
                ))
              ) : jobs.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={7} className="h-32 text-center">
                    <div className="flex flex-col items-center justify-center text-muted-foreground">
                      <Send className="h-8 w-8 mb-2 opacity-20" />
                      <p>Chưa có lượt đăng nào.</p>
                    </div>
                  </TableCell>
                </TableRow>
              ) : (
                jobs.map((j) => {
                  const meta = STATUS_META[j.status];
                  const StatusIcon = meta.icon;
                  return (
                    <TableRow key={j.id} className="hover:bg-blue-50/40 dark:hover:bg-blue-900/10">
                      <TableCell className="max-w-xs">
                        <span className="font-medium text-foreground line-clamp-1" title={j.article_title}>
                          {j.article_title || "(chưa có tiêu đề)"}
                        </span>
                        <span className="text-xs text-muted-foreground font-mono">/{j.article_slug}</span>
                      </TableCell>
                      <TableCell className="text-sm">
                        <span className="font-medium">{j.target_name}</span>
                      </TableCell>
                      <TableCell>
                        <Badge variant="secondary" className="text-[10px] uppercase">{j.mode}</Badge>
                      </TableCell>
                      <TableCell>
                        <Badge className={cn("gap-1.5 border-none font-medium", meta.className)}>
                          <StatusIcon className={cn("h-3 w-3", j.status === "sent" && "animate-spin")} />
                          {meta.label}
                          {j.retry_count > 0 && <span className="opacity-70">×{j.retry_count}</span>}
                        </Badge>
                      </TableCell>
                      <TableCell className="max-w-xs text-sm">
                        {j.status === "success" && j.published_url ? (
                          <a
                            href={j.published_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="inline-flex items-center gap-1 text-blue-600 dark:text-blue-400 hover:underline truncate"
                          >
                            <span className="truncate">{j.published_url}</span>
                            <ExternalLink className="h-3 w-3 shrink-0" />
                          </a>
                        ) : j.status === "failed" && j.error_message ? (
                          <span className="text-rose-600 dark:text-rose-400 text-xs line-clamp-2" title={j.error_message}>
                            {j.error_message}
                          </span>
                        ) : (
                          <span className="text-muted-foreground">—</span>
                        )}
                      </TableCell>
                      <TableCell className="text-sm text-muted-foreground">
                        <div className="flex items-center gap-1.5">
                          <Calendar className="h-3.5 w-3.5 opacity-70" />
                          <span>{new Date(j.created_at).toLocaleDateString("vi-VN")}</span>
                          <Clock className="h-3 w-3 ml-1 opacity-50" />
                          <span className="text-xs opacity-70">
                            {new Date(j.created_at).toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" })}
                          </span>
                        </div>
                      </TableCell>
                      <TableCell className="text-right">
                        <div className="flex items-center justify-end gap-1">
                          <Link href={`/pipeline/${j.job_id}`}>
                            <Button variant="ghost" size="sm" className="text-xs text-muted-foreground hover:text-blue-600">
                              Bài viết
                            </Button>
                          </Link>
                          {j.status === "pending" && (
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => handleCancel(j)}
                              className="text-xs text-muted-foreground hover:text-destructive"
                            >
                              Hủy
                            </Button>
                          )}
                        </div>
                      </TableCell>
                    </TableRow>
                  );
                })
              )}
            </TableBody>
          </Table>
        </div>

        {totalPages > 1 && (
          <div className="flex items-center justify-between p-4 border-t border-blue-500/10">
            <span className="text-sm text-muted-foreground">
              Trang {currentPage} / {totalPages}
            </span>
            <div className="flex gap-2">
              <Button
                variant="outline"
                size="sm"
                disabled={offset === 0}
                onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
                className="hover:bg-blue-50 dark:hover:bg-blue-900/20"
              >
                Trước
              </Button>
              <Button
                variant="outline"
                size="sm"
                disabled={currentPage >= totalPages}
                onClick={() => setOffset(offset + PAGE_SIZE)}
                className="hover:bg-blue-50 dark:hover:bg-blue-900/20"
              >
                Sau
              </Button>
            </div>
          </div>
        )}
      </Card>
    </div>
  );
}
