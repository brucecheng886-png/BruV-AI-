"""
Weather Plugin Handler
使用 Open-Meteo（免費，無需 API Key）查詢天氣
params: {city: "Taipei", latitude: 25.05, longitude: 121.53, days: 1}
"""
import logging
import httpx

logger = logging.getLogger(__name__)

# 常用城市座標預設
_CITY_COORDS = {
    "taipei": (25.05, 121.53),
    "台北": (25.05, 121.53),
    "台中": (24.15, 120.67),
    "高雄": (22.63, 120.31),
    "tokyo": (35.68, 139.69),
    "東京": (35.68, 139.69),
    "beijing": (39.91, 116.39),
    "shanghai": (31.23, 121.47),
    "new york": (40.71, -74.01),
    "london": (51.51, -0.13),
}

_WMO_CODES = {
    0: "晴天", 1: "大致晴朗", 2: "局部多雲", 3: "陰天",
    45: "霧", 48: "霜霧",
    51: "毛毛雨（輕）", 53: "毛毛雨", 55: "毛毛雨（重）",
    61: "小雨", 63: "中雨", 65: "大雨",
    71: "小雪", 73: "中雪", 75: "大雪",
    80: "陣雨（輕）", 81: "陣雨", 82: "陣雨（重）",
    95: "雷雨", 96: "雷雨伴冰雹", 99: "強雷雨伴冰雹",
}


async def run(action: str, params: dict, config: dict) -> dict:
    city = params.get("city", "")
    lat  = params.get("latitude")
    lon  = params.get("longitude")

    # 解析座標
    if lat is None or lon is None:
        key = city.lower()
        coords = _CITY_COORDS.get(key)
        if coords:
            lat, lon = coords
        else:
            return {
                "success": False,
                "error": f"找不到城市 '{city}' 的座標，請直接提供 latitude 和 longitude 參數",
            }

    days = min(int(params.get("days", 1)), 7)
    url  = "https://api.open-meteo.com/v1/forecast"

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url, params={
                "latitude": lat,
                "longitude": lon,
                "current": "temperature_2m,relative_humidity_2m,windspeed_10m,weathercode",
                "daily": "temperature_2m_max,temperature_2m_min,weathercode,precipitation_sum",
                "timezone": "auto",
                "forecast_days": days,
            })
            resp.raise_for_status()
    except Exception as e:
        return {"success": False, "error": f"天氣 API 請求失敗: {e}"}

    data = resp.json()
    current = data.get("current", {})
    daily   = data.get("daily", {})

    result = {
        "location": city or f"{lat},{lon}",
        "current": {
            "temperature": current.get("temperature_2m"),
            "humidity":    current.get("relative_humidity_2m"),
            "windspeed":   current.get("windspeed_10m"),
            "condition":   _WMO_CODES.get(current.get("weathercode", -1), "未知"),
        },
        "forecast": [],
    }

    times     = daily.get("time", [])
    max_temps = daily.get("temperature_2m_max", [])
    min_temps = daily.get("temperature_2m_min", [])
    conditions = daily.get("weathercode", [])
    precips   = daily.get("precipitation_sum", [])

    for i, t in enumerate(times):
        result["forecast"].append({
            "date":       t,
            "max_temp":   max_temps[i] if i < len(max_temps) else None,
            "min_temp":   min_temps[i] if i < len(min_temps) else None,
            "condition":  _WMO_CODES.get(conditions[i] if i < len(conditions) else -1, "未知"),
            "precipitation": precips[i] if i < len(precips) else 0,
        })

    return {"success": True, "data": result}
