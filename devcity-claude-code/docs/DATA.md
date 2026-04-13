# DATA.md — Zone Definitions & Social Ingestion

## core/zones.py — 8 NYC Zones (Baseline City)

```python
ZONES = [
    {
        "id": "nyc-manhattan",
        "name": "Manhattan",
        "city": "New York City",
        "lat": 40.7831,
        "lng": -73.9712,
        "subreddits": ["nyc", "manhattan", "AskNYC"],
        "rss_feed": "https://feeds.reuters.com/reuters/topNews",
        "demographic_weights": None,  # uses defaults
        "color": "#0F62FE",           # IBM blue — used on map
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

def get_zone_by_id(zone_id: str) -> dict:
    for zone in ZONES:
        if zone["id"] == zone_id:
            return zone
    raise ValueError(f"Unknown zone: {zone_id}")

def get_all_zone_ids() -> list[str]:
    return [z["id"] for z in ZONES]
```

---

## Week 4 — Multi-City Expansion (add these)

When extending to multiple cities, follow the same pattern:

### London Zones (Week 4)
```python
LONDON_ZONES = [
    {
        "id": "lon-central",
        "name": "Central London",
        "city": "London",
        "lat": 51.5074, "lng": -0.1278,
        "subreddits": ["london", "unitedkingdom"],
        "rss_feed": "https://feeds.bbci.co.uk/news/rss.xml",
        "color": "#0F62FE",
    },
    {
        "id": "lon-eastend",
        "name": "East End",
        "city": "London",
        "lat": 51.5200, "lng": -0.0550,
        "subreddits": ["london", "eastlondon"],
        "rss_feed": "https://feeds.bbci.co.uk/news/rss.xml",
        "color": "#24A148",
    },
]
```

### Chicago Zones (Week 4)
```python
CHICAGO_ZONES = [
    {
        "id": "chi-loop",
        "name": "The Loop",
        "city": "Chicago",
        "lat": 41.8827, "lng": -87.6233,
        "subreddits": ["chicago", "ChicagoSuburbs"],
        "rss_feed": "https://feeds.reuters.com/reuters/topNews",
        "color": "#0F62FE",
    },
]
```

---

## RSS Feed Sources

| Feed | URL | Use |
|---|---|---|
| Reuters Top News | `https://feeds.reuters.com/reuters/topNews` | General US news |
| BBC News | `https://feeds.bbci.co.uk/news/rss.xml` | UK / London zones |
| AP News | `https://rsshub.app/apnews/topics/apf-topnews` | Backup general |
| NY Times | `https://rss.nytimes.com/services/xml/rss/nyt/HomePage.xml` | NYC specific |
| Guardian | `https://www.theguardian.com/us/rss` | US progressive angle |

---

## Social Ingestion Notes

- **Reddit rate limit**: 60 requests/minute with OAuth. PRAW handles this. Never exceed 25 posts per subreddit per call.
- **RSS feeds**: No auth needed. Cache for 5 minutes. Don't hammer.
- **Post filtering**: Only use posts from the last 30 minutes. Filter out posts with negative karma.
- **Text cleaning**: Strip URLs, usernames, emojis before sending to WatsonX (reduces tokens).
- **No PII**: Never store individual usernames or post IDs. Only use post title text as a signal.

---

## Text Preprocessing (apply before WatsonX)

```python
import re

def clean_post(text: str) -> str:
    text = re.sub(r'http\S+', '', text)          # remove URLs
    text = re.sub(r'@\w+', '', text)             # remove @mentions
    text = re.sub(r'u/\w+', '', text)            # remove Reddit usernames
    text = re.sub(r'[^\w\s\.\!\?\,\-]', '', text)  # remove special chars
    text = re.sub(r'\s+', ' ', text).strip()     # collapse whitespace
    return text[:280]                             # cap at tweet length

def preprocess_posts(posts: list[str]) -> list[str]:
    cleaned = [clean_post(p) for p in posts]
    return [p for p in cleaned if len(p) > 20]  # drop very short posts
```
