import { test, expect, type Page } from "@playwright/test";
import { randomUUID } from "node:crypto";

const screens = [
  ["/dashboard", "Обзор", "Обзор закупок"],
  ["/suppliers", "Поставщики", "Поставщики"],
  ["/purchase-requests", "Заявки на закупку", "Заявки на закупку"],
  ["/rfqs", "RFQ", "RFQ"],
  ["/supplier-offers", "Предложения", "Предложения поставщиков"],
  ["/supplier-comparisons", "Сравнения", "Сравнения предложений"],
  ["/purchase-orders", "Заказы поставщикам", "Заказы поставщикам"],
  ["/alternative-requests", "Запросы на аналоги", "Запросы на аналоги"],
  ["/expected-deliveries", "Ожидаемые поставки", "Ожидаемые поставки"],
] as const;

async function loaded(page: Page) {
  await expect(page.getByRole("status")).toHaveCount(0);
  await expect(page.getByRole("alert")).toHaveCount(0);
}

async function fitsViewport(page: Page) {
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
}

async function saveRecord(page: Page, endpoint: string) {
  const response = page.waitForResponse((response) =>
    response.url().split("?")[0].endsWith(`/api/v1/${endpoint}/`) && response.request().method() === "POST");
  await page.getByRole("button", { name: "Сохранить", exact: true }).click();
  const result = await response;
  expect(result.status(), await result.text()).toBe(201);
  const record = await result.json();
  await expect(page).toHaveURL(new RegExp(`/${endpoint}/${record.id}$`));
  await loaded(page);
  return record;
}

test("all nine sections use real API, active navigation and responsive layouts", async ({ page }, testInfo) => {
  const errors: string[] = [];
  const ports: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("request", (request) => ports.push(new URL(request.url()).port));
  await page.goto("/dashboard");
  for (const [path, label, heading] of screens) {
    if (testInfo.project.name === "mobile") await page.getByRole("button", { name: "Открыть навигацию" }).click();
    await page.getByRole("navigation").getByRole("link", { name: label, exact: true }).click();
    await expect(page).toHaveURL(new RegExp(`${path}$`));
    await expect(page.getByRole("heading", { name: heading, exact: true, level: 1 })).toBeVisible();
    await loaded(page);
    await expect(page.locator(`nav a[href="${path}"]`)).toHaveAttribute("aria-current", "page");
    await fitsViewport(page);
    await page.screenshot({ path: testInfo.outputPath(`${path.slice(1)}.png`), fullPage: true });
  }
  expect(errors).toEqual([]);
  expect(ports).not.toContain("5500");
});

test("seeded detail pages, comparison JSON and early delivery reason", async ({ page, request }, testInfo) => {
  for (const resource of ["suppliers", "purchase-requests", "rfqs", "supplier-offers", "supplier-comparisons", "purchase-orders"]) {
    const result = await request.get(`/api/v1/${resource}/`);
    expect(result.ok()).toBe(true);
    const record = (await result.json()).results[0];
    expect(record).toBeTruthy();
    await page.goto(`/${resource}/${record.id}`);
    await loaded(page);
    await expect(page.locator("main h1")).toBeVisible();
    if (resource === "supplier-comparisons") {
      await expect(page.getByRole("heading", { name: "Критерии", exact: true })).toBeVisible();
      await expect(page.getByRole("heading", { name: "Результат сравнения" })).toBeVisible();
      await expect(page.locator(".json-details").first()).toBeVisible();
    }
    await fitsViewport(page);
    await page.screenshot({ path: testInfo.outputPath(`${resource}-detail.png`), fullPage: true });
  }
  await page.goto("/expected-deliveries");
  await loaded(page);
  await expect(page.getByText("Earlier delivery window agreed")).toBeVisible();
  await page.getByText("Данные доставки", { exact: true }).first().click();
  await expect(page.locator("details[open]")).toBeVisible();
  await fitsViewport(page);
});

test("supplier search, empty state and loading state", async ({ page }) => {
  await page.route("**/api/v1/suppliers/**", async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 300));
    await route.continue();
  });
  await page.goto("/suppliers");
  await expect(page.getByRole("status")).toBeVisible();
  await loaded(page);
  await page.getByLabel("Поиск поставщиков").fill("Aqua Supply");
  await page.getByRole("button", { name: "Поиск", exact: true }).click();
  await loaded(page);
  await expect(page.locator("tbody tr")).toHaveCount(1);
  await expect(page.locator("tbody")).toContainText("Aqua Supply");
  await page.getByLabel("Статус поставщика").selectOption("blocked");
  await loaded(page);
  await expect(page.getByText("Здесь пока пусто", { exact: true })).toBeVisible();
});

test("400 validation comes from actual API without exposing server internals", async ({ page }) => {
  await page.goto("/suppliers/new");
  await page.getByLabel("Название", { exact: true }).fill("Duplicate validation check");
  await page.getByLabel("Код", { exact: true }).fill("DEMO-SUP-001");
  const response = page.waitForResponse((response) => response.url().endsWith("/api/v1/suppliers/") && response.request().method() === "POST");
  await page.getByRole("button", { name: "Сохранить", exact: true }).click();
  expect((await response).status()).toBe(400);
  await expect(page.getByRole("alert")).toContainText("Код");
  await expect(page.getByRole("alert")).not.toContainText(/Traceback|<html|File "/i);
});

test("404, HTML 500 and JSON conflict are safe user-facing errors", async ({ page }) => {
  const missing = "00000000-0000-4000-8000-000000000000";
  await page.goto(`/rfqs/${missing}`);
  await expect(page.getByRole("alert")).toContainText("Запись не найдена");
  await page.route(`**/api/v1/rfqs/${missing}/`, (route) => route.fulfill({
    status: 500, contentType: "text/html", body: '<html><body>Traceback secret File "settings.py", line 1</body></html>',
  }));
  await page.reload();
  await expect(page.getByRole("alert")).toContainText("Ошибка сервера");
  await expect(page.locator("main")).not.toContainText(/Traceback|secret|settings.py/);
  await page.route("**/api/v1/suppliers/", (route) => route.request().method() === "POST"
    ? route.fulfill({ status: 409, json: { detail: "Конфликт: запись уже существует" } }) : route.continue());
  await page.goto("/suppliers/new");
  await page.getByLabel("Название", { exact: true }).fill("Conflict check");
  await page.getByLabel("Код", { exact: true }).fill(`CONFLICT-${Date.now()}`);
  await page.getByRole("button", { name: "Сохранить", exact: true }).click();
  await expect(page.getByRole("alert")).toHaveText("Конфликт: запись уже существует");
});

test("real PurchaseRequest -> RFQ -> Offer -> Comparison -> Order -> Approve -> Send", async ({ page, request }, testInfo) => {
  test.skip(testInfo.project.name !== "desktop", "Mutating workflow runs once against the real database");
  const code = `E2E-${Date.now()}`;
  const supplierName = `E2E Supplier ${code}`;
  const projectId = randomUUID();
  const nomenclatureIds = [randomUUID(), randomUUID()];

  await page.goto("/suppliers/new");
  await page.getByLabel("Название", { exact: true }).fill(supplierName);
  await page.getByLabel("Код", { exact: true }).fill(code);
  await page.getByLabel("Рейтинг", { exact: true }).fill("4.5");
  const supplier = await saveRecord(page, "suppliers");

  await page.goto("/purchase-requests/new");
  await page.getByLabel("Проект", { exact: true }).fill(projectId);
  await page.getByLabel("Версия спецификации", { exact: true }).fill(randomUUID());
  await page.getByLabel("Автор", { exact: true }).fill(randomUUID());
  await page.getByLabel("Комментарий", { exact: true }).fill(code);
  await page.getByRole("button", { name: "Добавить позицию", exact: true }).click();
  for (let i = 0; i < 2; i++) {
    const row = page.locator(".line-editor").nth(i);
    await row.getByLabel("Описание", { exact: true }).fill(`E2E Item ${i + 1}`);
    await row.getByLabel("Номенклатура", { exact: true }).fill(nomenclatureIds[i]);
    await row.getByLabel("Количество", { exact: true }).fill(String(i + 1));
    await row.getByLabel("Единица измерения", { exact: true }).fill(randomUUID());
    await row.getByLabel("Бюджетная цена", { exact: true }).fill("150");
    await row.getByLabel("Нужна к", { exact: true }).fill("2027-01-20");
  }
  const purchaseRequest = await saveRecord(page, "purchase-requests");
  expect(purchaseRequest.items).toHaveLength(2);
  await page.getByRole("link", { name: "Создать RFQ", exact: true }).click();
  await expect(page.getByLabel("Заявка на закупку", { exact: true })).toHaveValue(purchaseRequest.id);
  await page.getByLabel("Статус", { exact: true }).selectOption("open");
  await page.getByLabel("Срок ответа", { exact: true }).fill("2027-01-10T12:30");
  const rfq = await saveRecord(page, "rfqs");
  expect(rfq.purchase_request).toBe(purchaseRequest.id);
  expect(new Date(rfq.deadline_at).toISOString()).toBe("2027-01-10T07:30:00.000Z");

  await page.getByRole("button", { name: "Добавить поставщика", exact: true }).click();
  await page.getByLabel("Поставщик", { exact: true }).selectOption(supplier.id);
  await page.getByRole("button", { name: "Добавить", exact: true }).click();
  await expect(page.locator("tbody").first()).toContainText(supplierName);
  await page.getByRole("link", { name: "Новое предложение", exact: true }).click();
  await expect(page.getByLabel("RFQ", { exact: true })).toHaveValue(rfq.id);
  await page.getByLabel("Поставщик", { exact: true }).selectOption(supplier.id);
  await page.getByRole("button", { name: "Добавить позицию", exact: true }).click();
  for (let i = 0; i < 2; i++) {
    const row = page.locator(".line-editor").nth(i);
    await row.getByLabel("Позиция заявки", { exact: true }).selectOption(purchaseRequest.items[i].id);
    await row.getByLabel("Количество", { exact: true }).fill(String(i + 1));
    await row.getByLabel("Цена за единицу", { exact: true }).fill(i === 0 ? "100.1234" : "200");
    await row.getByLabel("Наличие", { exact: true }).selectOption("in_stock");
    await row.getByLabel("Доставка, дней", { exact: true }).fill("5");
    await row.getByLabel("Техническое соответствие", { exact: true }).selectOption("match");
  }
  const offer = await saveRecord(page, "supplier-offers");
  expect(offer.items).toHaveLength(2);
  await page.goto(`/rfqs/${rfq.id}`);
  await loaded(page);
  await page.getByRole("link", { name: "Сравнить предложения", exact: true }).click();
  await page.getByLabel("Выбранное предложение", { exact: true }).selectOption(offer.id);
  const comparison = await saveRecord(page, "supplier-comparisons");
  expect(comparison.result.selected_offer_id).toBe(offer.id);
  expect(comparison.result.offers[0].items[0].unit_price).toBe("100.1234");
  await expect(page.locator("main")).toContainText(supplierName);
  await fitsViewport(page);
  await page.screenshot({ path: testInfo.outputPath("comparison-created.png"), fullPage: true });

  await page.getByRole("link", { name: "Создать заказ", exact: true }).click();
  await expect(page.getByLabel("Поставщик", { exact: true })).toHaveValue(supplier.id);
  await expect(page.getByLabel("Проект", { exact: true })).toHaveValue(projectId);
  await expect(page.locator(".line-editor")).toHaveCount(2);
  await page.getByLabel("Номер заказа", { exact: true }).fill(code);
  const order = await saveRecord(page, "purchase-orders");
  expect(order.total_amount).toBe("500.1234");
  await expect(page.getByRole("button", { name: "Отправить", exact: true })).toHaveCount(0);
  await page.getByRole("button", { name: "Одобрить", exact: true }).click();
  await expect(page.getByRole("button", { name: "Отправить", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Одобрить", exact: true })).toHaveCount(0);
  await page.getByRole("button", { name: "Отправить", exact: true }).click();
  await expect(page.locator(".page-heading .status-pill")).toHaveText("Отправлен");
  await expect(page.getByRole("button", { name: "Отправить", exact: true })).toHaveCount(0);
  await page.reload();
  await loaded(page);
  const persisted = await (await request.get(`/api/v1/purchase-orders/${order.id}/`)).json();
  expect(persisted.status).toBe("sent");
  expect(persisted.approved_at).toBeTruthy();
  expect(persisted.sent_at).toBeTruthy();
  await page.screenshot({ path: testInfo.outputPath("order-sent.png"), fullPage: true });
});
