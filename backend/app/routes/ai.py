"""AI assistant endpoints."""
from fastapi import APIRouter
from app.models import ChatQuery, ChatResponse
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
def get_summary():
    """Get AI-generated summary of the loaded run."""
    return {
        "title": "Run Summary",
        "content": "Forest_Night_01 completed a 24-hour simulation achieving 94.2% detection accuracy. Primary concern: network bottleneck at relay nodes R1 and R2.",
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

