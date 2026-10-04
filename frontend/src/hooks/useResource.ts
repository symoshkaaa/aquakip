import { useCallback, useEffect, useMemo, useState } from "react";
import { getApiError } from "../api/client";
import { getAll, getResource } from "../api/procurement";
import type { PurchaseRequestDto, SupplierDto } from "../types/procurement";

export function useAsync<T>(load: () => Promise<T>) {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(null);
    setData(null);
    load().then((result) => { if (active) setData(result); })
      .catch((cause: unknown) => { if (active) setError(getApiError(cause)); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [load, revision]);
  const reload = useCallback(() => setRevision((value) => value + 1), []);
  return { data, loading, error, reload, setData };
}

export function useResource<T>(resource: string) {
  return useAsync(useCallback(() => getResource<T>(resource), [resource]));
}

export function useAll<T>(resource: string) {
  return useAsync(useCallback(() => getAll<T>(resource), [resource]));
}

export function useLookups() {
  const suppliers = useAll<SupplierDto>("suppliers/");
  const requests = useAll<PurchaseRequestDto>("purchase-requests/");
  const supplierNames = useMemo(() => new Map((suppliers.data ?? []).map((supplier) => [supplier.id, supplier.name])), [suppliers.data]);
  return { suppliers: suppliers.data ?? [], requests: requests.data ?? [], supplierNames,
    loading: suppliers.loading || requests.loading, error: suppliers.error || requests.error,
    reload: () => { suppliers.reload(); requests.reload(); } };
}

export function useSubmit() {
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  async function submit<T>(action: () => Promise<T>, onSuccess: (data: T) => void) {
    setSaving(true);
    setError(null);
    try { onSuccess(await action()); }
    catch (cause) { setError(getApiError(cause)); }
    finally { setSaving(false); }
  }
  return { saving, error, submit };
}
