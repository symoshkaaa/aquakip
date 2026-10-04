import { AlertCircle, Inbox, LoaderCircle, RefreshCw } from "lucide-react";

interface LoadStateProps {
  loading: boolean;
  error: string | null;
  empty: boolean;
  onRetry: () => void;
  emptyTitle?: string;
  emptyDetail?: string;
}

export default function LoadState({
  loading,
  error,
  empty,
  onRetry,
  emptyTitle = "Здесь пока пусто",
  emptyDetail = "Когда появятся записи, они отобразятся в этом списке.",
}: LoadStateProps) {
  if (loading) {
    return (
      <div className="state-panel" role="status">
        <LoaderCircle className="state-panel__icon state-panel__icon--spin" size={25} />
        <strong>Загружаем данные</strong>
      </div>
    );
  }

  if (error) {
    return (
      <div className="state-panel state-panel--error" role="alert">
        <AlertCircle className="state-panel__icon" size={25} />
        <strong>{error === "Запись не найдена" ? "Запись не найдена" : "Не удалось получить данные"}</strong>
        <span>{error}</span>
        <button className="button button--secondary" onClick={onRetry} type="button">
          <RefreshCw size={15} /> Повторить
        </button>
      </div>
    );
  }

  if (empty) {
    return (
      <div className="state-panel">
        <Inbox className="state-panel__icon" size={25} />
        <strong>{emptyTitle}</strong>
        <span>{emptyDetail}</span>
      </div>
    );
  }

  return null;
}
