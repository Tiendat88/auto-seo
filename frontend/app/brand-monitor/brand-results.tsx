"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import { ScoreGauge } from "@/components/score-gauge";
import type { BrandMonitorResponse } from "@/lib/types";
import { cn } from "@/lib/utils";
import { Trophy, TrendingUp, Heart, Target, Star, BarChart3, Globe, MessageSquare, Cpu, Quote } from "lucide-react";

function sentimentVariant(s: string): "default" | "secondary" | "destructive" {
  if (s === "positive") return "default";
  if (s === "negative") return "destructive";
  return "secondary";
}

function sentimentBadgeColor(s: string) {
  if (s === "positive") return "bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-900/30 dark:text-emerald-400 dark:border-emerald-800";
  if (s === "negative") return "bg-rose-50 text-rose-700 border-rose-200 dark:bg-rose-900/30 dark:text-rose-400 dark:border-rose-800";
  return "bg-slate-50 text-slate-700 border-slate-200 dark:bg-slate-800/50 dark:text-slate-400 dark:border-slate-700";
}

export function BrandResults({ result }: { result: BrandMonitorResponse }) {
  const { scores, aggregate, competitor_rankings, platform_analyses, provider_comparison } = result;

  return (
    <div className="space-y-8">
      {/* Score Cards */}
      {scores && (
        <div className="grid grid-cols-2 gap-4 md:grid-cols-5">
          {([
            ["Độ phủ (Visibility)", scores.visibility_score, <Globe key="visibility" className="h-5 w-5 text-blue-500 mb-2 opacity-80" />],
            ["Thị phần (SoV)", scores.share_of_voice, <BarChart3 key="sov" className="h-5 w-5 text-indigo-500 mb-2 opacity-80" />],
            ["Cảm xúc", scores.sentiment_score, <Heart key="sentiment" className="h-5 w-5 text-rose-500 mb-2 opacity-80" />],
            ["Vị trí", scores.position_score, <Target key="position" className="h-5 w-5 text-amber-500 mb-2 opacity-80" />],
            ["Tổng điểm", scores.overall_score, <Trophy key="overall" className="h-5 w-5 text-emerald-500 mb-2 opacity-80" />],
          ] as const).map(([label, value, icon], index) => (
            <Card key={label} className={`border-t-4 shadow-sm overflow-hidden hover:shadow-md transition-shadow
              ${index === 4 ? 'border-t-emerald-500 bg-emerald-50/10 dark:bg-emerald-950/10' : 
                index === 0 ? 'border-t-blue-500' :
                index === 1 ? 'border-t-indigo-500' :
                index === 2 ? 'border-t-rose-500' : 'border-t-amber-500'}`}>
              <CardContent className="flex flex-col items-center py-6 px-2 text-center">
                {icon}
                <ScoreGauge score={value} size={80} label="" />
                <span className="text-xs font-semibold mt-3 text-muted-foreground uppercase tracking-wider h-8 flex items-center justify-center">{label}</span>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Aggregate Summary */}
        <Card className="lg:col-span-1 shadow-sm border-blue-500/10 bg-gradient-to-b from-card to-blue-50/20 dark:to-blue-900/5">
          <CardHeader className="pb-3 border-b border-border/50">
            <CardTitle className="text-lg flex items-center gap-2 text-blue-800 dark:text-blue-200">
              <TrendingUp className="h-5 w-5" />
              Tóm tắt Tổng quan
            </CardTitle>
          </CardHeader>
          <CardContent className="pt-5 space-y-5 text-sm">
            <div className="space-y-4">
              <div className="flex justify-between items-center pb-2 border-b border-border/50">
                <span className="text-muted-foreground font-medium">Độ phủ nền tảng:</span>
                <span className="font-bold">{aggregate.platforms_mentioning_brand} / {aggregate.total_platforms}</span>
              </div>
              
              <div className="flex justify-between items-center pb-2 border-b border-border/50">
                <span className="text-muted-foreground font-medium">Cảm xúc chung:</span>
                <Badge variant="outline" className={cn("capitalize px-2.5 py-0.5", sentimentBadgeColor(aggregate.overall_sentiment))}>
                  {aggregate.overall_sentiment === "positive" ? "Tích cực" : 
                   aggregate.overall_sentiment === "negative" ? "Tiêu cực" : "Trung lập"}
                </Badge>
              </div>

              {aggregate.avg_brand_position && (
                <div className="flex justify-between items-center pb-2 border-b border-border/50">
                  <span className="text-muted-foreground font-medium">Vị trí trung bình:</span>
                  <span className="font-bold text-amber-600 dark:text-amber-400">#{aggregate.avg_brand_position.toFixed(1)}</span>
                </div>
              )}
            </div>

            {aggregate.brand_recommended_on.length > 0 && (
              <div className="pt-2">
                <span className="text-muted-foreground font-medium flex items-center gap-1 mb-2">
                  <Star className="h-4 w-4 text-amber-500" /> Được đề xuất trên:
                </span>
                <div className="flex flex-wrap gap-1.5">
                  {aggregate.brand_recommended_on.map(p => (
                    <Badge key={p} variant="secondary" className="bg-amber-100 text-amber-800 hover:bg-amber-200 dark:bg-amber-900/40 dark:text-amber-300 border-transparent">
                      {p}
                    </Badge>
                  ))}
                </div>
              </div>
            )}

            {aggregate.top_competitors.length > 0 && (
              <div className="pt-2">
                <span className="text-muted-foreground font-medium flex items-center gap-1 mb-2">
                  <Target className="h-4 w-4 text-rose-500" /> Đối thủ hàng đầu:
                </span>
                <div className="flex flex-wrap gap-1.5">
                  {aggregate.top_competitors.map((c) => (
                    <Badge key={c} variant="outline" className="border-rose-200 text-rose-700 bg-rose-50 dark:border-rose-800 dark:text-rose-400 dark:bg-rose-950/30">
                      {c}
                    </Badge>
                  ))}
                </div>
              </div>
            )}

            {aggregate.common_strengths.length > 0 && (
              <div className="pt-2 bg-emerald-50/50 dark:bg-emerald-950/20 p-3 rounded-lg border border-emerald-100 dark:border-emerald-900/50">
                <span className="font-semibold text-emerald-700 dark:text-emerald-400 block mb-1">Điểm mạnh:</span>
                <span className="text-emerald-600 dark:text-emerald-500 leading-relaxed">{aggregate.common_strengths.join(", ")}</span>
              </div>
            )}

            {aggregate.common_weaknesses.length > 0 && (
              <div className="pt-2 bg-rose-50/50 dark:bg-rose-950/20 p-3 rounded-lg border border-rose-100 dark:border-rose-900/50">
                <span className="font-semibold text-rose-700 dark:text-rose-400 block mb-1">Điểm yếu:</span>
                <span className="text-rose-600 dark:text-rose-500 leading-relaxed">{aggregate.common_weaknesses.join(", ")}</span>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Competitor Rankings */}
        {competitor_rankings.length > 0 && (
          <Card className="lg:col-span-2 shadow-sm border-blue-500/10">
            <CardHeader className="pb-3 border-b border-border/50 bg-muted/20">
              <CardTitle className="text-lg flex items-center gap-2 text-blue-800 dark:text-blue-200">
                <Trophy className="h-5 w-5" />
                Xếp hạng Đối thủ cạnh tranh
              </CardTitle>
            </CardHeader>
            <CardContent className="p-0 overflow-x-auto">
              <Table>
                <TableHeader className="bg-muted/30">
                  <TableRow>
                    <TableHead className="w-12 text-center">Hạng</TableHead>
                    <TableHead>Tên</TableHead>
                    <TableHead className="text-right">Độ phủ</TableHead>
                    <TableHead className="text-right">Thị phần</TableHead>
                    <TableHead className="text-right">Cảm xúc</TableHead>
                    <TableHead className="text-right">Vị trí</TableHead>
                    <TableHead className="text-right">Lượt nhắc</TableHead>
                    <TableHead className="text-right font-bold text-blue-700 dark:text-blue-400 bg-blue-50/50 dark:bg-blue-900/10">Tổng điểm</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {competitor_rankings
                    .sort((a, b) => b.overall_score - a.overall_score)
                    .map((c, i) => (
                      <TableRow key={c.name} className={cn(c.is_own && "bg-blue-50/40 dark:bg-blue-900/20 hover:bg-blue-50/80 dark:hover:bg-blue-900/30", "transition-colors")}>
                        <TableCell className="text-center font-medium">
                          {i === 0 ? <span className="flex items-center justify-center h-6 w-6 rounded-full bg-amber-100 text-amber-700 font-bold mx-auto text-xs">1</span> :
                           i === 1 ? <span className="flex items-center justify-center h-6 w-6 rounded-full bg-slate-100 text-slate-700 font-bold mx-auto text-xs">2</span> :
                           i === 2 ? <span className="flex items-center justify-center h-6 w-6 rounded-full bg-orange-100 text-orange-800 font-bold mx-auto text-xs">3</span> :
                           <span className="text-muted-foreground">{i + 1}</span>}
                        </TableCell>
                        <TableCell className="font-semibold flex items-center">
                          {c.name}
                          {c.is_own && <Badge variant="default" className="ml-2 text-[10px] bg-blue-600 hover:bg-blue-700 text-white">Bạn</Badge>}
                        </TableCell>
                        <TableCell className="text-right tabular-nums text-muted-foreground">{c.visibility_score.toFixed(0)}</TableCell>
                        <TableCell className="text-right tabular-nums text-muted-foreground">{c.share_of_voice.toFixed(0)}</TableCell>
                        <TableCell className="text-right tabular-nums">
                          <span className={c.sentiment_score >= 60 ? "text-emerald-600 dark:text-emerald-400" : c.sentiment_score <= 40 ? "text-rose-600 dark:text-rose-400" : "text-muted-foreground"}>
                            {c.sentiment_score.toFixed(0)}
                          </span>
                        </TableCell>
                        <TableCell className="text-right tabular-nums text-muted-foreground">{c.position_score.toFixed(0)}</TableCell>
                        <TableCell className="text-right tabular-nums text-muted-foreground">{c.mention_count}</TableCell>
                        <TableCell className="text-right tabular-nums font-bold text-lg bg-blue-50/30 dark:bg-blue-900/5">
                          {c.overall_score.toFixed(0)}
                        </TableCell>
                      </TableRow>
                    ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        )}
      </div>

      {/* Provider Comparison */}
      {provider_comparison.length > 0 && (
        <Card className="shadow-sm border-blue-500/10">
          <CardHeader className="pb-3 border-b border-border/50">
            <CardTitle className="text-lg flex items-center gap-2 text-blue-800 dark:text-blue-200">
              <Cpu className="h-5 w-5" />
              So sánh theo Mô hình AI
            </CardTitle>
          </CardHeader>
          <CardContent className="p-0 overflow-auto">
            {(() => {
              const providers = provider_comparison[0]?.providers.map((p) => p.provider) ?? [];
              return (
                <Table>
                  <TableHeader className="bg-muted/20">
                    <TableRow>
                      <TableHead className="font-semibold bg-muted/10 w-48">Đối thủ</TableHead>
                      {providers.map((p) => <TableHead key={p} className="text-center font-semibold capitalize">{p}</TableHead>)}
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {provider_comparison.map((row) => (
                      <TableRow key={row.competitor_name} className="hover:bg-muted/50">
                        <TableCell className="font-medium bg-muted/5">{row.competitor_name}</TableCell>
                        {row.providers.map((p) => (
                          <TableCell key={p.provider} className="text-center p-2">
                            <div className="flex flex-col items-center justify-center h-full min-h-12 border border-transparent hover:border-border rounded-md transition-colors p-1">
                              {p.brand_mentioned ? (
                                <Badge variant="outline" className={cn("text-[11px] px-2 py-0.5", sentimentBadgeColor(p.sentiment))}>
                                  {p.position ? `Top ${p.position}` : "Có mặt"}
                                </Badge>
                              ) : (
                                <span className="text-xs text-muted-foreground opacity-50 block w-full text-center">-</span>
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
        <Card className="shadow-sm border-blue-500/10 bg-gradient-to-b from-card to-blue-50/10 dark:to-blue-900/5">
          <CardHeader className="pb-4 border-b border-border/50">
            <CardTitle className="text-lg flex items-center gap-2 text-blue-800 dark:text-blue-200">
              <MessageSquare className="h-5 w-5" />
              Chi tiết từng Mô hình ({platform_analyses.length})
            </CardTitle>
          </CardHeader>
          <CardContent className="pt-6 space-y-4">
            {platform_analyses.map((pa, i) => (
              <details key={i} className="group rounded-xl border border-border/60 bg-card overflow-hidden shadow-sm transition-all open:ring-1 open:ring-blue-500/20">
                <summary className="flex cursor-pointer items-center justify-between p-4 hover:bg-muted/50 transition-colors">
                  <div className="flex flex-wrap items-center gap-3">
                    <span className="font-bold text-base capitalize min-w-[120px]">{pa.platform}</span>
                    
                    <Badge variant={pa.brand_mentioned ? "default" : "secondary"} className={cn(
                      pa.brand_mentioned ? "bg-blue-600 hover:bg-blue-700 text-white" : ""
                    )}>
                      {pa.brand_mentioned ? "Được đề cập" : "Không đề cập"}
                    </Badge>
                    
                    {pa.brand_position && (
                      <Badge variant="outline" className="border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-800/50 dark:bg-amber-950/30 dark:text-amber-400">
                        Top {pa.brand_position}
                      </Badge>
                    )}
                    
                    {pa.brand_mentioned && (
                      <Badge variant="outline" className={cn("capitalize", sentimentBadgeColor(pa.sentiment.overall))}>
                        {pa.sentiment.overall === "positive" ? "Tích cực" : pa.sentiment.overall === "negative" ? "Tiêu cực" : "Trung lập"}
                      </Badge>
                    )}
                  </div>
                  <div className="text-muted-foreground opacity-50 group-open:rotate-180 transition-transform">
                    <svg width="15" height="15" viewBox="0 0 15 15" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M3.13523 6.15803C3.3241 5.95657 3.64052 5.94637 3.84197 6.13523L7.5 9.56464L11.158 6.13523C11.3595 5.94637 11.6759 5.95657 11.8648 6.15803C12.0536 6.35949 12.0434 6.67591 11.842 6.86477L7.84197 10.6148C7.64964 10.7951 7.35036 10.7951 7.15803 10.6148L3.15803 6.86477C2.95657 6.67591 2.94637 6.35949 3.13523 6.15803Z" fill="currentColor" fillRule="evenodd" clipRule="evenodd"></path></svg>
                  </div>
                </summary>
                
                <div className="p-5 border-t border-border/50 bg-muted/10 space-y-5">
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div className="space-y-1">
                      <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Bối cảnh:</span>
                      <p className="capitalize font-medium">{pa.mention_context.replace(/_/g, " ")}</p>
                    </div>
                    {pa.brand_mentioned && (
                      <div className="space-y-1">
                        <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Lý do đánh giá:</span> 
                        <p className="text-sm">{pa.sentiment.reasoning}</p>
                      </div>
                    )}
                  </div>

                  {pa.sentiment.aspects.length > 0 && (
                    <div className="space-y-2">
                      <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Chi tiết Khía cạnh:</span>
                      <div className="flex flex-wrap gap-2">
                        {pa.sentiment.aspects.map((a, j) => (
                          <div key={j} className={cn(
                            "px-3 py-1.5 rounded-md border text-sm",
                            sentimentBadgeColor(a.sentiment)
                          )}>
                            <span className="font-semibold">{a.feature}:</span> {a.detail}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {pa.relevant_quotes.length > 0 && (
                    <div className="space-y-2 pt-2 border-t border-border/50">
                      <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground flex items-center gap-1.5">
                        <Quote className="h-3 w-3" /> Trích dẫn từ AI:
                      </span>
                      <div className="space-y-2">
                        {pa.relevant_quotes.map((q, j) => (
                          <div key={j} className="text-sm text-foreground bg-background border border-border p-3 rounded-lg relative pl-8">
                            <Quote className="h-4 w-4 text-muted-foreground absolute left-2.5 top-3 opacity-30" />
                            <p className="italic">{q}</p>
                          </div>
                        ))}
                      </div>
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
