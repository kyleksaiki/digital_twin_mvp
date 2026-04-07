"""AI assistant endpoints."""
from fastapi import APIRouter, Depends, Query
from app.models import ChatQuery, ChatResponse
from app.database import get_db
from app.db_models import RunRow
from sqlalchemy.orm import Session
import os
import re
from openai import OpenAI, APIError

router = APIRouter(prefix="/api/ai", tags=["ai"])

# Initialize OpenAI client
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
client = None

# Try to create client if valid API key exists
if OPENAI_API_KEY and OPENAI_API_KEY != "sk_test_placeholder":
    try:
        client = OpenAI(api_key=OPENAI_API_KEY)
    except Exception as e:
        print(f"Warning: Failed to initialize OpenAI client: {e}")
        client = None

# Mock responses for common queries
RESPONSE_MAP = {
    "battery": "R1 is at 23% battery — it's draining 3.2× faster than leaf sensors due to high relay traffic. Expect ~4.1 hours until critical threshold.",
    "gunshot": "Detected 28 gunshot events during the run; 26 were true positives with >0.90 confidence.",
    "bottleneck": "Nodes R1 and R2 handle 78% of total traffic. This creates a critical single-point-of-failure. Consider adding a relay node.",
    "false_positive": "The 6.8% false positive rate is slightly above the 5% target. Most false positives were chainsaw detections during high-wind periods.",
}

DEFAULT_RESPONSE = "Sorry, the AI is not working currently."


def is_math_expression(text):
    """Check if the input looks like a simple math expression."""
    # Simple check: contains only digits, spaces, and basic operators
    return bool(re.fullmatch(r'[\d\s+\-*/.()]+', text.strip()))


def evaluate_math(expression):
    """Safely evaluate simple math expressions (test mode)."""
    try:
        # Only allow safe operations
        result = eval(expression, {"__builtins__": {}}, {})
        return str(result)
    except Exception:
        return None


@router.get("/summary")
def get_summary(run_id: int = Query(None), db: Session = Depends(get_db)):
    """Get AI-generated summary of the loaded run."""
    # Fetch run details if run_id provided
    run_details = None
    default_fallback = "Unable to generate summary. Please check the AI service."
    
    if run_id:
        run_row = db.query(RunRow).filter(RunRow.id == run_id).first()
        if run_row:
            run_details = {
                "name": run_row.name,
                "duration": run_row.duration,
                "scenario": run_row.scenario,
                "model": run_row.model,
                "status": run_row.status,
                "date": str(run_row.date),
            }
            metrics = run_row.metrics
            if metrics:
                run_details["accuracy"] = metrics.accuracy
                run_details["fpr"] = metrics.fpr
                run_details["detections"] = metrics.detection_count
                run_details["latency_ms"] = metrics.latency_ms
                run_details["battery_health"] = metrics.battery_health
            default_fallback = f"Run {run_row.name} completed in {run_row.duration}. Overall status: {run_row.status}."
    
    # If no run details, return basic message
    if not run_details:
        return {
            "title": "Run Summary",
            "content": default_fallback,
        }
    
    # Try to generate AI summary if OpenAI is available
    if client:
        try:
            prompt = f"""Provide a concise 2-3 sentence summary of this forest monitoring simulation run:
            
Run: {run_details['name']}
Duration: {run_details['duration']}
Scenario: {run_details['scenario']}
Model: {run_details['model']}
Status: {run_details['status']}
"""
            
            if run_details.get("accuracy") is not None:
                prompt += f"Detection Accuracy: {run_details['accuracy']}%\n"
            if run_details.get("detections") is not None:
                prompt += f"Total Detections: {run_details['detections']}\n"
            if run_details.get("fpr") is not None:
                prompt += f"False Positive Rate: {run_details['fpr']}%\n"
            if run_details.get("latency_ms") is not None:
                prompt += f"Avg Latency: {run_details['latency_ms']}ms\n"
                
            prompt += "\nProvide a brief analysis of the run performance and any notable insights."
            
            response = client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {
                        "role": "system",
                        "content": "You are an AI assistant for a digital twin forest monitoring system. Provide concise, professional summaries of simulation runs.",
                    },
                    {
                        "role": "user",
                        "content": prompt,
                    }
                ],
                max_tokens=200,
                temperature=0.7,
            )
            summary = response.choices[0].message.content.strip()
            return {
                "title": "Run Summary",
                "content": summary,
            }
        except APIError as e:
            # Fall back to basic summary with run details
            pass
    
    # Fallback: return structured summary with run data
    return {
        "title": "Run Summary",
        "content": default_fallback,
    }


@router.post("/chat", response_model=ChatResponse)
def chat(query: ChatQuery) -> ChatResponse:
    """Chat endpoint for run-specific questions and AI assistance."""
    q_lower = query.q.lower().strip()
    
    # Test mode: Handle simple math expressions (e.g., "1 + 1" → "2")
    if is_math_expression(query.q):
        result = evaluate_math(query.q)
        if result is not None:
            return ChatResponse(answer=f"{query.q} = {result}")
    
    # Check for predefined keywords/responses
    for keyword, response in RESPONSE_MAP.items():
        if keyword in q_lower:
            return ChatResponse(answer=response)
    
    # Try to use OpenAI API if available
    if client:
        try:
            response = client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {
                        "role": "system",
                        "content": "You are an AI assistant for a digital twin forest monitoring system. Provide concise, helpful answers about sensor networks, battery life, data analysis, and detection accuracy.",
                    },
                    {
                        "role": "user",
                        "content": query.q,
                    }
                ],
                max_tokens=150,
                temperature=0.7,
            )
            answer = response.choices[0].message.content.strip()
            return ChatResponse(answer=answer)
        except APIError as e:
            # Fall back to default if API fails
            return ChatResponse(answer=DEFAULT_RESPONSE)
    
    # Fallback response
    return ChatResponse(answer=DEFAULT_RESPONSE)

