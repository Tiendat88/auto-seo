"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { StatusBadge } from "@/components/status-badge";
import { listJobs } from "@/lib/api";
import type { JobSummaryResponse, JobStatus } from "@/lib/types";

const STATUSES: JobStatus[] = [
  "pending", "researching", "planning", "generating",
  "scoring", "reviewing", "editing", "completed", "failed",
];

const PAGE_SIZE = 20;

export default function PipelineListPage() {
  const [jobs, setJobs] = useState<JobSummaryResponse[]>([]);
  const [total, setTotal] = useState(0);
  const [status, setStatus] = useState<string>("all");
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    listJobs({
      status: status === "all" ? undefined : status,
      limit: PAGE_SIZE,
      offset,
    })
      .then((res) => {
        setJobs(res.jobs);
        setTotal(res.total);
      })
      .finally(() => setLoading(false));
  }, [status, offset]);

  const totalPages = Math.ceil(total / PAGE_SIZE);
  const currentPage = Math.floor(offset / PAGE_SIZE) + 1;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Pipeline Jobs</h1>
        <Button render={<Link href="/pipeline/new" />}>
          <Plus className="mr-2 h-4 w-4" />
          New Job
        </Button>
      </div>

      <div className="flex items-center gap-4">
        <Select value={status} onValueChange={(v) => { if (v) { setStatus(v); setOffset(0); } }}>
          <SelectTrigger className="w-40">
            <SelectValue placeholder="Filter by status" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All statuses</SelectItem>
            {STATUSES.map((s) => (
              <SelectItem key={s} value={s} className="capitalize">{s}</SelectItem>
            ))}
          </SelectContent>
        </Select>
        <span className="text-sm text-muted-foreground">{total} total</span>
      </div>

      <div className="rounded-md border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Topic</TableHead>
              <TableHead>Status</TableHead>
              <TableHead className="text-right">Words</TableHead>
              <TableHead>Lang</TableHead>
              <TableHead className="text-right">Rev</TableHead>
              <TableHead>Created</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {loading ? (
              Array.from({ length: 5 }).map((_, i) => (
                <TableRow key={i}>
                  {Array.from({ length: 6 }).map((_, j) => (
                    <TableCell key={j}><Skeleton className="h-4 w-full" /></TableCell>
                  ))}
                </TableRow>
              ))
            ) : jobs.length === 0 ? (
              <TableRow>
                <TableCell colSpan={6} className="h-24 text-center text-muted-foreground">
                  No jobs found.
                </TableCell>
              </TableRow>
            ) : (
              jobs.map((job) => (
                <TableRow key={job.job_id} className="cursor-pointer hover:bg-muted/50">
                  <TableCell>
                    <Link href={`/pipeline/${job.job_id}`} className="font-medium hover:underline">
                      {job.topic}
                    </Link>
                  </TableCell>
                  <TableCell>
                    <StatusBadge status={job.status} currentStep={job.current_step} />
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    {job.target_word_count.toLocaleString()}
                  </TableCell>
                  <TableCell className="uppercase">{job.language}</TableCell>
                  <TableCell className="text-right tabular-nums">{job.revision_count}</TableCell>
                  <TableCell className="text-muted-foreground text-sm">
                    {new Date(job.created_at).toLocaleDateString()}
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </div>

      {totalPages > 1 && (
        <div className="flex items-center justify-between">
          <Button
            variant="outline"
            size="sm"
            disabled={offset === 0}
            onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
          >
            Previous
          </Button>
          <span className="text-sm text-muted-foreground">
            Page {currentPage} of {totalPages}
          </span>
          <Button
            variant="outline"
            size="sm"
            disabled={currentPage >= totalPages}
            onClick={() => setOffset(offset + PAGE_SIZE)}
          >
            Next
          </Button>
        </div>
      )}
    </div>
  );
}
