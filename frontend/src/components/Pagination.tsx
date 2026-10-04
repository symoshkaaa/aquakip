import { ArrowLeft, ArrowRight } from "lucide-react";
import type { ApiPage } from "../types/procurement";

interface PaginationProps {
  page: ApiPage<unknown>;
  onNavigate: (url: string | null) => void;
}

export default function Pagination({ page, onNavigate }: PaginationProps) {
  return (
    <div className="pagination">
      <span>Всего записей: <strong>{page.count}</strong></span>
      <div className="pagination__actions">
        <button
          aria-label="Предыдущая страница"
          className="icon-button"
          disabled={!page.previous}
          onClick={() => onNavigate(page.previous)}
          type="button"
        >
          <ArrowLeft size={16} />
        </button>
        <button
          aria-label="Следующая страница"
          className="icon-button"
          disabled={!page.next}
          onClick={() => onNavigate(page.next)}
          type="button"
        >
          <ArrowRight size={16} />
        </button>
      </div>
    </div>
  );
}