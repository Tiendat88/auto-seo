"use client";

import { useState } from "react";
import { Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { fanout } from "@/lib/api";
import { SUB_QUERY_TYPE_LABELS } from "@/lib/constants";
import type { FanOutResponse, SubQuery } from "@/lib/types";
import { toast } from "sonner";

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
      toast.error(err instanceof Error ? err.message : "Fan-out failed");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Query Fan-Out</h1>

      <Card>
        <CardHeader><CardTitle>Generate Sub-Queries</CardTitle></CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="space-y-2">
              <label className="text-sm font-medium">Target Query</label>
              <Input
                value={targetQuery}
                onChange={(e) => setTargetQuery(e.target.value)}
                placeholder="e.g., best CRM for startups"
                required
              />
            </div>

            <details className="rounded-md border p-3">
              <summary className="cursor-pointer text-sm font-medium text-muted-foreground hover:text-foreground">
                Content for Gap Analysis (optional)
              </summary>
              <div className="mt-3 space-y-4">
                <div className="space-y-2">
                  <label className="text-sm font-medium">Content URL</label>
                  <Input
                    type="url"
                    value={contentUrl}
                    onChange={(e) => setContentUrl(e.target.value)}
                    placeholder="https://example.com/article"
                  />
                </div>
                <div className="space-y-2">
                  <label className="text-sm font-medium">Or paste content</label>
                  <Textarea
                    value={existingContent}
                    onChange={(e) => setExistingContent(e.target.value)}
                    placeholder="Paste existing content..."
                    rows={4}
                  />
                </div>
              </div>
            </details>

            <Button type="submit" disabled={submitting || !targetQuery.trim()}>
              {submitting ? <><Loader2 className="mr-2 h-4 w-4 animate-spin" /> Generating...</> : "Generate Sub-Queries"}
            </Button>
          </form>
        </CardContent>
      </Card>

      {result && (
        <div className="space-y-6">
          <div className="flex items-center gap-4 text-sm text-muted-foreground">
            <span>{result.total_sub_queries} sub-queries generated</span>
            <span>Model: {result.model_used}</span>
          </div>

          {/* Gap Summary */}
          {result.gap_summary && (
            <Card>
              <CardHeader><CardTitle>Gap Analysis</CardTitle></CardHeader>
              <CardContent className="space-y-3">
                <div className="flex items-center justify-between text-sm">
                  <span>Coverage</span>
                  <span className="font-mono">
                    {result.gap_summary.covered} / {result.gap_summary.total} ({result.gap_summary.coverage_percent}%)
                  </span>
                </div>
                <Progress value={result.gap_summary.coverage_percent} className="h-3" />
                <div className="flex flex-wrap gap-2">
                  {result.gap_summary.covered_types.map((t) => (
                    <Badge key={t} variant="default">{SUB_QUERY_TYPE_LABELS[t] ?? t}</Badge>
                  ))}
                  {result.gap_summary.missing_types.map((t) => (
                    <Badge key={t} variant="destructive">{SUB_QUERY_TYPE_LABELS[t] ?? t}</Badge>
                  ))}
                </div>
              </CardContent>
            </Card>
          )}

          {/* Sub-queries grouped by type */}
          <div className="grid gap-4 md:grid-cols-2">
            {Object.entries(groupByType(result.sub_queries)).map(([type, queries]) => (
              <Card key={type}>
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm flex items-center justify-between">
                    {SUB_QUERY_TYPE_LABELS[type] ?? type}
                    <Badge variant="outline">{queries.length}</Badge>
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <ul className="space-y-2">
                    {queries.map((q, i) => (
                      <li key={i} className="flex items-start justify-between gap-2 text-sm">
                        <span>{q.query}</span>
                        <div className="flex shrink-0 items-center gap-1">
                          {q.covered !== null && (
                            <Badge variant={q.covered ? "default" : "destructive"} className="text-[10px]">
                              {q.covered ? "Covered" : "Missing"}
                            </Badge>
                          )}
                          {q.similarity_score !== null && (
                            <span className="text-xs text-muted-foreground font-mono">
                              {(q.similarity_score * 100).toFixed(0)}%
                            </span>
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
