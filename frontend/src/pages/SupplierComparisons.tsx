import { useState, type FormEvent } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { createResource } from "../api/procurement";
import JsonDetails from "../components/JsonDetails";
import { Back, dateLabel, Field, FormPage, NewButton, shortId, TableState } from "../components/RecordUI";
import LoadState from "../components/LoadState";
import PageHeading from "../components/PageHeading";
import { usePagedResource } from "../hooks/usePagedResource";
import { useAll, useLookups, useResource, useSubmit } from "../hooks/useResource";
import type { JsonValue, RfqDto, SupplierComparisonDto, SupplierOfferDto } from "../types/procurement";

export function SupplierComparisonsList() {
  const state = usePagedResource<SupplierComparisonDto>("supplier-comparisons/");
  return <><PageHeading title="Сравнения предложений" action={<NewButton to="/supplier-comparisons/new">Новое сравнение</NewButton>} />
    <TableState state={state}><table><thead><tr><th>Заявка на закупку</th><th>Версия</th><th>Создано</th><th>Сравнение</th></tr></thead><tbody>{state.page?.results.map((comparison) => <tr key={comparison.id}><td><Link className="table-link" to={`/purchase-requests/${comparison.purchase_request}`}>{shortId(comparison.purchase_request)}</Link></td><td>v{comparison.version}</td><td>{dateLabel(comparison.created_at, true)}</td><td><Link className="table-link" to={`/supplier-comparisons/${comparison.id}`}>Открыть сравнение</Link></td></tr>)}</tbody></table></TableState></>;
}

export function SupplierComparisonDetail() {
  const { comparisonId = "" } = useParams();
  const state = useResource<SupplierComparisonDto>(`supplier-comparisons/${comparisonId}/`);
  const lookups = useLookups();
  const result = state.data?.result;
  const selected = result && !Array.isArray(result) && typeof result === "object" && typeof result.selected_offer_id === "string" ? result.selected_offer_id : null;
  return <><Back to="/supplier-comparisons">Сравнения</Back><PageHeading title={state.data ? `Сравнение v${state.data.version}` : "Сравнение"} action={selected && <Link className="button button--primary" to={`/purchase-orders/new?offer=${selected}`}>Создать заказ</Link>} />
    <LoadState {...state} empty={false} onRetry={state.reload} />{state.data && <>
      <div className="record-meta"><Link className="table-link" to={`/purchase-requests/${state.data.purchase_request}`}>Заявка {shortId(state.data.purchase_request)}</Link><span>{dateLabel(state.data.created_at, true)}</span></div>
      <section className="record-section"><h2>Критерии</h2><JsonDetails value={state.data.criteria} suppliers={lookups.supplierNames} /></section>
      <section className="record-section"><h2>Результат сравнения</h2><JsonDetails value={state.data.result} suppliers={lookups.supplierNames} /></section>
    </>}</>;
}

export function SupplierComparisonForm() {
  const [params] = useSearchParams();
  const [requestId, setRequestId] = useState(params.get("purchase_request") ?? "");
  const offers = useAll<SupplierOfferDto>("supplier-offers/");
  const rfqs = useAll<RfqDto>("rfqs/");
  const versions = useAll<SupplierComparisonDto>(`supplier-comparisons/?purchase_request=${requestId}`);
  const lookups = useLookups();
  const action = useSubmit();
  const navigate = useNavigate();
  const related = offers.data?.filter((offer) => rfqs.data?.some((rfq) => rfq.id === offer.rfq && rfq.purchase_request === requestId)) ?? [];
  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const selected = related.find((offer) => offer.id === data.get("selected_offer"));
    void action.submit(async () => createResource<SupplierComparisonDto>("supplier-comparisons/", {
      purchase_request: requestId, version: data.get("version"),
      criteria: JSON.parse(String(data.get("criteria"))) as JsonValue,
      result: { selected_offer_id: selected?.id, selected_supplier_id: selected?.supplier,
        offers: related.map((offer) => ({ supplier_id: offer.supplier, offer_id: offer.id, currency_code: offer.currency_code,
          items: offer.items.map((item) => ({ nomenclature_id: item.nomenclature_id, quantity: item.quantity, unit_price: item.unit_price,
            delivery_days: item.delivery_days, availability: item.availability, technical_match: item.technical_match })) })) },
    }), (record) => navigate(`/supplier-comparisons/${record.id}`));
  }
  const loading = offers.loading || rfqs.loading || lookups.loading || versions.loading;
  const error = offers.error || rfqs.error || lookups.error || versions.error;
  const nextVersion = Math.max(0, ...(versions.data ?? []).map((entry) => entry.version)) + 1;
  return <FormPage title="Новое сравнение" back="/supplier-comparisons" {...action} disabled={loading || Boolean(error)} onSubmit={onSubmit}>
    <LoadState loading={loading} error={error} empty={false} onRetry={() => { offers.reload(); rfqs.reload(); lookups.reload(); versions.reload(); }} />
    <div className="form-grid"><Field label="Заявка на закупку" wide><select required value={requestId} onChange={(event) => setRequestId(event.target.value)}><option value="">Выберите заявку</option>{lookups.requests.map((request) => <option key={request.id} value={request.id}>{shortId(request.id)} {request.comment}</option>)}</select></Field>
      <Field label="Версия"><input key={`${requestId}-${nextVersion}`} type="number" name="version" min="1" step="1" defaultValue={nextVersion} required /></Field>
      <Field label="Выбранное предложение"><select key={requestId} name="selected_offer" required defaultValue=""><option value="">Выберите предложение</option>{related.map((offer) => <option key={offer.id} value={offer.id}>{lookups.supplierNames.get(offer.supplier) ?? shortId(offer.supplier)} / {shortId(offer.id)} / {offer.currency_code}</option>)}</select></Field>
      <Field label="Критерии" wide><textarea name="criteria" rows={5} required defaultValue={JSON.stringify({ price: "unit_price", delivery: "delivery_days", technical_match: "technical_match" }, null, 2)} /></Field>
    </div>
    <section className="record-section"><h2>Предложения по заявке</h2>{related.length ? related.map((offer) => <div className="related-record" key={offer.id}><Link className="table-link" to={`/supplier-offers/${offer.id}`}>{lookups.supplierNames.get(offer.supplier) ?? shortId(offer.supplier)}</Link><span>{offer.items.length} позиций</span><span>{dateLabel(offer.offer_date)}</span></div>) : <p className="muted">Предложений пока нет</p>}</section>
  </FormPage>;
}
