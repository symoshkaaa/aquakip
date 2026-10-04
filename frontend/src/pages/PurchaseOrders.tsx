import { Link, useParams } from "react-router-dom";
import { Check, Send } from "lucide-react";
import { approvePurchaseOrder, sendPurchaseOrder } from "../api/procurement";
import { Back, dateLabel, Detail, Details, Id, NewButton, SupplierName, TableState } from "../components/RecordUI";
import LoadState from "../components/LoadState";
import PageHeading from "../components/PageHeading";
import StatusPill from "../components/StatusPill";
import { usePagedResource } from "../hooks/usePagedResource";
import { useLookups, useResource, useSubmit } from "../hooks/useResource";
import type { PurchaseOrderDto } from "../types/procurement";

export function PurchaseOrderList() {
  const state = usePagedResource<PurchaseOrderDto>("purchase-orders/");
  const lookups = useLookups();
  const action = useSubmit();
  function runAction(order: PurchaseOrderDto) {
    void action.submit(() => order.status === "draft" ? approvePurchaseOrder(order.id) : sendPurchaseOrder(order.id), () => state.reload());
  }
  return <><PageHeading title="Заказы поставщикам" action={<NewButton to="/purchase-orders/new">Новый заказ</NewButton>} />
    {action.error && <div className="form-alert" role="alert">{action.error}</div>}
    <TableState state={state}><table><thead><tr><th>Номер</th><th>Поставщик</th><th>Проект</th><th>Сумма</th><th>Валюта</th><th>Статус</th><th>Одобрен</th><th>Отправлен</th><th /></tr></thead><tbody>{state.page?.results.map((order) => <tr key={order.id}>
      <td><Link className="table-link" to={`/purchase-orders/${order.id}`}>{order.number}</Link></td><td><SupplierName id={order.supplier} names={lookups.supplierNames} /></td><td><Id value={order.project_id} /></td><td className="amount-cell">{order.total_amount}</td><td>{order.currency_code}</td><td><StatusPill status={order.status} /></td><td>{dateLabel(order.approved_at, true)}</td><td>{dateLabel(order.sent_at, true)}</td>
      <td>{["draft", "approved"].includes(order.status) && <button className="icon-button" title={order.status === "draft" ? "Одобрить" : "Отправить"} aria-label={`${order.status === "draft" ? "Одобрить" : "Отправить"} ${order.number}`} disabled={action.saving} onClick={() => runAction(order)}>{order.status === "draft" ? <Check size={16} /> : <Send size={16} />}</button>}</td>
    </tr>)}</tbody></table></TableState></>;
}

export function PurchaseOrderDetail() {
  const { orderId = "" } = useParams();
  const state = useResource<PurchaseOrderDto>(`purchase-orders/${orderId}/`);
  const lookups = useLookups();
  const action = useSubmit();
  return <><Back to="/purchase-orders">Заказы поставщикам</Back><PageHeading title={state.data ? `Заказ ${state.data.number}` : "Заказ поставщику"} action={state.data && <StatusPill status={state.data.status} />} />
    <LoadState {...state} empty={false} onRetry={state.reload} />{state.data && <>
      <Details><Detail label="Поставщик"><SupplierName id={state.data.supplier} names={lookups.supplierNames} /></Detail><Detail label="Проект"><span className="mono">{state.data.project_id}</span></Detail><Detail label="Одобрен">{dateLabel(state.data.approved_at, true)}</Detail><Detail label="Отправлен">{dateLabel(state.data.sent_at, true)}</Detail></Details>
      <section className="record-section"><h2>Позиции заказа</h2><div className="table-scroll"><table><thead><tr><th>Номенклатура</th><th>Количество</th><th>Цена за единицу</th><th>Ожидаемая дата</th></tr></thead><tbody>{state.data.items.map((item) => <tr key={item.id}><td><Id value={item.nomenclature_id} /></td><td>{item.quantity}</td><td>{item.unit_price} {state.data?.currency_code}</td><td>{dateLabel(item.expected_date)}</td></tr>)}</tbody></table></div>
        <div className="order-total"><span>Итого</span><strong>{state.data.total_amount} {state.data.currency_code}</strong></div>
        {action.error && <div className="form-alert" role="alert">{action.error}</div>}
        <div className="order-actions">{state.data.status === "draft" && <button className="button button--primary" disabled={action.saving} onClick={() => void action.submit(() => approvePurchaseOrder(orderId), state.setData)}><Check size={16} />Одобрить</button>}{state.data.status === "approved" && <button className="button button--primary" disabled={action.saving} onClick={() => void action.submit(() => sendPurchaseOrder(orderId), state.setData)}><Send size={16} />Отправить</button>}</div>
      </section>
    </>}</>;
}
