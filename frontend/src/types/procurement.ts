export interface ApiPage<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

export interface SupplierDto {
  id: string;
  company_id: string;
  code: string;
  name: string;
  bin: string | null;
  supplier_type: string;
  status: "pending" | "active" | "inactive" | "blocked";
  rating: string | null;
  email: string;
  phone: string;
  created_at: string;
  updated_at: string;
}

export interface PurchaseRequestDto {
  id: string;
  company_id: string;
  project_id: string;
  specification_version_id: string;
  requested_by: string;
  status: "draft" | "submitted" | "approved" | "rejected" | "cancelled" | "ordered";
  comment: string;
  items: PurchaseRequestItemDto[];
  created_at: string;
  updated_at: string;
}

export interface PurchaseRequestItemDto {
  id: string;
  purchase_request: string;
  nomenclature_id: string;
  unit_id: string;
  quantity: string;
  budget_price: string | null;
  required_by: string | null;
  route_type: string;
  position: number;
  description: string;
}

export interface RfqDto {
  id: string;
  purchase_request: string;
  status: "draft" | "open" | "closed" | "cancelled";
  deadline_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface RfqRecipientDto {
  id: string;
  rfq: string;
  supplier: string;
  channel: "email" | "whatsapp" | "portal" | "manual";
  sent_at: string | null;
  delivery_status: "pending" | "sent" | "delivered" | "failed";
  created_at: string;
  updated_at: string;
}

export interface SupplierOfferItemDto {
  id: string;
  supplier_offer: string;
  request_item: string;
  nomenclature_id: string;
  quantity: string;
  unit_price: string;
  availability: "unknown" | "in_stock" | "on_order" | "out_of_stock";
  delivery_days: number | null;
  technical_match: "not_reviewed" | "match" | "partial" | "mismatch";
  created_at: string;
  updated_at: string;
}

export interface SupplierOfferDto {
  id: string;
  rfq: string;
  supplier: string;
  status: "received" | "verified" | "accepted" | "rejected" | "expired";
  currency_code: string;
  offer_date: string;
  valid_until: string | null;
  source_document_id: string | null;
  items: SupplierOfferItemDto[];
  created_at: string;
  updated_at: string;
}

export interface PurchaseOrderDto {
  id: string;
  project_id: string;
  supplier: string;
  status: "draft" | "approved" | "sent" | "cancelled";
  number: string;
  currency_code: string;
  total_amount: string;
  approved_at: string | null;
  sent_at: string | null;
  items: PurchaseOrderItemDto[];
  created_at: string;
  updated_at: string;
}

export interface PurchaseOrderItemDto {
  id: string;
  nomenclature_id: string;
  quantity: string;
  unit_price: string;
  expected_date: string | null;
  created_at: string;
  updated_at: string;
}

export interface SupplierComparisonDto {
  id: string;
  purchase_request: string;
  version: number;
  criteria: JsonValue;
  result: JsonValue;
  created_at: string;
  updated_at: string;
}

export interface AlternativeRequestDto {
  id: string;
  project_id: string;
  request_item: string;
  original_nomenclature_id: string;
  alternative_nomenclature_id: string;
  status: "requested" | "technical_review" | "technically_approved" | "technically_rejected" | "approved" | "rejected" | "cancelled";
  technical_review_id: string | null;
  client_decision: string | null;
  created_at: string;
  updated_at: string;
}

export interface ExpectedDeliveryDto {
  id: string;
  purchase_order: string;
  planned_date: string;
  actual_date: string | null;
  early_delivery_reason: string;
  status: "expected" | "in_transit" | "delivered" | "delayed" | "cancelled";
  tracking: JsonValue;
  created_at: string;
  updated_at: string;
}

export type JsonValue = string | number | boolean | null | JsonValue[] | { [key: string]: JsonValue };
