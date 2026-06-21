"use client";

import { use, useCallback, useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { AlertCircle, Download, RotateCcw, ChevronLeft, Zap, Coins, FileText, CheckCircle2, Globe } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import { StatusBadge } from "@/components/status-badge";
import { PipelineStepper } from "@/components/pipeline-stepper";
import { ScoreGauge } from "@/components/score-gauge";
import { ScoreDimensionBar } from "@/components/score-dimension-bar";
import { MarkdownRenderer } from "@/components/markdown-renderer";
import { JsonViewer } from "@/components/json-viewer";
import { PublishDialog } from "@/components/publish-dialog";
import { usePolling } from "@/hooks/use-polling";
import { getJob, resumeJob } from "@/lib/api";
import { TERMINAL_STATUSES } from "@/lib/constants";
import type { JobResponse, ArticleContent } from "@/lib/types";
import { toast } from "sonner";

function articleToMarkdown(content: ArticleContent): string {
  let md = "";
  for (const section of content.sections) {
    const level = section.heading_level === "h1" ? "#" : section.heading_level === "h2" ? "##" : "###";
    md += `${level} ${section.heading}\n\n${section.content}\n\n`;
  }
  if (content.faq.length > 0) {
    md += "## FAQ\n\n";
    for (const faq of content.faq) {
      md += `**${faq.question}**\n\n${faq.answer}\n\n`;
    }
  }
  return md;
}

function downloadMarkdown(content: ArticleContent, topic: string) {
  const md = articleToMarkdown(content);
  const blob = new Blob([md], { type: "text/markdown" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `${topic.toLowerCase().replace(/\\s+/g, "-").slice(0, 50)}.md`;
  a.click();
  URL.revokeObjectURL(url);
}

export default function JobDetailPage({
  params,
}: {
  params: Promise<{ jobId: string }>;
}) {
  const { jobId } = use(params);
  const router = useRouter();
  const [resuming, setResuming] = useState(false);
  const [activeTab, setActiveTab] = useState<string>("events");

  const fetcher = useCallback(() => {
    return getJob(jobId, false).then(async (job) => {
      if (TERMINAL_STATUSES.includes(job.status)) {
        return getJob(jobId, true);
      }
      return job;
    });
  }, [jobId]);

  const { data: job, isLoading } = usePolling<JobResponse>(fetcher, {
    interval: 2000,
    enabled: true,
  });

  const isActive = job ? !TERMINAL_STATUSES.includes(job.status) : false;

  const handleResume = async () => {
    setResuming(true);
    try {
      await resumeJob(jobId);
      toast.success("Đã tiếp tục tiến trình");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Lỗi khi tiếp tục");
    } finally {
      setResuming(false);
    }
  };

  const hasContent = !!(job?.result || job?.article_data);
  useEffect(() => {
    if (hasContent) {
      setActiveTab((prev) => (prev === "events" ? "article" : prev));
    }
  }, [hasContent]);

  if (isLoading || !job) {
    return (
      <div className="space-y-6 max-w-7xl mx-auto pb-10">
        <Skeleton className="h-10 w-32" />
        <Skeleton className="h-24 w-full rounded-xl" />
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          <Skeleton className="h-64 w-full md:col-span-2 rounded-xl" />
          <Skeleton className="h-64 w-full rounded-xl" />
        </div>
      </div>
    );
  }

  const result = job.result;
  const quality = result?.quality ?? job.quality_data;
  const review = result?.review ?? job.review_data;

  return (
    <div className="space-y-6 max-w-7xl mx-auto pb-10">
      {/* Header Controls */}
      <div className="flex items-center justify-between">
        <Button 
          variant="ghost" 
          size="sm" 
          onClick={() => router.push("/pipeline")}
          className="text-muted-foreground hover:text-blue-600 hover:bg-blue-50 dark:hover:bg-blue-900/20 transition-colors"
        >
          <ChevronLeft className="mr-1 h-4 w-4" />
          Quay lại danh sách
        </Button>
        {hasContent && job.status === "completed" && (
          <div className="flex items-center gap-2">
            <Button
              size="sm"
              variant="outline"
              onClick={() => downloadMarkdown(result?.content ?? job.article_data!, job.topic)}
              className="border-blue-200 text-blue-700 hover:bg-blue-50 dark:border-blue-800 dark:text-blue-300 dark:hover:bg-blue-900/20"
            >
              <Download className="mr-2 h-4 w-4" />
              Xuất file Markdown
            </Button>
            <PublishDialog jobId={job.job_id} />
          </div>
        )}
      </div>

      {/* Main Title Card */}
      <Card className="border-blue-500/10 shadow-sm overflow-hidden bg-card/50 backdrop-blur-sm relative">
        <div className="absolute top-0 left-0 w-1 h-full bg-blue-500"></div>
        <CardContent className="p-6 md:p-8">
          <div className="flex flex-col md:flex-row md:items-start justify-between gap-6">
            <div className="space-y-3">
              <div className="flex flex-wrap items-center gap-2">
                <StatusBadge status={job.status} currentStep={job.current_step} />
                <Badge variant="outline" className="bg-background border-blue-200 dark:border-blue-800 text-blue-700 dark:text-blue-300">
                  {job.target_word_count.toLocaleString()} từ
                </Badge>
                <Badge variant="outline" className="uppercase bg-background">
                  {job.language}
                </Badge>
                {job.revision_count > 0 && (
                  <Badge variant="secondary" className="bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400 border-none">
                    <RotateCcw className="mr-1 h-3 w-3" />
                    Đã sửa {job.revision_count} lần
                  </Badge>
                )}
              </div>
              <h1 className="text-3xl font-extrabold tracking-tight text-foreground leading-tight">
                {job.topic}
              </h1>
              <p className="text-sm text-muted-foreground font-mono">
                ID: {job.job_id}
              </p>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Pipeline Stepper */}
      {job.status !== "pending" && (
        <Card className="border-blue-500/10 shadow-sm">
          <CardContent className="py-6">
            <PipelineStepper status={job.status} currentStep={job.current_step} />
          </CardContent>
        </Card>
      )}

      {/* Error Banner */}
      {job.status === "failed" && job.error && (
        <Card className="border-destructive shadow-sm shadow-destructive/10 overflow-hidden relative">
          <div className="absolute top-0 left-0 w-1 h-full bg-destructive"></div>
          <CardContent className="flex flex-col sm:flex-row items-start sm:items-center gap-4 py-6">
            <div className="bg-destructive/10 p-3 rounded-full shrink-0">
              <AlertCircle className="h-6 w-6 text-destructive" />
            </div>
            <div className="flex-1 space-y-1">
              <h3 className="font-bold text-destructive text-lg">Quá trình bị lỗi</h3>
              <p className="text-sm text-muted-foreground/80 font-mono bg-muted/50 p-2 rounded-md break-all">
                {job.error}
              </p>
            </div>
            <Button size="default" onClick={handleResume} disabled={resuming} className="w-full sm:w-auto shrink-0 mt-2 sm:mt-0">
              <RotateCcw className="mr-2 h-4 w-4" />
              {resuming ? "Đang chạy lại..." : "Thử chạy lại"}
            </Button>
          </CardContent>
        </Card>
      )}

      {/* Artifact Tabs */}
      {(hasContent || quality || job.events_data) && (
        <Tabs value={activeTab} onValueChange={setActiveTab} className="w-full">
          <div className="sticky top-0 z-10 bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60 pt-2 pb-4">
            <TabsList className="w-full justify-start h-auto p-1 bg-muted/50 overflow-x-auto flex-nowrap border border-blue-500/10 shadow-sm">
              {hasContent && <TabsTrigger value="article" className="data-[state=active]:bg-white dark:data-[state=active]:bg-slate-900 data-[state=active]:text-blue-600 dark:data-[state=active]:text-blue-400 data-[state=active]:shadow-sm px-4 py-2">Bài viết</TabsTrigger>}
              {(result?.outline ?? job.outline_data) && <TabsTrigger value="outline" className="data-[state=active]:bg-white dark:data-[state=active]:bg-slate-900 data-[state=active]:text-blue-600 dark:data-[state=active]:text-blue-400 data-[state=active]:shadow-sm px-4 py-2">Dàn ý</TabsTrigger>}
              {quality && <TabsTrigger value="quality" className="data-[state=active]:bg-white dark:data-[state=active]:bg-slate-900 data-[state=active]:text-blue-600 dark:data-[state=active]:text-blue-400 data-[state=active]:shadow-sm px-4 py-2">Chất lượng</TabsTrigger>}
              {result?.seo_metadata && <TabsTrigger value="seo" className="data-[state=active]:bg-white dark:data-[state=active]:bg-slate-900 data-[state=active]:text-blue-600 dark:data-[state=active]:text-blue-400 data-[state=active]:shadow-sm px-4 py-2">SEO</TabsTrigger>}
              {(result?.competitive_analysis ?? job.analysis_data) && (
                <TabsTrigger value="research" className="data-[state=active]:bg-white dark:data-[state=active]:bg-slate-900 data-[state=active]:text-blue-600 dark:data-[state=active]:text-blue-400 data-[state=active]:shadow-sm px-4 py-2">Nghiên cứu</TabsTrigger>
              )}
              {result?.keyword_analysis && <TabsTrigger value="keywords" className="data-[state=active]:bg-white dark:data-[state=active]:bg-slate-900 data-[state=active]:text-blue-600 dark:data-[state=active]:text-blue-400 data-[state=active]:shadow-sm px-4 py-2">Từ khóa</TabsTrigger>}
              {result?.links && <TabsTrigger value="links" className="data-[state=active]:bg-white dark:data-[state=active]:bg-slate-900 data-[state=active]:text-blue-600 dark:data-[state=active]:text-blue-400 data-[state=active]:shadow-sm px-4 py-2">Liên kết</TabsTrigger>}
              {job.events_data && <TabsTrigger value="events" className="data-[state=active]:bg-white dark:data-[state=active]:bg-slate-900 data-[state=active]:text-blue-600 dark:data-[state=active]:text-blue-400 data-[state=active]:shadow-sm px-4 py-2">Nhật ký</TabsTrigger>}
            </TabsList>
          </div>

          <div className="mt-6">
            {/* Article Tab */}
            {hasContent && (
              <TabsContent value="article" className="mt-0 focus-visible:outline-none focus-visible:ring-0">
                <Card className="border-blue-500/10 shadow-sm">
                  <CardContent className="p-8 prose prose-blue dark:prose-invert max-w-none">
                    <MarkdownRenderer
                      content={articleToMarkdown(result?.content ?? job.article_data!)}
                    />
                  </CardContent>
                </Card>
              </TabsContent>
            )}

            {/* Outline Tab */}
            {(result?.outline ?? job.outline_data) && (
              <TabsContent value="outline" className="mt-0 focus-visible:outline-none focus-visible:ring-0">
                <Card className="border-blue-500/10 shadow-sm">
                  <CardContent className="p-6 md:p-8 space-y-8">
                    {(() => {
                      const outline = result?.outline ?? job.outline_data!;
                      return (
                        <>
                          <div className="border-b border-border pb-6">
                            <h2 className="text-2xl font-extrabold text-blue-900 dark:text-blue-100 mb-2">{outline.h1}</h2>
                          </div>
                          
                          <div className="space-y-6">
                            {outline.headings.map((h, i) => (
                              <div
                                key={i}
                                className="relative pl-6 before:absolute before:left-0 before:top-2 before:bottom-0 before:w-0.5 before:bg-blue-200 dark:before:bg-blue-800"
                                style={{ marginLeft: h.level === "h3" ? 24 : h.level === "h2" ? 0 : 0 }}
                              >
                                <div className="absolute left-[-4px] top-[10px] w-2.5 h-2.5 rounded-full bg-blue-500 ring-4 ring-background"></div>
                                <div className="flex flex-col sm:flex-row sm:items-center gap-2 mb-2">
                                  <Badge variant="outline" className="w-fit text-[10px] font-mono bg-blue-50 text-blue-700 border-blue-200 dark:bg-blue-900/20 dark:text-blue-300 dark:border-blue-800">{h.level}</Badge>
                                  <span className="font-bold text-lg text-foreground">{h.text}</span>
                                  <Badge variant="secondary" className="w-fit text-xs opacity-70">~{h.target_word_count} từ</Badge>
                                </div>
                                {h.key_points.length > 0 && (
                                  <ul className="mt-3 space-y-2 text-sm text-muted-foreground bg-muted/30 p-4 rounded-lg">
                                    {h.key_points.map((p, j) => (
                                      <li key={j} className="flex gap-2 items-start">
                                        <div className="mt-1.5 w-1.5 h-1.5 rounded-full bg-blue-400 shrink-0"></div>
                                        <span>{p}</span>
                                      </li>
                                    ))}
                                  </ul>
                                )}
                              </div>
                            ))}
                          </div>
                          
                          {outline.faq_questions.length > 0 && (
                            <div className="mt-8 pt-8 border-t border-border">
                              <h3 className="font-bold text-xl mb-4 flex items-center gap-2 text-blue-800 dark:text-blue-200">
                                <Zap className="h-5 w-5 text-amber-500" />
                                Câu hỏi thường gặp (FAQ)
                              </h3>
                              <div className="grid gap-3">
                                {outline.faq_questions.map((q, i) => (
                                  <div key={i} className="bg-muted/50 p-3 rounded-md font-medium text-sm flex gap-3 items-center">
                                    <div className="bg-blue-100 dark:bg-blue-900/50 text-blue-600 dark:text-blue-400 w-6 h-6 rounded-full flex items-center justify-center text-xs shrink-0">Q</div>
                                    {q}
                                  </div>
                                ))}
                              </div>
                            </div>
                          )}
                          
                          {outline.brief && (
                            <div className="mt-8 rounded-xl bg-gradient-to-br from-blue-50 to-indigo-50 dark:from-blue-950/40 dark:to-indigo-950/40 p-6 border border-blue-100 dark:border-blue-900/50">
                              <h3 className="font-bold text-lg mb-4 text-blue-800 dark:text-blue-300">Định hướng Nội dung</h3>
                              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                                <div className="bg-white/60 dark:bg-black/20 p-4 rounded-lg">
                                  <div className="text-xs uppercase font-bold text-blue-500 mb-1">Độc giả mục tiêu</div>
                                  <div className="text-sm font-medium">{outline.brief.target_audience}</div>
                                </div>
                                <div className="bg-white/60 dark:bg-black/20 p-4 rounded-lg">
                                  <div className="text-xs uppercase font-bold text-blue-500 mb-1">Giọng văn</div>
                                  <div className="text-sm font-medium capitalize">{outline.brief.tone}</div>
                                </div>
                                <div className="bg-white/60 dark:bg-black/20 p-4 rounded-lg">
                                  <div className="text-xs uppercase font-bold text-blue-500 mb-1">Góc nhìn / Tiếp cận</div>
                                  <div className="text-sm font-medium">{outline.brief.angle}</div>
                                </div>
                              </div>
                            </div>
                          )}
                        </>
                      );
                    })()}
                  </CardContent>
                </Card>
              </TabsContent>
            )}

            {/* Quality Tab */}
            {quality && (
              <TabsContent value="quality" className="mt-0 focus-visible:outline-none focus-visible:ring-0">
                <div className="grid gap-6 md:grid-cols-[300px_1fr]">
                  <Card className="border-blue-500/10 shadow-sm bg-gradient-to-b from-card to-blue-50/30 dark:to-blue-950/10">
                    <CardHeader className="text-center pb-0">
                      <CardTitle className="text-lg">Điểm Chất lượng</CardTitle>
                      <CardDescription>Đánh giá tổng quan mức độ chuẩn SEO</CardDescription>
                    </CardHeader>
                    <CardContent className="flex flex-col items-center justify-center py-8">
                      <ScoreGauge score={quality.overall * 100} label="" />
                      <Badge 
                        variant={quality.passes_threshold ? "default" : "destructive"} 
                        className={`mt-6 px-4 py-1.5 text-sm ${quality.passes_threshold ? 'bg-emerald-500 hover:bg-emerald-600' : ''}`}
                      >
                        {quality.passes_threshold ? (
                          <span className="flex items-center gap-1.5"><CheckCircle2 className="h-4 w-4"/> Đạt chuẩn phát hành</span>
                        ) : "Chưa đạt ngưỡng yêu cầu"}
                      </Badge>
                    </CardContent>
                  </Card>
                  
                  <Card className="border-blue-500/10 shadow-sm">
                    <CardHeader className="border-b border-border/50 pb-4">
                      <CardTitle>Chi tiết các tiêu chí</CardTitle>
                      <CardDescription>Điểm số từng thành phần của bài viết</CardDescription>
                    </CardHeader>
                    <CardContent className="pt-6 space-y-5">
                      {quality.dimensions.map((d) => (
                        <ScoreDimensionBar key={d.name} name={d.name} score={d.score} feedback={d.feedback} />
                      ))}
                    </CardContent>
                  </Card>
                </div>
                
                {review && (
                  <Card className="mt-6 border-blue-500/10 shadow-sm">
                    <CardHeader className="border-b border-border/50 bg-muted/20">
                      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                        <div>
                          <CardTitle className="text-xl">Kiểm duyệt bởi AI (Review)</CardTitle>
                          <CardDescription className="mt-1">{review.summary}</CardDescription>
                        </div>
                        <Badge 
                          variant={review.passed ? "default" : "destructive"}
                          className={`text-sm px-3 py-1 ${review.passed ? 'bg-emerald-500 hover:bg-emerald-600' : ''}`}
                        >
                          {review.passed ? "Đã duyệt" : "Cần chỉnh sửa lại"}
                        </Badge>
                      </div>
                    </CardHeader>
                    <CardContent className="pt-6 space-y-6">
                      {review.issues.length > 0 && (
                        <div>
                          <h4 className="font-bold text-destructive flex items-center gap-2 mb-3">
                            <AlertCircle className="h-5 w-5" />
                            Các vấn đề cần khắc phục
                          </h4>
                          <div className="rounded-md border overflow-hidden">
                            <Table>
                              <TableHeader className="bg-muted/50">
                                <TableRow>
                                  <TableHead className="w-[120px]">Mức độ</TableHead>
                                  <TableHead className="w-[150px]">Phân loại</TableHead>
                                  <TableHead>Mô tả vấn đề</TableHead>
                                  <TableHead>Đề xuất sửa</TableHead>
                                </TableRow>
                              </TableHeader>
                              <TableBody>
                                {review.issues.map((issue, i) => (
                                  <TableRow key={i}>
                                    <TableCell>
                                      <Badge 
                                        variant={issue.severity === "critical" ? "destructive" : "secondary"} 
                                        className="capitalize"
                                      >
                                        {issue.severity === "critical" ? "Nghiêm trọng" : "Cảnh báo"}
                                      </Badge>
                                    </TableCell>
                                    <TableCell className="font-medium text-sm">{issue.category}</TableCell>
                                    <TableCell className="text-sm">{issue.description}</TableCell>
                                    <TableCell className="text-sm text-muted-foreground bg-muted/30">{issue.suggestion}</TableCell>
                                  </TableRow>
                                ))}
                              </TableBody>
                            </Table>
                          </div>
                        </div>
                      )}
                      
                      {review.strengths.length > 0 && (
                        <div>
                          <h4 className="font-bold text-emerald-600 dark:text-emerald-400 flex items-center gap-2 mb-3">
                            <CheckCircle2 className="h-5 w-5" />
                            Điểm sáng của bài viết
                          </h4>
                          <div className="grid gap-2">
                            {review.strengths.map((s, i) => (
                              <div key={i} className="flex items-start gap-2 bg-emerald-50 dark:bg-emerald-950/20 text-emerald-800 dark:text-emerald-200 p-3 rounded-md text-sm border border-emerald-100 dark:border-emerald-900/50">
                                <CheckCircle2 className="h-4 w-4 mt-0.5 shrink-0" />
                                <span>{s}</span>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}
                    </CardContent>
                  </Card>
                )}
              </TabsContent>
            )}

            {/* SEO Tab */}
            {result?.seo_metadata && (
              <TabsContent value="seo" className="mt-0 focus-visible:outline-none focus-visible:ring-0">
                <div className="grid gap-6 md:grid-cols-2">
                  <Card className="border-blue-500/10 shadow-sm md:col-span-2">
                    <CardHeader className="border-b border-border/50 bg-blue-50/50 dark:bg-blue-900/10">
                      <CardTitle className="text-blue-800 dark:text-blue-200">Metadata Chính thức</CardTitle>
                    </CardHeader>
                    <CardContent className="pt-6 grid gap-6 md:grid-cols-2">
                      <div className="space-y-1">
                        <span className="text-xs font-bold uppercase text-muted-foreground">Thẻ Title (Tiêu đề)</span>
                        <div className="p-3 bg-muted rounded-md text-sm font-medium border-l-4 border-blue-500">
                          {result.seo_metadata.title_tag}
                        </div>
                        <div className="text-xs text-right text-muted-foreground mt-1">
                          {result.seo_metadata.title_tag.length} ký tự
                        </div>
                      </div>
                      
                      <div className="space-y-1">
                        <span className="text-xs font-bold uppercase text-muted-foreground">Từ khóa chính</span>
                        <div className="p-3 bg-muted rounded-md text-sm font-medium border-l-4 border-indigo-500">
                          {result.seo_metadata.primary_keyword}
                        </div>
                      </div>
                      
                      <div className="space-y-1 md:col-span-2">
                        <span className="text-xs font-bold uppercase text-muted-foreground">Thẻ Meta Description (Mô tả)</span>
                        <div className="p-3 bg-muted rounded-md text-sm font-medium border-l-4 border-emerald-500">
                          {result.seo_metadata.meta_description}
                        </div>
                        <div className="text-xs text-right text-muted-foreground mt-1">
                          {result.seo_metadata.meta_description.length} ký tự
                        </div>
                      </div>
                      
                      <div className="space-y-1 md:col-span-2">
                        <span className="text-xs font-bold uppercase text-muted-foreground">Đường dẫn URL (Slug)</span>
                        <div className="p-3 bg-muted rounded-md text-sm font-mono text-blue-600 dark:text-blue-400 border border-border">
                          /{result.seo_metadata.slug}
                        </div>
                      </div>
                    </CardContent>
                  </Card>
                  
                  {result.meta_options && (
                    <Card className="border-blue-500/10 shadow-sm md:col-span-2">
                      <CardHeader className="border-b border-border/50">
                        <CardTitle>Các lựa chọn thay thế (Alternatives)</CardTitle>
                        <CardDescription>Tham khảo các biến thể tiêu đề và mô tả khác</CardDescription>
                      </CardHeader>
                      <CardContent className="pt-6 grid md:grid-cols-2 gap-8">
                        <div>
                          <h4 className="font-bold text-sm mb-3 flex items-center gap-2">
                            <span className="bg-blue-100 text-blue-700 dark:bg-blue-900 dark:text-blue-300 p-1 rounded">T</span>
                            Các lựa chọn Tiêu đề (Title)
                          </h4>
                          <div className="space-y-2">
                            {result.meta_options.title_options.map((t, i) => (
                              <div key={i} className="p-2 text-sm bg-muted/50 rounded border border-border/50 hover:border-blue-300 dark:hover:border-blue-700 transition-colors cursor-default">
                                {t}
                              </div>
                            ))}
                          </div>
                        </div>
                        <div>
                          <h4 className="font-bold text-sm mb-3 flex items-center gap-2">
                            <span className="bg-emerald-100 text-emerald-700 dark:bg-emerald-900 dark:text-emerald-300 p-1 rounded">M</span>
                            Các lựa chọn Mô tả (Description)
                          </h4>
                          <div className="space-y-2">
                            {result.meta_options.description_options.map((d, i) => (
                              <div key={i} className="p-2 text-sm bg-muted/50 rounded border border-border/50 hover:border-emerald-300 dark:hover:border-emerald-700 transition-colors cursor-default">
                                {d}
                              </div>
                            ))}
                          </div>
                        </div>
                      </CardContent>
                    </Card>
                  )}
                  
                  {result.schema_markup && (
                    <div className="md:col-span-2">
                      <JsonViewer data={result.schema_markup} title="Dữ liệu cấu trúc JSON-LD (Schema Markup)" />
                    </div>
                  )}
                </div>
              </TabsContent>
            )}

            {/* Research Tab */}
            {(result?.competitive_analysis ?? job.analysis_data) && (
              <TabsContent value="research" className="mt-0 focus-visible:outline-none focus-visible:ring-0">
                <div className="space-y-6">
                  {(() => {
                    const analysis = result?.competitive_analysis ?? job.analysis_data;
                    if (!analysis) return null;
                    return (
                      <Card className="border-blue-500/10 shadow-sm bg-gradient-to-br from-card to-indigo-50/30 dark:to-indigo-950/10">
                        <CardHeader>
                          <CardTitle>Phân tích Đối thủ (Competitive Analysis)</CardTitle>
                          <CardDescription>Đánh giá thị trường và nội dung hiện tại</CardDescription>
                        </CardHeader>
                        <CardContent className="grid md:grid-cols-2 gap-6">
                          <div className="space-y-4">
                            <div className="bg-background rounded-lg border p-4">
                              <span className="text-xs font-bold text-muted-foreground uppercase block mb-1">Từ khóa cốt lõi</span>
                              <span className="text-lg font-bold text-blue-600 dark:text-blue-400">{analysis.keywords.primary}</span>
                            </div>
                            
                            <div className="bg-background rounded-lg border p-4">
                              <span className="text-xs font-bold text-muted-foreground uppercase block mb-2">Từ khóa phụ trợ</span>
                              <div className="flex flex-wrap gap-1.5">
                                {analysis.keywords.secondary.map((k) => (
                                  <Badge key={k} variant="secondary" className="font-normal">{k}</Badge>
                                ))}
                              </div>
                            </div>
                            
                            <div className="grid grid-cols-2 gap-4">
                              <div className="bg-background rounded-lg border p-4">
                                <span className="text-xs font-bold text-muted-foreground uppercase block mb-1">Mục đích tìm kiếm</span>
                                <span className="font-medium capitalize text-emerald-600 dark:text-emerald-400">{analysis.search_intent}</span>
                              </div>
                              <div className="bg-background rounded-lg border p-4">
                                <span className="text-xs font-bold text-muted-foreground uppercase block mb-1">Độ dài trung bình</span>
                                <span className="font-medium text-amber-600 dark:text-amber-400">{analysis.avg_word_count.toLocaleString()} từ</span>
                              </div>
                            </div>
                          </div>
                          
                          {analysis.content_gaps.length > 0 && (
                            <div className="bg-background rounded-lg border p-4">
                              <h4 className="font-bold mb-3 flex items-center gap-2 text-indigo-700 dark:text-indigo-300">
                                <Zap className="h-4 w-4" />
                                Khoảng trống Nội dung (Gaps)
                              </h4>
                              <div className="space-y-3">
                                {analysis.content_gaps.map((g, i) => (
                                  <div key={i} className="text-sm p-3 bg-muted/40 rounded-md border border-border/50">
                                    <div className="font-bold text-foreground mb-1">{g.topic}</div>
                                    <div className="text-muted-foreground">{g.reason}</div>
                                  </div>
                                ))}
                              </div>
                            </div>
                          )}
                        </CardContent>
                      </Card>
                    );
                  })()}

                  {job.serp_data && (
                    <Card className="border-blue-500/10 shadow-sm">
                      <CardHeader>
                        <CardTitle>Top Kết quả Tìm kiếm (SERP)</CardTitle>
                      </CardHeader>
                      <CardContent>
                        <div className="rounded-md border overflow-hidden">
                          <Table>
                            <TableHeader className="bg-muted/50">
                              <TableRow>
                                <TableHead className="w-[60px] text-center font-bold">TOP</TableHead>
                                <TableHead>Tiêu đề Trang</TableHead>
                                <TableHead>Tên Miền (Domain)</TableHead>
                              </TableRow>
                            </TableHeader>
                            <TableBody>
                              {job.serp_data.results.map((r) => (
                                <TableRow key={r.rank}>
                                  <TableCell className="text-center font-bold text-xl text-muted-foreground/50">
                                    {r.rank}
                                  </TableCell>
                                  <TableCell className="font-medium text-sm">{r.title}</TableCell>
                                  <TableCell className="text-sm text-blue-600 dark:text-blue-400">{r.domain}</TableCell>
                                </TableRow>
                              ))}
                            </TableBody>
                          </Table>
                        </div>
                      </CardContent>
                    </Card>
                  )}
                </div>
              </TabsContent>
            )}

            {/* Keywords Tab */}
            {result?.keyword_analysis && (
              <TabsContent value="keywords" className="mt-0 focus-visible:outline-none focus-visible:ring-0">
                <Card className="border-blue-500/10 shadow-sm">
                  <CardHeader>
                    <div className="flex items-center justify-between">
                      <div>
                        <CardTitle>Mật độ Từ khóa (Keyword Analysis)</CardTitle>
                        <CardDescription>Thống kê số lần xuất hiện và tỷ lệ mật độ</CardDescription>
                      </div>
                      {result.keyword_analysis.keyword_distribution && (
                        <div className="text-right">
                          <div className="text-xs text-muted-foreground font-bold uppercase mb-1">Điểm Phân bổ</div>
                          <div className="text-2xl font-extrabold text-blue-600 dark:text-blue-400">
                            {(result.keyword_analysis.keyword_distribution.distribution_score * 100).toFixed(0)}%
                          </div>
                        </div>
                      )}
                    </div>
                  </CardHeader>
                  <CardContent className="space-y-6">
                    <div className="rounded-xl bg-blue-50 dark:bg-blue-900/20 p-6 border border-blue-100 dark:border-blue-800">
                      <div className="flex flex-col sm:flex-row gap-4 justify-between items-start sm:items-center mb-4">
                        <div>
                          <Badge className="mb-2 bg-blue-600 hover:bg-blue-700 text-white">Từ khóa chính</Badge>
                          <h4 className="text-2xl font-bold text-blue-900 dark:text-blue-100">{result.keyword_analysis.primary.keyword}</h4>
                        </div>
                      </div>
                      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                        <div className="bg-white dark:bg-background p-4 rounded-lg shadow-sm">
                          <div className="text-xs text-muted-foreground uppercase font-bold mb-1">Số lần lặp lại</div>
                          <div className="text-xl font-bold">{result.keyword_analysis.primary.count} lần</div>
                        </div>
                        <div className="bg-white dark:bg-background p-4 rounded-lg shadow-sm">
                          <div className="text-xs text-muted-foreground uppercase font-bold mb-1">Mật độ (Density)</div>
                          <div className={`text-xl font-bold ${(result.keyword_analysis.primary.density * 100) > 3 ? 'text-amber-500' : 'text-emerald-500'}`}>
                            {(result.keyword_analysis.primary.density * 100).toFixed(2)}%
                          </div>
                        </div>
                        <div className="bg-white dark:bg-background p-4 rounded-lg shadow-sm">
                          <div className="text-xs text-muted-foreground uppercase font-bold mb-1">Vị trí xuất hiện</div>
                          <div className="flex gap-1 flex-wrap mt-1">
                            {result.keyword_analysis.primary.locations.map(loc => (
                              <Badge key={loc} variant="outline" className="text-[10px] uppercase">{loc}</Badge>
                            ))}
                          </div>
                        </div>
                      </div>
                    </div>
                    
                    {result.keyword_analysis.secondary.length > 0 && (
                      <div>
                        <h4 className="font-bold text-lg mb-3">Từ khóa LSI / Mở rộng</h4>
                        <div className="rounded-md border overflow-hidden">
                          <Table>
                            <TableHeader className="bg-muted/50">
                              <TableRow>
                                <TableHead>Từ khóa</TableHead>
                                <TableHead className="text-right w-[100px]">Số lần</TableHead>
                                <TableHead className="text-right w-[100px]">Mật độ</TableHead>
                              </TableRow>
                            </TableHeader>
                            <TableBody>
                              {result.keyword_analysis.secondary.map((k) => (
                                <TableRow key={k.keyword}>
                                  <TableCell className="font-medium">{k.keyword}</TableCell>
                                  <TableCell className="text-right tabular-nums">{k.count}</TableCell>
                                  <TableCell className="text-right tabular-nums">
                                    <Badge variant="secondary" className="font-mono">{(k.density * 100).toFixed(2)}%</Badge>
                                  </TableCell>
                                </TableRow>
                              ))}
                            </TableBody>
                          </Table>
                        </div>
                      </div>
                    )}
                  </CardContent>
                </Card>
              </TabsContent>
            )}

            {/* Links Tab */}
            {result?.links && (
              <TabsContent value="links" className="mt-0 focus-visible:outline-none focus-visible:ring-0">
                <div className="grid gap-6">
                  <Card className="border-blue-500/10 shadow-sm">
                    <CardHeader className="bg-indigo-50/50 dark:bg-indigo-900/10 border-b border-border/50">
                      <CardTitle className="text-indigo-800 dark:text-indigo-300">Đề xuất Liên kết Nội bộ (Internal Links)</CardTitle>
                    </CardHeader>
                    <CardContent className="pt-0 p-0">
                      <Table>
                        <TableHeader>
                          <TableRow className="bg-muted/30 hover:bg-muted/30">
                            <TableHead className="w-[200px]">Văn bản Neo (Anchor)</TableHead>
                            <TableHead className="w-[250px]">Gợi ý bài viết đích</TableHead>
                            <TableHead>Ngữ cảnh chèn</TableHead>
                          </TableRow>
                        </TableHeader>
                        <TableBody>
                          {result.links.internal.map((l, i) => (
                            <TableRow key={i}>
                              <TableCell className="font-bold text-indigo-600 dark:text-indigo-400">
                                <span className="underline decoration-indigo-300 dark:decoration-indigo-700 underline-offset-4">{l.anchor_text}</span>
                              </TableCell>
                              <TableCell className="text-sm font-medium">{l.suggested_target_topic}</TableCell>
                              <TableCell className="text-sm text-muted-foreground bg-muted/20 italic">"{l.placement_context}"</TableCell>
                            </TableRow>
                          ))}
                          {result.links.internal.length === 0 && (
                            <TableRow>
                              <TableCell colSpan={3} className="text-center py-8 text-muted-foreground">Không có đề xuất liên kết nội bộ.</TableCell>
                            </TableRow>
                          )}
                        </TableBody>
                      </Table>
                    </CardContent>
                  </Card>
                  
                  <Card className="border-blue-500/10 shadow-sm">
                    <CardHeader className="bg-emerald-50/50 dark:bg-emerald-900/10 border-b border-border/50">
                      <CardTitle className="text-emerald-800 dark:text-emerald-300">Tham khảo Ngoài (External/Outbound Links)</CardTitle>
                    </CardHeader>
                    <CardContent className="pt-0 p-0">
                      <Table>
                        <TableHeader>
                          <TableRow className="bg-muted/30 hover:bg-muted/30">
                            <TableHead className="w-[300px]">Tên nguồn / Tiêu đề</TableHead>
                            <TableHead className="w-[150px]">Vị trí chèn</TableHead>
                            <TableHead>Lý do trích dẫn</TableHead>
                          </TableRow>
                        </TableHeader>
                        <TableBody>
                          {result.links.external.map((l, i) => (
                            <TableRow key={i}>
                              <TableCell className="font-bold text-emerald-600 dark:text-emerald-400 flex items-center gap-2">
                                <Globe className="h-4 w-4 shrink-0 opacity-50" />
                                {l.title}
                              </TableCell>
                              <TableCell>
                                <Badge variant="outline" className="font-normal">{l.placement_section}</Badge>
                              </TableCell>
                              <TableCell className="text-sm text-muted-foreground">{l.authority_reason}</TableCell>
                            </TableRow>
                          ))}
                          {result.links.external.length === 0 && (
                            <TableRow>
                              <TableCell colSpan={3} className="text-center py-8 text-muted-foreground">Không có đề xuất liên kết ngoài.</TableCell>
                            </TableRow>
                          )}
                        </TableBody>
                      </Table>
                    </CardContent>
                  </Card>
                </div>
              </TabsContent>
            )}

            {/* Events Tab */}
            {job.events_data && (
              <TabsContent value="events" className="mt-0 focus-visible:outline-none focus-visible:ring-0">
                <Card className="border-blue-500/10 shadow-sm">
                  <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                      <FileText className="h-5 w-5 text-muted-foreground" />
                      Nhật ký Hoạt động Hệ thống
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="space-y-3 bg-black/5 dark:bg-black/40 rounded-xl p-4 max-h-[600px] overflow-auto font-mono text-sm border border-border/50">
                      {job.events_data.map((ev, i) => (
                        <div key={i} className="flex flex-col sm:flex-row sm:items-start gap-2 border-b border-border/40 pb-3 last:border-0 last:pb-0">
                          <div className="flex items-center gap-2 sm:w-48 shrink-0">
                            <span className="text-xs text-muted-foreground opacity-60">
                              {new Date(ev.timestamp).toLocaleTimeString('vi-VN', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' })}
                            </span>
                            <Badge variant="outline" className="text-[10px] bg-background/50 text-blue-600 dark:text-blue-400 border-blue-200 dark:border-blue-800">
                              {ev.step}
                            </Badge>
                          </div>
                          <div className="flex flex-col">
                            <span className="font-semibold text-foreground/80">{ev.event}</span>
                            <span className="text-muted-foreground text-xs break-words">{ev.detail}</span>
                          </div>
                        </div>
                      ))}
                    </div>
                  </CardContent>
                </Card>
              </TabsContent>
            )}
          </div>
        </Tabs>
      )}

      {/* Token Usage Summary */}
      {job.usage_data && job.usage_data.length > 0 && (
        <Card className="border-blue-500/10 shadow-sm mt-8 overflow-hidden">
          <CardHeader className="bg-slate-50 dark:bg-slate-900/50 border-b border-border/50">
            <CardTitle className="flex items-center gap-2 text-lg">
              <Coins className="h-5 w-5 text-amber-500" />
              Chi phí & Tiêu thụ Token (API)
            </CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            <Table>
              <TableHeader className="bg-muted/20">
                <TableRow className="hover:bg-transparent">
                  <TableHead className="font-semibold">Nhà cung cấp</TableHead>
                  <TableHead className="font-semibold">Model AI</TableHead>
                  <TableHead className="font-semibold">Bước xử lý</TableHead>
                  <TableHead className="text-right font-semibold">Token Đầu vào (Input)</TableHead>
                  <TableHead className="text-right font-semibold">Token Đầu ra (Output)</TableHead>
                  <TableHead className="text-right font-semibold">Chi phí (USD)</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {job.usage_data.map((u, i) => (
                  <TableRow key={i} className="hover:bg-muted/30">
                    <TableCell className="font-medium capitalize">{u.provider}</TableCell>
                    <TableCell>
                      <Badge variant="outline" className="font-mono text-xs font-normal">
                        {u.model}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-sm text-muted-foreground">{u.step}</TableCell>
                    <TableCell className="text-right tabular-nums text-sm">{u.input_tokens.toLocaleString()}</TableCell>
                    <TableCell className="text-right tabular-nums text-sm">{u.output_tokens.toLocaleString()}</TableCell>
                    <TableCell className="text-right tabular-nums font-mono text-xs">${u.cost.toFixed(4)}</TableCell>
                  </TableRow>
                ))}
                <TableRow className="bg-muted/50 hover:bg-muted/50">
                  <TableCell colSpan={3} className="font-bold text-lg uppercase tracking-wider text-right">Tổng cộng</TableCell>
                  <TableCell className="text-right tabular-nums font-bold text-blue-600 dark:text-blue-400">
                    {job.usage_data.reduce((s, u) => s + u.input_tokens, 0).toLocaleString()}
                  </TableCell>
                  <TableCell className="text-right tabular-nums font-bold text-emerald-600 dark:text-emerald-400">
                    {job.usage_data.reduce((s, u) => s + u.output_tokens, 0).toLocaleString()}
                  </TableCell>
                  <TableCell className="text-right tabular-nums font-bold text-lg text-rose-600 dark:text-rose-400">
                    ${job.usage_data.reduce((s, u) => s + u.cost, 0).toFixed(4)}
                  </TableCell>
                </TableRow>
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}

      {/* Loading indicator for active jobs with no data yet */}
      {isActive && !hasContent && !job.events_data && (
        <Card className="border-blue-500/20 shadow-lg shadow-blue-500/5 bg-gradient-to-br from-card to-blue-50/50 dark:to-blue-900/10">
          <CardContent className="flex flex-col items-center justify-center py-20">
            <div className="relative">
              <div className="absolute inset-0 bg-blue-500 rounded-full blur-xl opacity-20 animate-pulse"></div>
              <div className="animate-spin h-12 w-12 border-4 border-blue-600 border-t-transparent rounded-full relative z-10" />
            </div>
            <h3 className="mt-6 font-bold text-xl text-blue-900 dark:text-blue-100">Hệ thống đang xử lý...</h3>
            <p className="mt-2 text-sm text-muted-foreground text-center max-w-sm">
              AI đang làm việc chăm chỉ. Quá trình này có thể tốn từ 2-5 phút tùy theo độ dài và yêu cầu phức tạp của bài viết. Vui lòng giữ trang hoặc quay lại sau!
            </p>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
