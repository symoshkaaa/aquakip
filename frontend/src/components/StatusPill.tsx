const labels: Record<string, string> = {
  draft: "Черновик",
  open: "Открыт",
  closed: "Закрыт",
  cancelled: "Отменен",
  pending: "Ожидает",
  sent: "Отправлен",
  delivered: "Доставлен",
  failed: "Ошибка",
  received: "Получено",
  verified: "Проверено",
  accepted: "Принято",
  rejected: "Отклонено",
  expired: "Истекло",
  submitted: "На рассмотрении",
  approved: "Одобрено",
  ordered: "Заказано",
  active: "Активен",
  inactive: "Неактивен",
  blocked: "Заблокирован",
  expected: "Ожидается",
  in_transit: "В пути",
  delayed: "Задерживается",
  requested: "Запрошен",
  technical_review: "Техническая проверка",
  technically_approved: "Технически одобрен",
  technically_rejected: "Технически отклонён",
  unknown: "Не уточнено",
  in_stock: "В наличии",
  on_order: "Под заказ",
  out_of_stock: "Нет в наличии",
  not_reviewed: "Не проверено",
  match: "Соответствует",
  partial: "Частично",
  mismatch: "Не соответствует",
};

export default function StatusPill({ status }: { status: string }) {
  return (
    <span className={`status-pill status-pill--${status}`}>
      <span className="status-pill__dot" />
      {labels[status] ?? status.replaceAll("_", " ")}
    </span>
  );
}
