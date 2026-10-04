import { cloneElement, useId, type FormEvent, type ReactElement, type ReactNode } from "react";
import { ArrowLeft, Plus, Save, Trash2 } from "lucide-react";
import { Link } from "react-router-dom";
import LoadState from "./LoadState";
import Pagination from "./Pagination";
import PageHeading from "./PageHeading";
import type { ApiPage } from "../types/procurement";

export const uuidPattern = "[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}";
export function shortId(value: string) { return value ? `${value.slice(0, 8)}...${value.slice(-4)}` : "-"; }
export function dateLabel(value: string | null, time = false) {
  if (!value) return "-";
  const parsed = new Date(value.length === 10 ? `${value}T00:00:00+05:00` : value);
  if (Number.isNaN(parsed.valueOf())) return "-";
  return new Intl.DateTimeFormat("ru-RU", { dateStyle: "medium", ...(time ? { timeStyle: "short" as const } : {}), timeZone: "Asia/Almaty" }).format(parsed);
}
export function today() { return new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Almaty", year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date()); }
export function Id({ value }: { value: string }) { return <span className="mono" title={value}>{shortId(value)}</span>; }
export function SupplierName({ id, names }: { id: string; names: Map<string, string> }) { return <Link className="table-link" to={`/suppliers/${id}`}>{names.get(id) ?? shortId(id)}</Link>; }
export function NewButton({ to, children }: { to: string; children: ReactNode }) { return <Link className="button button--primary" to={to}><Plus size={16} />{children}</Link>; }
export function Back({ to, children }: { to: string; children: ReactNode }) { return <Link className="back-link" to={to}><ArrowLeft size={16} />{children}</Link>; }
export function Field({ label, children, wide = false }: { label: string; children: ReactElement<{ "aria-labelledby"?: string }>; wide?: boolean }) {
  const labelId = useId();
  return <label className={wide ? "field field--wide" : "field"}><span id={labelId}>{label}</span>{cloneElement(children, { "aria-labelledby": labelId })}</label>;
}
export function Details({ children }: { children: ReactNode }) { return <dl className="record-details">{children}</dl>; }
export function Detail({ label, children }: { label: string; children: ReactNode }) { return <div><dt>{label}</dt><dd>{children}</dd></div>; }
export function TableState<T>({ state, children }: { state: { page: ApiPage<T> | null; loading: boolean; error: string | null; reload: () => void; setPageUrl: (url: string | null) => void }; children: ReactNode }) {
  return <section className="surface list-surface"><LoadState loading={state.loading} error={state.error} empty={Boolean(state.page && !state.page.results.length)} onRetry={state.reload} />
    {!state.loading && !state.error && state.page && state.page.results.length > 0 && <><div className="table-scroll">{children}</div><Pagination page={state.page} onNavigate={state.setPageUrl} /></>}
  </section>;
}
export function FormPage({ title, back, saving, error, onSubmit, children, disabled = false }: { title: string; back: string; saving: boolean; error: string | null; onSubmit: (event: FormEvent<HTMLFormElement>) => void; children: ReactNode; disabled?: boolean }) {
  return <><Back to={back}>Назад</Back><PageHeading title={title} />
    <form className="record-form" onSubmit={onSubmit}><fieldset disabled={saving || disabled}>
      {children}
      {error && <div className="form-alert" role="alert">{error}</div>}
      <div className="form-actions"><Link className="button button--secondary" to={back}>Отмена</Link><button className="button button--primary" disabled={saving || disabled} type="submit"><Save size={16} />{saving ? "Сохраняем..." : "Сохранить"}</button></div>
    </fieldset></form></>;
}
export function RemoveLine({ onClick, disabled }: { onClick: () => void; disabled: boolean }) { return <button className="icon-button" type="button" title="Удалить позицию" aria-label="Удалить позицию" disabled={disabled} onClick={onClick}><Trash2 size={16} /></button>; }
