from sqlalchemy import func, select


def sql_page(session, statement, *, page: int, page_size: int, mapper, scalar: bool = True) -> dict:
    """Count the authorized query and fetch only the requested, stably ordered window."""
    query = statement.limit(None).offset(None)
    total = int(session.scalar(select(func.count()).select_from(query.order_by(None).subquery())) or 0)
    window = query.offset((page - 1) * page_size).limit(page_size)
    rows = session.scalars(window).all() if scalar else session.execute(window).all()
    return {"items": [mapper(row) for row in rows], "total": total, "page": page, "page_size": page_size}
