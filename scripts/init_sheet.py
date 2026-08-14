import asyncio

from app.config import get_settings
from app.services.google_sheets import GoogleSheetsService


async def run() -> None:
    settings = get_settings()
    service = GoogleSheetsService(settings)
    headers = await service.ensure_headers()
    print(f"Sheet ready: {settings.google_sheet_name}; headers={len(headers)}")


if __name__ == "__main__":
    asyncio.run(run())
