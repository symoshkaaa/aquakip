import { useState, type FormEvent } from "react";
import { Plus } from "lucide-react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { createResource } from "../api/procurement";
import { Back, dateLabel, Detail, Details, Field, FormPage, Id, NewButton, RemoveLine, shortId, SupplierName, TableState, today } from "../components/RecordUI";
import LoadState from "../components/LoadState";
import PageHeading from "../components/PageHeading";
import StatusPill from "../components/StatusPill";
import { usePagedResource } from "../hooks/usePagedResource";
import { useAll, useLookups, useResource, useSubmit } from "../hooks/useResource";
import type { RfqDto, SupplierOfferDto } from "../types/procurement";

export default function SupplierOffers() {
  const state = usePagedResource<SupplierOfferDto>("supplier-offers/");
  const lookups = useLookups();
  return <><PageHeading title="Предложения поставщиков" action={<NewButton to="/supplier-offers/new">Новое предложение</NewButton>} />
    <TableState state={state}><table><thead><tr><th>Предложение</th><th>Поставщик</th><th>RFQ</th><th>Статус</th><th>Валюта</th><th>Дата</th><th>Действует до</th><th>Позиций</th></tr></thead><tbody>{state.page?.results.map((offer) => <tr key={offer.id}><td><Link className="table-link" to={`/supplier-offers/${offer.id}`}>{shortId(offer.id)}</Link></td><td><SupplierName id={offer.supplier} names={lookups.supplierNames} /></td><td><Link className="table-link mono" to={`/rfqs/${offer.rfq}`}>{shortId(offer.rfq)}</Link></td><td><StatusPill status={offer.status} /></td><td>{offer.currency_code}</td><td>{dateLabel(offer.offer_date)}</td><td>{dateLabel(offer.valid_until)}</td><td>{offer.items.length}</td></tr>)}</tbody></table></TableState></>;
}

export function OfferItems({ offer }: { offer: SupplierOfferDto }) {
  return <div className="table-scroll"><table><thead><tr><th>Номенклатура</th><th>Количество</th><th>Цена за единицу</th><th>Наличие</th><th>Доставка, дней</th><th>Техническое соответствие</th></tr></thead><tbody>{offer.items.map((item) => <tr key={item.id}><td><Id value={item.nomenclature_id} /></td><td>{item.quantity}</td><td>{item.unit_price} {offer.currency_code}</td><td><StatusPill status={item.availability} /></td><td>{item.delivery_days ?? "-"}</td><td><StatusPill status={item.technical_match} /></td></tr>)}</tbody></table></div>;
}

export function SupplierOfferDetail() {
  const { offerId = "" } = useParams();
  const state = useResource<SupplierOfferDto>(`supplier-offers/${offerId}/`);
  const lookups = useLookups();
  return <><Back to="/supplier-offers">Предложения</Back><PageHeading title={`Предложение ${shortId(offerId)}`} action={state.data && <Link className="button button--primary" to={`/purchase-orders/new?offer=${offerId}`}>Создать заказ</Link>} />
    <LoadState {...state} empty={false} onRetry={state.reload} />{state.data && <>
      <Details><Detail label="Поставщик"><SupplierName id={state.data.supplier} names={lookups.supplierNames} /></Detail><Detail label="RFQ"><Link className="table-link" to={`/rfqs/${state.data.rfq}`}>{shortId(state.data.rfq)}</Link></Detail><Detail label="Статус"><StatusPill status={state.data.status} /></Detail><Detail label="Дата предложения">{dateLabel(state.data.offer_date)}</Detail><Detail label="Действует до">{dateLabel(state.data.valid_until)}</Detail><Detail label="Валюта">{state.data.currency_code}</Detail></Details>
      <section className="record-section"><h2>Позиции предложения</h2><OfferItems offer={state.data} /></section>
    </>}</>;
}

export function SupplierOfferForm() {
  const [params] = useSearchParams();
  const [rfqId, setRfqId] = useState(params.get("rfq") ?? "");
  const [rows, setRows] = useState([crypto.randomUUID()]);
  const rfqs = useAll<RfqDto>("rfqs/");
  const lookups = useLookups();
  const action = useSubmit();
  const navigate = useNavigate();
  const request = lookups.requests.find((entry) => entry.id === rfqs.data?.find((entry) => entry.id === rfqId)?.purchase_request);
  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const items = rows.map((_, index) => {
      const requestItem = request?.items.find((item) => item.id === data.get(`items.${index}.request_item`));
      return { request_item: requestItem?.id, nomenclature_id: requestItem?.nomenclature_id,
        quantity: data.get(`items.${index}.quantity`), unit_price: data.get(`items.${index}.unit_price`),
        availability: data.get(`items.${index}.availability`), delivery_days: data.get(`items.${index}.delivery_days`) || null,
        technical_match: data.get(`items.${index}.technical_match`) };
    });
    void action.submit(() => createResource<SupplierOfferDto>("supplier-offers/", {
      rfq: rfqId, supplier: data.get("supplier"), currency_code: data.get("currency_code"),
      offer_date: data.get("offer_date"), valid_until: data.get("valid_until") || null, items,
    }), (record) => navigate(`/supplier-offers/${record.id}`));
  }
  const loading = rfqs.loading || lookups.loading;
  const error = rfqs.error || lookups.error;
  return <FormPage title="Новое предложение поставщика" back="/supplier-offers" {...action} onSubmit={onSubmit} disabled={loading || Boolean(error) || !rfqs.data?.length || !lookups.suppliers.length}>
    <LoadState loading={loading} error={error} empty={Boolean(!loading && (!rfqs.data?.length || !lookups.suppliers.length))} onRetry={() => { rfqs.reload(); lookups.reload(); }} emptyTitle="Нет RFQ или поставщиков" />
    <div className="form-grid"><Field label="RFQ"><select value={rfqId} required onChange={(event) => { setRfqId(event.target.value); setRows([crypto.randomUUID()]); }}><option value="">Выберите RFQ</option>{rfqs.data?.map((rfq) => <option key={rfq.id} value={rfq.id}>RFQ {shortId(rfq.id)}</option>)}</select></Field><Field label="Поставщик"><select name="supplier" defaultValue="" required><option value="">Выберите поставщика</option>{lookups.suppliers.map((supplier) => <option key={supplier.id} value={supplier.id}>{supplier.name}</option>)}</select></Field>
      <Field label="Валюта"><input name="currency_code" defaultValue="KZT" required pattern="[A-Z]{3}" maxLength={3} /></Field><Field label="Дата предложения"><input name="offer_date" type="date" defaultValue={today()} required /></Field><Field label="Действует до"><input name="valid_until" type="date" /></Field>
    </div>
    <div className="section-heading"><h2>Позиции предложения</h2><button type="button" className="button button--secondary" disabled={!request} onClick={() => setRows((current) => [...current, crypto.randomUUID()])}><Plus size={16} />Добавить позицию</button></div>
    {rows.map((key, index) => <div className="line-editor" key={key}><div className="line-editor__heading"><h3>Позиция {index + 1}</h3><RemoveLine disabled={rows.length === 1} onClick={() => setRows((current) => current.filter((row) => row !== key))} /></div><div className="form-grid">
      <Field label="Позиция заявки" wide><select name={`items.${index}.request_item`} required defaultValue=""><option value="">Выберите позицию</option>{request?.items.map((item) => <option value={item.id} key={item.id}>{item.description || shortId(item.nomenclature_id)} / {item.quantity}</option>)}</select></Field>
      <Field label="Количество"><input name={`items.${index}.quantity`} type="number" min="0" step="0.000001" defaultValue="1" required /></Field><Field label="Цена за единицу"><input name={`items.${index}.unit_price`} type="number" min="0" step="0.0001" required /></Field>
      <Field label="Наличие"><select name={`items.${index}.availability`} defaultValue="unknown"><option value="unknown">Не уточнено</option><option value="in_stock">В наличии</option><option value="on_order">Под заказ</option><option value="out_of_stock">Нет в наличии</option></select></Field><Field label="Доставка, дней"><input name={`items.${index}.delivery_days`} type="number" min="0" step="1" /></Field>
      <Field label="Техническое соответствие"><select name={`items.${index}.technical_match`} defaultValue="not_reviewed"><option value="not_reviewed">Не проверено</option><option value="match">Соответствует</option><option value="partial">Частично</option><option value="mismatch">Не соответствует</option></select></Field>
    </div></div>)}
  </FormPage>;
}
