from typing import Any
import aiohttp

class DreamMSClient:
    def __init__(self, session: aiohttp.ClientSession, base_url: str) -> None:
        self.session=session
        self.base_url=base_url.rstrip('/')

    async def get_economy_average(self, item_name: str, period: int = 7) -> dict[str, Any]:
        async with self.session.get(f"{self.base_url}/economy", params={'item': item_name, 'period': period}) as response:
            text=await response.text()
            if response.status != 200:
                raise RuntimeError(f"Economy API returned status {response.status}: {text[:300]}")
            try:
                result=await response.json(content_type=None)
            except Exception as error:
                raise RuntimeError('Economy API did not return valid JSON.') from error
        if not result.get('ok'):
            raise RuntimeError(f"Economy API returned an unsuccessful response: {result}")
        data=result.get('data',{})
        avg=data.get('avgPrice')
        if not isinstance(avg,(int,float)):
            raise RuntimeError('The API did not return an average price.')
        return {'item': data.get('item',item_name), 'period': data.get('period',f'{period}D'), 'avg_price': int(avg), 'items_sold': data.get('itemsSold'), 'sales': data.get('sales')}
