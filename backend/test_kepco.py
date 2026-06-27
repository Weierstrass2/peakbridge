import asyncio
import httpx
from datetime import datetime, timedelta

async def test():
    # 어제 날짜로 시도 (오늘 데이터는 23시 이후에 갱신)
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y%m%d")
    today = datetime.now().strftime("%Y%m%d")
    
    url = "https://apis.data.go.kr/B552115/SmpWithForecastDemand/getSmpForecastDemand"
    
    for date in [yesterday, today]:
        params = {
            "serviceKey": "bfd9f8210ee4ea52b156c2b570822168f22977469c8765f7c346e217edc97533",
            "pageNo": "1",
            "numOfRows": "25",
            "dataType": "json",
            "areaCd": "1",
            "yymmdd": date
        }
        
        print(f"\n날짜: {date}")
        async with httpx.AsyncClient() as client:
            response = await client.get(url, params=params, timeout=10)
            print("상태코드:", response.status_code)
            print("응답:", response.text[:500])

asyncio.run(test())
