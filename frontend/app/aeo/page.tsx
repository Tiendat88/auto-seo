"use client";

import { useState } from "react";
import { Loader2, Link as LinkIcon, Type, Play, CheckCircle2, AlertCircle, Info } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ScoreGauge } from "@/components/score-gauge";
import { analyzeAeo } from "@/lib/api";
import type { AeoResponse } from "@/lib/types";
import { toast } from "sonner";
import { cn } from "@/lib/utils";
import { AEO_CHECK_NAME_VI } from "@/lib/constants";

export default function AeoPage() {
  const [inputType, setInputType] = useState<"url" | "text">("url");
  const [inputValue, setInputValue] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<AeoResponse | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!inputValue.trim()) return;
    setSubmitting(true);
    setResult(null);
    try {
      const res = await analyzeAeo({ input_type: inputType, input_value: inputValue });
      setResult(res);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Quá trình phân tích thất bại");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="space-y-6 max-w-7xl mx-auto pb-10">
      <div className="mb-8">
        <h1 className="text-3xl font-extrabold tracking-tight text-blue-900 dark:text-blue-100 flex items-center gap-2">
          Phân tích Nội dung AEO
        </h1>
        <p className="text-muted-foreground mt-1">
          Đánh giá mức độ tối ưu của nội dung cho Answer Engine Optimization (AEO)
        </p>
      </div>

      <Card className="border-blue-500/10 shadow-sm overflow-hidden bg-card/50 backdrop-blur-sm relative">
        <div className="absolute top-0 left-0 w-1 h-full bg-blue-500"></div>
        <CardHeader className="bg-blue-50/50 dark:bg-blue-900/10 border-b border-blue-500/10">
          <CardTitle className="text-blue-800 dark:text-blue-200">Kiểm tra Nội dung</CardTitle>
          <CardDescription>Nhập đường dẫn URL hoặc nội dung văn bản để hệ thống đánh giá</CardDescription>
        </CardHeader>
        <CardContent className="p-6 md:p-8">
          <form onSubmit={handleSubmit} className="space-y-6">
            <div className="p-4 rounded-xl border border-blue-100 dark:border-blue-900/50 bg-blue-50/30 dark:bg-blue-900/10">
              <Tabs value={inputType} onValueChange={(v) => setInputType(v as "url" | "text")} className="w-full">
                <TabsList className="w-full grid grid-cols-2 mb-4">
                  <TabsTrigger value="url" className="data-[state=active]:bg-white dark:data-[state=active]:bg-blue-950 data-[state=active]:text-blue-700 dark:data-[state=active]:text-blue-400">
                    <LinkIcon className="mr-2 h-4 w-4" /> Đường dẫn URL
                  </TabsTrigger>
                  <TabsTrigger value="text" className="data-[state=active]:bg-white dark:data-[state=active]:bg-blue-950 data-[state=active]:text-blue-700 dark:data-[state=active]:text-blue-400">
                    <Type className="mr-2 h-4 w-4" /> Văn bản (Văn bản thuần)
                  </TabsTrigger>
                </TabsList>
                <TabsContent value="url" className="mt-0">
                  <Input
                    type="url"
                    value={inputType === "url" ? inputValue : ""}
                    onChange={(e) => setInputValue(e.target.value)}
                    placeholder="Ví dụ: https://example.com/bai-viet-cua-ban"
                    className="py-6 text-lg focus-visible:ring-blue-500"
                  />
                  <p className="text-xs text-muted-foreground mt-2">Hệ thống sẽ tải nội dung từ trang web này để phân tích.</p>
                </TabsContent>
                <TabsContent value="text" className="mt-0">
                  <Textarea
                    value={inputType === "text" ? inputValue : ""}
                    onChange={(e) => setInputValue(e.target.value)}
                    placeholder="Dán toàn bộ nội dung bài viết của bạn vào đây..."
                    rows={8}
                    className="resize-y focus-visible:ring-blue-500"
                  />
                  <p className="text-xs text-muted-foreground mt-2">Sao chép và dán nội dung văn bản hoặc HTML để phân tích trực tiếp.</p>
                </TabsContent>
              </Tabs>
            </div>
            
            <Button 
              type="submit" 
              disabled={submitting || !inputValue.trim()}
              size="lg"
              className="w-full sm:w-auto bg-blue-600 hover:bg-blue-700 text-white shadow-md shadow-blue-500/20"
            >
              {submitting ? (
                <><Loader2 className="mr-2 h-5 w-5 animate-spin" /> Đang kiểm tra...</>
              ) : (
                <><Play className="mr-2 h-5 w-5" /> Bắt đầu Kiểm tra</>
              )}
            </Button>
          </form>
        </CardContent>
      </Card>

      {result && (
        <div className="space-y-6 animate-in fade-in slide-in-from-bottom-4 duration-500">
          <Card className="border-t-4 border-t-emerald-500 shadow-sm bg-gradient-to-br from-card to-emerald-50/10 dark:to-emerald-950/10">
            <CardContent className="p-8">
              <div className="flex flex-col sm:flex-row items-center gap-8 justify-center sm:justify-start">
                <ScoreGauge score={result.aeo_score} size={140} />
                <div className="text-center sm:text-left">
                  <h3 className="text-xl font-bold text-foreground mb-2">Điểm Chuẩn AEO (Readiness Score)</h3>
                  <Badge 
                    variant="outline" 
                    className={cn(
                      "text-lg px-4 py-1.5 font-bold uppercase tracking-wider mb-3",
                      result.aeo_score >= 80 ? "bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-900/30 dark:text-emerald-400 dark:border-emerald-800" :
                      result.aeo_score >= 60 ? "bg-blue-50 text-blue-700 border-blue-200 dark:bg-blue-900/30 dark:text-blue-400 dark:border-blue-800" :
                      result.aeo_score >= 40 ? "bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-900/30 dark:text-amber-400 dark:border-amber-800" :
                      "bg-rose-50 text-rose-700 border-rose-200 dark:bg-rose-900/30 dark:text-rose-400 dark:border-rose-800"
                    )}
                  >
                    Hạng {result.band}
                  </Badge>
                  <p className="text-sm text-muted-foreground max-w-md leading-relaxed">
                    Đánh giá mức độ nội dung của bạn sẵn sàng để được các mô hình AI (như ChatGPT, Gemini, Perplexity) trích xuất làm câu trả lời trực tiếp.
                  </p>
                </div>
              </div>
            </CardContent>
          </Card>

          <h3 className="text-xl font-bold text-blue-900 dark:text-blue-100 flex items-center gap-2 pt-4">
            <CheckCircle2 className="h-5 w-5 text-blue-500" /> Tiêu chí Đánh giá
          </h3>
          
          <div className="grid gap-6 md:grid-cols-3">
            {result.checks.map((check) => (
              <Card key={check.check_id} className={cn(
                "shadow-sm transition-all hover:shadow-md border-l-4",
                check.passed ? "border-l-emerald-500" : "border-l-rose-500"
              )}>
                <CardHeader className="pb-3 bg-muted/20 border-b border-border/50">
                  <div className="flex items-center justify-between">
                    <CardTitle className="text-base font-semibold">{AEO_CHECK_NAME_VI[check.name] ?? check.name}</CardTitle>
                    <Badge 
                      variant="outline" 
                      className={check.passed 
                        ? "bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-900/30 dark:text-emerald-400 dark:border-emerald-800" 
                        : "bg-rose-50 text-rose-700 border-rose-200 dark:bg-rose-900/30 dark:text-rose-400 dark:border-rose-800"
                      }
                    >
                      {check.passed ? "Đạt" : "Chưa đạt"}
                    </Badge>
                  </div>
                </CardHeader>
                <CardContent className="pt-4 space-y-4">
                  <div className="space-y-1.5">
                    <div className="flex items-center justify-between text-sm">
                      <span className="text-muted-foreground font-medium">Điểm số</span>
                      <span className="font-bold">{check.score} <span className="text-muted-foreground font-normal">/ {check.max_score}</span></span>
                    </div>
                    <Progress 
                      value={(check.score / check.max_score) * 100} 
                      className="h-2"
                      indicatorClassName={check.passed ? "bg-emerald-500" : "bg-amber-500"}
                    />
                  </div>
                  
                  {check.recommendation && (
                    <div className="bg-amber-50/50 dark:bg-amber-950/20 p-3 rounded-lg border border-amber-100 dark:border-amber-900/50 flex gap-2 items-start mt-2">
                      <AlertCircle className="h-4 w-4 text-amber-600 dark:text-amber-500 mt-0.5 shrink-0" />
                      <p className="text-sm text-amber-800 dark:text-amber-400 leading-snug">{check.recommendation}</p>
                    </div>
                  )}
                  
                  {Object.entries(check.details).length > 0 && (
                    <details className="group border border-border/60 rounded-md overflow-hidden">
                      <summary className="cursor-pointer text-sm font-medium bg-muted/30 px-3 py-2 flex items-center gap-2 hover:bg-muted/50 transition-colors">
                        <Info className="h-4 w-4 text-blue-500" />
                        Chi tiết dữ liệu
                      </summary>
                      <div className="p-3 bg-background space-y-2 text-sm border-t border-border/60 max-h-40 overflow-y-auto">
                        {Object.entries(check.details).map(([k, v]) => (
                          <div key={k} className="flex flex-col pb-2 border-b border-border/40 last:border-0 last:pb-0">
                            <span className="text-muted-foreground text-xs uppercase tracking-wider">{k}</span>
                            <span className="font-mono text-xs break-all mt-0.5">{typeof v === "object" ? JSON.stringify(v) : String(v)}</span>
                          </div>
                        ))}
                      </div>
                    </details>
                  )}
                </CardContent>
              </Card>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
