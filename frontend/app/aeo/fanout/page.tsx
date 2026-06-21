"use client";

import { useState } from "react";
import { Loader2, Network, Search, Link as LinkIcon, FileText, Layers, Target, Activity, CheckCircle2, AlertCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { fanout } from "@/lib/api";
import { SUB_QUERY_TYPE_LABELS } from "@/lib/constants";
import type { FanOutResponse, SubQuery } from "@/lib/types";
import { toast } from "sonner";
import { cn } from "@/lib/utils";

function groupByType(queries: SubQuery[]): Record<string, SubQuery[]> {
  const groups: Record<string, SubQuery[]> = {};
  for (const q of queries) {
    if (!groups[q.type]) groups[q.type] = [];
    groups[q.type].push(q);
  }
  return groups;
}

export default function FanoutPage() {
  const [targetQuery, setTargetQuery] = useState("");
  const [contentUrl, setContentUrl] = useState("");
  const [existingContent, setExistingContent] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<FanOutResponse | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!targetQuery.trim()) return;
    setSubmitting(true);
    setResult(null);
    try {
      const res = await fanout({
        target_query: targetQuery,
        content_url: contentUrl || undefined,
        existing_content: existingContent || undefined,
      });
      setResult(res);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Quá trình mở rộng truy vấn thất bại");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="space-y-6 max-w-7xl mx-auto pb-10">
      <div className="mb-8">
        <h1 className="text-3xl font-extrabold tracking-tight text-blue-900 dark:text-blue-100 flex items-center gap-2">
          Mở rộng Truy vấn <span className="text-muted-foreground font-normal text-2xl">(Fan-Out)</span>
        </h1>
        <p className="text-muted-foreground mt-1">
          Phân rã truy vấn gốc thành các ý định tìm kiếm cụ thể và đánh giá độ bao phủ nội dung
        </p>
      </div>

      <Card className="border-blue-500/10 shadow-sm overflow-hidden bg-card/50 backdrop-blur-sm relative">
        <div className="absolute top-0 left-0 w-1 h-full bg-blue-500"></div>
        <CardHeader className="bg-blue-50/50 dark:bg-blue-900/10 border-b border-blue-500/10">
          <CardTitle className="text-blue-800 dark:text-blue-200">Tạo Truy vấn con & Phân tích khoảng trống</CardTitle>
          <CardDescription>Nhập truy vấn gốc để AI phân rã thành các khía cạnh chi tiết</CardDescription>
        </CardHeader>
        <CardContent className="p-6 md:p-8">
          <form onSubmit={handleSubmit} className="space-y-6">
            <div className="space-y-2">
              <label className="text-sm font-semibold text-foreground uppercase tracking-wider flex items-center gap-2">
                <Search className="h-4 w-4 text-blue-500" /> Truy vấn gốc
              </label>
              <Input
                value={targetQuery}
                onChange={(e) => setTargetQuery(e.target.value)}
                placeholder="Ví dụ: phần mềm CRM tốt nhất cho startup"
                required
                className="py-6 text-lg focus-visible:ring-blue-500 border-blue-200 dark:border-blue-800"
              />
            </div>

            <details className="group rounded-xl border border-blue-100 dark:border-blue-900/50 bg-blue-50/30 dark:bg-blue-900/10 overflow-hidden transition-all">
              <summary className="cursor-pointer text-sm font-medium p-4 flex items-center justify-between hover:bg-blue-50/50 dark:hover:bg-blue-900/20 transition-colors">
                <div className="flex items-center gap-2 text-blue-800 dark:text-blue-300">
                  <Target className="h-4 w-4" />
                  Nội dung để Phân tích Khoảng trống (Tùy chọn)
                </div>
                <div className="text-muted-foreground opacity-50 group-open:rotate-180 transition-transform">
                  <svg width="15" height="15" viewBox="0 0 15 15" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M3.13523 6.15803C3.3241 5.95657 3.64052 5.94637 3.84197 6.13523L7.5 9.56464L11.158 6.13523C11.3595 5.94637 11.6759 5.95657 11.8648 6.15803C12.0536 6.35949 12.0434 6.67591 11.842 6.86477L7.84197 10.6148C7.64964 10.7951 7.35036 10.7951 7.15803 10.6148L3.15803 6.86477C2.95657 6.67591 2.94637 6.35949 3.13523 6.15803Z" fill="currentColor" fillRule="evenodd" clipRule="evenodd"></path></svg>
                </div>
              </summary>
              <div className="p-4 pt-0 space-y-4 border-t border-blue-100/50 dark:border-blue-900/30 mt-2">
                <p className="text-xs text-muted-foreground mb-4">
                  Cung cấp URL hoặc văn bản để hệ thống đánh giá xem nội dung của bạn đã bao phủ hết các truy vấn con vừa tạo hay chưa.
                </p>
                <div className="grid md:grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <label className="text-sm font-medium text-foreground flex items-center gap-1.5">
                      <LinkIcon className="h-3.5 w-3.5" /> Đường dẫn URL
                    </label>
                    <Input
                      type="url"
                      value={contentUrl}
                      onChange={(e) => setContentUrl(e.target.value)}
                      placeholder="https://example.com/bai-viet"
                      className="bg-background focus-visible:ring-blue-500"
                    />
                  </div>
                  <div className="space-y-2">
                    <label className="text-sm font-medium text-foreground flex items-center gap-1.5">
                      <FileText className="h-3.5 w-3.5" /> Hoặc dán nội dung văn bản
                    </label>
                    <Textarea
                      value={existingContent}
                      onChange={(e) => setExistingContent(e.target.value)}
                      placeholder="Dán nội dung bài viết hiện tại..."
                      rows={4}
                      className="resize-y bg-background focus-visible:ring-blue-500"
                    />
                  </div>
                </div>
              </div>
            </details>

            <Button 
              type="submit" 
              disabled={submitting || !targetQuery.trim()}
              size="lg"
              className="w-full sm:w-auto bg-blue-600 hover:bg-blue-700 text-white shadow-md shadow-blue-500/20"
            >
              {submitting ? (
                <><Loader2 className="mr-2 h-5 w-5 animate-spin" /> Đang xử lý phân rã...</>
              ) : (
                <><Network className="mr-2 h-5 w-5" /> Bắt đầu Mở rộng Truy vấn</>
              )}
            </Button>
          </form>
        </CardContent>
      </Card>

      {result && (
        <div className="space-y-6 animate-in fade-in slide-in-from-bottom-4 duration-500">
          <div className="flex flex-wrap items-center gap-4 text-sm bg-blue-50 dark:bg-blue-900/10 p-3 rounded-lg border border-blue-100 dark:border-blue-900/30">
            <Badge variant="outline" className="bg-background font-medium py-1 px-3 border-blue-200 dark:border-blue-800 text-blue-700 dark:text-blue-300">
              <Layers className="h-3.5 w-3.5 mr-1.5 inline" />
              {result.total_sub_queries} truy vấn con được tạo
            </Badge>
            <span className="text-muted-foreground flex items-center gap-1.5">
              <Activity className="h-4 w-4 opacity-50" />
              Mô hình: <span className="font-medium text-foreground">{result.model_used}</span>
            </span>
          </div>

          {/* Gap Summary */}
          {result.gap_summary && (
            <Card className="border-t-4 border-t-amber-500 shadow-sm bg-gradient-to-br from-card to-amber-50/10 dark:to-amber-950/10">
              <CardHeader className="pb-3 border-b border-border/50">
                <CardTitle className="text-lg flex items-center gap-2 text-amber-800 dark:text-amber-500">
                  <Target className="h-5 w-5" />
                  Phân tích Khoảng trống Nội dung (Gap Analysis)
                </CardTitle>
              </CardHeader>
              <CardContent className="pt-5 space-y-5">
                <div className="space-y-2">
                  <div className="flex items-center justify-between text-sm">
                    <span className="font-semibold uppercase tracking-wider text-muted-foreground">Độ bao phủ nội dung</span>
                    <span className="font-bold text-lg text-foreground">
                      {result.gap_summary.coverage_percent}% <span className="text-sm font-normal text-muted-foreground ml-1">({result.gap_summary.covered} / {result.gap_summary.total})</span>
                    </span>
                  </div>
                  <Progress 
                    value={result.gap_summary.coverage_percent} 
                    className="h-3 bg-muted"
                    indicatorClassName={
                      result.gap_summary.coverage_percent >= 80 ? "bg-emerald-500" :
                      result.gap_summary.coverage_percent >= 50 ? "bg-amber-500" : "bg-rose-500"
                    }
                  />
                </div>
                
                <div className="space-y-3 pt-2">
                  <span className="text-sm font-medium text-muted-foreground block border-b border-border/50 pb-1">Các nhóm ý định tìm kiếm:</span>
                  <div className="flex flex-wrap gap-2">
                    {result.gap_summary.covered_types.map((t) => (
                      <Badge key={t} variant="outline" className="bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-900/30 dark:text-emerald-400 dark:border-emerald-800 flex items-center gap-1 pl-1">
                        <CheckCircle2 className="h-3 w-3" />
                        {SUB_QUERY_TYPE_LABELS[t] ?? t}
                      </Badge>
                    ))}
                    {result.gap_summary.missing_types.map((t) => (
                      <Badge key={t} variant="outline" className="bg-rose-50 text-rose-700 border-rose-200 dark:bg-rose-900/30 dark:text-rose-400 dark:border-rose-800 flex items-center gap-1 pl-1">
                        <AlertCircle className="h-3 w-3" />
                        {SUB_QUERY_TYPE_LABELS[t] ?? t}
                      </Badge>
                    ))}
                  </div>
                </div>
              </CardContent>
            </Card>
          )}

          {/* Sub-queries grouped by type */}
          <div className="grid gap-6 md:grid-cols-2">
            {Object.entries(groupByType(result.sub_queries)).map(([type, queries]) => (
              <Card key={type} className="shadow-sm border-blue-500/10">
                <CardHeader className="pb-3 bg-muted/20 border-b border-border/50">
                  <CardTitle className="text-base font-semibold flex items-center justify-between text-blue-900 dark:text-blue-100">
                    <span className="flex items-center gap-2">
                      <Layers className="h-4 w-4 text-blue-500" />
                      {SUB_QUERY_TYPE_LABELS[type] ?? type}
                    </span>
                    <Badge variant="secondary" className="bg-blue-100 text-blue-700 dark:bg-blue-900/50 dark:text-blue-300 font-bold px-2.5">
                      {queries.length}
                    </Badge>
                  </CardTitle>
                </CardHeader>
                <CardContent className="pt-4 p-0">
                  <ul className="divide-y divide-border/50">
                    {queries.map((q, i) => (
                      <li key={i} className="flex flex-col sm:flex-row sm:items-start justify-between gap-3 p-4 hover:bg-muted/30 transition-colors">
                        <span className="text-sm font-medium leading-relaxed">{q.query}</span>
                        <div className="flex shrink-0 items-center justify-end gap-2 mt-1 sm:mt-0">
                          {q.similarity_score !== null && (
                            <span className="text-xs text-muted-foreground font-mono bg-muted px-1.5 py-0.5 rounded-md">
                              {(q.similarity_score * 100).toFixed(0)}%
                            </span>
                          )}
                          {q.covered !== null && (
                            <Badge 
                              variant="outline" 
                              className={cn(
                                "text-[11px] font-bold px-2 py-0.5 whitespace-nowrap",
                                q.covered 
                                  ? "bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-900/30 dark:text-emerald-400 dark:border-emerald-800" 
                                  : "bg-rose-50 text-rose-700 border-rose-200 dark:bg-rose-900/30 dark:text-rose-400 dark:border-rose-800"
                              )}
                            >
                              {q.covered ? "Đã bao phủ" : "Bị thiếu"}
                            </Badge>
                          )}
                        </div>
                      </li>
                    ))}
                  </ul>
                </CardContent>
              </Card>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
