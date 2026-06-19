"""Carbon Footprint Calculator Module.

This module contains configuration values and pure Python functions to compute monthly
greenhouse gas emissions (in kg CO2) from various sources (transport, electricity, diet, waste)
and generate personalized recommendations to reduce carbon footprint.
"""

from functools import lru_cache
from typing import Callable, Dict, List, Any, Tuple

# Configuration mapping and emission coefficients constants.
CONFIG: Dict[str, Any] = {
    "TRANSPORT": {
        "car_petrol": 0.192,   # kg CO2 per km
        "car_diesel": 0.171,   # kg CO2 per km
        "car_electric": 0.053, # kg CO2 per km
        "bike": 0.0,           # kg CO2 per km
        "bus": 0.089,          # kg CO2 per km
        "train": 0.041,        # kg CO2 per km
        "flight": 0.255        # kg CO2 per km
    },
    "ELECTRICITY_PER_UNIT": 0.82,  # kg CO2 per kWh (India grid average)
    "DIET": {
        "vegan": 1.5,        # kg CO2 per day
        "vegetarian": 1.7,   # kg CO2 per day
        "non_vegetarian": 3.3 # kg CO2 per day
    },
    "WASTE_PER_KG": 0.5,  # kg CO2 per kg of waste (non-recycled)
    "DAYS_PER_MONTH": 30,
    "WEEKS_PER_MONTH": 4.33,
    "INDIA_AVG_FOOTPRINT": 1500.0,
    "RECOMMENDATION_THRESHOLD": 0.35,
    "RECOMMENDATION_REDUCTION_FACTOR": 0.25,
    "CATEGORIES": {
        "LOW_LIMIT": 800.0,
        "MODERATE_LIMIT": 1500.0,
        "HIGH_LIMIT": 2500.0
    }
}


def calculate_transport_emissions(mode: str, km_per_day: float) -> float:
    """Calculates monthly carbon footprint for transportation.

    Formula:
        Emission = Emission Factor (kg CO2 / km) * Daily Distance (km) * 30 days

    Args:
        mode (str): The transportation mode (must be a key in CONFIG["TRANSPORT"]).
        km_per_day (float): Average kilometers traveled per day. Must be non-negative.

    Returns:
        float: Monthly carbon emissions in kg CO2.

    Raises:
        ValueError: If the transportation mode is invalid or km_per_day is negative.
    """
    if mode not in CONFIG["TRANSPORT"]:
        raise ValueError(
            f"Invalid transport mode: '{mode}'. Must be one of {list(CONFIG['TRANSPORT'].keys())}"
        )
    if km_per_day < 0:
        raise ValueError("Kilometers per day cannot be negative.")
    
    emissions = CONFIG["TRANSPORT"][mode] * km_per_day * CONFIG["DAYS_PER_MONTH"]
    return round(emissions, 2)


def calculate_electricity_emissions(units_per_month: float) -> float:
    """Calculates monthly carbon footprint for electricity.

    Formula:
        Emission = Monthly Electricity Units (kWh) * Grid Emission Factor (kg CO2 / kWh)

    Args:
        units_per_month (float): Monthly electricity consumption in kWh. Must be non-negative.

    Returns:
        float: Monthly carbon emissions in kg CO2.

    Raises:
        ValueError: If units_per_month is negative.
    """
    if units_per_month < 0:
        raise ValueError("Electricity units per month cannot be negative.")
    
    emissions = units_per_month * CONFIG["ELECTRICITY_PER_UNIT"]
    return round(emissions, 2)


def calculate_diet_emissions(diet_type: str) -> float:
    """Calculates monthly carbon footprint for diet.

    Formula:
        Emission = Daily Diet Emission Factor (kg CO2 / day) * 30 days

    Args:
        diet_type (str): The type of diet (must be a key in CONFIG["DIET"]).

    Returns:
        float: Monthly carbon emissions in kg CO2.

    Raises:
        ValueError: If diet_type is invalid.
    """
    if diet_type not in CONFIG["DIET"]:
        raise ValueError(
            f"Invalid diet type: '{diet_type}'. Must be one of {list(CONFIG['DIET'].keys())}"
        )
        
    emissions = CONFIG["DIET"][diet_type] * CONFIG["DAYS_PER_MONTH"]
    return round(emissions, 2)


def calculate_waste_emissions(kg_per_week: float) -> float:
    """Calculates monthly carbon footprint for household waste.

    Formula:
        Emission = Weekly Waste (kg) * 4.33 weeks/month * Waste Emission Factor (kg CO2 / kg)

    Args:
        kg_per_week (float): Average non-recycled waste generated per week in kg. Must be non-negative.

    Returns:
        float: Monthly carbon emissions in kg CO2.

    Raises:
        ValueError: If kg_per_week is negative.
    """
    if kg_per_week < 0:
        raise ValueError("Waste weight per week cannot be negative.")
        
    emissions = kg_per_week * CONFIG["WEEKS_PER_MONTH"] * CONFIG["WASTE_PER_KG"]
    return round(emissions, 2)


def cache_dict_lru(func: Callable[[dict], dict]) -> Callable[[dict], dict]:
    """Decorator to cache functions taking a dictionary argument using lru_cache.

    Args:
        func (Callable): The function to wrap and cache.

    Returns:
        Callable: The decorated function.
    """
    @lru_cache(maxsize=128)
    def cached_version(data_tuple: Tuple[Tuple[str, Any], ...]) -> dict:
        return func(dict(data_tuple))
    
    def wrapper(data: dict) -> dict:
        if isinstance(data, dict):
            data_tuple = tuple(sorted(data.items()))
            return cached_version(data_tuple)
        return cached_version(data)
    
    wrapper.cache_info = cached_version.cache_info
    wrapper.cache_clear = cached_version.cache_clear
    return wrapper


def get_footprint_category(total: float) -> str:
    """Determines the footprint scale category based on monthly total emissions.

    Args:
        total (float): Total monthly emissions in kg CO2.

    Returns:
        str: Category classification string ('Low', 'Moderate', 'High', or 'Very High').
    """
    if total < CONFIG["CATEGORIES"]["LOW_LIMIT"]:
        return "Low"
    elif total < CONFIG["CATEGORIES"]["MODERATE_LIMIT"]:
        return "Moderate"
    elif total < CONFIG["CATEGORIES"]["HIGH_LIMIT"]:
        return "High"
    return "Very High"


def get_comparison_to_average(total: float) -> float:
    """Computes comparison percentage of emissions vs. the national Indian average.

    Args:
        total (float): Total monthly emissions in kg CO2.

    Returns:
        float: Percentage comparison rounded to 2 decimal places.
    """
    return round((total / CONFIG["INDIA_AVG_FOOTPRINT"]) * 100, 2)


@cache_dict_lru
def calculate_total_footprint(data: dict) -> dict:
    """Calculates the breakdown and total carbon footprint.

    Input data format:
        {
            "transport_mode": str,
            "km_per_day": float,
            "electricity_units": float,
            "diet_type": str,
            "waste_kg_per_week": float
        }

    Args:
        data (dict): Dictionary mapping resource categories to consumption values.

    Returns:
        dict: A breakdown dictionary containing category emissions, total, and rankings.

    Raises:
        ValueError: If input values are negative or invalid.
        KeyError: If required keys are missing in the data dictionary.
    """
    transport = calculate_transport_emissions(
        data["transport_mode"], 
        float(data["km_per_day"])
    )
    electricity = calculate_electricity_emissions(
        float(data["electricity_units"])
    )
    diet = calculate_diet_emissions(
        data["diet_type"]
    )
    waste = calculate_waste_emissions(
        float(data["waste_kg_per_week"])
    )
    
    total = round(transport + electricity + diet + waste, 2)
    category = get_footprint_category(total)
    comparison = get_comparison_to_average(total)
    
    return {
        "transport": transport,
        "electricity": electricity,
        "diet": diet,
        "waste": waste,
        "total": total,
        "category": category,
        "comparison_to_average": comparison,
        "transport_mode": data["transport_mode"],
        "diet_type": data["diet_type"]
    }


def get_recommendations(breakdown: dict) -> List[Dict[str, Any]]:
    """Generates targeted carbon-reduction recommendations based on emissions contributors.

    Logic:
        For each category, if it is the LARGEST contributor AND accounts for more than
        35% (CONFIG["RECOMMENDATION_THRESHOLD"]) of the total emissions, a specific
        recommendation is created.

    Args:
        breakdown (dict): Breakdown dictionary as returned by `calculate_total_footprint`.

    Returns:
        List[Dict[str, Any]]: List of recommendation dictionaries.
    """
    total = breakdown.get("total", 0.0)
    if total <= 0:
        return []
        
    categories = ["transport", "electricity", "diet", "waste"]
    max_val = max(breakdown.get(cat, 0.0) for cat in categories)
    recommendations: List[Dict[str, Any]] = []
    
    for cat in categories:
        val = breakdown.get(cat, 0.0)
        is_largest = (val == max_val)
        is_over_threshold = ((val / total) > CONFIG["RECOMMENDATION_THRESHOLD"])
        
        if is_largest and is_over_threshold:
            potential_reduction = round(val * CONFIG["RECOMMENDATION_REDUCTION_FACTOR"], 2)
            
            if cat == "transport":
                mode = breakdown.get("transport_mode")
                if mode in ["car_petrol", "car_diesel"]:
                    recommendations.append({
                        "category": "Transport",
                        "issue": f"High travel emissions from driving a gasoline/diesel car ({mode.replace('_', ' ')}).",
                        "suggestion": "Consider carpooling, using public transit (bus/train), or switching to an electric or hybrid vehicle.",
                        "potential_reduction_kg": potential_reduction
                    })
                elif mode == "flight":
                    recommendations.append({
                        "category": "Transport",
                        "issue": "High emissions from frequent air travel.",
                        "suggestion": "Reduce flight frequency by opting for virtual meetings where possible, or offset flight emissions through verified tree plantation/carbon-offset programs.",
                        "potential_reduction_kg": potential_reduction
                    })
                else:
                    recommendations.append({
                        "category": "Transport",
                        "issue": f"Transport is your highest contributor via {mode.replace('_', ' ')}.",
                        "suggestion": "Try walking or cycling for short commutes, and combine errands to reduce total distance traveled.",
                        "potential_reduction_kg": potential_reduction
                    })
                    
            elif cat == "electricity":
                recommendations.append({
                    "category": "Electricity",
                    "issue": "High household electricity consumption from the grid.",
                    "suggestion": "Upgrade to LED bulbs, unplug phantom-load electronics when not in use, choose 5-star energy-efficient appliances, or install rooftop solar panels.",
                    "potential_reduction_kg": potential_reduction
                })
                
            elif cat == "diet":
                diet_type = breakdown.get("diet_type")
                if diet_type == "non_vegetarian":
                    recommendations.append({
                        "category": "Diet",
                        "issue": "High dietary carbon footprint due to meat consumption.",
                        "suggestion": "Reduce red meat consumption by introducing more plant-based meals, or transition toward a vegetarian or vegan diet.",
                        "potential_reduction_kg": potential_reduction
                    })
                else:
                    recommendations.append({
                        "category": "Diet",
                        "issue": f"Dietary choices ({diet_type}) represent your largest emission source.",
                        "suggestion": "Buy locally grown, organic, and seasonal foods to minimize packaging and long-distance transportation emissions.",
                        "potential_reduction_kg": potential_reduction
                    })
                    
            elif cat == "waste":
                recommendations.append({
                    "category": "Waste",
                    "issue": "High volume of non-recycled waste generation.",
                    "suggestion": "Start composting organic waste at home, actively sort recyclable items (paper, glass, metal), and avoid single-use plastics.",
                    "potential_reduction_kg": potential_reduction
                })
                
    return recommendations
