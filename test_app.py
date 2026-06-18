import unittest
import json
import time
from unittest.mock import patch, MagicMock
from app import app, CACHE, RATE_LIMIT_TRACKER

class TestCarbonApp(unittest.TestCase):

    def setUp(self):
        # Configure app for testing
        app.config["TESTING"] = True
        app.config["DEBUG"] = False
        self.client = app.test_client()
        # Reset cache and rate limit tracker for clean tests
        CACHE.clear()
        RATE_LIMIT_TRACKER.clear()

    def test_index_route(self):
        """
        1. test_index_route - GET / returns 200
        """
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"What's Your Carbon Footprint?", response.data)

    def test_security_headers(self):
        """
        2. test_security_headers - GET / response has X-Frame-Options header
        """
        response = self.client.get("/")
        self.assertIn("X-Frame-Options", response.headers)
        self.assertEqual(response.headers["X-Frame-Options"], "DENY")
        self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(response.headers["X-XSS-Protection"], "1; mode=block")

    def test_calculate_valid_input(self):
        """
        3. test_calculate_valid_input - POST /api/calculate with valid data returns 200 
           and JSON with 'breakdown' and 'recommendations' keys
        """
        payload = {
            "transport_mode": "car_petrol",
            "km_per_day": 20,
            "electricity_units": 150,
            "diet_type": "vegan",
            "waste_kg_per_week": 5
        }
        response = self.client.post(
            "/api/calculate",
            data=json.dumps(payload),
            content_type="application/json"
        )
        self.assertEqual(response.status_code, 200)
        res_data = json.loads(response.data.decode("utf-8"))
        self.assertIn("breakdown", res_data)
        self.assertIn("recommendations", res_data)

    def test_calculate_missing_field(self):
        """
        4. test_calculate_missing_field - POST /api/calculate with missing field returns 400
        """
        payload = {
            "transport_mode": "car_petrol",
            "km_per_day": 20,
            "electricity_units": 150
            # diet_type and waste_kg_per_week are missing
        }
        response = self.client.post(
            "/api/calculate",
            data=json.dumps(payload),
            content_type="application/json"
        )
        self.assertEqual(response.status_code, 400)
        res_data = json.loads(response.data.decode("utf-8"))
        self.assertEqual(res_data["code"], "VALIDATION_ERROR")

    def test_calculate_invalid_transport_mode(self):
        """
        5. test_calculate_invalid_transport_mode - POST /api/calculate with invalid 
           transport_mode (e.g. "spaceship") returns 400
        """
        payload = {
            "transport_mode": "spaceship",
            "km_per_day": 20,
            "electricity_units": 150,
            "diet_type": "vegan",
            "waste_kg_per_week": 5
        }
        response = self.client.post(
            "/api/calculate",
            data=json.dumps(payload),
            content_type="application/json"
        )
        self.assertEqual(response.status_code, 400)
        res_data = json.loads(response.data.decode("utf-8"))
        self.assertEqual(res_data["code"], "VALIDATION_ERROR")

    def test_calculate_negative_values(self):
        """
        6. test_calculate_negative_values - POST /api/calculate with negative km_per_day returns 400
        """
        payload = {
            "transport_mode": "car_petrol",
            "km_per_day": -10,
            "electricity_units": 150,
            "diet_type": "vegan",
            "waste_kg_per_week": 5
        }
        response = self.client.post(
            "/api/calculate",
            data=json.dumps(payload),
            content_type="application/json"
        )
        self.assertEqual(response.status_code, 400)
        res_data = json.loads(response.data.decode("utf-8"))
        self.assertEqual(res_data["code"], "VALIDATION_ERROR")

    def test_calculate_response_structure(self):
        """
        7. test_calculate_response_structure - verify breakdown dict contains keys: 
           transport, electricity, diet, waste, total, category, comparison_to_average
        """
        payload = {
            "transport_mode": "car_petrol",
            "km_per_day": 20,
            "electricity_units": 150,
            "diet_type": "vegan",
            "waste_kg_per_week": 5
        }
        response = self.client.post(
            "/api/calculate",
            data=json.dumps(payload),
            content_type="application/json"
        )
        self.assertEqual(response.status_code, 200)
        res_data = json.loads(response.data.decode("utf-8"))
        breakdown = res_data["breakdown"]
        
        required_keys = ["transport", "electricity", "diet", "waste", "total", "category", "comparison_to_average"]
        for key in required_keys:
            self.assertIn(key, breakdown)

    def test_chat_empty_message(self):
        """
        8. test_chat_empty_message - POST /chat with empty message returns 400
        """
        payload = {"message": "   ", "history": []}
        response = self.client.post(
            "/chat",
            data=json.dumps(payload),
            content_type="application/json"
        )
        self.assertEqual(response.status_code, 400)
        res_data = json.loads(response.data.decode("utf-8"))
        self.assertEqual(res_data["code"], "VALIDATION_ERROR")

    def test_chat_message_too_long(self):
        """
        9. test_chat_message_too_long - POST /chat with message over 500 chars returns 400
        """
        long_message = "a" * 501
        payload = {"message": long_message, "history": []}
        response = self.client.post(
            "/chat",
            data=json.dumps(payload),
            content_type="application/json"
        )
        self.assertEqual(response.status_code, 400)
        res_data = json.loads(response.data.decode("utf-8"))
        self.assertEqual(res_data["code"], "VALIDATION_ERROR")

    @patch("app.requests.post")
    def test_chat_with_footprint_context(self, mock_post):
        """
        10. test_chat_with_footprint_context - POST /chat with valid message + footprint_data 
            returns 200 (mock the Gemini API call using unittest.mock.patch)
        """
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "candidates": [
                {
                    "content": {
                        "parts": [{"text": "Based on your calculations, your electricity emissions represent your largest share."}]
                    }
                }
            ]
        }
        mock_post.return_value = mock_response

        with patch("app.GEMINI_API_KEY", "fake_key"):
            payload = {
                "message": "Suggest custom ways to reduce emissions",
                "history": [],
                "footprint_data": {
                    "transport": 100.0,
                    "electricity": 200.0,
                    "diet": 50.0,
                    "waste": 20.0,
                    "total": 370.0,
                    "category": "Low"
                }
            }
            response = self.client.post(
                "/chat",
                data=json.dumps(payload),
                content_type="application/json"
            )
            self.assertEqual(response.status_code, 200)
            res_data = json.loads(response.data.decode("utf-8"))
            self.assertEqual(res_data["reply"], "Based on your calculations, your electricity emissions represent your largest share.")

    def test_rate_limiting(self):
        """
        11. test_rate_limiting - POST /chat 21 times rapidly, verify 21st returns 429
        """
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "candidates": [{"content": {"parts": [{"text": "Reply"}]}}]
        }

        with patch("app.requests.post", return_value=mock_response), patch("app.GEMINI_API_KEY", "fake_key"):
            payload = {"message": "Hello"}
            
            # Send 20 queries rapidly
            for _ in range(20):
                response = self.client.post(
                    "/chat",
                    data=json.dumps(payload),
                    content_type="application/json"
                )
                self.assertEqual(response.status_code, 200)

            # The 21st query must trigger a 429 Rate Limit response
            response_21 = self.client.post(
                "/chat",
                data=json.dumps(payload),
                content_type="application/json"
            )
            self.assertEqual(response_21.status_code, 429)
            res_data = json.loads(response_21.data.decode("utf-8"))
            self.assertEqual(res_data["code"], "RATE_LIMIT_EXCEEDED")

    def test_calculate_boundary_low_category(self):
        """
        12. test_calculate_boundary_low_category - input that gives total < 800 returns category "Low"
        """
        payload = {
            "transport_mode": "bike",
            "km_per_day": 0,
            "electricity_units": 10,
            "diet_type": "vegan",
            "waste_kg_per_week": 1
        }
        response = self.client.post(
            "/api/calculate",
            data=json.dumps(payload),
            content_type="application/json"
        )
        self.assertEqual(response.status_code, 200)
        res_data = json.loads(response.data.decode("utf-8"))
        self.assertEqual(res_data["breakdown"]["category"], "Low")

    def test_calculate_boundary_very_high(self):
        """
        13. test_calculate_boundary_very_high - input that gives total >= 2500 returns "Very High"
        """
        payload = {
            "transport_mode": "flight",
            "km_per_day": 300,
            "electricity_units": 1000,
            "diet_type": "non_vegetarian",
            "waste_kg_per_week": 40
        }
        response = self.client.post(
            "/api/calculate",
            data=json.dumps(payload),
            content_type="application/json"
        )
        self.assertEqual(response.status_code, 200)
        res_data = json.loads(response.data.decode("utf-8"))
        self.assertEqual(res_data["breakdown"]["category"], "Very High")

    def test_recommendations_not_empty(self):
        """
        14. test_recommendations_not_empty - calculate returns non-empty recommendations list
        """
        payload = {
            "transport_mode": "bike",
            "km_per_day": 0,
            "electricity_units": 600,
            "diet_type": "vegan",
            "waste_kg_per_week": 1
        }
        response = self.client.post(
            "/api/calculate",
            data=json.dumps(payload),
            content_type="application/json"
        )
        self.assertEqual(response.status_code, 200)
        res_data = json.loads(response.data.decode("utf-8"))
        self.assertTrue(len(res_data["recommendations"]) > 0)

    def test_compare_route(self):
        """
        15. test_compare_route - GET /compare returns 200
        """
        response = self.client.get("/compare")
        self.assertEqual(response.status_code, 200)

    def test_tips_route(self):
        """
        16. test_tips_route - GET /tips returns 200
        """
        response = self.client.get("/tips")
        self.assertEqual(response.status_code, 200)

    def test_about_route(self):
        """
        17. test_about_route - GET /about returns 200
        """
        response = self.client.get("/about")
        self.assertEqual(response.status_code, 200)

    def test_response_time_header(self):
        """
        18. test_response_time_header - verify X-Response-Time header present in responses
        """
        response = self.client.get("/")
        self.assertIn("X-Response-Time", response.headers)

    def test_cache_hit(self):
        """
        19. test_cache_hit - same calculate request twice returns same result (verify caching works)
        """
        from carbon_calculator import calculate_total_footprint
        calculate_total_footprint.cache_clear()
        
        payload = {
            "transport_mode": "car_petrol",
            "km_per_day": 20,
            "electricity_units": 150,
            "diet_type": "vegan",
            "waste_kg_per_week": 5
        }
        
        # Call once
        self.client.post(
            "/api/calculate",
            data=json.dumps(payload),
            content_type="application/json"
        )
        # Call twice
        self.client.post(
            "/api/calculate",
            data=json.dumps(payload),
            content_type="application/json"
        )
        
        info = calculate_total_footprint.cache_info()
        self.assertTrue(info.hits >= 1)

    def test_content_type_json(self):
        """
        20. test_content_type_json - /api/calculate response Content-Type is application/json
        """
        payload = {
            "transport_mode": "car_petrol",
            "km_per_day": 20,
            "electricity_units": 150,
            "diet_type": "vegan",
            "waste_kg_per_week": 5
        }
        response = self.client.post(
            "/api/calculate",
            data=json.dumps(payload),
            content_type="application/json"
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.headers["Content-Type"].startswith("application/json"))

if __name__ == "__main__":
    unittest.main()
