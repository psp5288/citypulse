from pydantic import BaseModel


class AnalyticsResponse(BaseModel):
    labels: list[str] = []
    crowd_series: list[float] = []
    risk_series: list[float] = []
    sentiment_series: list[float] = []
    weather_series: list[float] = []
    risk_distribution: list[int] = [0, 0, 0, 0]
    inference_labels: list[str] = []
    inference_series: list[int] = []
    kpis: dict = {}
