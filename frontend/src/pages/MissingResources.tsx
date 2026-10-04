import { useState } from "react";
import { AlertTriangle, Boxes, ClipboardList, Plus, X } from "lucide-react";
import PageHeading from "../components/PageHeading";

type Resource = "suppliers" | "requests";

const resourceDetails: Record<Resource, { title: string; description: string; endpoints: string[] }> = {
  suppliers: {
    title: "Поставщики",
    description: "Реестр компаний, участвующих в закупочных процедурах.",
    endpoints: ["GET /api/v1/suppliers/", "POST /api/v1/suppliers/"],
  },
  requests: {
    title: "Заявки на закупку",
    description: "Потребности проектов, переданные в закупочную функцию.",
    endpoints: ["GET /api/v1/purchase-requests/", "POST /api/v1/purchase-requests/"],
  },
};

function SupplierFormModal({ onClose }: { onClose: () => void }) {
  return (
    <div className="modal-backdrop" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
      <section aria-labelledby="supplier-modal-title" aria-modal="true" className="modal" role="dialog">
        <div className="modal__heading">
          <div>
            <p className="eyebrow">НОВАЯ ЗАПИСЬ</p>
            <h2 id="supplier-modal-title">Добавить поставщика</h2>
          </div>
          <button aria-label="Закрыть" className="icon-button" onClick={onClose} type="button"><X size={18} /></button>
        </div>
        <div className="endpoint-alert endpoint-alert--compact">
          <AlertTriangle size={18} />
          <span>Форма станет доступна после реализации <code>POST /api/v1/suppliers/</code>. Данные не отправляются и не сохраняются.</span>
        </div>
        <form className="form-grid" onSubmit={(event) => event.preventDefault()}>
          <label>Название<input disabled placeholder="Например, Aqua Supply LLP" /></label>
          <label>Код поставщика<input disabled placeholder="SUP-001" /></label>
          <label>БИН<input disabled placeholder="12 цифр" /></label>
          <label>Тип поставщика<input disabled placeholder="manufacturer" /></label>
          <div className="modal__actions">
            <button className="button button--secondary" onClick={onClose} type="button">Закрыть</button>
            <button className="button button--primary" disabled type="submit">Сохранить</button>
          </div>
        </form>
      </section>
    </div>
  );
}

export default function MissingResources({ resource }: { resource: Resource }) {
  const [modalOpen, setModalOpen] = useState(false);
  const details = resourceDetails[resource];
  const Icon = resource === "suppliers" ? Boxes : ClipboardList;

  return (
    <>
      <PageHeading
        title={details.title}
        description={details.description}
        action={resource === "suppliers" ? (
          <button className="button button--primary" onClick={() => setModalOpen(true)} type="button">
            <Plus size={16} /> Добавить поставщика
          </button>
        ) : undefined}
      />

      <section className="surface resource-placeholder">
        <div className="resource-placeholder__icon"><Icon size={21} /></div>
        <div className="resource-placeholder__content">
          <p className="eyebrow">BACKEND INTEGRATION · TODO</p>
          <h2>Endpoint пока не реализован</h2>
          <p className="page-description">
            Backend router сейчас публикует только RFQ и Supplier Offers. Этот раздел не подставляет демонстрационные записи и не отправляет запросы в несуществующий endpoint.
          </p>
          <div className="endpoint-list" aria-label="Отсутствующие endpoints">
            {details.endpoints.map((endpoint) => <code key={endpoint}>{endpoint}</code>)}
          </div>
        </div>
      </section>

      {resource === "suppliers" && (
        <section className="surface resource-table">
          <div className="surface__heading">
            <div><p className="eyebrow">РЕЕСТР</p><h2>Все поставщики</h2></div>
            <span className="count-chip">0 записей · API недоступен</span>
          </div>
          <div className="table-scroll">
            <table>
              <thead><tr><th>Поставщик</th><th>БИН</th><th>Тип</th><th>Статус</th><th>Рейтинг</th></tr></thead>
              <tbody><tr><td colSpan={5}>
                <div className="table-empty">Список появится после подключения GET endpoint поставщиков.</div>
              </td></tr></tbody>
            </table>
          </div>
        </section>
      )}

      {resource === "requests" && (
        <section className="surface resource-table">
          <div className="surface__heading">
            <div><p className="eyebrow">ЗАКУПОЧНЫЕ ПОТРЕБНОСТИ</p><h2>Заявки</h2></div>
            <span className="count-chip">Ожидается API</span>
          </div>
          <div className="table-scroll">
            <table>
              <thead><tr><th>Заявка</th><th>Проект</th><th>Версия спецификации</th><th>Создана</th><th>Статус</th></tr></thead>
              <tbody><tr><td colSpan={5}>
                <div className="table-empty">Список и создание заявок требуют недостающих GET/POST endpoints.</div>
              </td></tr></tbody>
            </table>
          </div>
        </section>
      )}

      {modalOpen && <SupplierFormModal onClose={() => setModalOpen(false)} />}
    </>
  );
}