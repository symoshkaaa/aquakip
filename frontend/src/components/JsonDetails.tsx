import type { JsonValue } from "../types/procurement";

const labels: Record<string, string> = {
  supplier_id: "Поставщик", selected_supplier_id: "Выбранный поставщик", selected_offer_id: "Выбранное предложение",
  offer_id: "Предложение", offers: "Предложения", items: "Позиции", price: "Цена", unit_price: "Цена за единицу",
  quantity: "Количество", delivery: "Доставка", delivery_days: "Срок, дней", availability: "Наличие",
  technical_match: "Техническое соответствие", score: "Оценка", currency_code: "Валюта",
  nomenclature_id: "Номенклатура", carrier: "Перевозчик", tracking_number: "Номер отслеживания", received_by: "Получатель",
};

export default function JsonDetails({ value, suppliers = new Map<string, string>() }: { value: JsonValue; suppliers?: Map<string, string> }) {
  if (value === null) return <span className="muted">-</span>;
  if (typeof value !== "object") return <span className="json-value">{typeof value === "boolean" ? (value ? "Да" : "Нет") : (typeof value === "string" ? (suppliers.get(value) ?? value) : String(value))}</span>;
  if (Array.isArray(value)) return value.length ? <div className="json-array">{value.map((entry, index) => <div className="json-array__row" key={index}><span className="json-index">{index + 1}</span><JsonDetails value={entry} suppliers={suppliers} /></div>)}</div> : <span className="muted">Нет записей</span>;
  return Object.keys(value).length ? <dl className="json-details">{Object.entries(value).map(([key, entry]) => <div key={key}><dt>{labels[key] ?? key.replaceAll("_", " ")}</dt><dd><JsonDetails value={entry} suppliers={suppliers} /></dd></div>)}</dl> : <span className="muted">Нет данных</span>;
}
