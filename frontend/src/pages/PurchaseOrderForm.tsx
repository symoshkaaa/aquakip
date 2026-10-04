import { useCallback, useState, type FormEvent } from "react";
import { Plus } from "lucide-react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { createResource, getResource } from "../api/procurement";
import { Field, FormPage, RemoveLine, uuidPattern } from "../components/RecordUI";
import LoadState from "../components/LoadState";
import { useAsync, useLookups, useSubmit } from "../hooks/useResource";
import type { PurchaseOrderDto, PurchaseRequestDto, RfqDto, SupplierDto, SupplierOfferDto } from "../types/procurement";

interface Source { offer: SupplierOfferDto | null; request: PurchaseRequestDto | null }

export default function PurchaseOrderForm() {
  const [params] = useSearchParams();
  const offerId = params.get("offer");
  const lookups = useLookups();
  const source = useAsync(useCallback(async (): Promise<Source> => {
    if (!offerId) return { offer: null, request: null };
    const offer = await getResource<SupplierOfferDto>(`supplier-offers/${offerId}/`);
    const rfq = await getResource<RfqDto>(`rfqs/${offer.rfq}/`);
    const request = await getResource<PurchaseRequestDto>(`purchase-requests/${rfq.purchase_request}/`);
    return { offer, request };
  }, [offerId]));
  if (source.loading || lookups.loading || source.error || lookups.error) return <LoadState loading={source.loading || lookups.loading} error={source.error || lookups.error} empty={false} onRetry={() => { source.reload(); lookups.reload(); }} />;
  return source.data && <OrderEditor key={offerId ?? "manual"} source={source.data} suppliers={lookups.suppliers} />;
}

function OrderEditor({ source, suppliers }: { source: Source; suppliers: SupplierDto[] }) {
  const [rows, setRows] = useState(() => source.offer?.items.map((item) => ({ key: crypto.randomUUID(), nomenclature_id: item.nomenclature_id, quantity: item.quantity, unit_price: item.unit_price })) ?? [{ key: crypto.randomUUID(), nomenclature_id: "", quantity: "1", unit_price: "" }]);
  const action = useSubmit();
  const navigate = useNavigate();
  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    void action.submit(() => createResource<PurchaseOrderDto>("purchase-orders/", {
      project_id: data.get("project_id"), supplier: data.get("supplier"), number: data.get("number"), currency_code: data.get("currency_code"),
      items: rows.map((_, index) => ({ nomenclature_id: data.get(`items.${index}.nomenclature_id`), quantity: data.get(`items.${index}.quantity`), unit_price: data.get(`items.${index}.unit_price`), expected_date: data.get(`items.${index}.expected_date`) || null })),
    }), (record) => navigate(`/purchase-orders/${record.id}`));
  }
  return <FormPage title="Новый заказ поставщику" back="/purchase-orders" {...action} onSubmit={onSubmit} disabled={!suppliers.length}>
    <div className="form-grid"><Field label="Номер заказа"><input name="number" required maxLength={64} /></Field><Field label="Поставщик"><select name="supplier" required defaultValue={source.offer?.supplier ?? ""}><option value="">Выберите поставщика</option>{suppliers.map((supplier) => <option key={supplier.id} value={supplier.id}>{supplier.name}</option>)}</select></Field>
      <Field label="Проект"><input name="project_id" required pattern={uuidPattern} defaultValue={source.request?.project_id} /></Field><Field label="Валюта"><input name="currency_code" required pattern="[A-Z]{3}" maxLength={3} defaultValue={source.offer?.currency_code ?? "KZT"} /></Field>
    </div>
    <div className="section-heading"><h2>Позиции заказа</h2><button type="button" className="button button--secondary" onClick={() => setRows((current) => [...current, { key: crypto.randomUUID(), nomenclature_id: "", quantity: "1", unit_price: "" }])}><Plus size={16} />Добавить позицию</button></div>
    {rows.map((row, index) => <div className="line-editor" key={row.key}><div className="line-editor__heading"><h3>Позиция {index + 1}</h3><RemoveLine disabled={rows.length === 1} onClick={() => setRows((current) => current.filter((entry) => entry.key !== row.key))} /></div><div className="form-grid">
      <Field label="Номенклатура" wide><input name={`items.${index}.nomenclature_id`} pattern={uuidPattern} required defaultValue={row.nomenclature_id} /></Field><Field label="Количество"><input name={`items.${index}.quantity`} type="number" min="0" step="0.000001" required defaultValue={row.quantity} /></Field><Field label="Цена за единицу"><input name={`items.${index}.unit_price`} type="number" min="0" step="0.0001" required defaultValue={row.unit_price} /></Field><Field label="Ожидаемая дата"><input name={`items.${index}.expected_date`} type="date" /></Field>
    </div></div>)}
  </FormPage>;
}
