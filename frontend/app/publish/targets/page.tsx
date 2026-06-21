"use client";

import { useState, useEffect, useCallback } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  listPublishTargets,
  createPublishTarget,
  deletePublishTarget,
  testPublishConnection,
} from "@/lib/api";
import type { PublishTarget, PublishMode } from "@/lib/types";
import { cn } from "@/lib/utils";
import { toast } from "sonner";
import { Server, Plus, Trash2, Plug, CheckCircle2, Loader2, Check, Zap } from "lucide-react";

export default function PublishTargetsPage() {
  const [targets, setTargets] = useState<PublishTarget[]>([]);
  const [loading, setLoading] = useState(true);

  const [name, setName] = useState("");
  const [endpointUrl, setEndpointUrl] = useState("");
  const [secretKey, setSecretKey] = useState("");
  const [defaultMode, setDefaultMode] = useState<PublishMode>("draft");
  const [autoPublish, setAutoPublish] = useState(false);

  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await listPublishTargets();
      setTargets(res.targets);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Không tải được danh sách đích đăng");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const resetForm = () => {
    setName("");
    setEndpointUrl("");
    setSecretKey("");
    setDefaultMode("draft");
    setAutoPublish(false);
  };

  const validForm = name.trim().length >= 2 && endpointUrl.startsWith("http") && secretKey.length >= 4;

  const handleTest = async () => {
    if (!endpointUrl.startsWith("http") || secretKey.length < 4) {
      toast.error("Nhập URL endpoint và secret key trước khi test");
      return;
    }
    setTesting(true);
    try {
      const res = await testPublishConnection({ endpoint_url: endpointUrl, secret_key: secretKey });
      if (res.success) {
        toast.success("Kết nối thành công! Endpoint nhận được dữ liệu test.");
      } else {
        toast.error(`Kết nối thất bại: ${res.error ?? "không rõ lỗi"}`);
      }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Test kết nối thất bại");
    } finally {
      setTesting(false);
    }
  };

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!validForm) {
      toast.error("Kiểm tra lại: tên, URL hợp lệ (http...) và secret ≥ 4 ký tự");
      return;
    }
    setSaving(true);
    try {
      await createPublishTarget({
        name: name.trim(),
        endpoint_url: endpointUrl.trim(),
        secret_key: secretKey,
        default_mode: defaultMode,
        auto_publish: autoPublish,
      });
      toast.success(`Đã thêm đích đăng "${name.trim()}"`);
      resetForm();
      load();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Thêm đích đăng thất bại");
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (target: PublishTarget) => {
    if (!confirm(`Xóa đích đăng "${target.name}"? Các bài đã đăng vẫn được giữ lịch sử.`)) return;
    try {
      await deletePublishTarget(target.id);
      toast.success(`Đã xóa "${target.name}"`);
      setTargets((prev) => prev.filter((t) => t.id !== target.id));
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Xóa thất bại");
    }
  };

  return (
    <div className="mx-auto max-w-4xl space-y-6 animate-in fade-in slide-in-from-bottom-4 duration-500">
      <div className="flex items-center gap-3">
        <div className="p-3 bg-blue-500/10 rounded-xl">
          <Server className="w-6 h-6 text-blue-500" />
        </div>
        <div>
          <h1 className="text-2xl font-bold">Đích đăng (Publish Targets)</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Khai báo website nhận bài tự động. AutoSEO sẽ POST bài viết tới endpoint kèm secret key.
          </p>
        </div>
      </div>

      {/* Add form */}
      <form onSubmit={handleCreate}>
        <Card className="border-blue-500/20 shadow-lg shadow-blue-500/5">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Plus className="w-5 h-5 text-blue-500" />
              Thêm đích đăng mới
            </CardTitle>
            <CardDescription>
              Endpoint phải nhận POST JSON theo chuẩn AutoSEO (xem AUTOSEO_INTEGRATION_GUIDE.md).
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-5">
            <div className="space-y-2">
              <label className="text-sm font-medium">Tên gợi nhớ</label>
              <Input
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="VD: Blog công ty (WordPress)"
                maxLength={200}
              />
            </div>
            <div className="space-y-2">
              <label className="text-sm font-medium">URL Endpoint</label>
              <Input
                value={endpointUrl}
                onChange={(e) => setEndpointUrl(e.target.value)}
                placeholder="https://example.com/api/autoseo/receive"
              />
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="space-y-2">
                <label className="text-sm font-medium">Secret Key</label>
                <Input
                  type="password"
                  value={secretKey}
                  onChange={(e) => setSecretKey(e.target.value)}
                  placeholder="Khớp với secret trong code website"
                />
              </div>
              <div className="space-y-2">
                <label className="text-sm font-medium">Chế độ mặc định</label>
                <Select value={defaultMode} onValueChange={(v) => { if (v) setDefaultMode(v as PublishMode); }}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="draft">Bản nháp (draft)</SelectItem>
                    <SelectItem value="published">Đăng ngay (published)</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>
            <button
              type="button"
              onClick={() => setAutoPublish((v) => !v)}
              className={cn(
                "flex w-full items-center gap-3 rounded-lg border p-3 text-left transition-colors",
                autoPublish
                  ? "border-emerald-300 bg-emerald-50 dark:border-emerald-800 dark:bg-emerald-900/20"
                  : "border-border hover:bg-muted/50"
              )}
            >
              <span
                className={cn(
                  "flex h-5 w-5 shrink-0 items-center justify-center rounded border",
                  autoPublish ? "border-emerald-600 bg-emerald-600 text-white" : "border-muted-foreground/40"
                )}
              >
                {autoPublish && <Check className="h-3.5 w-3.5" />}
              </span>
              <span>
                <span className="flex items-center gap-1.5 text-sm font-medium">
                  <Zap className="h-3.5 w-3.5 text-emerald-500" />
                  Tự động đăng khi bài viết hoàn thành
                </span>
                <span className="mt-0.5 block text-xs text-muted-foreground">
                  Mọi bài mới hoàn thành (kể cả từ chiến dịch) sẽ tự POST tới đích này theo chế độ mặc định.
                </span>
              </span>
            </button>

            <div className="flex flex-col sm:flex-row gap-3 pt-2">
              <Button
                type="button"
                variant="outline"
                onClick={handleTest}
                disabled={testing}
                className="border-blue-200 text-blue-700 hover:bg-blue-50 dark:border-blue-800 dark:text-blue-300 dark:hover:bg-blue-900/20"
              >
                {testing ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Plug className="mr-2 h-4 w-4" />}
                Test kết nối
              </Button>
              <Button
                type="submit"
                disabled={saving || !validForm}
                className="flex-1 bg-blue-600 hover:bg-blue-700 text-white"
              >
                {saving ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Plus className="mr-2 h-4 w-4" />}
                Lưu đích đăng
              </Button>
            </div>
          </CardContent>
        </Card>
      </form>

      {/* List */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Danh sách đích đăng ({targets.length})</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {loading ? (
            Array.from({ length: 2 }).map((_, i) => <Skeleton key={i} className="h-16 w-full rounded-lg" />)
          ) : targets.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-10 text-muted-foreground">
              <Server className="h-8 w-8 mb-2 opacity-20" />
              <p>Chưa có đích đăng nào. Thêm một cái ở trên để bắt đầu.</p>
            </div>
          ) : (
            targets.map((t) => (
              <div
                key={t.id}
                className="flex items-center justify-between gap-4 rounded-lg border border-border/60 p-4 hover:bg-blue-50/40 dark:hover:bg-blue-900/10 transition-colors"
              >
                <div className="min-w-0 space-y-1">
                  <div className="flex items-center gap-2">
                    <CheckCircle2 className="h-4 w-4 text-emerald-500 shrink-0" />
                    <span className="font-semibold truncate">{t.name}</span>
                    <Badge variant="secondary" className="text-[10px] uppercase">{t.default_mode}</Badge>
                    {t.auto_publish && (
                      <Badge className="gap-1 border-none bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400 text-[10px]">
                        <Zap className="h-3 w-3" />
                        Tự động
                      </Badge>
                    )}
                  </div>
                  <p className="text-xs text-muted-foreground font-mono truncate">{t.endpoint_url}</p>
                  <p className="text-xs text-muted-foreground">Secret: {t.secret_key}</p>
                </div>
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={() => handleDelete(t)}
                  className="text-muted-foreground hover:text-destructive shrink-0"
                >
                  <Trash2 className="h-4 w-4" />
                </Button>
              </div>
            ))
          )}
        </CardContent>
      </Card>
    </div>
  );
}
