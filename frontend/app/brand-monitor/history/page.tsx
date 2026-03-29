"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import { Skeleton } from "@/components/ui/skeleton";
import { listBrandAnalyses } from "@/lib/api";
import type { BrandAnalysisSummary } from "@/lib/types";
import { cn } from "@/lib/utils";

const PAGE_SIZE = 20;

export default function BrandHistoryPage() {
  const [analyses, setAnalyses] = useState<BrandAnalysisSummary[]>([]);
  const [total, setTotal] = useState(0);
  const [brandFilter, setBrandFilter] = useState("");
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    listBrandAnalyses({
      brand_name: brandFilter || undefined,
      limit: PAGE_SIZE,
      offset,
    })
      .then((res) => {
        setAnalyses(res.analyses);
        setTotal(res.total);
      })
      .finally(() => setLoading(false));
  }, [brandFilter, offset]);

  const totalPages = Math.ceil(total / PAGE_SIZE);
  const currentPage = Math.floor(offset / PAGE_SIZE) + 1;

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold">Brand Analysis History</h1>

      <div className="flex items-center gap-4">
        <Input
          value={brandFilter}
          onChange={(e) => { setBrandFilter(e.target.value); setOffset(0); }}
          placeholder="Filter by brand name..."
          className="max-w-xs"
        />
        <span className="text-sm text-muted-foreground">{total} total</span>
      </div>

      <div className="rounded-md border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Brand</TableHead>
              <TableHead>Query / URL</TableHead>
              <TableHead className="text-right">Overall</TableHead>
              <TableHead className="text-right">Visibility</TableHead>
              <TableHead>Model</TableHead>
              <TableHead className="text-right">Prompts</TableHead>
              <TableHead>Date</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {loading ? (
              Array.from({ length: 5 }).map((_, i) => (
                <TableRow key={i}>
                  {Array.from({ length: 7 }).map((_, j) => (
                    <TableCell key={j}><Skeleton className="h-4 w-full" /></TableCell>
                  ))}
                </TableRow>
              ))
            ) : analyses.length === 0 ? (
              <TableRow>
                <TableCell colSpan={7} className="h-24 text-center text-muted-foreground">
                  No analyses found.
                </TableCell>
              </TableRow>
            ) : (
              analyses.map((a) => (
                <TableRow key={a.id} className="cursor-pointer hover:bg-muted/50">
                  <TableCell>
                    <Link href={`/brand-monitor/${a.id}`} className="font-medium hover:underline">
                      {a.brand_name}
                    </Link>
                  </TableCell>
                  <TableCell className="max-w-xs truncate text-sm text-muted-foreground">
                    {a.url ?? a.query}
                  </TableCell>
                  <TableCell className={cn("text-right tabular-nums font-medium",
                    a.overall_score >= 70 ? "text-primary" : a.overall_score >= 40 ? "text-muted-foreground" : "text-destructive"
                  )}>
                    {a.overall_score.toFixed(0)}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">{a.visibility_score.toFixed(0)}</TableCell>
                  <TableCell className="text-xs text-muted-foreground">{a.model_used}</TableCell>
                  <TableCell className="text-right tabular-nums">{a.prompt_count}</TableCell>
                  <TableCell className="text-sm text-muted-foreground">
                    {a.created_at ? new Date(a.created_at).toLocaleDateString() : "-"}
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </div>

      {totalPages > 1 && (
        <div className="flex items-center justify-between">
          <Button variant="outline" size="sm" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}>
            Previous
          </Button>
          <span className="text-sm text-muted-foreground">Page {currentPage} of {totalPages}</span>
          <Button variant="outline" size="sm" disabled={currentPage >= totalPages} onClick={() => setOffset(offset + PAGE_SIZE)}>
            Next
          </Button>
        </div>
      )}
    </div>
  );
}
