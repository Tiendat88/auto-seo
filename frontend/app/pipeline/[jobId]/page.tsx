"use client";

import { use, useCallback, useState } from "react";
import { useRouter } from "next/navigation";
import { AlertCircle, Download, RotateCcw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
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
  a.download = `${topic.toLowerCase().replace(/\s+/g, "-").slice(0, 50)}.md`;
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
      toast.success("Job resumed");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to resume");
    } finally {
      setResuming(false);
    }
  };

  if (isLoading || !job) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-8 w-96" />
        <Skeleton className="h-12 w-full" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  const result = job.result;
  const hasContent = result || job.article_data;
  const quality = result?.quality ?? job.quality_data;
  const review = result?.review ?? job.review_data;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold">{job.topic}</h1>
          <div className="mt-1 flex items-center gap-3 text-sm text-muted-foreground">
            <StatusBadge status={job.status} currentStep={job.current_step} />
            <span>{job.target_word_count.toLocaleString()} words</span>
            <span className="uppercase">{job.language}</span>
            {job.revision_count > 0 && <span>{job.revision_count} revisions</span>}
          </div>
        </div>
        <div className="flex gap-2">
          {hasContent && job.status === "completed" && (
            <Button
              variant="outline"
              size="sm"
              onClick={() => downloadMarkdown(result?.content ?? job.article_data!, job.topic)}
            >
              <Download className="mr-2 h-4 w-4" />
              Export
            </Button>
          )}
          <Button variant="outline" size="sm" onClick={() => router.push("/pipeline")}>
            Back
          </Button>
        </div>
      </div>

      {/* Pipeline Stepper */}
      {job.status !== "pending" && (
        <Card>
          <CardContent className="py-4">
            <PipelineStepper status={job.status} currentStep={job.current_step} />
          </CardContent>
        </Card>
      )}

      {/* Error Banner */}
      {job.status === "failed" && job.error && (
        <Card className="border-destructive">
          <CardContent className="flex items-start gap-3 py-4">
            <AlertCircle className="mt-0.5 h-5 w-5 text-destructive shrink-0" />
            <div className="flex-1">
              <p className="font-medium text-destructive">Pipeline failed</p>
              <p className="text-sm text-muted-foreground mt-1">{job.error}</p>
            </div>
            <Button size="sm" onClick={handleResume} disabled={resuming}>
              <RotateCcw className="mr-2 h-4 w-4" />
              {resuming ? "Resuming..." : "Resume"}
            </Button>
          </CardContent>
        </Card>
      )}

      {/* Artifact Tabs */}
      {(hasContent || quality || job.events_data) && (
        <Tabs defaultValue={hasContent ? "article" : "events"}>
          <TabsList className="flex-wrap">
            {hasContent && <TabsTrigger value="article">Article</TabsTrigger>}
            {(result?.outline ?? job.outline_data) && <TabsTrigger value="outline">Outline</TabsTrigger>}
            {quality && <TabsTrigger value="quality">Quality</TabsTrigger>}
            {result?.seo_metadata && <TabsTrigger value="seo">SEO</TabsTrigger>}
            {(result?.competitive_analysis ?? job.analysis_data) && (
              <TabsTrigger value="research">Research</TabsTrigger>
            )}
            {result?.keyword_analysis && <TabsTrigger value="keywords">Keywords</TabsTrigger>}
            {result?.links && <TabsTrigger value="links">Links</TabsTrigger>}
            {job.events_data && <TabsTrigger value="events">Events</TabsTrigger>}
          </TabsList>

          {/* Article Tab */}
          {hasContent && (
            <TabsContent value="article">
              <Card>
                <CardContent className="pt-6">
                  <MarkdownRenderer
                    content={articleToMarkdown(result?.content ?? job.article_data!)}
                  />
                </CardContent>
              </Card>
            </TabsContent>
          )}

          {/* Outline Tab */}
          {(result?.outline ?? job.outline_data) && (
            <TabsContent value="outline">
              <Card>
                <CardContent className="pt-6 space-y-4">
                  {(() => {
                    const outline = result?.outline ?? job.outline_data!;
                    return (
                      <>
                        <h2 className="text-xl font-bold">{outline.h1}</h2>
                        <div className="space-y-3">
                          {outline.headings.map((h, i) => (
                            <div
                              key={i}
                              className="border-l-2 border-border pl-3"
                              style={{ marginLeft: h.level === "h3" ? 16 : h.level === "h2" ? 0 : 0 }}
                            >
                              <div className="flex items-center gap-2">
                                <Badge variant="outline" className="text-[10px]">{h.level}</Badge>
                                <span className="font-medium">{h.text}</span>
                                <span className="text-xs text-muted-foreground">~{h.target_word_count}w</span>
                              </div>
                              {h.key_points.length > 0 && (
                                <ul className="mt-1 ml-4 list-disc text-sm text-muted-foreground">
                                  {h.key_points.map((p, j) => <li key={j}>{p}</li>)}
                                </ul>
                              )}
                            </div>
                          ))}
                        </div>
                        {outline.faq_questions.length > 0 && (
                          <div>
                            <h3 className="font-medium mb-2">FAQ Questions</h3>
                            <ul className="list-disc ml-4 text-sm">
                              {outline.faq_questions.map((q, i) => <li key={i}>{q}</li>)}
                            </ul>
                          </div>
                        )}
                        {outline.brief && (
                          <div className="rounded-md bg-muted/50 p-4 space-y-2">
                            <h3 className="font-medium">Article Brief</h3>
                            <div className="grid grid-cols-2 gap-2 text-sm">
                              <div><span className="text-muted-foreground">Audience:</span> {outline.brief.target_audience}</div>
                              <div><span className="text-muted-foreground">Tone:</span> {outline.brief.tone}</div>
                              <div><span className="text-muted-foreground">Angle:</span> {outline.brief.angle}</div>
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
            <TabsContent value="quality">
              <div className="grid gap-6 md:grid-cols-[200px_1fr]">
                <Card>
                  <CardContent className="flex flex-col items-center justify-center py-6">
                    <ScoreGauge score={quality.overall * 100} label="Overall" />
                    <Badge variant={quality.passes_threshold ? "default" : "destructive"} className="mt-2">
                      {quality.passes_threshold ? "Passes" : "Below threshold"}
                    </Badge>
                  </CardContent>
                </Card>
                <Card>
                  <CardHeader><CardTitle>Score Dimensions</CardTitle></CardHeader>
                  <CardContent className="space-y-3">
                    {quality.dimensions.map((d) => (
                      <ScoreDimensionBar key={d.name} name={d.name} score={d.score} feedback={d.feedback} />
                    ))}
                  </CardContent>
                </Card>
              </div>
              {review && (
                <Card className="mt-6">
                  <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                      Review
                      <Badge variant={review.passed ? "default" : "destructive"}>
                        {review.passed ? "Passed" : "Needs revision"}
                      </Badge>
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-4">
                    <p className="text-sm">{review.summary}</p>
                    {review.issues.length > 0 && (
                      <Table>
                        <TableHeader>
                          <TableRow>
                            <TableHead>Severity</TableHead>
                            <TableHead>Category</TableHead>
                            <TableHead>Issue</TableHead>
                            <TableHead>Suggestion</TableHead>
                          </TableRow>
                        </TableHeader>
                        <TableBody>
                          {review.issues.map((issue, i) => (
                            <TableRow key={i}>
                              <TableCell>
                                <Badge variant={issue.severity === "critical" ? "destructive" : "outline"} className="capitalize">
                                  {issue.severity}
                                </Badge>
                              </TableCell>
                              <TableCell>{issue.category}</TableCell>
                              <TableCell className="text-sm">{issue.description}</TableCell>
                              <TableCell className="text-sm text-muted-foreground">{issue.suggestion}</TableCell>
                            </TableRow>
                          ))}
                        </TableBody>
                      </Table>
                    )}
                    {review.strengths.length > 0 && (
                      <div>
                        <h4 className="font-medium mb-1">Strengths</h4>
                        <ul className="list-disc ml-4 text-sm text-muted-foreground">
                          {review.strengths.map((s, i) => <li key={i}>{s}</li>)}
                        </ul>
                      </div>
                    )}
                  </CardContent>
                </Card>
              )}
            </TabsContent>
          )}

          {/* SEO Tab */}
          {result?.seo_metadata && (
            <TabsContent value="seo">
              <div className="space-y-6">
                <Card>
                  <CardHeader><CardTitle>SEO Metadata</CardTitle></CardHeader>
                  <CardContent className="space-y-3 text-sm">
                    <div><span className="text-muted-foreground">Title:</span> {result.seo_metadata.title_tag}</div>
                    <div><span className="text-muted-foreground">Description:</span> {result.seo_metadata.meta_description}</div>
                    <div><span className="text-muted-foreground">Primary Keyword:</span> {result.seo_metadata.primary_keyword}</div>
                    <div><span className="text-muted-foreground">Slug:</span> <code className="bg-muted px-1 rounded">{result.seo_metadata.slug}</code></div>
                  </CardContent>
                </Card>
                {result.meta_options && (
                  <Card>
                    <CardHeader><CardTitle>Meta Options</CardTitle></CardHeader>
                    <CardContent className="space-y-4">
                      <div>
                        <h4 className="text-sm font-medium mb-2">Title Options</h4>
                        <ol className="list-decimal ml-4 text-sm space-y-1">
                          {result.meta_options.title_options.map((t, i) => <li key={i}>{t}</li>)}
                        </ol>
                      </div>
                      <div>
                        <h4 className="text-sm font-medium mb-2">Description Options</h4>
                        <ol className="list-decimal ml-4 text-sm space-y-1">
                          {result.meta_options.description_options.map((d, i) => <li key={i}>{d}</li>)}
                        </ol>
                      </div>
                    </CardContent>
                  </Card>
                )}
                {result.schema_markup && (
                  <JsonViewer data={result.schema_markup} title="JSON-LD Schema Markup" />
                )}
              </div>
            </TabsContent>
          )}

          {/* Research Tab */}
          {(result?.competitive_analysis ?? job.analysis_data) && (
            <TabsContent value="research">
              <div className="space-y-6">
                {job.serp_data && (
                  <Card>
                    <CardHeader><CardTitle>SERP Results</CardTitle></CardHeader>
                    <CardContent>
                      <Table>
                        <TableHeader>
                          <TableRow>
                            <TableHead className="w-12">#</TableHead>
                            <TableHead>Title</TableHead>
                            <TableHead>Domain</TableHead>
                          </TableRow>
                        </TableHeader>
                        <TableBody>
                          {job.serp_data.results.map((r) => (
                            <TableRow key={r.rank}>
                              <TableCell className="tabular-nums">{r.rank}</TableCell>
                              <TableCell className="text-sm">{r.title}</TableCell>
                              <TableCell className="text-sm text-muted-foreground">{r.domain}</TableCell>
                            </TableRow>
                          ))}
                        </TableBody>
                      </Table>
                    </CardContent>
                  </Card>
                )}
                {(() => {
                  const analysis = result?.competitive_analysis ?? job.analysis_data;
                  if (!analysis) return null;
                  return (
                    <Card>
                      <CardHeader><CardTitle>Competitive Analysis</CardTitle></CardHeader>
                      <CardContent className="space-y-4 text-sm">
                        <div>
                          <span className="text-muted-foreground">Primary keyword:</span>{" "}
                          <Badge variant="outline">{analysis.keywords.primary}</Badge>
                        </div>
                        <div className="flex flex-wrap gap-1">
                          <span className="text-muted-foreground">Secondary:</span>
                          {analysis.keywords.secondary.map((k) => (
                            <Badge key={k} variant="secondary">{k}</Badge>
                          ))}
                        </div>
                        <div>
                          <span className="text-muted-foreground">Search intent:</span>{" "}
                          <Badge className="capitalize">{analysis.search_intent}</Badge>
                        </div>
                        <div>
                          <span className="text-muted-foreground">Avg word count:</span>{" "}
                          {analysis.avg_word_count.toLocaleString()}
                        </div>
                        {analysis.content_gaps.length > 0 && (
                          <div>
                            <h4 className="font-medium mb-1">Content Gaps</h4>
                            <ul className="list-disc ml-4 space-y-1">
                              {analysis.content_gaps.map((g, i) => (
                                <li key={i}><strong>{g.topic}</strong> — {g.reason}</li>
                              ))}
                            </ul>
                          </div>
                        )}
                      </CardContent>
                    </Card>
                  );
                })()}
              </div>
            </TabsContent>
          )}

          {/* Keywords Tab */}
          {result?.keyword_analysis && (
            <TabsContent value="keywords">
              <Card>
                <CardHeader><CardTitle>Keyword Analysis</CardTitle></CardHeader>
                <CardContent className="space-y-4">
                  <div className="rounded-md bg-muted/50 p-4">
                    <h4 className="font-medium">{result.keyword_analysis.primary.keyword}</h4>
                    <div className="mt-1 grid grid-cols-3 gap-4 text-sm">
                      <div><span className="text-muted-foreground">Count:</span> {result.keyword_analysis.primary.count}</div>
                      <div><span className="text-muted-foreground">Density:</span> {(result.keyword_analysis.primary.density * 100).toFixed(1)}%</div>
                      <div><span className="text-muted-foreground">Locations:</span> {result.keyword_analysis.primary.locations.join(", ")}</div>
                    </div>
                  </div>
                  {result.keyword_analysis.secondary.length > 0 && (
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead>Keyword</TableHead>
                          <TableHead className="text-right">Count</TableHead>
                          <TableHead className="text-right">Density</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {result.keyword_analysis.secondary.map((k) => (
                          <TableRow key={k.keyword}>
                            <TableCell>{k.keyword}</TableCell>
                            <TableCell className="text-right tabular-nums">{k.count}</TableCell>
                            <TableCell className="text-right tabular-nums">{(k.density * 100).toFixed(1)}%</TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  )}
                  {result.keyword_analysis.keyword_distribution && (
                    <div>
                      <h4 className="font-medium mb-2">
                        Distribution Score: {(result.keyword_analysis.keyword_distribution.distribution_score * 100).toFixed(0)}%
                      </h4>
                    </div>
                  )}
                </CardContent>
              </Card>
            </TabsContent>
          )}

          {/* Links Tab */}
          {result?.links && (
            <TabsContent value="links">
              <div className="space-y-6">
                <Card>
                  <CardHeader><CardTitle>Internal Link Suggestions</CardTitle></CardHeader>
                  <CardContent>
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead>Anchor Text</TableHead>
                          <TableHead>Target Topic</TableHead>
                          <TableHead>Context</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {result.links.internal.map((l, i) => (
                          <TableRow key={i}>
                            <TableCell className="font-medium">{l.anchor_text}</TableCell>
                            <TableCell>{l.suggested_target_topic}</TableCell>
                            <TableCell className="text-sm text-muted-foreground">{l.placement_context}</TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </CardContent>
                </Card>
                <Card>
                  <CardHeader><CardTitle>External References</CardTitle></CardHeader>
                  <CardContent>
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead>Title</TableHead>
                          <TableHead>Section</TableHead>
                          <TableHead>Reason</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {result.links.external.map((l, i) => (
                          <TableRow key={i}>
                            <TableCell className="font-medium">{l.title}</TableCell>
                            <TableCell>{l.placement_section}</TableCell>
                            <TableCell className="text-sm text-muted-foreground">{l.authority_reason}</TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </CardContent>
                </Card>
              </div>
            </TabsContent>
          )}

          {/* Events Tab */}
          {job.events_data && (
            <TabsContent value="events">
              <Card>
                <CardHeader><CardTitle>Pipeline Events</CardTitle></CardHeader>
                <CardContent>
                  <div className="space-y-2 max-h-96 overflow-auto">
                    {job.events_data.map((ev, i) => (
                      <div key={i} className="flex items-start gap-3 text-sm border-b border-border pb-2 last:border-0">
                        <span className="text-xs text-muted-foreground shrink-0 tabular-nums">
                          {new Date(ev.timestamp).toLocaleTimeString()}
                        </span>
                        <Badge variant="outline" className="shrink-0 text-[10px]">{ev.step}</Badge>
                        <span className="text-muted-foreground">{ev.event}</span>
                        <span className="flex-1 truncate">{ev.detail}</span>
                      </div>
                    ))}
                  </div>
                </CardContent>
              </Card>
            </TabsContent>
          )}
        </Tabs>
      )}

      {/* Token Usage */}
      {job.usage_data && job.usage_data.length > 0 && (
        <Card>
          <CardHeader><CardTitle>Token Usage</CardTitle></CardHeader>
          <CardContent>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Provider</TableHead>
                  <TableHead>Model</TableHead>
                  <TableHead>Step</TableHead>
                  <TableHead className="text-right">Input</TableHead>
                  <TableHead className="text-right">Output</TableHead>
                  <TableHead className="text-right">Cost</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {job.usage_data.map((u, i) => (
                  <TableRow key={i}>
                    <TableCell>{u.provider}</TableCell>
                    <TableCell className="text-sm text-muted-foreground">{u.model}</TableCell>
                    <TableCell>{u.step}</TableCell>
                    <TableCell className="text-right tabular-nums">{u.input_tokens.toLocaleString()}</TableCell>
                    <TableCell className="text-right tabular-nums">{u.output_tokens.toLocaleString()}</TableCell>
                    <TableCell className="text-right tabular-nums">${u.cost.toFixed(4)}</TableCell>
                  </TableRow>
                ))}
                <TableRow className="font-medium">
                  <TableCell colSpan={3}>Total</TableCell>
                  <TableCell className="text-right tabular-nums">
                    {job.usage_data.reduce((s, u) => s + u.input_tokens, 0).toLocaleString()}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    {job.usage_data.reduce((s, u) => s + u.output_tokens, 0).toLocaleString()}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
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
        <Card>
          <CardContent className="flex items-center justify-center py-12">
            <div className="text-center space-y-2">
              <div className="animate-spin h-8 w-8 border-4 border-primary border-t-transparent rounded-full mx-auto" />
              <p className="text-sm text-muted-foreground">Pipeline is running...</p>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
