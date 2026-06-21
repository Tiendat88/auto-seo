"use client";

import { use, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { getBrandAnalysis } from "@/lib/api";
import type { BrandMonitorResponse } from "@/lib/types";
import { BrandResults } from "../brand-results";
import { ChevronLeft } from "lucide-react";

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
      .catch((err) => setError(err instanceof Error ? err.message : "Tải dữ liệu thất bại"))
      .finally(() => setLoading(false));
  }, [analysisId]);

  if (loading) {
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

  if (error || !result) {
    return (
      <div className="space-y-6 max-w-7xl mx-auto pb-10">
        <div className="bg-destructive/10 text-destructive p-4 rounded-md font-medium">
          {error ?? "Không tìm thấy dữ liệu phân tích"}
        </div>
        <Button variant="outline" onClick={() => router.push("/brand-monitor/history")}>
          <ChevronLeft className="mr-2 h-4 w-4" /> Quay lại Lịch sử
        </Button>
      </div>
    );
  }

  return (
    <div className="space-y-6 max-w-7xl mx-auto pb-10">
      <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-4">
        <div>
          <h1 className="text-3xl font-extrabold tracking-tight text-blue-900 dark:text-blue-100 flex items-center gap-2">
            Báo cáo: <span className="text-blue-600 dark:text-blue-400">{result.brand_name}</span>
          </h1>
          <p className="text-muted-foreground mt-1">
            {result.query ? `Truy vấn: "${result.query}"` : `Đã phân tích ${result.queries.length} kịch bản`}
          </p>
        </div>
        <Button 
          variant="ghost" 
          onClick={() => router.push("/brand-monitor/history")}
          className="text-muted-foreground hover:text-blue-600 hover:bg-blue-50 dark:hover:bg-blue-900/20 transition-colors"
        >
          <ChevronLeft className="mr-1 h-4 w-4" />
          Quay lại Lịch sử
        </Button>
      </div>
      <BrandResults result={result} />
    </div>
  );
}
