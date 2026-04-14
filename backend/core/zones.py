ZONES = [
    {
        "id": "nyc-manhattan",
        "name": "Manhattan",
        "city": "New York City",
        "lat": 40.7831,
        "lng": -73.9712,
        "subreddits": ["nyc", "manhattan", "AskNYC"],
        "rss_feed": "https://feeds.reuters.com/reuters/topNews",
        "demographic_weights": None,
        "color": "#0F62FE",
    },
    {
        "id": "nyc-brooklyn",
        "name": "Brooklyn",
        "city": "New York City",
        "lat": 40.6782,
        "lng": -73.9442,
        "subreddits": ["brooklyn", "nyc"],
        "rss_feed": "https://feeds.reuters.com/reuters/topNews",
        "demographic_weights": {
            "passive_consumer": 0.28,
            "skeptic": 0.22,
            "emotional_reactor": 0.16,
            "early_adopter": 0.14,
            "amplifier": 0.08,
            "contrarian": 0.07,
            "institutional": 0.05,
        },
        "color": "#24A148",
    },
    {
        "id": "nyc-queens",
        "name": "Queens",
        "city": "New York City",
        "lat": 40.7282,
        "lng": -73.7949,
        "subreddits": ["queens", "nyc"],
        "rss_feed": "https://feeds.reuters.com/reuters/topNews",
        "demographic_weights": None,
        "color": "#F0A500",
    },
    {
        "id": "nyc-bronx",
        "name": "The Bronx",
        "city": "New York City",
        "lat": 40.8448,
        "lng": -73.8648,
        "subreddits": ["TheBronx", "nyc"],
        "rss_feed": "https://feeds.reuters.com/reuters/topNews",
        "demographic_weights": None,
        "color": "#DA1E28",
    },
    {
        "id": "nyc-statenisland",
        "name": "Staten Island",
        "city": "New York City",
        "lat": 40.5795,
        "lng": -74.1502,
        "subreddits": ["statenisland", "nyc"],
        "rss_feed": "https://feeds.reuters.com/reuters/topNews",
        "demographic_weights": {
            "institutional": 0.15,
            "skeptic": 0.22,
            "passive_consumer": 0.30,
            "emotional_reactor": 0.12,
            "early_adopter": 0.08,
            "amplifier": 0.07,
            "contrarian": 0.06,
        },
        "color": "#8A3FFC",
    },
    {
        "id": "nyc-harlem",
        "name": "Harlem",
        "city": "New York City",
        "lat": 40.8116,
        "lng": -73.9465,
        "subreddits": ["Harlem", "nyc", "AskNYC"],
        "rss_feed": "https://feeds.reuters.com/reuters/topNews",
        "demographic_weights": None,
        "color": "#00D4FF",
    },
    {
        "id": "nyc-lowereast",
        "name": "Lower East Side",
        "city": "New York City",
        "lat": 40.7157,
        "lng": -73.9863,
        "subreddits": ["lowereastside", "nyc"],
        "rss_feed": "https://feeds.reuters.com/reuters/topNews",
        "demographic_weights": {
            "early_adopter": 0.18,
            "amplifier": 0.14,
            "emotional_reactor": 0.17,
            "passive_consumer": 0.25,
            "skeptic": 0.14,
            "contrarian": 0.07,
            "institutional": 0.05,
        },
        "color": "#FF7EB6",
    },
    {
        "id": "nyc-flushing",
        "name": "Flushing",
        "city": "New York City",
        "lat": 40.7675,
        "lng": -73.8330,
        "subreddits": ["queens", "nyc", "ABCDesis"],
        "rss_feed": "https://feeds.reuters.com/reuters/topNews",
        "demographic_weights": {
            "institutional": 0.18,
            "passive_consumer": 0.33,
            "skeptic": 0.20,
            "emotional_reactor": 0.10,
            "early_adopter": 0.09,
            "amplifier": 0.06,
            "contrarian": 0.04,
        },
        "color": "#42BE65",
    },
]


# Chicago district simulation profiles (mirrors the monitored districts in districts.py).
# Each gets calibrated demographic_weights reflecting real neighbourhood character.
CHICAGO_SIMULATION_ZONES = {
    "downtown": {
        "id": "downtown", "name": "Downtown Core", "city": "Chicago",
        "demographic_weights": {
            "institutional": 0.18, "early_adopter": 0.18, "amplifier": 0.14,
            "passive_consumer": 0.20, "skeptic": 0.14, "emotional_reactor": 0.10, "contrarian": 0.06,
        },
    },
    "midtown": {
        "id": "midtown", "name": "Midtown East", "city": "Chicago",
        "demographic_weights": {
            "early_adopter": 0.20, "amplifier": 0.16, "institutional": 0.14,
            "passive_consumer": 0.22, "skeptic": 0.14, "emotional_reactor": 0.09, "contrarian": 0.05,
        },
    },
    "harbor": {
        "id": "harbor", "name": "Harbor District", "city": "Chicago",
        "demographic_weights": {
            "passive_consumer": 0.30, "emotional_reactor": 0.18, "early_adopter": 0.15,
            "amplifier": 0.12, "skeptic": 0.12, "institutional": 0.08, "contrarian": 0.05,
        },
    },
    "arts": {
        "id": "arts", "name": "Arts Quarter", "city": "Chicago",
        "demographic_weights": {
            "early_adopter": 0.22, "emotional_reactor": 0.20, "amplifier": 0.16,
            "contrarian": 0.14, "passive_consumer": 0.16, "skeptic": 0.08, "institutional": 0.04,
        },
    },
    "financial": {
        "id": "financial", "name": "Financial Row", "city": "Chicago",
        "demographic_weights": {
            "institutional": 0.26, "skeptic": 0.22, "passive_consumer": 0.22,
            "early_adopter": 0.12, "amplifier": 0.08, "contrarian": 0.06, "emotional_reactor": 0.04,
        },
    },
    "westside": {
        "id": "westside", "name": "Westside Park", "city": "Chicago",
        "demographic_weights": {
            "passive_consumer": 0.36, "emotional_reactor": 0.22, "skeptic": 0.16,
            "contrarian": 0.10, "early_adopter": 0.08, "amplifier": 0.05, "institutional": 0.03,
        },
    },
    "university": {
        "id": "university", "name": "University Hill", "city": "Chicago",
        "demographic_weights": {
            "skeptic": 0.30, "contrarian": 0.18, "early_adopter": 0.18,
            "institutional": 0.14, "passive_consumer": 0.12, "amplifier": 0.05, "emotional_reactor": 0.03,
        },
    },
    "market": {
        "id": "market", "name": "Market District", "city": "Chicago",
        "demographic_weights": {
            "passive_consumer": 0.28, "emotional_reactor": 0.20, "amplifier": 0.16,
            "early_adopter": 0.14, "skeptic": 0.12, "institutional": 0.06, "contrarian": 0.04,
        },
    },
}


def get_zone_by_id(zone_id: str) -> dict:
    for zone in ZONES:
        if zone["id"] == zone_id:
            return zone
    # Fall back to Chicago simulation zones (district IDs like "downtown", "westside", etc.)
    if zone_id in CHICAGO_SIMULATION_ZONES:
        return CHICAGO_SIMULATION_ZONES[zone_id]
    raise ValueError(f"Unknown zone: {zone_id}")


def get_all_zone_ids() -> list[str]:
    return [z["id"] for z in ZONES]
