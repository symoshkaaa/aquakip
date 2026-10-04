import { api } from "./client";
import type {
  AlternativeRequestDto,
  ApiPage,
  ExpectedDeliveryDto,
  PurchaseOrderDto,
  RfqDto,
  RfqRecipientDto,
  SupplierComparisonDto,
  SupplierOfferDto,
} from "../types/procurement";

function readPageParams(pageUrl?: string | null): URLSearchParams | undefined {
  if (!pageUrl) return undefined;
  const url = new URL(pageUrl, window.location.origin);
  return url.searchParams;
}

export async function getResource<T>(resource: string): Promise<T> {
  return (await api.get<T>(resource)).data;
}

export async function createResource<T>(resource: string, data: unknown): Promise<T> {
  return (await api.post<T>(resource, data)).data;
}

export async function getAll<T>(resource: string): Promise<T[]> {
  const records: T[] = [];
  let next: string | null | undefined;
  const visited = new Set<string>();
  do {
    if (next && visited.has(next)) throw new Error("Repeated pagination cursor");
    if (next) visited.add(next);
    const page = await getPage<T>(resource, next);
    records.push(...page.results);
    next = page.next;
  } while (next);
  return records;
}

export async function getPage<T>(
  resource: string,
  pageUrl?: string | null,
): Promise<ApiPage<T>> {
  const response = await api.get<ApiPage<T>>(resource, { params: readPageParams(pageUrl) });
  return response.data;
}

export async function getRfq(id: string): Promise<RfqDto> {
  const response = await api.get<RfqDto>(`rfqs/${id}/`);
  return response.data;
}

export async function getRecipients(id: string, pageUrl?: string | null): Promise<ApiPage<RfqRecipientDto>> {
  return getPage<RfqRecipientDto>(`rfqs/${id}/recipients/`, pageUrl);
}

export async function createRecipient(
  id: string,
  data: Pick<RfqRecipientDto, "supplier" | "channel">,
): Promise<RfqRecipientDto> {
  const response = await api.post<RfqRecipientDto>(`rfqs/${id}/recipients/`, data);
  return response.data;
}

export async function listRfqs(pageUrl?: string | null): Promise<ApiPage<RfqDto>> {
  return getPage<RfqDto>("rfqs/", pageUrl);
}

export async function listOffers(pageUrl?: string | null): Promise<ApiPage<SupplierOfferDto>> {
  return getPage<SupplierOfferDto>("supplier-offers/", pageUrl);
}

export async function listSupplierComparisons(pageUrl?: string | null): Promise<ApiPage<SupplierComparisonDto>> {
  return getPage<SupplierComparisonDto>("supplier-comparisons/", pageUrl);
}

export async function getSupplierComparison(id: string): Promise<SupplierComparisonDto> {
  const response = await api.get<SupplierComparisonDto>(`supplier-comparisons/${id}/`);
  return response.data;
}

export async function listPurchaseOrders(pageUrl?: string | null): Promise<ApiPage<PurchaseOrderDto>> {
  return getPage<PurchaseOrderDto>("purchase-orders/", pageUrl);
}

export async function getPurchaseOrder(id: string): Promise<PurchaseOrderDto> {
  const response = await api.get<PurchaseOrderDto>(`purchase-orders/${id}/`);
  return response.data;
}

export async function approvePurchaseOrder(id: string): Promise<PurchaseOrderDto> {
  const response = await api.post<PurchaseOrderDto>(`purchase-orders/${id}/approve/`);
  return response.data;
}

export async function sendPurchaseOrder(id: string): Promise<PurchaseOrderDto> {
  const response = await api.post<PurchaseOrderDto>(`purchase-orders/${id}/send/`);
  return response.data;
}

export async function listAlternativeRequests(pageUrl?: string | null): Promise<ApiPage<AlternativeRequestDto>> {
  return getPage<AlternativeRequestDto>("alternative-requests/", pageUrl);
}

export async function listExpectedDeliveries(pageUrl?: string | null): Promise<ApiPage<ExpectedDeliveryDto>> {
  return getPage<ExpectedDeliveryDto>("expected-deliveries/", pageUrl);
}
