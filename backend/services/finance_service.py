"""
Finance intelligence — 100% free, no API keys required.

Sources:
  1. Yahoo Finance (unofficial chart API) — real-time stock index quotes
  2. Frankfurter.app — ECB currency exchange rates (updated daily)
  3. World Bank API — macro indicators: GDP growth, inflation, unemployment

Country → local index mapping covers ~40 major markets.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

import httpx

logger = logging.getLogger(__name__)

# ── Country → primary stock index (Yahoo Finance symbol) ────────────────────
_INDEX_MAP: dict[str, tuple[str, str]] = {
    "US": ("^GSPC",  "S&P 500"),
    "GB": ("^FTSE",  "FTSE 100"),
    "DE": ("^GDAXI", "DAX"),
    "FR": ("^FCHI",  "CAC 40"),
    "JP": ("^N225",  "Nikkei 225"),
    "CN": ("000001.SS", "Shanghai Composite"),
    "HK": ("^HSI",   "Hang Seng"),
    "IN": ("^BSESN", "BSE Sensex"),
    "AU": ("^AXJO",  "ASX 200"),
    "CA": ("^GSPTSE","TSX Composite"),
    "BR": ("^BVSP",  "Bovespa"),
    "KR": ("^KS11",  "KOSPI"),
    "TW": ("^TWII",  "TAIEX"),
    "SG": ("^STI",   "Straits Times"),
    "MX": ("^MXX",   "IPC Mexico"),
    "ZA": ("^J200.JO","JSE Top 40"),
    "SE": ("^OMX",   "OMX Stockholm"),
    "NL": ("^AEX",   "AEX Amsterdam"),
    "ES": ("^IBEX",  "IBEX 35"),
    "IT": ("FTSEMIB.MI","FTSE MIB"),
    "CH": ("^SSMI",  "SMI Switzerland"),
    "PL": ("^WIG20", "WIG20 Warsaw"),
    "TR": ("XU100.IS","BIST 100"),
    "SA": ("^TASI.SR","Tadawul"),
    "AE": ("^DFMGI", "DFM General"),
    "EG": ("^CASE30","EGX 30"),
    "NG": ("^NGSE",  "Nigerian SE"),
    "AR": ("^MERV",  "MERVAL"),
    "RU": ("IMOEX.ME","Moscow Exchange"),
    "ID": ("^JKSE",  "IDX Composite"),
    "TH": ("^SET.BK","SET Thailand"),
    "MY": ("^KLSE",  "KLCI Malaysia"),
    "PH": ("PSEi.PS","PSEi Philippines"),
    "VN": ("^VNINDEX","VN-Index"),
    "PK": ("^KSE",   "KSE 100"),
    "IL": ("^TA125.TA","TA-125 Israel"),
    "NZ": ("^NZ50",  "NZX 50"),
    "NO": ("OBX.OL", "OBX Oslo"),
    "DK": ("^OMXC25","OMX Copenhagen"),
    "FI": ("^OMXH25","OMX Helsinki"),
}

# ── Country → ISO 4217 currency code ────────────────────────────────────────
_CURRENCY_MAP: dict[str, str] = {
    "US": "USD", "GB": "GBP", "EU": "EUR", "JP": "JPY", "CN": "CNY",
    "IN": "INR", "AU": "AUD", "CA": "CAD", "CH": "CHF", "SE": "SEK",
    "NO": "NOK", "DK": "DKK", "NZ": "NZD", "SG": "SGD", "HK": "HKD",
    "KR": "KRW", "BR": "BRL", "MX": "MXN", "ZA": "ZAR", "TR": "TRY",
    "SA": "SAR", "AE": "AED", "EG": "EGP", "NG": "NGN", "AR": "ARS",
    "RU": "RUB", "ID": "IDR", "TH": "THB", "MY": "MYR", "PH": "PHP",
    "VN": "VND", "PK": "PKR", "PL": "PLN", "CZ": "CZK", "HU": "HUF",
    "IL": "ILS", "DE": "EUR", "FR": "EUR", "IT": "EUR", "ES": "EUR",
    "NL": "EUR", "BE": "EUR", "AT": "EUR", "PT": "EUR", "FI": "EUR",
    "GR": "EUR", "IE": "EUR", "KE": "KES", "GH": "GHS", "TW": "TWD",
    "UA": "UAH", "TN": "TND", "MA": "MAD",
}

# Eurozone countries (all use EUR)
_EUROZONE = {"DE","FR","IT","ES","NL","BE","AT","PT","FI","GR","IE","LU","SK","SI","EE","LV","LT","MT","CY"}


async def fetch_country_finance(country_code: str, country_name: str) -> dict:
    """
    Fetch market intelligence for a country:
    - Local stock index (Yahoo Finance)
    - Local currency vs USD (Frankfurter)
    - Macro indicator: GDP growth + inflation (World Bank)

    Returns:
    {
      "index": { "symbol", "name", "price", "change_pct", "currency", "market_state" } | None,
      "currency": { "code", "rate_vs_usd", "rate_vs_eur", "label" } | None,
      "macro": { "gdp_growth_pct", "inflation_pct", "unemployment_pct", "year" } | None,
      "timezone_label": str,
      "market_open": bool
    }
    """
    cc = (country_code or "").upper()

    index_task = _fetch_index(cc)
    fx_task = _fetch_currency(cc)
    macro_task = _fetch_macro(cc, country_name)

    index_data, fx_data, macro_data = await asyncio.gather(
        index_task, fx_task, macro_task, return_exceptions=True
    )

    return {
        "index": index_data if not isinstance(index_data, Exception) else None,
        "currency": fx_data if not isinstance(fx_data, Exception) else None,
        "macro": macro_data if not isinstance(macro_data, Exception) else None,
    }


async def _fetch_index(cc: str) -> dict | None:
    """Yahoo Finance unofficial chart API — no key required."""
    if cc not in _INDEX_MAP:
        return None

    symbol, name = _INDEX_MAP[cc]
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
    params = {"interval": "1d", "range": "5d"}
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=10.0, headers=headers) as client:
            r = await client.get(url, params=params)
            if r.status_code != 200:
                logger.debug("Yahoo Finance %s for %s", r.status_code, symbol)
                return None
            data = r.json()

        result = data.get("chart", {}).get("result", [])
        if not result:
            return None

        meta = result[0].get("meta", {})
        price = meta.get("regularMarketPrice") or meta.get("previousClose")
        prev_close = meta.get("chartPreviousClose") or meta.get("previousClose")
        currency = meta.get("currency", "")
        market_state = meta.get("marketState", "")

        change_pct = None
        if price and prev_close and prev_close != 0:
            change_pct = round((price - prev_close) / prev_close * 100, 2)

        return {
            "symbol": symbol,
            "name": name,
            "price": round(float(price), 2) if price else None,
            "change_pct": change_pct,
            "currency": currency,
            "market_state": market_state,  # PRE, REGULAR, POST, CLOSED
        }
    except Exception as e:
        logger.debug("Yahoo Finance fetch error for %s: %s", symbol, e)
        return None


async def _fetch_currency(cc: str) -> dict | None:
    """
    Frankfurter.app — free ECB exchange rates, no key.
    Returns local currency rate vs USD (and vs EUR for non-EUR currencies).
    """
    # Determine local currency
    local_ccy = _CURRENCY_MAP.get(cc)
    if not local_ccy:
        return None
    if local_ccy == "USD":
        # US dollar — show EUR and GBP rates
        return await _frankfurter_quote("EUR", ["USD", "GBP", "JPY", "CHF"])

    # For all other currencies: get rate vs USD
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            r = await client.get(
                "https://api.frankfurter.app/latest",
                params={"from": "USD", "to": local_ccy},
            )
            if r.status_code != 200:
                return None
            data = r.json()

        rate = data.get("rates", {}).get(local_ccy)
        if rate is None:
            return None

        return {
            "code": local_ccy,
            "rate_vs_usd": round(float(rate), 4),
            "label": f"1 USD = {round(float(rate), 4)} {local_ccy}",
            "date": data.get("date", ""),
        }
    except Exception as e:
        logger.debug("Frankfurter fetch error for %s: %s", cc, e)
        return None


async def _frankfurter_quote(base: str, targets: list[str]) -> dict | None:
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            r = await client.get(
                "https://api.frankfurter.app/latest",
                params={"from": base, "to": ",".join(targets)},
            )
            if r.status_code != 200:
                return None
            data = r.json()
        rates = data.get("rates", {})
        return {
            "code": base,
            "rates": rates,
            "label": f"1 {base} = " + " · ".join(f"{v} {k}" for k, v in list(rates.items())[:2]),
            "date": data.get("date", ""),
        }
    except Exception:
        return None


async def _fetch_macro(cc: str, country_name: str) -> dict | None:
    """
    World Bank API — free, no key, JSON.
    Fetches most recent values for:
      NY.GDP.MKTP.KD.ZG — GDP growth (%)
      FP.CPI.TOTL.ZG    — Inflation (CPI %)
      SL.UEM.TOTL.ZS    — Unemployment (% of labor force)
    """
    if not cc:
        return None

    indicators = {
        "gdp_growth_pct": "NY.GDP.MKTP.KD.ZG",
        "inflation_pct": "FP.CPI.TOTL.ZG",
        "unemployment_pct": "SL.UEM.TOTL.ZS",
    }
    base = "https://api.worldbank.org/v2/country"
    results: dict[str, float | None] = {}
    year: int | None = None

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            tasks = {
                key: client.get(
                    f"{base}/{cc}/indicator/{ind}",
                    params={"format": "json", "mrv": 3, "per_page": 3},
                )
                for key, ind in indicators.items()
            }
            responses = await asyncio.gather(*tasks.values(), return_exceptions=True)

        for key, resp in zip(tasks.keys(), responses):
            if isinstance(resp, Exception):
                results[key] = None
                continue
            try:
                payload = resp.json()
                entries = payload[1] if isinstance(payload, list) and len(payload) > 1 else []
                for entry in entries:
                    if entry.get("value") is not None:
                        results[key] = round(float(entry["value"]), 2)
                        if year is None:
                            try:
                                year = int(entry.get("date", "0"))
                            except ValueError:
                                pass
                        break
                else:
                    results[key] = None
            except Exception:
                results[key] = None

        if all(v is None for v in results.values()):
            return None

        return {**results, "year": year}
    except Exception as e:
        logger.debug("World Bank fetch error for %s: %s", cc, e)
        return None
