"""AI assistant endpoints.

Both the summary and the chat endpoint build their context from real run data
in the database — metrics, detections, battery simulation output, node health.
Nothing is hardcoded or fabricated: if a value hasn't been computed yet it is
reported as unavailable rather than invented.
"""
import json
import logging
import os
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.db_models import (
    AIEventRow,
    BatterySimResultRow,
    NetworkNodeRow,
    RunRow,
)
from app.models import ChatQuery, ChatResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ai", tags=["ai"])

# Model is configurable so you can switch without touching code.
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip() or "gpt-4o-mini"
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()

client = None
try:
    from openai import OpenAI

    if OPENAI_API_KEY and OPENAI_API_KEY != "sk_test_placeholder":
        try:
            client = OpenAI(api_key=OPENAI_API_KEY)
        except Exception as exc:
            logger.warning("Failed to initialize OpenAI client: %s", exc)
            client = None
except Exception as exc:  # openai package missing entirely
    logger.warning("openai package unavailable: %s", exc)

NO_KEY_MESSAGE = (
    "The AI assistant isn't configured on this server yet. Add an OPENAI_API_KEY "
    "to backend/.env and restart the backend to enable it."
)

SYSTEM_PROMPT = (
    "You are the AI assistant for a digital twin of a Shaman forest-monitoring "
    "sensor network. You answer questions about a specific simulation run using "
    "ONLY the run data provided to you.\n\n"
    "Rules:\n"
    "- Ground every number you cite in the provided run data. Never invent "
    "metrics, detection counts, or battery figures.\n"
    "- If the data needed to answer is missing or zero, say so plainly and "
    "explain what the user would need to do to populate it (usually: upload "
    "audio when creating a run so the pipeline produces detections).\n"
    "- A value of 0 means 'not yet measured', not 'measured as zero' — say "
    "which one you mean when it matters.\n"
    "- Be concise and concrete. Prefer two or three sentences over a lecture.\n"
    "- You may explain general concepts (confidence thresholds, mesh routing, "
    "power budgets) without run data."
)


def _resolve_run_id(explicit_run_id: Optional[int], context: Optional[Dict[str, Any]]) -> Optional[int]:
    """Pull a run id from the query param, or from the frontend's context blob."""
    if explicit_run_id:
        return explicit_run_id
    if isinstance(context, dict):
        run_context = context.get("run")
        if isinstance(run_context, dict):
            run_id = run_context.get("id")
            try:
                return int(run_id) if run_id is not None else None
            except (TypeError, ValueError):
                return None
    return None


def _build_run_context(db: Session, run_id: Optional[int]) -> Optional[Dict[str, Any]]:
    """Assemble everything known about a run from the database."""
    if not run_id:
        return None
    row = db.query(RunRow).filter(RunRow.id == run_id).first()
    if not row:
        return None

    ctx: Dict[str, Any] = {
        "run": {
            "id": row.id,
            "name": row.name,
            "date": str(row.date),
            "scenario": row.scenario,
            "shaman_i_processor": row.shamani,
            "shaman_ii_processor": row.shamanii,
            "duration_setting": row.duration,
            "status": row.status,
        }
    }

    metrics = row.metrics
    if metrics:
        ctx["metrics"] = {
            "accuracy_percent": metrics.accuracy,
            "false_positive_rate_percent": metrics.fpr,
            "avg_latency_ms": metrics.latency_ms,
            "detection_count": metrics.detection_count,
            "battery_health_percent": metrics.battery_health,
            "congestion": metrics.congestion,
            "throughput": metrics.throughput,
            "confidence_threshold": metrics.conf_threshold,
        }
    else:
        ctx["metrics"] = None

    detections = sorted(row.detections or [], key=lambda d: -d.count)
    ctx["detections_by_type"] = (
        [{"event_type": d.event_type, "count": d.count} for d in detections] or None
    )

    ctx["ai_event_count"] = db.query(AIEventRow).filter(AIEventRow.run_id == run_id).count()

    battery = (
        db.query(BatterySimResultRow)
        .filter(BatterySimResultRow.run_id == run_id)
        .order_by(BatterySimResultRow.id.desc())
        .first()
    )
    if battery:
        try:
            breakdown = json.loads(battery.breakdown_json or "{}")
        except (TypeError, ValueError):
            breakdown = {}
        ctx["battery_simulation"] = {
            "node_id": battery.node_id,
            "battery_capacity_wh": battery.battery_wh,
            "energy_consumed_wh": battery.energy_consumed_wh,
            "energy_remaining_wh": battery.energy_remaining_wh,
            "final_battery_percent": battery.final_battery_percent,
            "average_power_w": battery.average_power_w,
            "avg_drain_percent_per_hour": battery.avg_drain_percent_per_hour,
            "projected_total_life_hours": battery.projected_total_life_hours,
            "simulated_duration_hours": battery.duration_hours,
            "duration_source": battery.duration_source,
            "duration_source_note": (
                "measured from the uploaded audio file"
                if battery.duration_source == "audio"
                else "estimated from the run's duration setting (no audio uploaded)"
            ),
            "total_detections": battery.total_detections,
            "node_still_alive": battery.alive,
            "component_energy_wh": breakdown,
        }
    else:
        ctx["battery_simulation"] = None

    nodes = db.query(NetworkNodeRow).filter(NetworkNodeRow.run_id == run_id).all()
    if nodes:
        ctx["network"] = {
            "node_count": len(nodes),
            "nodes_by_health": {
                health: sum(1 for n in nodes if n.health == health)
                for health in sorted({n.health for n in nodes})
            },
            "total_ai_detections_across_nodes": sum(n.ai_det or 0 for n in nodes),
        }
    else:
        ctx["network"] = None

    return ctx


def _has_real_detection_data(ctx: Dict[str, Any]) -> bool:
    if ctx.get("ai_event_count"):
        return True
    metrics = ctx.get("metrics") or {}
    return bool(metrics.get("detection_count"))


def _format_context_for_prompt(ctx: Dict[str, Any]) -> str:
    """Render the context as readable JSON plus guidance about empty values."""
    lines = [
        "RUN DATA (the only facts you may cite):",
        json.dumps(ctx, indent=2, default=str),
    ]
    if not _has_real_detection_data(ctx):
        lines.append(
            "\nNOTE: this run has no processed audio, so detection metrics are "
            "empty or zero. Do not present zeros as measured results — explain "
            "that no audio has been processed for this run yet."
        )
    if not ctx.get("battery_simulation"):
        lines.append(
            "\nNOTE: no battery simulation has been stored for this run, so no "
            "battery figures are available."
        )
    return "\n".join(lines)


def _deterministic_summary(ctx: Optional[Dict[str, Any]]) -> str:
    """Factual summary built directly from run data — used when OpenAI is unavailable."""
    if not ctx:
        return "No run is loaded. Select a run to see its summary."

    run = ctx["run"]
    parts = [
        f"{run['name']} — scenario \"{run['scenario']}\", duration setting "
        f"{run['duration_setting']}, status {run['status']}."
    ]

    if _has_real_detection_data(ctx):
        metrics = ctx.get("metrics") or {}
        count = metrics.get("detection_count") or ctx.get("ai_event_count") or 0
        detail = f"{count} AI detection events recorded"
        if metrics.get("avg_latency_ms"):
            detail += f", averaging {metrics['avg_latency_ms']} ms latency"
        types = ctx.get("detections_by_type") or []
        if types:
            top = ", ".join(f"{d['event_type']} ({d['count']})" for d in types[:4])
            detail += f". Detections by type: {top}"
        parts.append(detail + ".")
    else:
        parts.append(
            "No audio has been processed for this run, so there are no detection "
            "metrics yet. Create a run with an audio file to populate them."
        )

    battery = ctx.get("battery_simulation")
    if battery:
        parts.append(
            f"Battery simulation: {battery['final_battery_percent']:.2f}% remaining after "
            f"{battery['simulated_duration_hours']:.2f} h "
            f"({battery['duration_source_note']}), averaging "
            f"{battery['average_power_w'] * 1000:.2f} mW."
        )
    else:
        parts.append("No battery simulation has been recorded for this run.")

    return " ".join(parts)


def _ask_openai(user_content: str, context_block: Optional[str], max_tokens: int) -> Optional[str]:
    """Call OpenAI, returning None on any failure so callers can fall back."""
    if not client:
        return None
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    if context_block:
        messages.append({"role": "system", "content": context_block})
    else:
        messages.append(
            {
                "role": "system",
                "content": "No run is currently loaded. Answer general questions only.",
            }
        )
    messages.append({"role": "user", "content": user_content})

    try:
        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=messages,
            max_tokens=max_tokens,
            temperature=0.4,
        )
        return (response.choices[0].message.content or "").strip() or None
    except Exception as exc:
        logger.warning("OpenAI request failed: %s", exc)
        return None


@router.get("/summary")
def get_summary(run_id: int = Query(None), db: Session = Depends(get_db)):
    """AI-generated summary of the loaded run, grounded in real run data."""
    ctx = _build_run_context(db, run_id)
    if not ctx:
        return {
            "title": "Run Summary",
            "content": "No run is loaded. Select a run to see its summary.",
        }

    answer = _ask_openai(
        "Summarize this run in 2-4 sentences: what was configured, what the "
        "detection results were, and what the battery simulation showed. "
        "Call out anything a reviewer should notice.",
        _format_context_for_prompt(ctx),
        max_tokens=250,
    )
    return {"title": "Run Summary", "content": answer or _deterministic_summary(ctx)}


@router.post("/chat", response_model=ChatResponse)
def chat(
    query: ChatQuery,
    run_id: int = Query(None),
    db: Session = Depends(get_db),
) -> ChatResponse:
    """Answer a question about the loaded run using real run data."""
    question = (query.q or "").strip()
    if not question:
        return ChatResponse(answer="Ask me something about this run and I'll take a look.")

    resolved_run_id = _resolve_run_id(run_id, query.context)
    ctx = _build_run_context(db, resolved_run_id)
    context_block = _format_context_for_prompt(ctx) if ctx else None

    answer = _ask_openai(question, context_block, max_tokens=400)
    if answer:
        return ChatResponse(answer=answer)

    # No OpenAI available — be honest rather than returning a canned answer.
    if not client:
        if ctx:
            return ChatResponse(
                answer=f"{NO_KEY_MESSAGE}\n\nHere's what I can tell you from the run data:\n{_deterministic_summary(ctx)}"
            )
        return ChatResponse(answer=NO_KEY_MESSAGE)

    return ChatResponse(
        answer="I couldn't reach the AI service just now. Please try again in a moment."
    )
