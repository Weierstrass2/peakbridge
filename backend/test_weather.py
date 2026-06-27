import asyncio
from app.services.weather_service import WeatherService

async def test():
    ws = WeatherService()
    result = await ws.get_weather_summary()
    print(result)

asyncio.run(test())
