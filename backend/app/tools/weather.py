"""天气工具。没配 WEATHER_API_KEY 时返回「服务未配置」，不要 500。"""

import httpx

from app.core.config import settings


async def get_weather(city: str) -> str:
    """查城市天气。没 Key、超时、对方报错都返回中文说明。"""
    if not settings.WEATHER_API_KEY:
        return "服务未配置"
    url = "https://api.openweathermap.org/data/2.5/weather"
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(url, params={"q": city, "appid": settings.WEATHER_API_KEY, "lang": "zh_cn", "units": "metric"})
            if resp.status_code >= 400:
                return f"天气查询失败：HTTP {resp.status_code}"
            data = resp.json()
            desc = (data.get("weather") or [{}])[0].get("description", "")
            temp = (data.get("main") or {}).get("temp")
            return f"{city}：{desc}，气温 {temp}°C"
    except Exception as exc:
        return f"天气查询失败：{exc}"
