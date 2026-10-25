import { useIsFetching } from "@tanstack/react-query";
import { endCollection, useCollection } from "../features/collection/collectionStore";

// Global activity indicator:
//  - a thin top bar that animates whenever ANY react-query fetch is in flight
//  - a floating toast while a background collection job is running (Celery work
//    that continues after the HTTP call returned)
export function TopProgress() {
  const fetching = useIsFetching();
  const collection = useCollection();
  const busy = fetching > 0 || !!collection;

  return (
    <>
      <div className={`top-progress${busy ? " active" : ""}`} aria-hidden="true" />
      {collection && (
        <div className="collect-toast" role="status" aria-live="polite">
          <span className="spinner" />
          <div>
            <strong>Идёт сбор и анализ</strong>
            <div className="muted small">
              «{collection.label}» — ролики, речь, OCR, риск. Список обновится сам, как будут готовы.
            </div>
          </div>
          <button className="icon-btn" onClick={endCollection} title="Скрыть" aria-label="Скрыть">✕</button>
        </div>
      )}
    </>
  );
}
