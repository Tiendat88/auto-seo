"use client";

import { useState } from "react";
import { ChevronDown, ChevronRight, Copy } from "lucide-react";
import { Button } from "@/components/ui/button";

function JsonNode({ data, depth = 0 }: { data: unknown; depth?: number }) {
  const [expanded, setExpanded] = useState(depth < 2);

  if (data === null || data === undefined) {
    return <span className="text-muted-foreground">null</span>;
  }

  if (typeof data === "boolean") {
    return <span className="text-primary">{String(data)}</span>;
  }

  if (typeof data === "number") {
    return <span className="text-primary">{data}</span>;
  }

  if (typeof data === "string") {
    return <span className="text-accent-foreground">&quot;{data}&quot;</span>;
  }

  if (Array.isArray(data)) {
    if (data.length === 0) return <span>[]</span>;
    return (
      <span>
        <button
          onClick={() => setExpanded(!expanded)}
          className="inline-flex items-center gap-0.5 text-muted-foreground hover:text-foreground"
        >
          {expanded ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
          [{data.length}]
        </button>
        {expanded && (
          <div className="ml-4 border-l border-border pl-2">
            {data.map((item, i) => (
              <div key={i}>
                <JsonNode data={item} depth={depth + 1} />
                {i < data.length - 1 && ","}
              </div>
            ))}
          </div>
        )}
      </span>
    );
  }

  if (typeof data === "object") {
    const entries = Object.entries(data);
    if (entries.length === 0) return <span>{"{}"}</span>;
    return (
      <span>
        <button
          onClick={() => setExpanded(!expanded)}
          className="inline-flex items-center gap-0.5 text-muted-foreground hover:text-foreground"
        >
          {expanded ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
          {"{"}
          {!expanded && `${entries.length} keys`}
        </button>
        {expanded && (
          <div className="ml-4 border-l border-border pl-2">
            {entries.map(([key, value], i) => (
              <div key={key}>
                <span className="text-foreground font-medium">{key}</span>
                {": "}
                <JsonNode data={value} depth={depth + 1} />
                {i < entries.length - 1 && ","}
              </div>
            ))}
          </div>
        )}
        {expanded && "}"}
      </span>
    );
  }

  return <span>{String(data)}</span>;
}

export function JsonViewer({
  data,
  title,
}: {
  data: unknown;
  title?: string;
}) {
  const copyToClipboard = () => {
    navigator.clipboard.writeText(JSON.stringify(data, null, 2));
  };

  return (
    <div className="rounded-md border bg-muted/30 p-3">
      {title && (
        <div className="mb-2 flex items-center justify-between">
          <span className="text-sm font-medium">{title}</span>
          <Button variant="ghost" size="icon" onClick={copyToClipboard} className="h-6 w-6">
            <Copy className="h-3 w-3" />
          </Button>
        </div>
      )}
      <pre className="overflow-auto text-xs font-mono">
        <JsonNode data={data} />
      </pre>
    </div>
  );
}
