"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { PlusCircle, Layers, Calendar, Clock, Globe } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { StatusBadge } from "@/components/status-badge";
import { listJobs } from "@/lib/api";
import type { JobSummaryResponse, JobStatus } from "@/lib/types";

const STATUSES: JobStatus[] = [
  "pending", "researching", "planning", "generating",
  "scoring", "reviewing", "editing", "completed", "failed",
];

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

const PAGE_SIZE = 20;

export default function PipelineListPage() {
  const [jobs, setJobs] = useState<JobSummaryResponse[]>([]);
  const [total, setTotal] = useState(0);
  const [status, setStatus] = useState<string>("all");
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    const fetchJobs = async () => {
      setLoading(true);
      try {
        const res = await listJobs({
          status: status === "all" ? undefined : status,
          limit: PAGE_SIZE,
          offset,
        });
        if (active) {
          setJobs(res.jobs);
          setTotal(res.total);
        }
      } finally {
        if (active) {
          setLoading(false);
        }
      }
    };
    fetchJobs();
    return () => { active = false; };
  }, [status, offset]);

  const totalPages = Math.ceil(total / PAGE_SIZE);
  const currentPage = Math.floor(offset / PAGE_SIZE) + 1;

  return (
    <div className="space-y-6 max-w-7xl mx-auto pb-10">
      {/* Header Section */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-3xl font-extrabold tracking-tight text-blue-900 dark:text-blue-100">
            Quản lý Bài viết
          </h1>
          <p className="text-muted-foreground mt-1">
            Theo dõi và quản lý tiến độ tạo bài viết tự động
          </p>
        </div>
        <div className="flex gap-2">
          <Link href="/pipeline/new">
            <Button
              className="bg-blue-600 hover:bg-blue-700 text-white shadow-md shadow-blue-500/20 transition-all hover:shadow-blue-500/40"
            >
              <PlusCircle className="mr-2 h-4 w-4" />
              Khởi tạo Bài viết
            </Button>
          </Link>
        </div>
      </div>

      {/* Filters and Stats */}
      <Card className="border-blue-500/10 shadow-sm overflow-hidden bg-card/50 backdrop-blur-sm">
        <div className="p-4 flex flex-col sm:flex-row items-center justify-between gap-4 border-b border-blue-500/10 bg-blue-50/50 dark:bg-blue-900/10">
          <div className="flex items-center gap-4 w-full sm:w-auto">
            <Select value={status} onValueChange={(v) => { if (v) { setStatus(v); setOffset(0); } }}>
              <SelectTrigger className="w-full sm:w-[200px] bg-background border-blue-200 dark:border-blue-800">
                <SelectValue placeholder="Lọc theo trạng thái" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Tất cả trạng thái</SelectItem>
                {STATUSES.map((s) => (
                  <SelectItem key={s} value={s} className="capitalize">
                    {STATUS_VI[s] || s}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <div className="flex items-center gap-2 text-sm text-blue-600 dark:text-blue-400 font-medium bg-blue-100 dark:bg-blue-900/30 px-3 py-1.5 rounded-full">
              <Layers className="h-4 w-4" />
              <span>Tổng số: {total}</span>
            </div>
          </div>
        </div>

        {/* Table Content */}
        <div className="overflow-x-auto">
          <Table>
            <TableHeader className="bg-muted/30">
              <TableRow className="hover:bg-transparent">
                <TableHead className="font-semibold text-blue-900 dark:text-blue-200">Chủ đề Bài viết</TableHead>
                <TableHead className="font-semibold text-blue-900 dark:text-blue-200">Trạng thái</TableHead>
                <TableHead className="text-right font-semibold text-blue-900 dark:text-blue-200">Số từ mục tiêu</TableHead>
                <TableHead className="font-semibold text-blue-900 dark:text-blue-200">Ngôn ngữ</TableHead>
                <TableHead className="text-right font-semibold text-blue-900 dark:text-blue-200">Lượt sửa</TableHead>
                <TableHead className="font-semibold text-blue-900 dark:text-blue-200">Thời gian tạo</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {loading ? (
                Array.from({ length: 5 }).map((_, i) => (
                  <TableRow key={i}>
                    {Array.from({ length: 6 }).map((_, j) => (
                      <TableCell key={j}><Skeleton className="h-5 w-full" /></TableCell>
                    ))}
                  </TableRow>
                ))
              ) : jobs.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={6} className="h-32 text-center">
                    <div className="flex flex-col items-center justify-center text-muted-foreground">
                      <Layers className="h-8 w-8 mb-2 opacity-20" />
                      <p>Không tìm thấy bài viết nào.</p>
                      {status !== "all" && (
                        <Button variant="link" onClick={() => setStatus("all")} className="mt-2">
                          Xóa bộ lọc
                        </Button>
                      )}
                    </div>
                  </TableCell>
                </TableRow>
              ) : (
                jobs.map((job) => (
                  <TableRow 
                    key={job.job_id} 
                    className="cursor-pointer transition-colors hover:bg-blue-50/50 dark:hover:bg-blue-900/20 group"
                  >
                    <TableCell>
                      <Link href={`/pipeline/${job.job_id}`} className="block w-full">
                        <span className="font-semibold text-foreground group-hover:text-blue-600 dark:group-hover:text-blue-400 transition-colors line-clamp-1">
                          {job.topic}
                        </span>
                        <span className="text-xs text-muted-foreground mt-1 flex items-center gap-1">
                          <span className="font-mono text-[10px] opacity-60">{job.job_id.split('-')[0]}</span>
                        </span>
                      </Link>
                    </TableCell>
                    <TableCell>
                      <Link href={`/pipeline/${job.job_id}`} className="block w-full">
                        <StatusBadge status={job.status} currentStep={job.current_step} />
                      </Link>
                    </TableCell>
                    <TableCell className="text-right tabular-nums">
                      <Link href={`/pipeline/${job.job_id}`} className="block w-full text-muted-foreground font-medium">
                        {job.target_word_count.toLocaleString()}
                      </Link>
                    </TableCell>
                    <TableCell>
                      <Link href={`/pipeline/${job.job_id}`} className="block w-full">
                        <div className="flex items-center gap-1 text-muted-foreground">
                          <Globe className="h-3 w-3" />
                          <span className="uppercase text-xs font-bold">{job.language}</span>
                        </div>
                      </Link>
                    </TableCell>
                    <TableCell className="text-right tabular-nums">
                      <Link href={`/pipeline/${job.job_id}`} className="block w-full">
                        {job.revision_count > 0 ? (
                          <span className="inline-flex items-center justify-center px-2 py-1 text-xs font-bold leading-none text-amber-600 bg-amber-100 rounded-full dark:bg-amber-900/30 dark:text-amber-400">
                            {job.revision_count}
                          </span>
                        ) : (
                          <span className="text-muted-foreground/50">-</span>
                        )}
                      </Link>
                    </TableCell>
                    <TableCell>
                      <Link href={`/pipeline/${job.job_id}`} className="block w-full text-sm text-muted-foreground">
                        <div className="flex items-center gap-1.5">
                          <Calendar className="h-3.5 w-3.5 opacity-70" />
                          <span>{new Date(job.created_at).toLocaleDateString('vi-VN')}</span>
                          <Clock className="h-3 w-3 ml-1 opacity-50" />
                          <span className="text-xs opacity-70">{new Date(job.created_at).toLocaleTimeString('vi-VN', {hour: '2-digit', minute:'2-digit'})}</span>
                        </div>
                      </Link>
                    </TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </div>
        
        {/* Pagination */}
        {totalPages > 1 && (
          <div className="flex items-center justify-between p-4 border-t border-border/50 bg-muted/10">
            <Button
              variant="outline"
              size="sm"
              disabled={offset === 0}
              onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
              className="hover:bg-blue-50 dark:hover:bg-blue-900/20"
            >
              Trang trước
            </Button>
            <span className="text-sm font-medium text-muted-foreground">
              Trang <span className="text-foreground">{currentPage}</span> / {totalPages}
            </span>
            <Button
              variant="outline"
              size="sm"
              disabled={currentPage >= totalPages}
              onClick={() => setOffset(offset + PAGE_SIZE)}
              className="hover:bg-blue-50 dark:hover:bg-blue-900/20"
            >
              Trang sau
            </Button>
          </div>
        )}
      </Card>
    </div>
  );
}
