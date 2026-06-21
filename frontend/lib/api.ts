import type {
  AeoRequest,
  AeoResponse,
  ArticleRequest,
  BrandAnalysisListResponse,
  BrandMonitorRequest,
  BrandMonitorResponse,
  FanOutRequest,
  FanOutResponse,
  JobListResponse,
  JobResponse,
  CampaignRequest,
  CampaignResponse,
  PublishTarget,
  PublishTargetListResponse,
  PublishJob,
  PublishJobListResponse,
  CreateTargetRequest,
  CreatePublishJobRequest,
  TestConnectionRequest,
  TestConnectionResponse,
} from "./types";

export class ApiError extends Error {
  constructor(
    public status: number,
    public data: Record<string, unknown> = {},
  ) {
    const detail =
      typeof data.detail === "string" ? data.detail : `HTTP ${status}`;
    super(detail);
    this.name = "ApiError";
  }
}

async function fetchApi<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json", ...options?.headers },
    ...options,
  });
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new ApiError(response.status, data as Record<string, unknown>);
  }
  return response.json() as Promise<T>;
}

// --- Jobs ---

export function createJob(request: ArticleRequest): Promise<JobResponse> {
  return fetchApi("/api/jobs", {
    method: "POST",
    body: JSON.stringify(request),
  });
}

export function createCampaign(request: CampaignRequest): Promise<CampaignResponse> {
  return fetchApi("/api/jobs/campaign", {
    method: "POST",
    body: JSON.stringify(request),
  });
}

export function listJobs(params: {
  status?: string;
  limit?: number;
  offset?: number;
}): Promise<JobListResponse> {
  const sp = new URLSearchParams();
  if (params.status) sp.set("status", params.status);
  if (params.limit) sp.set("limit", String(params.limit));
  if (params.offset) sp.set("offset", String(params.offset));
  return fetchApi(`/api/jobs?${sp.toString()}`);
}

export function getJob(
  jobId: string,
  full = false,
): Promise<JobResponse> {
  const sp = full ? "?full=true" : "";
  return fetchApi(`/api/jobs/${jobId}${sp}`);
}

export function resumeJob(jobId: string): Promise<JobResponse> {
  return fetchApi(`/api/jobs/${jobId}/resume`, { method: "POST" });
}

// --- Brand Monitor ---

export function analyzeBrand(
  request: BrandMonitorRequest,
): Promise<BrandMonitorResponse> {
  return fetchApi("/api/brand-monitor/analyze", {
    method: "POST",
    body: JSON.stringify(request),
  });
}

export interface SSEEvent {
  event: string;
  data: Record<string, unknown>;
}

export function streamBrandAnalysis(
  request: BrandMonitorRequest,
  onEvent: (event: SSEEvent) => void,
  onError: (error: Error) => void,
  onComplete: () => void,
): AbortController {
  const controller = new AbortController();

  (async () => {
    try {
      const response = await fetch("/api/brand-monitor/analyze/stream", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(request),
        signal: controller.signal,
      });

      if (!response.ok || !response.body) {
        throw new ApiError(response.status);
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() ?? "";

        let currentEvent = "";
        let currentData = "";

        for (const line of lines) {
          if (line.startsWith("event: ")) {
            currentEvent = line.slice(7).trim();
          } else if (line.startsWith("data: ")) {
            currentData = line.slice(6);
          } else if (line === "" && currentEvent && currentData) {
            try {
              const parsed = JSON.parse(currentData) as Record<string, unknown>;
              onEvent({ event: currentEvent, data: parsed });
            } catch {
              // skip malformed data
            }
            currentEvent = "";
            currentData = "";
          }
        }
      }

      onComplete();
    } catch (err) {
      if ((err as Error).name !== "AbortError") {
        onError(err as Error);
      }
    }
  })();

  return controller;
}

export function listBrandAnalyses(params: {
  brand_name?: string;
  limit?: number;
  offset?: number;
}): Promise<BrandAnalysisListResponse> {
  const sp = new URLSearchParams();
  if (params.brand_name) sp.set("brand_name", params.brand_name);
  if (params.limit) sp.set("limit", String(params.limit));
  if (params.offset) sp.set("offset", String(params.offset));
  return fetchApi(`/api/brand-monitor/analyses?${sp.toString()}`);
}

export function getBrandAnalysis(id: string): Promise<BrandMonitorResponse> {
  return fetchApi(`/api/brand-monitor/analyses/${id}`);
}

// --- AEO ---

export function analyzeAeo(request: AeoRequest): Promise<AeoResponse> {
  return fetchApi("/api/aeo/analyze", {
    method: "POST",
    body: JSON.stringify(request),
  });
}

export function fanout(request: FanOutRequest): Promise<FanOutResponse> {
  return fetchApi("/api/aeo/fanout", {
    method: "POST",
    body: JSON.stringify(request),
  });
}

// --- Publish Targets ---

export function listPublishTargets(): Promise<PublishTargetListResponse> {
  return fetchApi("/api/publish/targets");
}

export function createPublishTarget(request: CreateTargetRequest): Promise<PublishTarget> {
  return fetchApi("/api/publish/targets", {
    method: "POST",
    body: JSON.stringify(request),
  });
}

export function deletePublishTarget(targetId: string): Promise<void> {
  return fetchApi(`/api/publish/targets/${targetId}`, { method: "DELETE" });
}

export function testPublishConnection(request: TestConnectionRequest): Promise<TestConnectionResponse> {
  return fetchApi("/api/publish/targets/test", {
    method: "POST",
    body: JSON.stringify(request),
  });
}

// --- Publish Jobs ---

export function listPublishJobs(params: {
  limit?: number;
  offset?: number;
  status?: string;
}): Promise<PublishJobListResponse> {
  const sp = new URLSearchParams();
  if (params.limit) sp.set("limit", String(params.limit));
  if (params.offset) sp.set("offset", String(params.offset));
  if (params.status) sp.set("status", params.status);
  return fetchApi(`/api/publish/jobs?${sp.toString()}`);
}

export function createPublishJob(request: CreatePublishJobRequest): Promise<PublishJob> {
  return fetchApi("/api/publish/jobs", {
    method: "POST",
    body: JSON.stringify(request),
  });
}

export function getPublishJob(publishJobId: string): Promise<PublishJob> {
  return fetchApi(`/api/publish/jobs/${publishJobId}`);
}

export function cancelPublishJob(publishJobId: string): Promise<PublishJob> {
  return fetchApi(`/api/publish/jobs/${publishJobId}/cancel`, { method: "POST" });
}

