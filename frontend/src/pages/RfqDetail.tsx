import { useState, type FormEvent } from "react";
import { Plus } from "lucide-react";
import { Link, useParams } from "react-router-dom";
import { createRecipient } from "../api/procurement";
import { Back, dateLabel, Detail, Details, Field, NewButton, shortId, SupplierName, TableState } from "../components/RecordUI";
import LoadState from "../components/LoadState";
import PageHeading from "../components/PageHeading";
import StatusPill from "../components/StatusPill";
import { usePagedResource } from "../hooks/usePagedResource";
import { useLookups, useResource, useSubmit } from "../hooks/useResource";
import type { RfqDto, RfqRecipientDto, SupplierOfferDto } from "../types/procurement";

export default function RfqDetail() {
  const { rfqId = "" } = useParams();
  const rfq = useResource<RfqDto>(`rfqs/${rfqId}/`);
  const recipients = usePagedResource<RfqRecipientDto>(`rfqs/${rfqId}/recipients/`);
  const offers = usePagedResource<SupplierOfferDto>(`supplier-offers/?rfq=${rfqId}`);
  const lookups = useLookups();
  const action = useSubmit();
  const [adding, setAdding] = useState(false);
  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    void action.submit(() => createRecipient(rfqId, { supplier: String(data.get("supplier")), channel: data.get("channel") as RfqRecipientDto["channel"] }), () => { setAdding(false); recipients.reload(); });
  }
  return <><Back to="/rfqs">Запросы цен</Back><PageHeading title={`RFQ ${shortId(rfqId)}`} action={rfq.data && <StatusPill status={rfq.data.status} />} />
    <LoadState {...rfq} empty={false} onRetry={rfq.reload} />{rfq.data && <>
      <Details><Detail label="Заявка на закупку"><Link className="table-link" to={`/purchase-requests/${rfq.data.purchase_request}`}>{shortId(rfq.data.purchase_request)}</Link></Detail><Detail label="Срок ответа">{dateLabel(rfq.data.deadline_at, true)}</Detail><Detail label="Создан">{dateLabel(rfq.data.created_at, true)}</Detail></Details>
      <section className="record-section"><div className="section-heading"><h2>Получатели</h2><button type="button" className="button button--secondary" onClick={() => setAdding((value) => !value)}><Plus size={16} />Добавить поставщика</button></div>
        {adding && <form className="inline-form" onSubmit={onSubmit}><LoadState loading={lookups.loading} error={lookups.error} empty={false} onRetry={lookups.reload} />
          <Field label="Поставщик"><select name="supplier" required defaultValue=""><option value="">Выберите поставщика</option>{lookups.suppliers.map((supplier) => <option key={supplier.id} value={supplier.id} disabled={recipients.page?.results.some((entry) => entry.supplier === supplier.id)}>{supplier.name}</option>)}</select></Field>
          <Field label="Канал"><select name="channel" defaultValue="email"><option value="email">Email</option><option value="whatsapp">WhatsApp</option><option value="portal">Портал</option><option value="manual">Вручную</option></select></Field>
          <button type="submit" className="button button--primary" disabled={action.saving || lookups.loading || Boolean(lookups.error)}>Добавить</button>{action.error && <p className="form-alert" role="alert">{action.error}</p>}
        </form>}
        <TableState state={recipients}><table><thead><tr><th>Поставщик</th><th>Канал</th><th>Статус доставки</th><th>Отправлено</th></tr></thead><tbody>{recipients.page?.results.map((entry) => <tr key={entry.id}><td><SupplierName id={entry.supplier} names={lookups.supplierNames} /></td><td>{entry.channel}</td><td><StatusPill status={entry.delivery_status} /></td><td>{dateLabel(entry.sent_at, true)}</td></tr>)}</tbody></table></TableState>
      </section>
      <section className="record-section"><div className="section-heading"><h2>Предложения поставщиков</h2><div className="row-actions"><Link className="button button--secondary" to={`/supplier-comparisons/new?purchase_request=${rfq.data.purchase_request}`}>Сравнить предложения</Link><NewButton to={`/supplier-offers/new?rfq=${rfqId}`}>Новое предложение</NewButton></div></div>
        <TableState state={offers}><table><thead><tr><th>Поставщик</th><th>Дата</th><th>Действует до</th><th>Валюта</th><th>Позиций</th><th>Статус</th></tr></thead><tbody>{offers.page?.results.map((offer) => <tr key={offer.id}><td><Link className="table-link" to={`/supplier-offers/${offer.id}`}>{lookups.supplierNames.get(offer.supplier) ?? shortId(offer.supplier)}</Link></td><td>{dateLabel(offer.offer_date)}</td><td>{dateLabel(offer.valid_until)}</td><td>{offer.currency_code}</td><td>{offer.items.length}</td><td><StatusPill status={offer.status} /></td></tr>)}</tbody></table></TableState>
      </section>
    </>}</>;
}
