"use client";

import { useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Check, Loader2, X, Circle, Search, Globe, Play, Activity } from "lucide-react";

import { analyzeBrand, streamBrandAnalysis, type SSEEvent } from "@/lib/api";
import { BRAND_STREAM_STAGES } from "@/lib/constants";
import type { BrandMonitorRequest, BrandMonitorResponse, BrandStreamStage } from "@/lib/types";
import { toast } from "sonner";
import { BrandResults } from "./brand-results";

type StageStatus = "pending" | "active" | "complete" | "error";

interface StageState {
  status: StageStatus;
  message: string;
  details: string[];
}

export default function BrandMonitorPage() {
  const [brandName, setBrandName] = useState("");
  const [mode, setMode] = useState<"query" | "url">("query");
  const [query, setQuery] = useState("");
  const [url, setUrl] = useState("");
  const [fetchMode, setFetchMode] = useState<"browser" | "api">("api");
  const [competitors, setCompetitors] = useState("");
  const [keywords, setKeywords] = useState("");
  const [customPrompts, setCustomPrompts] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [streaming, setStreaming] = useState(false);
  const [result, setResult] = useState<BrandMonitorResponse | null>(null);
  const [stages, setStages] = useState<Record<string, StageState>>({});
  const controllerRef = useRef<AbortController | null>(null);

  const buildRequest = (): BrandMonitorRequest => ({
    brand_name: brandName,
    query: mode === "query" ? query : undefined,
    url: mode === "url" ? url : undefined,
    fetch_mode: fetchMode,
    competitors: competitors ? competitors.split(",").map((s) => s.trim()).filter(Boolean) : [],
    keywords: keywords ? keywords.split(",").map((s) => s.trim()).filter(Boolean) : [],
    custom_prompts: customPrompts ? customPrompts.split("\n").filter(Boolean) : [],
  });

  const handleAnalyze = async () => {
    setSubmitting(true);
    setResult(null);
    try {
      const res = await analyzeBrand(buildRequest());
      setResult(res);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Quá trình phân tích thất bại");
    } finally {
      setSubmitting(false);
    }
  };

  const handleStream = () => {
    setStreaming(true);
    setResult(null);
    const initialStages: Record<string, StageState> = {};
    for (const s of BRAND_STREAM_STAGES) {
      initialStages[s.key] = { status: "pending", message: "", details: [] };
    }
    setStages(initialStages);

    const controller = streamBrandAnalysis(
      buildRequest(),
      (event: SSEEvent) => {
        const stage = event.data.stage as BrandStreamStage | undefined;

        if (event.event === "stage-start" && stage) {
          setStages((prev) => ({
            ...prev,
            [stage]: { ...prev[stage], status: "active", message: event.data.message as string ?? "" },
          }));
        } else if (event.event === "complete") {
          const finalResult = event.data.result as unknown as BrandMonitorResponse;
          setResult(finalResult);
          setStreaming(false);
          setStages((prev) => {
            const updated = { ...prev };
            for (const key of Object.keys(updated)) {
              if (updated[key].status === "active") {
                updated[key] = { ...updated[key], status: "complete" };
              }
            }
            return updated;
          });
        } else if (event.event === "error") {
          if (stage) {
            setStages((prev) => ({
              ...prev,
              [stage]: { ...prev[stage], status: "error", message: event.data.message as string ?? "Error" },
            }));
          }
        } else if (stage) {
          // Other events - add details
          setStages((prev) => {
            const current = prev[stage] ?? { status: "active", message: "", details: [] };
            const detail = event.data.message as string ??
              event.data.name as string ??
              event.data.prompt as string ??
              JSON.stringify(event.data);
            return {
              ...prev,
              [stage]: {
                ...current,
                status: current.status === "pending" ? "active" : current.status,
                details: [...current.details, detail],
              },
            };
          });
          // Mark previous stages as complete
          if (stage) {
            const stageIdx = BRAND_STREAM_STAGES.findIndex((s) => s.key === stage);
            if (stageIdx > 0) {
              setStages((prev) => {
                const updated = { ...prev };
                for (let i = 0; i < stageIdx; i++) {
                  const key = BRAND_STREAM_STAGES[i].key;
                  if (updated[key]?.status === "active") {
                    updated[key] = { ...updated[key], status: "complete" };
                  }
                }
                return updated;
              });
            }
          }
        }
      },
      (error) => {
        toast.error(error.message);
        setStreaming(false);
      },
      () => setStreaming(false),
    );
    controllerRef.current = controller;
  };

  const canSubmit = brandName.length > 0 && (mode === "query" ? query.length > 0 : url.length > 0);

  return (
    <div className="space-y-6 max-w-7xl mx-auto pb-10">
      <div className="mb-8">
        <h1 className="text-3xl font-extrabold tracking-tight text-blue-900 dark:text-blue-100">
          Giám sát Thương hiệu
        </h1>
        <p className="text-muted-foreground mt-1">
          Theo dõi độ phủ, định vị cạnh tranh và cảm xúc thương hiệu trên không gian mạng
        </p>
      </div>

      <Card className="border-blue-500/10 shadow-sm overflow-hidden bg-card/50 backdrop-blur-sm relative">
        <div className="absolute top-0 left-0 w-1 h-full bg-blue-500"></div>
        <CardHeader className="bg-blue-50/50 dark:bg-blue-900/10 border-b border-blue-500/10">
          <CardTitle className="text-blue-800 dark:text-blue-200">Khởi tạo Phân tích mới</CardTitle>
          <CardDescription>Nhập thông tin thương hiệu để bắt đầu quét dữ liệu AI</CardDescription>
        </CardHeader>
        <CardContent className="p-6 md:p-8 space-y-8">
          <div className="space-y-2">
            <label className="text-sm font-semibold text-foreground uppercase tracking-wider">Tên Thương hiệu</label>
            <Input
              value={brandName}
              onChange={(e) => setBrandName(e.target.value)}
              placeholder="Ví dụ: Notion, Apple, VinFast"
              required
              className="text-lg py-6 focus-visible:ring-blue-500"
            />
          </div>

          <div className="p-4 rounded-xl border border-blue-100 dark:border-blue-900/50 bg-blue-50/30 dark:bg-blue-900/10 space-y-4">
            <label className="text-sm font-semibold text-foreground uppercase tracking-wider block">Nguồn & Phương thức quét</label>
            <Tabs value={mode} onValueChange={(v) => setMode(v as "query" | "url")} className="w-full">
              <TabsList className="w-full grid grid-cols-2 mb-4">
                <TabsTrigger value="query" className="data-[state=active]:bg-white dark:data-[state=active]:bg-blue-950 data-[state=active]:text-blue-700 dark:data-[state=active]:text-blue-400">
                  <Search className="h-4 w-4 mr-2" />
                  Truy vấn đơn
                </TabsTrigger>
                <TabsTrigger value="url" className="data-[state=active]:bg-white dark:data-[state=active]:bg-blue-950 data-[state=active]:text-blue-700 dark:data-[state=active]:text-blue-400">
                  <Globe className="h-4 w-4 mr-2" />
                  Khám phá qua URL
                </TabsTrigger>
              </TabsList>
              <TabsContent value="query" className="mt-0 space-y-2">
                <p className="text-xs text-muted-foreground mb-2">Quét kết quả dựa trên một câu hỏi hoặc từ khóa cụ thể mà người dùng thường tìm kiếm.</p>
                <Input
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="Ví dụ: ứng dụng ghi chú tốt nhất hiện nay"
                  className="focus-visible:ring-blue-500"
                />
              </TabsContent>
              <TabsContent value="url" className="mt-0 space-y-2">
                <p className="text-xs text-muted-foreground mb-2">Hệ thống sẽ tự động đọc trang web để tìm ra đối thủ cạnh tranh và tạo ra hàng chục kịch bản câu hỏi để quét tự động.</p>
                <Input
                  type="url"
                  value={url}
                  onChange={(e) => setUrl(e.target.value)}
                  placeholder="https://notion.so"
                  className="focus-visible:ring-blue-500"
                />
              </TabsContent>
            </Tabs>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div className="space-y-2">
              <label className="text-sm font-semibold text-foreground uppercase tracking-wider block">Đối thủ cạnh tranh <span className="text-muted-foreground lowercase font-normal">(cách nhau dấu phẩy)</span></label>
              <Input
                value={competitors}
                onChange={(e) => setCompetitors(e.target.value)}
                placeholder="Obsidian, Evernote"
                className="focus-visible:ring-blue-500"
              />
            </div>
            <div className="space-y-2">
              <label className="text-sm font-semibold text-foreground uppercase tracking-wider block">Chế độ lấy dữ liệu</label>
              <Tabs value={fetchMode} onValueChange={(v) => setFetchMode(v as "browser" | "api")}>
                <TabsList className="w-full">
                  <TabsTrigger value="api" className="flex-1">Trực tiếp qua API</TabsTrigger>
                  <TabsTrigger value="browser" className="flex-1">Giả lập Trình duyệt</TabsTrigger>
                </TabsList>
              </Tabs>
            </div>
          </div>

          <div className="space-y-2">
            <label className="text-sm font-semibold text-foreground uppercase tracking-wider block">Từ khóa mục tiêu <span className="text-muted-foreground lowercase font-normal">(cách nhau dấu phẩy)</span></label>
            <Input
              value={keywords}
              onChange={(e) => setKeywords(e.target.value)}
              placeholder="ghi chú, làm việc nhóm, năng suất"
              className="focus-visible:ring-blue-500"
            />
          </div>

          <div className="space-y-2">
            <label className="text-sm font-semibold text-foreground uppercase tracking-wider block">Kịch bản tuỳ chỉnh <span className="text-muted-foreground lowercase font-normal">(mỗi câu hỏi một dòng)</span></label>
            <Textarea
              value={customPrompts}
              onChange={(e) => setCustomPrompts(e.target.value)}
              placeholder="Nền tảng ghi chú nào phù hợp cho sinh viên?&#10;So sánh Notion và Evernote về tính năng AI."
              rows={3}
              className="resize-y focus-visible:ring-blue-500"
            />
          </div>

          <div className="flex flex-col sm:flex-row gap-4 pt-4 border-t border-border/50">
            <Button 
              size="lg"
              onClick={handleStream} 
              disabled={!canSubmit || submitting || streaming}
              className="flex-1 bg-blue-600 hover:bg-blue-700 text-white shadow-md shadow-blue-500/20"
            >
              {streaming ? (
                <><Loader2 className="mr-2 h-5 w-5 animate-spin" /> Đang Live Stream...</>
              ) : (
                <><Activity className="mr-2 h-5 w-5" /> Phân tích trực tiếp (Live Stream)</>
              )}
            </Button>
            <Button 
              variant="outline" 
              size="lg"
              onClick={handleAnalyze} 
              disabled={!canSubmit || submitting || streaming}
              className="flex-1 border-blue-200 text-blue-700 hover:bg-blue-50 dark:border-blue-800 dark:text-blue-300 dark:hover:bg-blue-900/20"
            >
              {submitting ? (
                <><Loader2 className="mr-2 h-5 w-5 animate-spin" /> Đang chạy ngầm...</>
              ) : (
                <><Play className="mr-2 h-5 w-5" /> Phân tích ngầm (Đợi kết quả)</>
              )}
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Streaming Progress */}
      {streaming && Object.keys(stages).length > 0 && (
        <Card className="border-blue-500/10 shadow-sm border-l-4 border-l-blue-500">
          <CardHeader className="pb-2">
            <CardTitle className="text-lg flex items-center gap-2">
              <Activity className="h-5 w-5 text-blue-500 animate-pulse" />
              Tiến trình xử lý
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4 pt-4">
            {BRAND_STREAM_STAGES.map((stage) => {
              const state = stages[stage.key];
              if (!state) return null;
              return (
                <div key={stage.key} className="flex items-start gap-3 bg-muted/30 p-3 rounded-lg border border-border/50">
                  <div className="mt-0.5 shrink-0 bg-background rounded-full p-1 border">
                    {state.status === "complete" && <Check className="h-4 w-4 text-emerald-500" />}
                    {state.status === "active" && <Loader2 className="h-4 w-4 animate-spin text-blue-500" />}
                    {state.status === "error" && <X className="h-4 w-4 text-destructive" />}
                    {state.status === "pending" && <Circle className="h-4 w-4 text-muted-foreground opacity-30" />}
                  </div>
                  <div className="flex-1 min-w-0">
                    <span className={`text-sm font-bold ${state.status === 'active' ? 'text-blue-600 dark:text-blue-400' : ''}`}>{stage.label}</span>
                    {state.message && (
                      <p className="text-sm text-muted-foreground mt-0.5">{state.message}</p>
                    )}
                    {state.details.length > 0 && (
                      <div className="mt-2 flex flex-wrap gap-1.5">
                        {state.details.slice(-5).map((d, i) => (
                          <Badge key={i} variant="outline" className="text-[10px] bg-background text-muted-foreground truncate max-w-full">
                            {d}
                          </Badge>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              );
            })}
          </CardContent>
        </Card>
      )}

      {/* Results */}
      {result && <BrandResults result={result} />}
    </div>
  );
}
