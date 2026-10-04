import { useState, type FormEvent } from "react";
import { Search } from "lucide-react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { createResource } from "../api/procurement";
import { Back, dateLabel, Detail, Details, Field, FormPage, NewButton, TableState, uuidPattern } from "../components/RecordUI";
import PageHeading from "../components/PageHeading";
import LoadState from "../components/LoadState";
import StatusPill from "../components/StatusPill";
import { usePagedResource } from "../hooks/usePagedResource";
import { useResource, useSubmit } from "../hooks/useResource";
import type { SupplierDto } from "../types/procurement";

export function SuppliersList() {
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("");
  const state = usePagedResource<SupplierDto>(`suppliers/?${new URLSearchParams({ search, status })}`);
  return <><PageHeading title="Поставщики" action={<NewButton to="/suppliers/new">Новый поставщик</NewButton>} />
    <div className="list-toolbar"><form className="search-form" onSubmit={(event) => { event.preventDefault(); setSearch(String(new FormData(event.currentTarget).get("search") ?? "")); }}>
      <input aria-label="Поиск поставщиков" name="search" placeholder="Название, код, БИН или email" type="search" />
      <button className="icon-button" title="Поиск" aria-label="Поиск" type="submit"><Search size={17} /></button>
    </form><select aria-label="Статус поставщика" value={status} onChange={(event) => setStatus(event.target.value)}><option value="">Все статусы</option><option value="active">Активен</option><option value="pending">Ожидает</option><option value="inactive">Неактивен</option><option value="blocked">Заблокирован</option></select><span className="muted">{state.page?.count ?? "-"} поставщиков</span></div>
    <TableState state={state}><table><thead><tr><th>Поставщик</th><th>Код</th><th>Статус</th><th>Рейтинг</th><th>Email</th><th>Телефон</th></tr></thead><tbody>{state.page?.results.map((supplier) => <tr key={supplier.id}>
      <td><Link className="table-link" to={`/suppliers/${supplier.id}`}>{supplier.name}</Link></td><td>{supplier.code}</td><td><StatusPill status={supplier.status} /></td><td>{supplier.rating ?? "-"}</td><td>{supplier.email || "-"}</td><td>{supplier.phone || "-"}</td>
    </tr>)}</tbody></table></TableState></>;
}

export function SupplierDetail() {
  const { supplierId = "" } = useParams();
  const state = useResource<SupplierDto>(`suppliers/${supplierId}/`);
  return <><Back to="/suppliers">Поставщики</Back><PageHeading title={state.data?.name ?? "Поставщик"} action={state.data && <StatusPill status={state.data.status} />} />
    <LoadState {...state} empty={false} onRetry={state.reload} />{state.data && <Details>
      <Detail label="Код">{state.data.code}</Detail><Detail label="БИН">{state.data.bin ?? "-"}</Detail><Detail label="Тип">{state.data.supplier_type}</Detail>
      <Detail label="Рейтинг">{state.data.rating ?? "-"}</Detail><Detail label="Email">{state.data.email || "-"}</Detail><Detail label="Телефон">{state.data.phone || "-"}</Detail>
      <Detail label="Компания"><span className="mono">{state.data.company_id}</span></Detail><Detail label="Создан">{dateLabel(state.data.created_at, true)}</Detail>
    </Details>}</>;
}

export function SupplierForm() {
  const action = useSubmit();
  const navigate = useNavigate();
  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const values = Object.fromEntries(new FormData(event.currentTarget));
    const payload: Record<string, FormDataEntryValue | null> = { ...values, rating: values.rating || null, bin: values.bin || null };
    if (!values.company_id) delete payload.company_id;
    void action.submit(() => createResource<SupplierDto>("suppliers/", payload), (record) => navigate(`/suppliers/${record.id}`));
  }
  return <FormPage title="Новый поставщик" back="/suppliers" onSubmit={onSubmit} {...action}><div className="form-grid">
    <Field label="Название"><input name="name" required maxLength={255} /></Field><Field label="Код"><input name="code" required maxLength={64} /></Field>
    <Field label="БИН"><input name="bin" maxLength={20} /></Field><Field label="Тип поставщика"><input name="supplier_type" defaultValue="equipment" required maxLength={48} /></Field>
    <Field label="Статус"><select name="status" defaultValue="active"><option value="active">Активен</option><option value="pending">Ожидает</option><option value="inactive">Неактивен</option><option value="blocked">Заблокирован</option></select></Field>
    <Field label="Рейтинг"><input name="rating" type="number" step="0.001" /></Field><Field label="Email"><input name="email" type="email" /></Field><Field label="Телефон"><input name="phone" maxLength={64} /></Field>
    <Field label="Компания" wide><input name="company_id" pattern={uuidPattern} /></Field>
  </div></FormPage>;
}
