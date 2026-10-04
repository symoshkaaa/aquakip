import { useCallback } from "react";
import { ArrowRight, ClipboardList, FileText, PackageCheck, Send, Truck } from "lucide-react";
import { Link } from "react-router-dom";
import { getAll } from "../api/procurement";
import { dateLabel, shortId, SupplierName, today } from "../components/RecordUI";
import LoadState from "../components/LoadState";
import PageHeading from "../components/PageHeading";
import StatusPill from "../components/StatusPill";
import { useAsync } from "../hooks/useResource";
import type { ExpectedDeliveryDto, PurchaseOrderDto, PurchaseRequestDto, RfqDto, SupplierDto, SupplierOfferDto } from "../types/procurement";

export default function Dashboard() {
  const state = useAsync(useCallback(async () => {
    const [requests, rfqs, offers, orders, deliveries, suppliers] = await Promise.all([
      getAll<PurchaseRequestDto>("purchase-requests/"), getAll<RfqDto>("rfqs/"), getAll<SupplierOfferDto>("supplier-offers/"),
      getAll<PurchaseOrderDto>("purchase-orders/"), getAll<ExpectedDeliveryDto>("expected-deliveries/"), getAll<SupplierDto>("suppliers/"),
    ]);
    return { requests, rfqs, offers, orders, deliveries, suppliers };
  }, []));
  const data = state.data;
  const names = new Map(data?.suppliers.map((supplier) => [supplier.id, supplier.name]) ?? []);
  const orderNames = new Map(data?.orders.map((order) => [order.id, order.number]) ?? []);
  const upcoming = data?.deliveries.filter((delivery) => !["delivered", "cancelled"].includes(delivery.status) && delivery.planned_date >= today()).sort((a, b) => a.planned_date.localeCompare(b.planned_date)).slice(0, 6) ?? [];
  return <><PageHeading eyebrow="AQUA KIP" title="Обзор закупок" />
    <LoadState {...state} empty={false} onRetry={state.reload} />{data && <>
      <section className="metric-grid" aria-label="Сводка закупок">{[
        { label: "Заявки на закупку", count: data.requests.length, path: "/purchase-requests", icon: ClipboardList, tone: "plain" },
        { label: "Активные RFQ", count: data.rfqs.filter((rfq) => rfq.status === "open").length, path: "/rfqs", icon: Send, tone: "dark" },
        { label: "Предложения", count: data.offers.length, path: "/supplier-offers", icon: FileText, tone: "lime" },
        { label: "Заказы поставщикам", count: data.orders.length, path: "/purchase-orders", icon: PackageCheck, tone: "blue" },
        { label: "Ожидаемые поставки", count: data.deliveries.length, path: "/expected-deliveries", icon: Truck, tone: "rose" },
      ].map(({ label, count, path, icon: Icon, tone }) => <Link className={`metric-card metric-card--${tone}`} to={path} key={path}><div className="metric-card__top"><span>{label}</span><Icon size={18} /></div><strong>{count}</strong></Link>)}</section>
      <div className="dashboard-grid"><section className="record-section"><div className="section-heading"><h2>Последние RFQ</h2><Link className="text-link" to="/rfqs">Все запросы <ArrowRight size={15} /></Link></div><div className="table-scroll"><table><thead><tr><th>RFQ</th><th>Заявка</th><th>Статус</th><th>Срок ответа</th></tr></thead><tbody>{data.rfqs.slice(0, 6).map((rfq) => <tr key={rfq.id}><td><Link className="table-link" to={`/rfqs/${rfq.id}`}>{shortId(rfq.id)}</Link></td><td><Link className="table-link mono" to={`/purchase-requests/${rfq.purchase_request}`}>{shortId(rfq.purchase_request)}</Link></td><td><StatusPill status={rfq.status} /></td><td>{dateLabel(rfq.deadline_at)}</td></tr>)}</tbody></table></div>{!data.rfqs.length && <p className="inline-empty">Запросов цен пока нет</p>}</section>
      <section className="record-section"><div className="section-heading"><h2>Ближайшие поставки</h2><Link className="text-link" to="/expected-deliveries">Все <ArrowRight size={15} /></Link></div>{upcoming.map((delivery) => <Link className="delivery-summary" key={delivery.id} to={`/purchase-orders/${delivery.purchase_order}`}><Truck size={20} /><div><strong>{orderNames.get(delivery.purchase_order) ?? shortId(delivery.purchase_order)}</strong><span>{dateLabel(delivery.planned_date)}</span></div><StatusPill status={delivery.status} /></Link>)}{!upcoming.length && <p className="inline-empty">Ближайших поставок нет</p>}</section></div>
      <section className="record-section"><div className="section-heading"><h2>Последние заказы</h2><Link className="text-link" to="/purchase-orders">Все заказы <ArrowRight size={15} /></Link></div><div className="table-scroll"><table><thead><tr><th>Номер</th><th>Поставщик</th><th>Сумма</th><th>Статус</th><th>Создан</th></tr></thead><tbody>{data.orders.slice(0, 6).map((order) => <tr key={order.id}><td><Link className="table-link" to={`/purchase-orders/${order.id}`}>{order.number}</Link></td><td><SupplierName id={order.supplier} names={names} /></td><td>{order.total_amount} {order.currency_code}</td><td><StatusPill status={order.status} /></td><td>{dateLabel(order.created_at)}</td></tr>)}</tbody></table></div>{!data.orders.length && <p className="inline-empty">Заказов пока нет</p>}</section>
    </>}</>;
}
