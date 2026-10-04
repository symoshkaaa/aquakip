import { Link } from "react-router-dom";
import JsonDetails from "../components/JsonDetails";
import { dateLabel, shortId, TableState } from "../components/RecordUI";
import PageHeading from "../components/PageHeading";
import StatusPill from "../components/StatusPill";
import { usePagedResource } from "../hooks/usePagedResource";
import { useAll } from "../hooks/useResource";
import type { ExpectedDeliveryDto, PurchaseOrderDto } from "../types/procurement";

export default function ExpectedDeliveries() {
  const state = usePagedResource<ExpectedDeliveryDto>("expected-deliveries/");
  const orders = useAll<PurchaseOrderDto>("purchase-orders/");
  const names = new Map(orders.data?.map((order) => [order.id, order.number]) ?? []);
  return <><PageHeading title="Ожидаемые поставки" />
    <TableState state={state}><table><thead><tr><th>Заказ поставщику</th><th>Плановая дата</th><th>Фактическая дата</th><th>Статус</th><th>Отслеживание</th></tr></thead><tbody>{state.page?.results.map((delivery) => <tr key={delivery.id}><td><Link className="table-link" to={`/purchase-orders/${delivery.purchase_order}`}>{names.get(delivery.purchase_order) ?? shortId(delivery.purchase_order)}</Link></td><td>{dateLabel(delivery.planned_date)}</td><td>{dateLabel(delivery.actual_date)}{delivery.actual_date && delivery.actual_date < delivery.planned_date && <span className="early-reason">{delivery.early_delivery_reason}</span>}</td><td><StatusPill status={delivery.status} /></td><td><details className="tracking-details"><summary>Данные доставки</summary><JsonDetails value={delivery.tracking} /></details></td></tr>)}</tbody></table></TableState></>;
}
