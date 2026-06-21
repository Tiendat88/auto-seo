"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import { Skeleton } from "@/components/ui/skeleton";
import { listBrandAnalyses } from "@/lib/api";
import type { BrandAnalysisSummary } from "@/lib/types";
import { cn } from "@/lib/utils";
import { Search, History, Calendar, Clock } from "lucide-react";

const PAGE_SIZE = 20;

export default function BrandHistoryPage() {
  const [analyses, setAnalyses] = useState<BrandAnalysisSummary[]>([]);
  const [total, setTotal] = useState(0);
  const [brandFilter, setBrandFilter] = useState("");
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    const fetchAnalyses = async () => {
      setLoading(true);
      try {
        const res = await listBrandAnalyses({
          brand_name: brandFilter || undefined,
          limit: PAGE_SIZE,
          offset,
        });
        if (active) {
          setAnalyses(res.analyses);
          setTotal(res.total);
        }
      } finally {
        if (active) {
          setLoading(false);
        }
      }
    };
    fetchAnalyses();
    return () => { active = false; };
  }, [brandFilter, offset]);

  const totalPages = Math.ceil(total / PAGE_SIZE);
  const currentPage = Math.floor(offset / PAGE_SIZE) + 1;

  return (
    <div className="space-y-6 max-w-7xl mx-auto pb-10">
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-3xl font-extrabold tracking-tight text-blue-900 dark:text-blue-100 flex items-center gap-3">
            Lịch sử Phân tích
          </h1>
          <p className="text-muted-foreground mt-1">
            Xem lại các báo cáo giám sát thương hiệu đã thực hiện trước đây
          </p>
        </div>
      </div>

      <Card className="border-blue-500/10 shadow-sm overflow-hidden bg-card/50 backdrop-blur-sm">
        <div className="p-4 flex flex-col sm:flex-row items-center justify-between gap-4 border-b border-blue-500/10 bg-blue-50/50 dark:bg-blue-900/10">
          <div className="relative w-full sm:max-w-xs">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input
              value={brandFilter}
              onChange={(e) => { setBrandFilter(e.target.value); setOffset(0); }}
              placeholder="Lọc theo tên thương hiệu..."
              className="pl-9 bg-background focus-visible:ring-blue-500 border-blue-200 dark:border-blue-800"
            />
          </div>
          <div className="flex items-center gap-2 text-sm text-blue-600 dark:text-blue-400 font-medium bg-blue-100 dark:bg-blue-900/30 px-3 py-1.5 rounded-full whitespace-nowrap">
            <History className="h-4 w-4" />
            <span>Tổng số: {total} báo cáo</span>
          </div>
        </div>

        <div className="overflow-x-auto">
          <Table>
            <TableHeader className="bg-muted/30">
              <TableRow className="hover:bg-transparent">
                <TableHead className="font-semibold text-blue-900 dark:text-blue-200">Thương hiệu</TableHead>
                <TableHead className="font-semibold text-blue-900 dark:text-blue-200">Truy vấn / URL gốc</TableHead>
                <TableHead className="text-right font-semibold text-blue-900 dark:text-blue-200">Tổng điểm</TableHead>
                <TableHead className="text-right font-semibold text-blue-900 dark:text-blue-200">Độ phủ (Visibility)</TableHead>
                <TableHead className="font-semibold text-blue-900 dark:text-blue-200">Mô hình AI</TableHead>
                <TableHead className="text-right font-semibold text-blue-900 dark:text-blue-200">Số kịch bản</TableHead>
                <TableHead className="font-semibold text-blue-900 dark:text-blue-200">Thời gian tạo</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {loading ? (
                Array.from({ length: 5 }).map((_, i) => (
                  <TableRow key={i}>
                    {Array.from({ length: 7 }).map((_, j) => (
                      <TableCell key={j}><Skeleton className="h-5 w-full" /></TableCell>
                    ))}
                  </TableRow>
                ))
              ) : analyses.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={7} className="h-32 text-center">
                    <div className="flex flex-col items-center justify-center text-muted-foreground">
                      <History className="h-8 w-8 mb-2 opacity-20" />
                      <p>Không tìm thấy báo cáo nào.</p>
                      {brandFilter && (
                        <Button variant="link" onClick={() => { setBrandFilter(""); setOffset(0); }} className="mt-2 text-blue-600">
                          Xóa bộ lọc
                        </Button>
                      )}
                    </div>
                  </TableCell>
                </TableRow>
              ) : (
                analyses.map((a) => (
                  <TableRow key={a.id} className="cursor-pointer transition-colors hover:bg-blue-50/50 dark:hover:bg-blue-900/20 group">
                    <TableCell>
                      <Link href={`/brand-monitor/${a.id}`} className="block w-full">
                        <span className="font-bold text-foreground group-hover:text-blue-600 dark:group-hover:text-blue-400 transition-colors">
                          {a.brand_name}
                        </span>
                      </Link>
                    </TableCell>
                    <TableCell className="max-w-xs truncate text-sm text-muted-foreground">
                      <Link href={`/brand-monitor/${a.id}`} className="block w-full truncate" title={a.url ?? a.query}>
                        {a.url ? (
                          <span className="text-blue-500 hover:underline">{a.url}</span>
                        ) : (
                          <span className="italic">"{a.query}"</span>
                        )}
                      </Link>
                    </TableCell>
                    <TableCell className="text-right tabular-nums">
                      <Link href={`/brand-monitor/${a.id}`} className="block w-full">
                        <Badge 
                          variant="outline" 
                          className={cn(
                            "font-bold px-2 py-0.5",
                            a.overall_score >= 70 ? "bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-900/30 dark:text-emerald-400 dark:border-emerald-800" : 
                            a.overall_score >= 40 ? "bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-900/30 dark:text-amber-400 dark:border-amber-800" : 
                            "bg-rose-50 text-rose-700 border-rose-200 dark:bg-rose-900/30 dark:text-rose-400 dark:border-rose-800"
                          )}
                        >
                          {a.overall_score.toFixed(0)}
                        </Badge>
                      </Link>
                    </TableCell>
                    <TableCell className="text-right tabular-nums">
                      <Link href={`/brand-monitor/${a.id}`} className="block w-full text-foreground font-medium">
                        {a.visibility_score.toFixed(0)}
                      </Link>
                    </TableCell>
                    <TableCell>
                      <Link href={`/brand-monitor/${a.id}`} className="block w-full">
                        <Badge variant="secondary" className="text-[10px] font-normal uppercase">{a.model_used}</Badge>
                      </Link>
                    </TableCell>
                    <TableCell className="text-right tabular-nums">
                      <Link href={`/brand-monitor/${a.id}`} className="block w-full text-muted-foreground">
                        {a.prompt_count}
                      </Link>
                    </TableCell>
                    <TableCell>
                      <Link href={`/brand-monitor/${a.id}`} className="block w-full text-sm text-muted-foreground">
                        <div className="flex items-center gap-1.5">
                          <Calendar className="h-3.5 w-3.5 opacity-70" />
                          <span>{a.created_at ? new Date(a.created_at).toLocaleDateString('vi-VN') : "-"}</span>
                          {a.created_at && (
                            <>
                              <Clock className="h-3 w-3 ml-1 opacity-50" />
                              <span className="text-xs opacity-70">{new Date(a.created_at).toLocaleTimeString('vi-VN', {hour: '2-digit', minute:'2-digit'})}</span>
                            </>
                          )}
                        </div>
                      </Link>
                    </TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </div>

        {totalPages > 1 && (
          <div className="flex items-center justify-between p-4 border-t border-border/50 bg-muted/10">
            <Button 
              variant="outline" 
              size="sm" 
              disabled={offset === 0} 
              onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
              className="hover:bg-blue-50 dark:hover:bg-blue-900/20"
            >
              Trang trước
            </Button>
            <span className="text-sm font-medium text-muted-foreground">Trang <span className="text-foreground">{currentPage}</span> / {totalPages}</span>
            <Button 
              variant="outline" 
              size="sm" 
              disabled={currentPage >= totalPages} 
              onClick={() => setOffset(offset + PAGE_SIZE)}
              className="hover:bg-blue-50 dark:hover:bg-blue-900/20"
            >
              Trang sau
            </Button>
          </div>
        )}
      </Card>
    </div>
  );
}
