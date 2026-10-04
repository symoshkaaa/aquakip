import { useEffect, useState } from "react";
import { getPage } from "../api/procurement";
import { getApiError } from "../api/client";
import type { ApiPage } from "../types/procurement";

export function usePagedResource<T>(resource: string) {
  const [page, setPage] = useState<ApiPage<T> | null>(null);
  const [navigation, setNavigation] = useState<{ resource: string; url: string | null }>({ resource, url: null });
  const pageUrl = navigation.resource === resource ? navigation.url : null;
  const [refreshKey, setRefreshKey] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(null);
    setPage(null);

    getPage<T>(resource, pageUrl)
      .then((response) => {
        if (active) setPage(response);
      })
      .catch((cause: unknown) => {
        if (active) setError(getApiError(cause));
      })
      .finally(() => {
        if (active) setLoading(false);
      });

    return () => {
      active = false;
    };
  }, [resource, pageUrl, refreshKey]);

  return {
    page,
    loading,
    error,
    setPageUrl: (url: string | null) => setNavigation({ resource, url }),
    reload: () => { setNavigation({ resource, url: null }); setRefreshKey((value) => value + 1); },
  };
}
