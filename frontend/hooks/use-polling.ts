"use client";

import { useCallback, useEffect, useRef, useState } from "react";

interface UsePollingOptions<T> {
  interval: number;
  enabled: boolean;
  onSuccess?: (data: T) => void;
}

interface UsePollingResult<T> {
  data: T | null;
  error: Error | null;
  isLoading: boolean;
  refetch: () => Promise<void>;
}

export function usePolling<T>(
  fetcher: () => Promise<T>,
  options: UsePollingOptions<T>,
): UsePollingResult<T> {
  const { interval, enabled, onSuccess } = options;
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const onSuccessRef = useRef(onSuccess);
  onSuccessRef.current = onSuccess;

  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;

  const doFetch = useCallback(async () => {
    try {
      const result = await fetcherRef.current();
      setData(result);
      setError(null);
      onSuccessRef.current?.(result);
    } catch (err) {
      setError(err as Error);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    doFetch();
  }, [doFetch]);

  useEffect(() => {
    if (!enabled) return;
    const id = setInterval(doFetch, interval);
    return () => clearInterval(id);
  }, [enabled, interval, doFetch]);

  return { data, error, isLoading, refetch: doFetch };
}
