"use client";

import { use, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { getBrandAnalysis } from "@/lib/api";
import type { BrandMonitorResponse } from "@/lib/types";
import { BrandResults } from "../brand-results";

export default function BrandAnalysisDetailPage({
  params,
}: {
  params: Promise<{ analysisId: string }>;
}) {
  const { analysisId } = use(params);
  const router = useRouter();
  const [result, setResult] = useState<BrandMonitorResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getBrandAnalysis(analysisId)
      .then(setResult)
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load"))
      .finally(() => setLoading(false));
  }, [analysisId]);

  if (loading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  if (error || !result) {
    return (
      <div className="space-y-4">
        <p className="text-destructive">{error ?? "Analysis not found"}</p>
        <Button variant="outline" onClick={() => router.push("/brand-monitor/history")}>
          Back to History
        </Button>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">{result.brand_name}</h1>
          <p className="text-sm text-muted-foreground">
            {result.query || `${result.queries.length} prompts analyzed`}
          </p>
        </div>
        <Button variant="outline" onClick={() => router.push("/brand-monitor/history")}>
          Back
        </Button>
      </div>
      <BrandResults result={result} />
    </div>
  );
}
