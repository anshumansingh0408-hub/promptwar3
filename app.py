"""CarbonWise - AI Carbon Footprint Assistant Backend.

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
import gzip
import io
import requests
from flask import Flask, render_template, request, jsonify, g, Response
from carbon_calculator import (
    CONFIG as CALC_CONFIG,
    calculate_total_footprint,
    get_recommendations
)
from utils import (
    get_cache_key,
    check_rate_limit,
    validate_calculate_data,
    validate_chat_data,
    format_system_prompt,
    format_gemini_contents,
    call_gemini_api
)

app = Flask(__name__)

# Load simple .env file manually if it exists on startup
if os.path.exists(".env"):
    with open(".env", "r") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, val = line.split("=", 1)
                os.environ[key.strip()] = val.strip()

# =====================================================================
# Constants Section
# =====================================================================
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


def cached_calculate(
    mode: str, km: float, elec: float, diet: str, waste: float
) -> dict:
    """Wrapper function to call the cached calculator logic.

    Args:
        mode (str): Transport mode.
        km (float): Daily km.
        elec (float): Monthly kWh.
        diet (str): Diet type.
        waste (float): Weekly waste kg.

    Returns:
        dict: Emission calculations breakdown.
    """
    data = {
        "transport_mode": mode,
        "km_per_day": km,
        "electricity_units": elec,
        "diet_type": diet,
        "waste_kg_per_week": waste
    }
    return calculate_total_footprint(data)


@app.before_request
def start_timer() -> None:
    """Initializes the request timer to evaluate latency durations.

    Args:
        None

    Returns:
        None
    """
    g.start = time.time()


def should_compress(response: Response, accept_encoding: str) -> bool:
    """Checks if the Flask Response qualifies for gzip compression.

    Args:
        response (Response): Flask Response object.
        accept_encoding (str): Accept-Encoding request header.

    Returns:
        bool: True if response should be compressed, False otherwise.
    """
    return not (
        "gzip" not in accept_encoding.lower() or
        response.status_code < 200 or
        response.status_code >= 300 or
        "Content-Encoding" in response.headers or
        response.direct_passthrough
    )


def compress_response(response: Response) -> Response:
    """Compresses HTML and JSON responses using gzip if requested.

    Args:
        response (Response): Flask Response object.

    Returns:
        Response: Compressed or original Response object.
    """
    accept = request.headers.get("Accept-Encoding", "")
    if not should_compress(response, accept):
        return response

    gzip_buffer = io.BytesIO()
    with gzip.GzipFile(mode="wb", fileobj=gzip_buffer) as gzip_file:
        gzip_file.write(response.get_data())
    
    response.set_data(gzip_buffer.getvalue())
    response.headers["Content-Encoding"] = "gzip"
    response.headers["Content-Length"] = len(response.get_data())
    return response


@app.after_request
def log_request_time_and_security(response: Response) -> Response:
    """Appends security headers and records response processing latency.

    Args:
        response (Response): Flask Response object.

    Returns:
        Response: Outgoing Response object with headers added.
    """
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    
    if hasattr(g, "start"):
        duration = time.time() - g.start
        response.headers["X-Response-Time"] = f"{duration:.3f}s"
    
    return compress_response(response)


@app.route("/", methods=["GET"])
def index() -> str:
    """Serves the main carbon assistant index interface page.

    Args:
        None

    Returns:
        str: Rendered HTML template string.
    """
    return render_template("index.html")


@app.route("/tips", methods=["GET"])
def tips() -> str:
    """Serves the reduction tips page.

    Args:
        None

    Returns:
        str: Rendered HTML template string.
    """
    return render_template("tips.html")


@app.route("/about", methods=["GET"])
def about() -> str:
    """Serves the about page.

    Args:
        None

    Returns:
        str: Rendered HTML template string.
    """
    return render_template("about.html")


@app.route("/compare", methods=["GET"])
def compare() -> str:
    """Serves the compare page.

    Args:
        None

    Returns:
        str: Rendered HTML template string.
    """
    return render_template("compare.html")


def process_calculation(validated_data: dict) -> dict:
    """Invokes cached calculation and compiles recommendations.

    Args:
        validated_data (dict): Pre-validated carbon footprint inputs.

    Returns:
        dict: Breakdown and recommendations dictionary.
    """
    breakdown = cached_calculate(
        validated_data["transport_mode"],
        validated_data["km_per_day"],
        validated_data["electricity_units"],
        validated_data["diet_type"],
        validated_data["waste_kg_per_week"]
    )
    return {
        "breakdown": breakdown,
        "recommendations": get_recommendations(breakdown)
    }


@app.route("/api/calculate", methods=["POST"])
def api_calculate() -> Response:
    """JSON API route to evaluate monthly carbon footprint.

    Args:
        None

    Returns:
        Response: JSON response containing breakdown or error details.
    """
    data = request.get_json(silent=True)
    val_data, err = validate_calculate_data(data, CALC_CONFIG)
    if err:
        return jsonify({"error": err, "code": "VALIDATION_ERROR"}), 400

    try:
        result = process_calculation(val_data)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": f"Calculation error: {str(e)}", "code": "SERVER_ERROR"}), 500


def check_cache(cache_key: str, now: float) -> str | None:
    """Checks the in-memory cache for a valid non-expired reply.

    Args:
        cache_key (str): The unique cache key.
        now (float): Current timestamp.

    Returns:
        str or None: Cached reply if valid, otherwise None.
    """
    if cache_key in CACHE:
        entry = CACHE[cache_key]
        if now < entry["expiry"]:
            return entry["reply"]
        del CACHE[cache_key]
    return None


def update_cache(cache_key: str, reply: str, expiry_time: float) -> None:
    """Updates the in-memory cache with a new reply and expiration time.

    Args:
        cache_key (str): The unique cache key.
        reply (str): The text response to cache.
        expiry_time (float): Expiration timestamp.

    Returns:
        None
    """
    CACHE[cache_key] = {"reply": reply, "expiry": expiry_time}


def handle_api_exception(e: Exception) -> Response:
    """Translates Gemini API/network exceptions into appropriate HTTP responses.

    Args:
        e (Exception): The caught exception.

    Returns:
        Response: Flask JSON response.
    """
    if isinstance(e, ValueError):
        err_msg = str(e)
        code = "API_KEY_MISSING" if "API key" in err_msg else "API_ERROR"
        status = 500 if code == "API_KEY_MISSING" else 502
        return jsonify({"error": err_msg, "code": code}), status
    if isinstance(e, requests.exceptions.Timeout):
        return jsonify({"error": "Connection to the chatbot service timed out.", "code": "TIMEOUT"}), 504
    if isinstance(e, requests.exceptions.RequestException):
        return jsonify({"error": f"Network exception: {str(e)}", "code": "API_ERROR"}), 502
    return jsonify({"error": f"Internal chatbot service error: {str(e)}", "code": "SERVER_ERROR"}), 500


def fetch_chat_reply(
    contents: list, system_prompt: str
) -> Response | str:
    """Contacts Gemini API and handles exceptions or returns reply.

    Args:
        contents (list): Gemini formatted history.
        system_prompt (str): Configured system prompt.

    Returns:
        Response or str: Flask Response on error, or string reply.
    """
    try:
        return call_gemini_api(
            model=CONFIG["MODEL"],
            api_key=GEMINI_API_KEY,
            contents=contents,
            system_prompt=system_prompt,
            max_tokens=CONFIG["MAX_TOKENS"]
        )
    except Exception as e:
        return handle_api_exception(e)


def perform_api_and_cache(
    cache_key: str, contents: list, sys_prompt: str, now: float
) -> Response:
    """Executes the API request, handles response caching and error logic.

    Args:
        cache_key (str): Cache key.
        contents (list): Gemini formatted history.
        sys_prompt (str): System prompt.
        now (float): Current timestamp.

    Returns:
        Response: Flask JSON response.
    """
    res_or_str = fetch_chat_reply(contents, sys_prompt)
    if isinstance(res_or_str, Response):
        return res_or_str

    update_cache(cache_key, res_or_str, now + CONFIG["CACHE_TTL"])
    return jsonify({"reply": res_or_str})


def handle_chat_session(
    msg: str, hist: list, fp_data: dict | None
) -> Response:
    """Processes validation details, checks cache, and invokes API response flow.

    Args:
        msg (str): Sanitized user message.
        hist (list): Conversation history.
        fp_data (dict or None): User footprint data.

    Returns:
        Response: Flask JSON response.
    """
    cache_key = get_cache_key(msg, fp_data)
    now = time.time()
    cached = check_cache(cache_key, now)
    if cached:
        return jsonify({"reply": cached})

    sys_prompt = format_system_prompt(fp_data, SYSTEM_PROMPT)
    contents = format_gemini_contents(msg, hist, CONFIG["MAX_HISTORY_LENGTH"])
    return perform_api_and_cache(cache_key, contents, sys_prompt, now)


@app.route("/chat", methods=["POST"])
def chat() -> Response:
    """JSON API chat route representing the CarbonWise conversational helper.

    Args:
        None

    Returns:
        Response: JSON response with the assistant's reply text, or error codes.
    """
    ip = request.remote_addr or "127.0.0.1"
    if not check_rate_limit(ip, RATE_LIMIT_TRACKER, CONFIG["RATE_LIMIT_WINDOW"], CONFIG["RATE_LIMIT_REQUESTS"]):
        return jsonify({
            "error": "Too many requests. Please try again after a minute.",
            "code": "RATE_LIMIT_EXCEEDED"
        }), 429

    data = request.get_json(silent=True)
    validation_res, error_msg = validate_chat_data(data, CONFIG["MAX_MESSAGE_LENGTH"])
    if error_msg:
        return jsonify({"error": error_msg, "code": "VALIDATION_ERROR"}), 400

    message, history, footprint_data = validation_res
    return handle_chat_session(message, history, footprint_data)


if __name__ == "__main__":
    app.run(
        host="0.0.0.0", 
        port=int(os.environ.get("PORT", 8080)), 
        debug=False
    )
