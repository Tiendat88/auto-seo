"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import { ScoreGauge } from "@/components/score-gauge";
import type { BrandMonitorResponse } from "@/lib/types";
import { cn } from "@/lib/utils";

function sentimentVariant(s: string): "default" | "secondary" | "destructive" {
  if (s === "positive") return "default";
  if (s === "negative") return "destructive";
  return "secondary";
}

export function BrandResults({ result }: { result: BrandMonitorResponse }) {
  const { scores, aggregate, competitor_rankings, platform_analyses, provider_comparison } = result;

  return (
    <div className="space-y-6">
      {/* Score Cards */}
      {scores && (
        <div className="grid grid-cols-2 gap-4 md:grid-cols-5">
          {([
            ["Visibility", scores.visibility_score],
            ["Share of Voice", scores.share_of_voice],
            ["Sentiment", scores.sentiment_score],
            ["Position", scores.position_score],
            ["Overall", scores.overall_score],
          ] as const).map(([label, value]) => (
            <Card key={label}>
              <CardContent className="flex flex-col items-center py-4">
                <ScoreGauge score={value} size={80} label={label} />
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* Aggregate Summary */}
      <Card>
        <CardHeader><CardTitle>Summary</CardTitle></CardHeader>
        <CardContent className="space-y-3 text-sm">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <span className="text-muted-foreground">Brand mentioned:</span>{" "}
              {aggregate.platforms_mentioning_brand} / {aggregate.total_platforms} platforms
            </div>
            <div>
              <span className="text-muted-foreground">Sentiment:</span>{" "}
              <Badge variant={sentimentVariant(aggregate.overall_sentiment)} className="capitalize">
                {aggregate.overall_sentiment}
              </Badge>
            </div>
            {aggregate.avg_brand_position && (
              <div>
                <span className="text-muted-foreground">Avg position:</span>{" "}
                #{aggregate.avg_brand_position.toFixed(1)}
              </div>
            )}
            <div>
              <span className="text-muted-foreground">Recommended on:</span>{" "}
              {aggregate.brand_recommended_on.length > 0
                ? aggregate.brand_recommended_on.join(", ")
                : "None"}
            </div>
          </div>
          {aggregate.top_competitors.length > 0 && (
            <div>
              <span className="text-muted-foreground">Top competitors:</span>{" "}
              {aggregate.top_competitors.map((c) => (
                <Badge key={c} variant="outline" className="mr-1">{c}</Badge>
              ))}
            </div>
          )}
          {aggregate.common_strengths.length > 0 && (
            <div>
              <span className="text-muted-foreground">Strengths:</span>{" "}
              <span className="text-primary">{aggregate.common_strengths.join(", ")}</span>
            </div>
          )}
          {aggregate.common_weaknesses.length > 0 && (
            <div>
              <span className="text-muted-foreground">Weaknesses:</span>{" "}
              <span className="text-destructive">{aggregate.common_weaknesses.join(", ")}</span>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Competitor Rankings */}
      {competitor_rankings.length > 0 && (
        <Card>
          <CardHeader><CardTitle>Competitor Rankings</CardTitle></CardHeader>
          <CardContent>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>#</TableHead>
                  <TableHead>Name</TableHead>
                  <TableHead className="text-right">Visibility</TableHead>
                  <TableHead className="text-right">SoV</TableHead>
                  <TableHead className="text-right">Sentiment</TableHead>
                  <TableHead className="text-right">Position</TableHead>
                  <TableHead className="text-right">Overall</TableHead>
                  <TableHead className="text-right">Mentions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {competitor_rankings
                  .sort((a, b) => b.overall_score - a.overall_score)
                  .map((c, i) => (
                    <TableRow key={c.name} className={cn(c.is_own && "bg-primary/5")}>
                      <TableCell className="tabular-nums">{i + 1}</TableCell>
                      <TableCell className="font-medium">
                        {c.name}
                        {c.is_own && <Badge variant="outline" className="ml-2 text-[10px]">You</Badge>}
                      </TableCell>
                      <TableCell className="text-right tabular-nums">{c.visibility_score.toFixed(0)}</TableCell>
                      <TableCell className="text-right tabular-nums">{c.share_of_voice.toFixed(0)}</TableCell>
                      <TableCell className="text-right tabular-nums">{c.sentiment_score.toFixed(0)}</TableCell>
                      <TableCell className="text-right tabular-nums">{c.position_score.toFixed(0)}</TableCell>
                      <TableCell className="text-right tabular-nums font-medium">{c.overall_score.toFixed(0)}</TableCell>
                      <TableCell className="text-right tabular-nums">{c.mention_count}</TableCell>
                    </TableRow>
                  ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}

      {/* Provider Comparison */}
      {provider_comparison.length > 0 && (
        <Card>
          <CardHeader><CardTitle>Provider Comparison</CardTitle></CardHeader>
          <CardContent className="overflow-auto">
            {(() => {
              const providers = provider_comparison[0]?.providers.map((p) => p.provider) ?? [];
              return (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Competitor</TableHead>
                      {providers.map((p) => <TableHead key={p} className="text-center capitalize">{p}</TableHead>)}
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {provider_comparison.map((row) => (
                      <TableRow key={row.competitor_name}>
                        <TableCell className="font-medium">{row.competitor_name}</TableCell>
                        {row.providers.map((p) => (
                          <TableCell key={p.provider} className="text-center">
                            <div className="flex flex-col items-center gap-0.5">
                              {p.brand_mentioned ? (
                                <Badge variant={sentimentVariant(p.sentiment)} className="text-[10px]">
                                  {p.position ? `#${p.position}` : "Yes"}
                                </Badge>
                              ) : (
                                <span className="text-xs text-muted-foreground">-</span>
                              )}
                            </div>
                          </TableCell>
                        ))}
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              );
            })()}
          </CardContent>
        </Card>
      )}

      {/* Platform Analyses */}
      {platform_analyses.length > 0 && (
        <Card>
          <CardHeader><CardTitle>Platform Details ({platform_analyses.length})</CardTitle></CardHeader>
          <CardContent className="space-y-4">
            {platform_analyses.map((pa, i) => (
              <details key={i} className="rounded-md border p-3">
                <summary className="flex cursor-pointer items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className="font-medium capitalize">{pa.platform}</span>
                    <Badge variant={pa.brand_mentioned ? "default" : "secondary"}>
                      {pa.brand_mentioned ? "Mentioned" : "Not mentioned"}
                    </Badge>
                    {pa.brand_position && (
                      <Badge variant="outline">#{pa.brand_position}</Badge>
                    )}
                    <Badge variant={sentimentVariant(pa.sentiment.overall)} className="capitalize">
                      {pa.sentiment.overall}
                    </Badge>
                  </div>
                </summary>
                <div className="mt-3 space-y-2 text-sm">
                  <div>
                    <span className="text-muted-foreground">Context:</span>{" "}
                    <span className="capitalize">{pa.mention_context.replace(/_/g, " ")}</span>
                  </div>
                  <div>
                    <span className="text-muted-foreground">Reasoning:</span> {pa.sentiment.reasoning}
                  </div>
                  {pa.sentiment.aspects.length > 0 && (
                    <div>
                      <span className="text-muted-foreground">Aspects:</span>
                      <div className="mt-1 flex flex-wrap gap-1">
                        {pa.sentiment.aspects.map((a, j) => (
                          <Badge key={j} variant={sentimentVariant(a.sentiment)}>
                            {a.feature}: {a.detail}
                          </Badge>
                        ))}
                      </div>
                    </div>
                  )}
                  {pa.relevant_quotes.length > 0 && (
                    <div>
                      <span className="text-muted-foreground">Quotes:</span>
                      <ul className="mt-1 list-disc ml-4">
                        {pa.relevant_quotes.map((q, j) => (
                          <li key={j} className="text-muted-foreground italic">&quot;{q}&quot;</li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              </details>
            ))}
          </CardContent>
        </Card>
      )}
    </div>
  );
}
