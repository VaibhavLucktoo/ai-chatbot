"""Atomic metric inserts and SQL aggregation; no private content is retained."""
from datetime import datetime, timedelta, timezone
from uuid import UUID
from sqlalchemy import and_, case, func, insert, select, text
from app.storage.models import ChatMetric as R, ModelCallMetric as C


async def write_metrics(database, batch):
    async with database.transaction() as connection:
        await connection.execute(insert(R), [request for request, _ in batch])
        calls = [call for _, request_calls in batch for call in request_calls]
        if calls:
            await connection.execute(insert(C), calls)


def count_where(condition):
    return func.count().filter(condition)


def latency(column):
    return {"average_ms": func.avg(column),
            "median_ms": func.percentile_cont(0.5).within_group(column),
            "p95_ms": func.percentile_cont(0.95).within_group(column)}


def rounded(value):
    return round(float(value), 2) if value is not None else None


def call_totals():
    return dict(attempts=func.count(), provider_requests=count_where(C.provider_requested.is_(True)),
                succeeded=count_where(C.status == "success"), failed=count_where(C.status == "error"),
                cancelled=count_where(C.status == "cancelled"), rate_limited=count_where(C.http_status == 429),
                usage_available_calls=count_where(and_(C.input_tokens.is_not(None), C.output_tokens.is_not(None))),
                total_reported_calls=count_where(C.total_tokens.is_not(None)),
                input_tokens=func.sum(C.input_tokens), output_tokens=func.sum(C.output_tokens), total_tokens=func.sum(C.total_tokens),
                priced_calls=count_where(C.estimated_cost_usd.is_not(None)), estimated_cost_usd=func.sum(C.estimated_cost_usd),
                average_ms=func.avg(C.duration_ms), p95_ms=func.percentile_cont(0.95).within_group(C.duration_ms),
                average_queue_ms=func.avg(C.queue_ms), average_provider_ms=func.avg(C.provider_ms))


def serialize_call_totals(row):
    result = dict(row)
    for name in ("average_ms", "p95_ms", "average_queue_ms", "average_provider_ms"):
        result[name] = rounded(result[name])
    result["estimated_cost_usd"] = float(result["estimated_cost_usd"]) if result["estimated_cost_usd"] is not None else None
    result["usage_complete"] = result["usage_available_calls"] == result["provider_requests"]
    result["cost_complete"] = result["priced_calls"] == result["provider_requests"]
    return result


async def read_metrics(database, *, hours=24, model=None, assistant_id: UUID | None = None,
                       workspace_only: bool = False, provider: str | None = None, offset=0, limit=25):
    until = datetime.now(timezone.utc)
    since = until - timedelta(hours=hours)
    request_filter = [R.started_at >= since, R.started_at <= until]
    selected_calls = []
    if model is not None:
        selected_calls.append(C.model == model)
    if provider is not None:
        selected_calls.append(C.provider == provider)
    if selected_calls:
        request_filter.append(R.id.in_(select(C.request_id).where(*selected_calls)))
    if assistant_id is not None:
        request_filter.append(R.assistant_id == assistant_id)
    if workspace_only:
        request_filter.append(R.assistant_id.is_(None))
    call_filter = [*request_filter, *selected_calls]
    async with database.transaction() as connection:
        # All totals, charts and recent rows describe the same committed snapshot.
        await connection.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"))
        counts = (await connection.execute(select(
            func.count().label("total"),
            count_where(and_(R.http_status >= 200, R.http_status < 300, R.outcome != "cancelled")).label("successful"),
            count_where(R.outcome == "cancelled").label("cancelled"),
            count_where(R.retrieval_performed.is_(True)).label("retrieval_requests"),
            func.avg(R.result_count).filter(R.retrieval_performed.is_(True)).label("average_results"),
            func.avg(R.source_count).filter(R.outcome == "answered").label("average_sources"),
            *[expression.label(name) for name, expression in latency(R.duration_ms).items()],
            func.avg(R.graph_ms).label("average_graph_ms"),
        ).where(*request_filter))).mappings().one()
        requests = dict(counts)
        requests["unsuccessful"] = requests["total"] - requests["successful"]
        requests["success_rate"] = round(100 * requests["successful"] / requests["total"], 2) if requests["total"] else None
        for name in ("average_ms", "median_ms", "p95_ms", "average_graph_ms", "average_results", "average_sources"):
            requests[name] = rounded(requests[name])
        outcomes = dict((await connection.execute(select(R.outcome, func.count()).where(*request_filter).group_by(R.outcome))).all())
        intents = dict((await connection.execute(select(R.intent, func.count()).where(*request_filter, R.intent.is_not(None)).group_by(R.intent))).all())
        total_columns = call_totals()
        columns = [expression.label(name) for name, expression in total_columns.items()]
        call_statement = select(*columns).select_from(C).join(R, R.id == C.request_id).where(*call_filter)
        calls = serialize_call_totals((await connection.execute(call_statement)).mappings().one())
        model_rows = (await connection.execute(select(C.model, C.provider, *columns).join(R, R.id == C.request_id)
                       .where(*call_filter).group_by(C.model, C.provider).order_by(func.count().desc()))).mappings().all()
        models = [dict(model=row["model"], provider=row["provider"], **serialize_call_totals({key: row[key] for key in total_columns})) for row in model_rows]
        stage_rows = (await connection.execute(select(C.stage, *columns).join(R, R.id == C.request_id)
                       .where(*call_filter).group_by(C.stage).order_by(C.stage))).mappings().all()
        call_stages = [dict(stage=row["stage"], **serialize_call_totals({key: row[key] for key in total_columns})) for row in stage_rows]
        # Aggregate calls once per request before joining: review/follow-up calls
        # must never multiply request counts or distort request percentiles.
        per_request = select(C.request_id,
            func.count().label("attempts"),
            count_where(C.provider_requested.is_(True)).label("provider_requests"),
            count_where(C.status == "error").label("failed_calls"),
            func.sum(C.input_tokens).label("input_tokens"),
            func.sum(C.output_tokens).label("output_tokens"),
            func.sum(C.estimated_cost_usd).label("estimated_cost_usd"),
            count_where(C.estimated_cost_usd.is_not(None)).label("priced_calls"),
            count_where(and_(C.input_tokens.is_not(None), C.output_tokens.is_not(None))).label("usage_available_calls"),
        ).where(*selected_calls).group_by(C.request_id).subquery()
        identity = [R.assistant_id, R.assistant_name, R.assistant_revision, R.connection_id,
                    R.connection_revision, R.configured_provider, R.configured_model]
        comparison_rows = (await connection.execute(select(*identity,
            func.count().label("requests"),
            count_where(and_(R.http_status >= 200, R.http_status < 300, R.outcome != "cancelled")).label("successful"),
            *[expression.label(name) for name, expression in latency(R.duration_ms).items()],
            *[func.sum(per_request.c[name]).label(name) for name in (
                "attempts", "provider_requests", "failed_calls", "input_tokens", "output_tokens",
                "estimated_cost_usd", "priced_calls", "usage_available_calls")],
        ).select_from(R).outerjoin(per_request, per_request.c.request_id == R.id)
            .where(*request_filter).group_by(*identity).order_by(func.count().desc(), R.assistant_id,
                                                               R.assistant_revision, R.connection_revision))).mappings().all()
        assistants = []
        for row in comparison_rows:
            item = dict(row)
            for name in ("assistant_id", "connection_id"):
                item[name] = str(item[name]) if item[name] is not None else None
            for name in ("average_ms", "median_ms", "p95_ms"):
                item[name] = rounded(item[name])
            for name in ("attempts", "provider_requests", "failed_calls", "priced_calls", "usage_available_calls"):
                item[name] = item[name] or 0
            item["success_rate"] = round(100 * item["successful"] / item["requests"], 2)
            item["estimated_cost_usd"] = float(item["estimated_cost_usd"]) if item["estimated_cost_usd"] is not None else None
            item["cost_complete"] = item["priced_calls"] == item["provider_requests"]
            item["usage_complete"] = item["usage_available_calls"] == item["provider_requests"]
            assistants.append(item)
        # Fixed JSON timing keys are numeric application measurements, never source text.
        workflow_stages = {}
        from app.services.metrics import NODES
        stage_columns = [func.avg(R.stage_timings_ms[name].as_float()).label(name) for name in sorted(NODES)]
        stage_values = (await connection.execute(select(*stage_columns).where(*request_filter))).mappings().one()
        workflow_stages = {name: rounded(value) for name, value in stage_values.items() if value is not None}
        bucket = func.date_trunc("hour" if hours <= 48 else "day", R.started_at)
        timeline = [{"at": row.at.isoformat(), "requests": row.requests, "unsuccessful": row.unsuccessful,
                     "average_ms": rounded(row.average_ms)} for row in (await connection.execute(select(
            bucket.label("at"), func.count().label("requests"),
            count_where((R.http_status >= 400) | (R.outcome == "cancelled") | R.http_status.is_(None)).label("unsuccessful"),
            func.avg(R.duration_ms).label("average_ms"),
        ).where(*request_filter).group_by(bucket).order_by(bucket))).all()]
        recent_rows = (await connection.execute(select(R).where(*request_filter).order_by(R.started_at.desc(), R.id)
                                               .offset(offset).limit(limit))).mappings().all()
        ids = [row["id"] for row in recent_rows]
        call_order = case((C.stage == "follow_up", 0), (C.stage == "answer", 1), (C.stage == "review", 2), else_=3)
        recent_calls = (await connection.execute(select(C).where(C.request_id.in_(ids)).order_by(call_order, C.id))).mappings().all() if ids else []
        call_map = {identifier: [] for identifier in ids}
        for row in recent_calls:
            call = dict(row)
            call.pop("request_id")
            call["id"] = str(call["id"])
            call["estimated_cost_usd"] = float(call["estimated_cost_usd"]) if call["estimated_cost_usd"] is not None else None
            call_map[row["request_id"]].append(call)
        recent = []
        for row in recent_rows:
            item = dict(row)
            item["id"], item["instance_id"] = str(row["id"]), str(row["instance_id"])
            item["started_at"] = row["started_at"].isoformat()
            for name in ("assistant_id", "connection_id"):
                item[name] = str(item[name]) if item[name] is not None else None
            item["calls"] = call_map[row["id"]]
            recent.append(item)
        model_choices = list((await connection.execute(select(C.model).join(R, R.id == C.request_id).where(
            R.started_at >= since, R.started_at <= until, C.model.is_not(None)).distinct().order_by(C.model))).scalars())
        minute_requests = await connection.scalar(select(func.count()).select_from(R).where(*request_filter, R.started_at >= until - timedelta(minutes=1)))
        provider_choices = list((await connection.execute(select(C.provider).join(R, R.id == C.request_id).where(
            R.started_at >= since, R.started_at <= until, C.provider.is_not(None)).distinct().order_by(C.provider))).scalars())
        choice_rows = (await connection.execute(select(R.assistant_id, R.assistant_name).where(
            R.started_at >= since, R.started_at <= until, R.assistant_id.is_not(None))
            .distinct(R.assistant_id).order_by(R.assistant_id, R.started_at.desc(), R.id))).all()
        assistant_choices = [{"id": str(row.assistant_id), "name": row.assistant_name or str(row.assistant_id)} for row in choice_rows]
    return {"window": {"since": since.isoformat(), "until": until.isoformat(), "hours": hours, "model": model,
                       "assistant_id": str(assistant_id) if assistant_id else None,
                       "workspace_only": workspace_only, "provider": provider},
            "requests": requests, "outcomes": outcomes, "intents": intents, "calls": calls, "models": models,
            "assistants": assistants, "available_assistants": assistant_choices, "available_providers": provider_choices,
            "call_stages": call_stages, "workflow_stages_ms": workflow_stages, "timeline": timeline,
            "requests_last_minute": minute_requests, "available_models": model_choices,
            "recent": {"items": recent, "total": requests["total"], "limit": limit, "offset": offset}}
