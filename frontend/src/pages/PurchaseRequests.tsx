import { useState, type FormEvent } from "react";
import { Plus } from "lucide-react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { createResource } from "../api/procurement";
import { Back, dateLabel, Detail, Details, Field, FormPage, Id, NewButton, RemoveLine, shortId, TableState, uuidPattern } from "../components/RecordUI";
import LoadState from "../components/LoadState";
import PageHeading from "../components/PageHeading";
import StatusPill from "../components/StatusPill";
import { usePagedResource } from "../hooks/usePagedResource";
import { useAll, useResource, useSubmit } from "../hooks/useResource";
import type { PurchaseRequestDto, RfqDto } from "../types/procurement";

export function PurchaseRequestsList() {
  const state = usePagedResource<PurchaseRequestDto>("purchase-requests/");
  return <><PageHeading title="Заявки на закупку" action={<NewButton to="/purchase-requests/new">Новая заявка</NewButton>} />
    <TableState state={state}><table><thead><tr><th>Заявка</th><th>Статус</th><th>Проект</th><th>Версия спецификации</th><th>Автор</th><th>Создана</th></tr></thead><tbody>{state.page?.results.map((request) => <tr key={request.id}>
      <td><Link className="table-link" to={`/purchase-requests/${request.id}`}>Заявка {shortId(request.id)}</Link><span className="sub-cell">{request.items.length} позиций</span></td><td><StatusPill status={request.status} /></td><td><Id value={request.project_id} /></td><td><Id value={request.specification_version_id} /></td><td><Id value={request.requested_by} /></td><td>{dateLabel(request.created_at, true)}</td>
    </tr>)}</tbody></table></TableState></>;
}

export function PurchaseRequestDetail() {
  const { requestId = "" } = useParams();
  const state = useResource<PurchaseRequestDto>(`purchase-requests/${requestId}/`);
  const rfqs = useAll<RfqDto>(`rfqs/?purchase_request=${requestId}`);
  return <><Back to="/purchase-requests">Заявки на закупку</Back><PageHeading title={`Заявка ${shortId(requestId)}`} action={state.data && <NewButton to={`/rfqs/new?purchase_request=${requestId}`}>Создать RFQ</NewButton>} />
    <LoadState {...state} empty={false} onRetry={state.reload} />{state.data && <>
      <Details><Detail label="Статус"><StatusPill status={state.data.status} /></Detail><Detail label="Проект"><span className="mono">{state.data.project_id}</span></Detail><Detail label="Версия спецификации"><span className="mono">{state.data.specification_version_id}</span></Detail><Detail label="Автор"><span className="mono">{state.data.requested_by}</span></Detail><Detail label="Создана">{dateLabel(state.data.created_at, true)}</Detail><Detail label="Комментарий">{state.data.comment || "-"}</Detail></Details>
      <section className="record-section"><h2>Позиции заявки</h2><div className="table-scroll"><table><thead><tr><th>Позиция</th><th>Номенклатура</th><th>Количество</th><th>Единица</th><th>Нужна к</th><th>Бюджетная цена</th><th>Маршрут</th></tr></thead><tbody>{state.data.items.map((item) => <tr key={item.id}><td>{item.description || `Позиция ${item.position}`}</td><td><Id value={item.nomenclature_id} /></td><td>{item.quantity}</td><td><Id value={item.unit_id} /></td><td>{dateLabel(item.required_by)}</td><td>{item.budget_price ?? "-"}</td><td>{item.route_type}</td></tr>)}</tbody></table></div></section>
      <section className="record-section"><h2>Запросы цен</h2><LoadState {...rfqs} empty={Boolean(rfqs.data && !rfqs.data.length)} onRetry={rfqs.reload} />{rfqs.data?.map((rfq) => <Link key={rfq.id} className="related-record" to={`/rfqs/${rfq.id}`}><span>RFQ {shortId(rfq.id)}</span><StatusPill status={rfq.status} /><span>{dateLabel(rfq.deadline_at)}</span></Link>)}</section>
    </>}</>;
}

export function PurchaseRequestForm() {
  const [rows, setRows] = useState([crypto.randomUUID()]);
  const action = useSubmit();
  const navigate = useNavigate();
  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const payload = {
      project_id: form.get("project_id"), specification_version_id: form.get("specification_version_id"),
      requested_by: form.get("requested_by"), comment: form.get("comment"),
      items: rows.map((_, index) => Object.fromEntries(["description", "nomenclature_id", "quantity", "unit_id", "required_by", "budget_price", "route_type"].map((key) => [key, form.get(`items.${index}.${key}`) || (key === "required_by" || key === "budget_price" ? null : "")]))),
    };
    void action.submit(() => createResource<PurchaseRequestDto>("purchase-requests/", payload), (record) => navigate(`/purchase-requests/${record.id}`));
  }
  return <FormPage title="Новая заявка на закупку" back="/purchase-requests" {...action} onSubmit={onSubmit}>
    <div className="form-grid"><Field label="Проект"><input name="project_id" required pattern={uuidPattern} /></Field><Field label="Версия спецификации"><input name="specification_version_id" required pattern={uuidPattern} /></Field><Field label="Автор"><input name="requested_by" required pattern={uuidPattern} /></Field><Field label="Комментарий"><input name="comment" /></Field></div>
    <div className="section-heading"><h2>Позиции заявки</h2><button className="button button--secondary" type="button" onClick={() => setRows((current) => [...current, crypto.randomUUID()])}><Plus size={16} />Добавить позицию</button></div>
    {rows.map((key, index) => <div className="line-editor" key={key}><div className="line-editor__heading"><h3>Позиция {index + 1}</h3><RemoveLine disabled={rows.length === 1} onClick={() => setRows((current) => current.filter((row) => row !== key))} /></div><div className="form-grid">
      <Field label="Описание"><input name={`items.${index}.description`} maxLength={512} /></Field><Field label="Номенклатура"><input name={`items.${index}.nomenclature_id`} required pattern={uuidPattern} /></Field>
      <Field label="Количество"><input name={`items.${index}.quantity`} type="number" required min="0.000001" step="0.000001" defaultValue="1" /></Field><Field label="Единица измерения"><input name={`items.${index}.unit_id`} required pattern={uuidPattern} /></Field>
      <Field label="Нужна к"><input name={`items.${index}.required_by`} type="date" /></Field><Field label="Бюджетная цена"><input name={`items.${index}.budget_price`} type="number" min="0" step="0.0001" /></Field><Field label="Маршрут закупки"><input name={`items.${index}.route_type`} defaultValue="standard" required maxLength={48} /></Field>
    </div></div>)}
  </FormPage>;
}
