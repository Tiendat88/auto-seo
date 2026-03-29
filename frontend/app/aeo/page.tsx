"use client";

import { useState } from "react";
import { Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ScoreGauge } from "@/components/score-gauge";
import { analyzeAeo } from "@/lib/api";
import type { AeoResponse } from "@/lib/types";
import { toast } from "sonner";

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
      toast.error(err instanceof Error ? err.message : "Analysis failed");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">AEO Content Analyzer</h1>

      <Card>
        <CardHeader><CardTitle>Analyze Content</CardTitle></CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-4">
            <Tabs value={inputType} onValueChange={(v) => setInputType(v as "url" | "text")}>
              <TabsList>
                <TabsTrigger value="url">URL</TabsTrigger>
                <TabsTrigger value="text">Text</TabsTrigger>
              </TabsList>
              <TabsContent value="url" className="mt-2">
                <Input
                  type="url"
                  value={inputType === "url" ? inputValue : ""}
                  onChange={(e) => setInputValue(e.target.value)}
                  placeholder="https://example.com/article"
                />
              </TabsContent>
              <TabsContent value="text" className="mt-2">
                <Textarea
                  value={inputType === "text" ? inputValue : ""}
                  onChange={(e) => setInputValue(e.target.value)}
                  placeholder="Paste your article content here..."
                  rows={8}
                />
              </TabsContent>
            </Tabs>
            <Button type="submit" disabled={submitting || !inputValue.trim()}>
              {submitting ? <><Loader2 className="mr-2 h-4 w-4 animate-spin" /> Analyzing...</> : "Analyze"}
            </Button>
          </form>
        </CardContent>
      </Card>

      {result && (
        <div className="space-y-6">
          <div className="flex items-center gap-6">
            <ScoreGauge score={result.aeo_score} size={120} />
            <div>
              <Badge variant={result.aeo_score >= 60 ? "default" : result.aeo_score >= 40 ? "secondary" : "destructive"} className="text-lg px-3 py-1">
                {result.band}
              </Badge>
              <p className="mt-1 text-sm text-muted-foreground">AEO Readiness Score</p>
            </div>
          </div>

          <div className="grid gap-4 md:grid-cols-3">
            {result.checks.map((check) => (
              <Card key={check.check_id}>
                <CardHeader className="pb-2">
                  <div className="flex items-center justify-between">
                    <CardTitle className="text-sm">{check.name}</CardTitle>
                    <Badge variant={check.passed ? "default" : "destructive"}>
                      {check.passed ? "Pass" : "Fail"}
                    </Badge>
                  </div>
                </CardHeader>
                <CardContent className="space-y-3">
                  <div className="flex items-center justify-between text-sm">
                    <span className="text-muted-foreground">Score</span>
                    <span className="font-mono">{check.score} / {check.max_score}</span>
                  </div>
                  <Progress value={(check.score / check.max_score) * 100} className="h-2" />
                  {check.recommendation && (
                    <p className="text-xs text-muted-foreground">{check.recommendation}</p>
                  )}
                  {Object.entries(check.details).length > 0 && (
                    <details className="text-xs">
                      <summary className="cursor-pointer text-muted-foreground hover:text-foreground">
                        Details
                      </summary>
                      <div className="mt-2 space-y-1">
                        {Object.entries(check.details).map(([k, v]) => (
                          <div key={k}>
                            <span className="text-muted-foreground">{k}:</span>{" "}
                            <span>{typeof v === "object" ? JSON.stringify(v) : String(v)}</span>
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
