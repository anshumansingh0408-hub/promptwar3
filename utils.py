"""
utils.py - Helper and Utility functions for CarbonWise AI Assistant

This module encapsulates validation, payload schema checks, API communications,
formatting helpers, rate-limiting, and caching utilities.
"""

import time
import hashlib
import json
import requests


def get_cache_key(message: str, footprint_data: dict | None) -> str:
    """Generates a unique SHA-256 hash key using user message and footprint data.

    Args:
        message (str): Sanitized user query string.
        footprint_data (dict or None): Calculated emissions footprint details.

    Returns:
        str: A 64-character hexadecimal hash string.
    """
    # Canonicalize footprint dict to keep keys sorted
    fp_str = json.dumps(footprint_data, sort_keys=True) if footprint_data else ""
    combined = f"{message.strip()}_{fp_str}"
    return hashlib.sha256(combined.encode("utf-8")).hexdigest()


def check_rate_limit(ip: str, tracker: dict, window: int, limit: int) -> bool:
    """Enforces IP-based rate limiting.

    Checks if the request limit has been reached inside the tracking window.

    Args:
        ip (str): The requesting client IP address.
        tracker (dict): Rate limit tracker state dictionary.
        window (int): Time window in seconds.
        limit (int): Maximum request limit in that window.

    Returns:
        bool: True if request is allowed, False if limit has been exceeded.
    """
    now = time.time()
    if ip not in tracker:
        tracker[ip] = []

    # Filter out timestamps older than the window
    recent_requests = [t for t in tracker[ip] if now - t < window]
    tracker[ip] = recent_requests

    if len(recent_requests) >= limit:
        return False

    tracker[ip].append(now)
    return True


def validate_calculate_data(data: dict | None, calc_config: dict) -> tuple[dict | None, str | None]:
    """Validates calculate API post request data.

    Args:
        data (dict or None): The incoming raw json dictionary.
        calc_config (dict): The configuration containing enums.

    Returns:
        tuple: (validated_data_dict or None, error_message or None)
    """
    if not data:
        return None, "Missing JSON request payload."

    required_fields = [
        "transport_mode",
        "km_per_day",
        "electricity_units",
        "diet_type",
        "waste_kg_per_week",
    ]
    for field in required_fields:
        if field not in data:
            return None, f"Required field '{field}' is missing."

    transport_mode = data.get("transport_mode")
    diet_type = data.get("diet_type")
    km_per_day = data.get("km_per_day")
    electricity_units = data.get("electricity_units")
    waste_kg_per_week = data.get("waste_kg_per_week")

    # Enums validation
    if transport_mode not in calc_config["TRANSPORT"]:
        return (
            None,
            f"Invalid transport mode. Must be one of: {list(calc_config['TRANSPORT'].keys())}",
        )
    if diet_type not in calc_config["DIET"]:
        return None, f"Invalid diet type. Must be one of: {list(calc_config['DIET'].keys())}"

    # Number type and bounds validation
    if not isinstance(km_per_day, (int, float)) or km_per_day < 0:
        return None, "km_per_day must be a number greater than or equal to 0."
    if not isinstance(electricity_units, (int, float)) or electricity_units < 0:
        return None, "electricity_units must be a number greater than or equal to 0."
    if not isinstance(waste_kg_per_week, (int, float)) or waste_kg_per_week < 0:
        return None, "waste_kg_per_week must be a number greater than or equal to 0."

    return {
        "transport_mode": transport_mode,
        "km_per_day": float(km_per_day),
        "electricity_units": float(electricity_units),
        "diet_type": diet_type,
        "waste_kg_per_week": float(waste_kg_per_week),
    }, None


def validate_chat_data(
    data: dict | None, max_length: int
) -> tuple[tuple[str, list, dict | None] | None, str | None]:
    """Validates chat API POST inputs and sanitizes the user message.

    Args:
        data (dict or None): The incoming raw json dictionary.
        max_length (int): Maximum allowed length of a user message.

    Returns:
        tuple: (tuple(message, history, footprint_data) or None, error_message or None)
    """
    if not data:
        data = {}

    message = data.get("message")
    history = data.get("history", [])
    footprint_data = data.get("footprint_data")

    # Message type validation
    if not isinstance(message, str):
        return None, "Message parameter must be a string."

    message = message.strip()
    if not message:
        return None, "Message query cannot be empty."

    if len(message) > max_length:
        return (
            None,
            f"Message exceeds maximum permitted length of {max_length} characters.",
        )

    return (message, history, footprint_data), None


def format_system_prompt(footprint_data: dict | None, base_system_prompt: str) -> str:
    """Formats the system instructions for Gemini with footprint context if present.

    Args:
        footprint_data (dict or None): Calculated footprint breakdown details.
        base_system_prompt (str): Default instructions.

    Returns:
        str: Expanded system instructions.
    """
    if footprint_data and isinstance(footprint_data, dict):
        fp_context = (
            f"User's footprint data: Transport={footprint_data.get('transport', 0):.1f}kg, "
            f"Electricity={footprint_data.get('electricity', 0):.1f}kg, "
            f"Diet={footprint_data.get('diet', 0):.1f}kg, "
            f"Waste={footprint_data.get('waste', 0):.1f}kg, "
            f"Total={footprint_data.get('total', 0):.1f}kg CO2/month, "
            f"Category={footprint_data.get('category', 'Unknown')}"
        )
        return f"{fp_context}\n\n{base_system_prompt}"
    return base_system_prompt


def format_gemini_contents(message: str, history: list, max_history_len: int) -> list:
    """Formats dialogue history and message into the Gemini request contents format.

    Args:
        message (str): The current sanitized query message.
        history (list): Array of past messages.
        max_history_len (int): Maximum history elements to keep.

    Returns:
        list: Gemini contents payload.
    """
    contents = []
    history_limit = history[-max_history_len:] if history else []

    for turn in history_limit:
        role = "model" if turn.get("role") in ["assistant", "model"] else "user"
        text = turn.get("text") or turn.get("content") or ""
        contents.append({"role": role, "parts": [{"text": text}]})

    # Append current message
    contents.append({"role": "user", "parts": [{"text": message}]})
    return contents


def call_gemini_api(
    model: str, api_key: str, contents: list, system_prompt: str, max_tokens: int
) -> str:
    """Contacts the Gemini API to retrieve a content generation reply.

    Args:
        model (str): Gemini model identifier.
        api_key (str): API key for validation.
        contents (list): Gemini request body contents array.
        system_prompt (str): Full system instructions string.
        max_tokens (int): Maximum output tokens.

    Returns:
        str: Assistant text reply.

    Raises:
        ValueError: If api_key is missing, response candidates are empty, or request fails.
        requests.exceptions.Timeout: If the API call times out.
        requests.exceptions.RequestException: On general API request connection errors.
    """
    if not api_key:
        raise ValueError("Gemini API key is not configured on the server.")

    api_url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    payload = {
        "contents": contents,
        "systemInstruction": {"parts": [{"text": system_prompt}]},
        "generationConfig": {"maxOutputTokens": max_tokens},
    }

    response = requests.post(api_url, json=payload, timeout=15)
    if response.status_code != 200:
        raise ValueError(f"API request failed with code {response.status_code}: {response.text}")

    res_json = response.json()
    candidates = res_json.get("candidates", [])
    if not candidates:
        raise ValueError("No response options generated by Gemini API.")

    parts = candidates[0].get("content", {}).get("parts", [])
    if not parts:
        raise ValueError("Empty text response from Gemini API.")

    return parts[0].get("text", "")
