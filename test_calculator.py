import unittest
from carbon_calculator import (
    CONFIG,
    calculate_transport_emissions,
    calculate_electricity_emissions,
    calculate_diet_emissions,
    calculate_waste_emissions,
    calculate_total_footprint,
    get_recommendations
)

class TestCarbonCalculator(unittest.TestCase):

    def test_transport_emissions_car(self):
        """
        Verify calculate_transport_emissions('car_petrol', 20) returns correct value (0.192 * 20 * 30).
        """
        expected = 0.192 * 20 * 30
        self.assertAlmostEqual(calculate_transport_emissions("car_petrol", 20.0), expected)

    def test_transport_emissions_bike(self):
        """
        Verify bike returns 0.
        """
        self.assertAlmostEqual(calculate_transport_emissions("bike", 15.0), 0.0)

    def test_electricity_emissions(self):
        """
        Verify calculate_electricity_emissions(200) returns 200 * 0.82.
        """
        expected = 200 * 0.82
        self.assertAlmostEqual(calculate_electricity_emissions(200.0), expected)

    def test_diet_emissions_vegan(self):
        """
        Verify vegan diet calculation.
        """
        expected = 1.5 * 30
        self.assertAlmostEqual(calculate_diet_emissions("vegan"), expected)

    def test_diet_emissions_nonveg(self):
        """
        Verify non-vegetarian diet calculation.
        """
        expected = 3.3 * 30
        self.assertAlmostEqual(calculate_diet_emissions("non_vegetarian"), expected)

    def test_waste_emissions(self):
        """
        Verify waste calculation with weekly to monthly conversion.
        """
        expected = round(5.0 * 4.33 * 0.5, 2)
        self.assertAlmostEqual(calculate_waste_emissions(5.0), expected)

    def test_total_footprint_structure(self):
        """
        Verify calculate_total_footprint returns dict with all required keys.
        """
        data = {
            "transport_mode": "car_petrol",
            "km_per_day": 20.0,
            "electricity_units": 200.0,
            "diet_type": "vegetarian",
            "waste_kg_per_week": 5.0
        }
        res = calculate_total_footprint(data)
        self.assertIsInstance(res, dict)
        required_keys = ["transport", "electricity", "diet", "waste", "total", "category", "comparison_to_average"]
        for key in required_keys:
            self.assertIn(key, res)

    def test_category_low(self):
        """
        Verify total < 800 returns 'Low' category.
        """
        # Low footprint data: low consumption
        data = {
            "transport_mode": "bike",
            "km_per_day": 10.0,
            "electricity_units": 50.0,
            "diet_type": "vegan",
            "waste_kg_per_week": 2.0
        }
        res = calculate_total_footprint(data)
        self.assertTrue(res["total"] < 800)
        self.assertEqual(res["category"], "Low")

    def test_category_very_high(self):
        """
        Verify total >= 2500 returns 'Very High' category.
        """
        # Very high footprint data: extreme consumption
        data = {
            "transport_mode": "flight",
            "km_per_day": 300.0,
            "electricity_units": 800.0,
            "diet_type": "non_vegetarian",
            "waste_kg_per_week": 40.0
        }
        res = calculate_total_footprint(data)
        self.assertTrue(res["total"] >= 2500)
        self.assertEqual(res["category"], "Very High")

    def test_recommendations_transport(self):
        """
        Verify get_recommendations returns transport suggestion when transport is the largest contributor.
        """
        breakdown = {
            "transport": 300.0,
            "electricity": 50.0,
            "diet": 50.0,
            "waste": 50.0,
            "total": 450.0,
            "transport_mode": "car_petrol",
            "diet_type": "vegetarian"
        }
        # transport = 300 / 450 = 66.7% (> 35% and largest)
        recs = get_recommendations(breakdown)
        self.assertTrue(any(rec["category"] == "Transport" for rec in recs))

    def test_recommendations_returns_list(self):
        """
        Verify get_recommendations always returns a list.
        """
        breakdown_empty = {
            "transport": 0.0,
            "electricity": 0.0,
            "diet": 0.0,
            "waste": 0.0,
            "total": 0.0
        }
        recs = get_recommendations(breakdown_empty)
        self.assertIsInstance(recs, list)

if __name__ == "__main__":
    unittest.main()
