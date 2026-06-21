"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { listPublishTargets, createPublishJob, getPublishJob } from "@/lib/api";
import type { PublishTarget, PublishMode, PublishJob } from "@/lib/types";
import { toast } from "sonner";
import { Send, Loader2, CheckCircle2, AlertCircle, ExternalLink, Server } from "lucide-react";

const ACTIVE_STATUSES: string[] = ["pending", "sent"];

export function PublishDialog({ jobId }: { jobId: string }) {
  const [open, setOpen] = useState(false);
  const [targets, setTargets] = useState<PublishTarget[]>([]);
  const [loadingTargets, setLoadingTargets] = useState(false);
  const [targetId, setTargetId] = useState("");
  const [mode, setMode] = useState<PublishMode>("draft");
  const [publishing, setPublishing] = useState(false);
  const [publishJob, setPublishJob] = useState<PublishJob | null>(null);
  const pollRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const clearPoll = () => {
    if (pollRef.current) clearTimeout(pollRef.current);
    pollRef.current = null;
  };

  const loadTargets = useCallback(async () => {
    setLoadingTargets(true);
    try {
      const res = await listPublishTargets();
      setTargets(res.targets);
      if (res.targets.length > 0) {
        setTargetId(res.targets[0].id);
        setMode(res.targets[0].default_mode);
      }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Không tải được danh sách đích đăng");
    } finally {
      setLoadingTargets(false);
    }
  }, []);

  useEffect(() => {
    if (open) {
      setPublishJob(null);
      loadTargets();
    } else {
      clearPoll();
      setPublishing(false);
    }
    return clearPoll;
  }, [open, loadTargets]);

  const poll = useCallback((id: string) => {
    const tick = async () => {
      try {
        const pj = await getPublishJob(id);
        setPublishJob(pj);
        if (ACTIVE_STATUSES.includes(pj.status)) {
          pollRef.current = setTimeout(tick, 1500);
        } else {
          setPublishing(false);
          if (pj.status === "success") toast.success("Đăng bài thành công!");
          else if (pj.status === "failed") toast.error("Đăng bài thất bại — xem chi tiết lỗi.");
        }
      } catch {
        setPublishing(false);
      }
    };
    pollRef.current = setTimeout(tick, 800);
  }, []);

  const onSelectTarget = (id: string) => {
    setTargetId(id);
    const t = targets.find((x) => x.id === id);
    if (t) setMode(t.default_mode);
  };

  const handlePublish = async () => {
    if (!targetId) {
      toast.error("Chọn một đích đăng");
      return;
    }
    setPublishing(true);
    setPublishJob(null);
    try {
      const pj = await createPublishJob({ job_id: jobId, target_id: targetId, mode });
      setPublishJob(pj);
      poll(pj.id);
    } catch (err) {
      setPublishing(false);
      toast.error(err instanceof Error ? err.message : "Tạo lệnh đăng thất bại");
    }
  };

  const status = publishJob?.status;

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger
        render={
          <Button
            size="sm"
            className="bg-emerald-600 hover:bg-emerald-700 text-white shadow-md shadow-emerald-500/20"
          />
        }
      >
        <Send className="mr-2 h-4 w-4" />
        Đăng bài
      </DialogTrigger>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Send className="h-4 w-4 text-emerald-600" />
            Đăng bài lên website
          </DialogTitle>
          <DialogDescription>
            AutoSEO sẽ POST bài viết (HTML + meta + schema + FAQ) tới đích đăng đã chọn.
          </DialogDescription>
        </DialogHeader>

        {loadingTargets ? (
          <div className="flex items-center justify-center py-8 text-muted-foreground">
            <Loader2 className="h-5 w-5 animate-spin" />
          </div>
        ) : targets.length === 0 ? (
          <div className="flex flex-col items-center gap-3 py-6 text-center text-muted-foreground">
            <Server className="h-8 w-8 opacity-20" />
            <p className="text-sm">Chưa có đích đăng nào.</p>
            <Link href="/publish/targets">
              <Button variant="outline" size="sm">Thêm đích đăng</Button>
            </Link>
          </div>
        ) : (
          <div className="space-y-4">
            <div className="space-y-2">
              <label className="text-sm font-medium">Đích đăng</label>
              <Select value={targetId} onValueChange={(v) => { if (v) onSelectTarget(v); }}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {targets.map((t) => (
                    <SelectItem key={t.id} value={t.id}>{t.name}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <label className="text-sm font-medium">Chế độ</label>
              <Select value={mode} onValueChange={(v) => { if (v) setMode(v as PublishMode); }}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="draft">Bản nháp (draft)</SelectItem>
                  <SelectItem value="published">Đăng ngay (published)</SelectItem>
                </SelectContent>
              </Select>
            </div>

            {publishJob && (
              <div
                className={
                  "rounded-lg border p-3 text-sm " +
                  (status === "success"
                    ? "border-emerald-200 bg-emerald-50 text-emerald-800 dark:border-emerald-800 dark:bg-emerald-900/20 dark:text-emerald-300"
                    : status === "failed"
                    ? "border-rose-200 bg-rose-50 text-rose-800 dark:border-rose-800 dark:bg-rose-900/20 dark:text-rose-300"
                    : "border-blue-200 bg-blue-50 text-blue-800 dark:border-blue-800 dark:bg-blue-900/20 dark:text-blue-300")
                }
              >
                <div className="flex items-center gap-2 font-medium">
                  {status === "success" ? (
                    <CheckCircle2 className="h-4 w-4" />
                  ) : status === "failed" ? (
                    <AlertCircle className="h-4 w-4" />
                  ) : (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  )}
                  {status === "success"
                    ? "Đã đăng thành công"
                    : status === "failed"
                    ? "Đăng thất bại"
                    : status === "sent"
                    ? "Đang gửi tới website..."
                    : "Đang chờ xử lý..."}
                </div>
                {status === "success" && publishJob.published_url && (
                  <a
                    href={publishJob.published_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="mt-1 inline-flex items-center gap-1 underline underline-offset-2"
                  >
                    {publishJob.published_url}
                    <ExternalLink className="h-3 w-3" />
                  </a>
                )}
                {status === "failed" && publishJob.error_message && (
                  <p className="mt-1 text-xs opacity-80 break-words">{publishJob.error_message}</p>
                )}
              </div>
            )}

            <div className="flex justify-end gap-2 pt-1">
              <Link href="/publish/history" className="self-center text-xs text-muted-foreground underline underline-offset-2">
                Xem lịch sử đăng
              </Link>
              <Button
                onClick={handlePublish}
                disabled={publishing || !targetId}
                className="bg-emerald-600 hover:bg-emerald-700 text-white"
              >
                {publishing ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Send className="mr-2 h-4 w-4" />}
                {status === "success" ? "Đăng lại" : "Đăng bài"}
              </Button>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
