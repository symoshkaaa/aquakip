import { Link } from "react-router-dom";
import { Id, shortId, TableState } from "../components/RecordUI";
import PageHeading from "../components/PageHeading";
import StatusPill from "../components/StatusPill";
import { usePagedResource } from "../hooks/usePagedResource";
import { useLookups } from "../hooks/useResource";
import type { AlternativeRequestDto } from "../types/procurement";

export default function AlternativeRequests() {
  const state = usePagedResource<AlternativeRequestDto>("alternative-requests/");
  const lookups = useLookups();
  return <><PageHeading title="Запросы на аналоги" />
    <TableState state={state}><table><thead><tr><th>Исходная номенклатура</th><th>Альтернативная номенклатура</th><th>Заявка</th><th>Статус</th><th>Техническая проверка</th><th>Решение клиента</th></tr></thead><tbody>{state.page?.results.map((alternative) => {
      const request = lookups.requests.find((entry) => entry.items.some((item) => item.id === alternative.request_item));
      return <tr key={alternative.id}><td><Id value={alternative.original_nomenclature_id} /></td><td><Id value={alternative.alternative_nomenclature_id} /></td><td>{request ? <Link className="table-link" to={`/purchase-requests/${request.id}`}>{shortId(request.id)}</Link> : <Id value={alternative.request_item} />}</td><td><StatusPill status={alternative.status} /></td><td>{alternative.technical_review_id ? <Id value={alternative.technical_review_id} /> : "-"}</td><td>{alternative.client_decision ? <StatusPill status={alternative.client_decision} /> : "-"}</td></tr>;
    })}</tbody></table></TableState></>;
}
