from sqlalchemy import select

from app.models import EvaluationRun
from app.pagination import sql_page


class EvaluationService:
    def __init__(self, session_factory) -> None:
        self._session_factory = session_factory

    @staticmethod
    def _dict(item: EvaluationRun, *, include_details: bool = False) -> dict:
        return {
            "id": str(item.id), "name": item.name, "dataset_version": item.dataset_version,
            "case_count": item.case_count, "metrics": item.metrics,
            "details": item.details if include_details else [],
            "created_by": item.created_by, "created_at": item.created_at,
        }

    def create(self, *, name: str, dataset_version: str, case_count: int, metrics: dict, details: list, created_by: str) -> dict:
        with self._session_factory() as session:
            item = EvaluationRun(
                name=name, dataset_version=dataset_version, case_count=case_count,
                metrics=metrics, details=details, created_by=created_by,
            )
            session.add(item)
            session.commit()
            session.refresh(item)
            return self._dict(item, include_details=True)

    def list(self, *, limit: int = 20, page: int | None = None, page_size: int = 10) -> list[dict] | dict:
        with self._session_factory() as session:
            query = select(EvaluationRun).order_by(EvaluationRun.created_at.desc(), EvaluationRun.id.desc())
            if page is not None:
                return sql_page(session, query, page=page, page_size=page_size, mapper=self._dict)
            items = session.scalars(query.limit(limit)).all()
            return [self._dict(item) for item in items]

    def get(self, run_id) -> dict | None:
        with self._session_factory() as session:
            item = session.get(EvaluationRun, run_id)
            return self._dict(item, include_details=True) if item else None
