"""
CarbonWise - AI Carbon Footprint Assistant Backend

Purpose:
Provide a smart web application that calculates household monthly carbon footprint emissions 
and delivers conversational green living advice through a context-aware AI chat assistant.

Architecture:
1. Deterministic Calculation Engine (carbon_calculator.py):
   Pure Python functions calculate transport, electricity, diet, and waste emissions using
   fixed factors, categorizing footprints and comparing against the Indian average (1500 kg/month).
2. Flask Controller (app.py):
   - Exposes REST endpoints: /api/calculate (footprint assessment) and /chat (dialogue integration).
   - Injects user footprint context directly into Gemini AI chatbot system instructions.
   - Enforces rate limiting (20 requests/IP/min) and in-memory caches response pairs (TTL 5 mins).
   - Serves static templates and appends mandatory security headers (nosniff, DENY, XSS).
"""

import os
import time
import hashlib
import json
import requests
import gzip
import io
from flask import Flask, render_template, request, jsonify, g
from carbon_calculator import (
    CONFIG as CALC_CONFIG,
    calculate_total_footprint,
    get_recommendations
)

app = Flask(__name__)
from functools import lru_cache

def cached_calculate(transport_mode, km_per_day, electricity_units, diet_type, waste_kg_per_week):
    data = {
        "transport_mode": transport_mode,
        "km_per_day": km_per_day,
        "electricity_units": electricity_units,
        "diet_type": diet_type,
        "waste_kg_per_week": waste_kg_per_week
    }
    return calculate_total_footprint(data)

# Load simple .env file manually if it exists on startup
if os.path.exists(".env"):
    with open(".env", "r") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, val = line.split("=", 1)
                os.environ[key.strip()] = val.strip()

# Application Configuration
CONFIG = {
    "MAX_MESSAGE_LENGTH": 500,
    "MAX_HISTORY_LENGTH": 10,
    "RATE_LIMIT_REQUESTS": 20,
    "RATE_LIMIT_WINDOW": 60,
    "MAX_TOKENS": 1024,
    "MODEL": "gemini-3.1-flash-lite",
    "CACHE_TTL": 300  # 5 minutes
}

# API Configuration
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

# Simple In-Memory Cache for chatbot answers
# Structure: { cache_key: { "reply": str, "expiry": float } }
CACHE = {}

# Rate limit tracker
# Structure: { ip_address: [timestamp, timestamp, ...] }
RATE_LIMIT_TRACKER = {}

# System prompt for CarbonWise
SYSTEM_PROMPT = (
    "You are CarbonWise, a friendly AI assistant that helps users understand and reduce their carbon footprint. \n"
    "You have access to the user's calculated carbon footprint data (transport, electricity, diet, waste emissions in kg CO2/month).\n"
    "Use this data to give SPECIFIC, PERSONALIZED advice — reference their actual numbers.\n"
    "Be encouraging, practical, and India-focused (mention Indian context like BEST buses, metro systems, LPG vs induction, etc).\n"
    "Keep responses concise with actionable bullet points. Never be preachy or guilt-inducing."
)


def get_cache_key(message: str, footprint_data: dict) -> str:
    """
    Generates a unique SHA-256 hash key using user message and their footprint data.

    Parameters:
        message (str): Sanitized user query string.
        footprint_data (dict or None): Calculated emissions footprint details.

    Returns:
        str: A 64-character hexadecimal hash string.
    """
    # Canonicalize footprint dict to keep keys sorted
    fp_str = json.dumps(footprint_data, sort_keys=True) if footprint_data else ""
    combined = f"{message.strip()}_{fp_str}"
    return hashlib.sha256(combined.encode("utf-8")).hexdigest()


def check_rate_limit(ip: str) -> bool:
    """
    Enforces IP-based rate limiting. Checks if the request limit (RATE_LIMIT_REQUESTS) 
    has been reached inside the tracking window (RATE_LIMIT_WINDOW).

    Parameters:
        ip (str): The requesting client IP address.

    Returns:
        bool: True if request is allowed, False if limit has been exceeded.
    """
    now = time.time()
    if ip not in RATE_LIMIT_TRACKER:
        RATE_LIMIT_TRACKER[ip] = []
    
    # Filter out timestamps older than the window
    recent_requests = [t for t in RATE_LIMIT_TRACKER[ip] if now - t < CONFIG["RATE_LIMIT_WINDOW"]]
    RATE_LIMIT_TRACKER[ip] = recent_requests
    
    if len(recent_requests) >= CONFIG["RATE_LIMIT_REQUESTS"]:
        return False
        
    RATE_LIMIT_TRACKER[ip].append(now)
    return True


@app.before_request
def start_timer():
    g.start = time.time()


def compress_response(response):
    accept_encoding = request.headers.get("Accept-Encoding", "")
    if (
        "gzip" not in accept_encoding.lower() or
        response.status_code < 200 or
        response.status_code >= 300 or
        "Content-Encoding" in response.headers or
        response.direct_passthrough
    ):
        return response

    content = response.get_data()
    gzip_buffer = io.BytesIO()
    with gzip.GzipFile(mode="wb", fileobj=gzip_buffer) as gzip_file:
        gzip_file.write(content)
    
    response.set_data(gzip_buffer.getvalue())
    response.headers["Content-Encoding"] = "gzip"
    response.headers["Content-Length"] = len(response.get_data())
    return response


@app.after_request
def log_request_time_and_security(response):
    """
    Global Flask interceptor that appends safety headers and timing logs on outgoing responses.
    """
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    
    if hasattr(g, "start"):
        duration = time.time() - g.start
        response.headers["X-Response-Time"] = f"{duration:.3f}s"
    
    return compress_response(response)


@app.route("/", methods=["GET"])
def index():
    """
    Serves the main carbon assistant index interface page.
    """
    return render_template("index.html")


@app.route("/tips", methods=["GET"])
def tips():
    """
    Serves the reduction tips page.
    """
    return render_template("tips.html")


@app.route("/about", methods=["GET"])
def about():
    """
    Serves the about page.
    """
    return render_template("about.html")


@app.route("/compare", methods=["GET"])
def compare():
    """
    Serves the compare page.
    """
    return render_template("compare.html")


@app.route("/api/calculate", methods=["POST"])
def api_calculate():
    """
    JSON API route to evaluate monthly carbon footprint breakdown and recommendations.

    Accepts POST JSON payload:
        {
            "transport_mode": str,
            "km_per_day": float/int,
            "electricity_units": float/int,
            "diet_type": str,
            "waste_kg_per_week": float/int
        }

    Returns:
        JSON response with breakdown values and personalized reduction action items,
        or validation error description under 400 Bad Request status.
    """
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Missing JSON request payload.", "code": "VALIDATION_ERROR"}), 400

    required_fields = ["transport_mode", "km_per_day", "electricity_units", "diet_type", "waste_kg_per_week"]
    for field in required_fields:
        if field not in data:
            return jsonify({"error": f"Required field '{field}' is missing.", "code": "VALIDATION_ERROR"}), 400

    transport_mode = data.get("transport_mode")
    diet_type = data.get("diet_type")
    km_per_day = data.get("km_per_day")
    electricity_units = data.get("electricity_units")
    waste_kg_per_week = data.get("waste_kg_per_week")

    # Enums validation
    if transport_mode not in CALC_CONFIG["TRANSPORT"]:
        return jsonify({"error": f"Invalid transport mode. Must be one of: {list(CALC_CONFIG['TRANSPORT'].keys())}", "code": "VALIDATION_ERROR"}), 400
    if diet_type not in CALC_CONFIG["DIET"]:
        return jsonify({"error": f"Invalid diet type. Must be one of: {list(CALC_CONFIG['DIET'].keys())}", "code": "VALIDATION_ERROR"}), 400

    # Number type and bounds validation
    if not isinstance(km_per_day, (int, float)) or km_per_day < 0:
        return jsonify({"error": "km_per_day must be a number greater than or equal to 0.", "code": "VALIDATION_ERROR"}), 400
    if not isinstance(electricity_units, (int, float)) or electricity_units < 0:
        return jsonify({"error": "electricity_units must be a number greater than or equal to 0.", "code": "VALIDATION_ERROR"}), 400
    if not isinstance(waste_kg_per_week, (int, float)) or waste_kg_per_week < 0:
        return jsonify({"error": "waste_kg_per_week must be a number greater than or equal to 0.", "code": "VALIDATION_ERROR"}), 400

    try:
        breakdown = cached_calculate(
            transport_mode,
            km_per_day,
            electricity_units,
            diet_type,
            waste_kg_per_week
        )
        recommendations = get_recommendations(breakdown)
        return jsonify({
            "breakdown": breakdown,
            "recommendations": recommendations
        })
    except Exception as e:
        return jsonify({"error": f"Calculation error: {str(e)}", "code": "SERVER_ERROR"}), 500


@app.route("/chat", methods=["POST"])
def chat():
    """
    JSON API chat route representing the CarbonWise conversational helper.

    Accepts POST JSON payload:
        {
            "message": str,
            "history": list,             # optional array of past conversation dicts
            "footprint_data": dict/None  # optional current calculated emission values
        }

    Returns:
        JSON response with the assistant's reply text, or appropriate status error codes.
    """
    # 1. Rate Limiting Check
    ip = request.remote_addr or "127.0.0.1"
    if not check_rate_limit(ip):
        return jsonify({"error": "Too many requests. Please try again after a minute.", "code": "RATE_LIMIT_EXCEEDED"}), 429

    # 2. Payload Extraction
    data = request.get_json(silent=True) or {}
    message = data.get("message")
    history = data.get("history", [])
    footprint_data = data.get("footprint_data")

    # 3. Message Sanitization & Length Check
    if not isinstance(message, str):
        return jsonify({"error": "Message parameter must be a string.", "code": "VALIDATION_ERROR"}), 400
    
    message = message.strip()
    if not message:
        return jsonify({"error": "Message query cannot be empty.", "code": "VALIDATION_ERROR"}), 400
        
    if len(message) > CONFIG["MAX_MESSAGE_LENGTH"]:
        return jsonify({
            "error": f"Message exceeds maximum permitted length of {CONFIG['MAX_MESSAGE_LENGTH']} characters.",
            "code": "VALIDATION_ERROR"
        }), 400

    # 4. Read Cache
    cache_key = get_cache_key(message, footprint_data)
    now = time.time()
    if cache_key in CACHE:
        entry = CACHE[cache_key]
        if now < entry["expiry"]:
            return jsonify({"reply": entry["reply"]})
        else:
            del CACHE[cache_key]

    # 5. Build full system instructions including user context
    if footprint_data and isinstance(footprint_data, dict):
        fp_context = (
            f"User's footprint data: Transport={footprint_data.get('transport', 0):.1f}kg, "
            f"Electricity={footprint_data.get('electricity', 0):.1f}kg, "
            f"Diet={footprint_data.get('diet', 0):.1f}kg, "
            f"Waste={footprint_data.get('waste', 0):.1f}kg, "
            f"Total={footprint_data.get('total', 0):.1f}kg CO2/month, "
            f"Category={footprint_data.get('category', 'Unknown')}"
        )
        full_system_prompt = f"{fp_context}\n\n{SYSTEM_PROMPT}"
    else:
        full_system_prompt = SYSTEM_PROMPT

    # 6. Format dialogue history into Gemini parts schema
    contents = []
    history_limit = history[-CONFIG["MAX_HISTORY_LENGTH"]:] if history else []
    for h in history_limit:
        role = "model" if h.get("role") in ["assistant", "model"] else "user"
        text = h.get("text") or h.get("content") or ""
        contents.append({
            "role": role,
            "parts": [{"text": text}]
        })
    
    # Append current message
    contents.append({
        "role": "user",
        "parts": [{"text": message}]
    })

    # 7. Contact Gemini Service
    if not GEMINI_API_KEY:
        return jsonify({"error": "Gemini API key is not configured on the server.", "code": "API_KEY_MISSING"}), 500

    api_url = f"https://generativelanguage.googleapis.com/v1beta/models/{CONFIG['MODEL']}:generateContent?key={GEMINI_API_KEY}"
    payload = {
        "contents": contents,
        "systemInstruction": {
            "parts": [{"text": full_system_prompt}]
        },
        "generationConfig": {
            "maxOutputTokens": CONFIG["MAX_TOKENS"]
        }
    }

    try:
        response = requests.post(api_url, json=payload, timeout=15)
        if response.status_code != 200:
            return jsonify({
                "error": f"API request failed with code {response.status_code}: {response.text}",
                "code": "API_ERROR"
            }), response.status_code
        
        res_json = response.json()
        candidates = res_json.get("candidates", [])
        if not candidates:
            return jsonify({"error": "No response options generated by Gemini API.", "code": "API_ERROR"}), 502

        parts = candidates[0].get("content", {}).get("parts", [])
        if not parts:
            return jsonify({"error": "Empty text response from Gemini API.", "code": "API_ERROR"}), 502

        reply = parts[0].get("text", "")

        # 8. Cache response entry
        CACHE[cache_key] = {
            "reply": reply,
            "expiry": now + CONFIG["CACHE_TTL"]
        }

        return jsonify({"reply": reply})

    except requests.exceptions.Timeout:
        return jsonify({"error": "Connection to the chatbot service timed out.", "code": "TIMEOUT"}), 504
    except requests.exceptions.RequestException as e:
        return jsonify({"error": f"Network exception: {str(e)}", "code": "API_ERROR"}), 502
    except Exception as e:
        return jsonify({"error": f"Internal chatbot service error: {str(e)}", "code": "SERVER_ERROR"}), 500


if __name__ == "__main__":
    app.run(
        host="0.0.0.0", 
        port=int(os.environ.get("PORT", 8080)), 
        debug=False
    )
