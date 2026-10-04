import axios from "axios";

const configuredApiUrl = import.meta.env.VITE_API_URL || "/api/v1/";
const configuredUrl = new URL(configuredApiUrl, window.location.origin);
const apiPath = `${configuredUrl.pathname.replace(/\/$/, "")}/`;

export const api = axios.create({
  baseURL: import.meta.env.DEV ? apiPath : `${configuredUrl.origin}${apiPath}`,
  headers: { Accept: "application/json" },
  timeout: 12000,
});

const fieldLabels: Record<string, string> = {
  quantity: "Количество", unit_price: "Цена", items: "Позиции", number: "Номер",
  supplier: "Поставщик", rfq: "RFQ", purchase_request: "Заявка", project_id: "Проект",
  nomenclature_id: "Номенклатура", unit_id: "Единица", version: "Версия",
  name: "Название", code: "Код", email: "Email", status: "Статус",
  valid_until: "Срок действия", currency_code: "Валюта", budget_price: "Бюджетная цена",
  request_item: "Позиция заявки", early_delivery_reason: "Обоснование", total_amount: "Сумма",
};

function safeMessage(value: unknown): string | null {
  if (typeof value !== "string") return null;
  if (/<\/?[a-z!][^>]*>|traceback|stacktrace|\bat\s+\S+\s*\([^)]*:\d+|File\s+".*",\s+line/i.test(value)) return null;
  return value.slice(0, 600);
}

function validationMessages(value: unknown, path = ""): string[] {
  const text = safeMessage(value);
  if (text) return [path ? `${path}: ${text}` : text];
  if (Array.isArray(value)) return value.flatMap((entry, index) =>
    validationMessages(entry, entry && typeof entry === "object" ? `${path} ${index + 1}` : path));
  if (value && typeof value === "object") return Object.entries(value).flatMap(([key, entry]) =>
    validationMessages(entry, [path, ["detail", "non_field_errors", "__all__"].includes(key) ? "" : (fieldLabels[key] ?? key)].filter(Boolean).join(" / ")));
  return [];
}

export function getApiError(error: unknown): string {
  if (axios.isAxiosError(error)) {
    const status = error.response?.status;
    if (status === 404) return "Запись не найдена";
    if (status && status >= 500) return "Ошибка сервера";
    if (error.code === "ECONNABORTED") return "Превышено время ожидания. Попробуйте ещё раз.";
    if (!error.response) return "Нет соединения с сервером. Попробуйте ещё раз.";
    const data: unknown = error.response.data;
    const messages = typeof data === "object" ? validationMessages(data) : [];
    if (status === 409) return messages.join(" · ") || "Конфликт данных. Обновите запись и повторите действие.";
    if (status === 400) return messages.join(" · ") || "Проверьте введённые данные.";
    if (status === 403) return "Недостаточно прав для этого действия.";
    return messages.join(" · ") || "Не удалось выполнить запрос.";
  }
  if (error instanceof SyntaxError) return "Некорректный JSON. Проверьте критерии и результат.";
  return "Не удалось выполнить действие. Попробуйте ещё раз.";
}
