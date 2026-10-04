import { useState, type FormEvent } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { createResource } from "../api/procurement";
import { dateLabel, Field, FormPage, NewButton, shortId, TableState } from "../components/RecordUI";
import PageHeading from "../components/PageHeading";
import LoadState from "../components/LoadState";
import StatusPill from "../components/StatusPill";
import { usePagedResource } from "../hooks/usePagedResource";
import { useAll, useSubmit } from "../hooks/useResource";
import type { PurchaseRequestDto, RfqDto } from "../types/procurement";

export default function Rfqs() {
  const state = usePagedResource<RfqDto>("rfqs/");
  return <><PageHeading title="RFQ" action={<NewButton to="/rfqs/new">Новый запрос цен</NewButton>} />
    <TableState state={state}><table><thead><tr><th>RFQ</th><th>Заявка на закупку</th><th>Статус</th><th>Срок ответа</th><th>Создан</th></tr></thead><tbody>{state.page?.results.map((rfq) => <tr key={rfq.id}>
      <td><Link className="table-link" to={`/rfqs/${rfq.id}`}>RFQ {shortId(rfq.id)}</Link></td><td><Link className="table-link mono" to={`/purchase-requests/${rfq.purchase_request}`}>{shortId(rfq.purchase_request)}</Link></td><td><StatusPill status={rfq.status} /></td><td>{dateLabel(rfq.deadline_at, true)}</td><td>{dateLabel(rfq.created_at, true)}</td>
    </tr>)}</tbody></table></TableState></>;
}

export function RfqForm() {
  const [params] = useSearchParams();
  const [requestId, setRequestId] = useState(params.get("purchase_request") ?? "");
  const requests = useAll<PurchaseRequestDto>("purchase-requests/");
  const action = useSubmit();
  const navigate = useNavigate();
  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const deadline = String(form.get("deadline_at") ?? "");
    void action.submit(() => createResource<RfqDto>("rfqs/", {
      purchase_request: form.get("purchase_request"), status: form.get("status"),
      deadline_at: deadline ? new Date(deadline).toISOString() : null,
    }), (record) => navigate(`/rfqs/${record.id}`));
  }
  return <FormPage title="Новый запрос цен" back="/rfqs" {...action} disabled={requests.loading || Boolean(requests.error) || !requests.data?.length} onSubmit={onSubmit}>
    <LoadState {...requests} empty={Boolean(requests.data && !requests.data.length)} onRetry={requests.reload} emptyTitle="Нет заявок на закупку" />
    <div className="form-grid"><Field label="Заявка на закупку" wide><select name="purchase_request" required value={requestId} onChange={(event) => setRequestId(event.target.value)}><option value="">Выберите заявку</option>{requests.data?.map((request) => <option value={request.id} key={request.id}>{shortId(request.id)} {request.comment}</option>)}</select></Field>
      <Field label="Статус"><select name="status" defaultValue="draft"><option value="draft">Черновик</option><option value="open">Открыт</option></select></Field><Field label="Срок ответа"><input name="deadline_at" type="datetime-local" /></Field>
    </div>
  </FormPage>;
}
