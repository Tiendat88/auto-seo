"use client";

import { useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Check, Loader2, X, Circle } from "lucide-react";
import { ScoreGauge } from "@/components/score-gauge";
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
      toast.error(err instanceof Error ? err.message : "Analysis failed");
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
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Brand Monitor</h1>

      <Card>
        <CardHeader><CardTitle>New Analysis</CardTitle></CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <label className="text-sm font-medium">Brand Name</label>
            <Input
              value={brandName}
              onChange={(e) => setBrandName(e.target.value)}
              placeholder="e.g., Notion"
              required
            />
          </div>

          <Tabs value={mode} onValueChange={(v) => setMode(v as "query" | "url")}>
            <TabsList>
              <TabsTrigger value="query">Single Query</TabsTrigger>
              <TabsTrigger value="url">URL Discovery</TabsTrigger>
            </TabsList>
            <TabsContent value="query" className="mt-2">
              <Input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="e.g., best note-taking app"
              />
            </TabsContent>
            <TabsContent value="url" className="mt-2">
              <Input
                type="url"
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                placeholder="https://notion.so"
              />
            </TabsContent>
          </Tabs>

          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <label className="text-sm font-medium">Fetch Mode</label>
              <Tabs value={fetchMode} onValueChange={(v) => setFetchMode(v as "browser" | "api")}>
                <TabsList className="w-full">
                  <TabsTrigger value="api" className="flex-1">API</TabsTrigger>
                  <TabsTrigger value="browser" className="flex-1">Browser</TabsTrigger>
                </TabsList>
              </Tabs>
            </div>
            <div className="space-y-2">
              <label className="text-sm font-medium">Competitors (comma-separated)</label>
              <Input
                value={competitors}
                onChange={(e) => setCompetitors(e.target.value)}
                placeholder="Obsidian, Evernote"
              />
            </div>
          </div>

          <div className="space-y-2">
            <label className="text-sm font-medium">Keywords (comma-separated)</label>
            <Input
              value={keywords}
              onChange={(e) => setKeywords(e.target.value)}
              placeholder="note-taking, productivity, collaboration"
            />
          </div>

          <div className="space-y-2">
            <label className="text-sm font-medium">Custom Prompts (one per line)</label>
            <Textarea
              value={customPrompts}
              onChange={(e) => setCustomPrompts(e.target.value)}
              placeholder="What is the best note-taking app for teams?"
              rows={3}
            />
          </div>

          <div className="flex gap-3">
            <Button onClick={handleAnalyze} disabled={!canSubmit || submitting || streaming}>
              {submitting ? <><Loader2 className="mr-2 h-4 w-4 animate-spin" /> Analyzing...</> : "Analyze"}
            </Button>
            <Button variant="outline" onClick={handleStream} disabled={!canSubmit || submitting || streaming}>
              {streaming ? <><Loader2 className="mr-2 h-4 w-4 animate-spin" /> Streaming...</> : "Analyze (Live)"}
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Streaming Progress */}
      {streaming && Object.keys(stages).length > 0 && (
        <Card>
          <CardHeader><CardTitle>Progress</CardTitle></CardHeader>
          <CardContent className="space-y-3">
            {BRAND_STREAM_STAGES.map((stage) => {
              const state = stages[stage.key];
              if (!state) return null;
              return (
                <div key={stage.key} className="flex items-start gap-3">
                  <div className="mt-0.5">
                    {state.status === "complete" && <Check className="h-4 w-4 text-primary" />}
                    {state.status === "active" && <Loader2 className="h-4 w-4 animate-spin text-primary" />}
                    {state.status === "error" && <X className="h-4 w-4 text-destructive" />}
                    {state.status === "pending" && <Circle className="h-4 w-4 text-muted-foreground" />}
                  </div>
                  <div className="flex-1">
                    <span className="text-sm font-medium">{stage.label}</span>
                    {state.message && (
                      <p className="text-xs text-muted-foreground">{state.message}</p>
                    )}
                    {state.details.length > 0 && (
                      <div className="mt-1 flex flex-wrap gap-1">
                        {state.details.slice(-5).map((d, i) => (
                          <Badge key={i} variant="secondary" className="text-[10px]">{d}</Badge>
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
