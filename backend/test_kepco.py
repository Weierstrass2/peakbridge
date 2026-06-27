import asyncio
from app.services.kepco_service import KepcoService

async def test():
    kepco = KepcoService()
    result = await kepco.get_kepco_summary()
    print(result)

asyncio.run(test())
