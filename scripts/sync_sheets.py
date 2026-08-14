import asyncio
import logging

from app.config import get_settings
from app.db.database import Database
from app.db.repository import Repository
from app.logging_config import configure_logging
from app.services.google_sheets import GoogleSheetsService, load_ai_result


async def run() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    if not settings.google_sheets_enabled:
        raise RuntimeError("GOOGLE_SHEETS_ENABLED must be true")
    repository = Repository(Database(settings.database_path))
    sheets = GoogleSheetsService(settings)
    applications = await repository.list_unsynced()
    success = 0
    for application in applications:
        try:
            sync = await sheets.upsert(application, load_ai_result(application))
            await repository.mark_sheet_sync(
                application.application_id, synced=True, row=sync.row
            )
            success += 1
        except Exception:
            logging.exception(
                "Unable to sync application_id=%s", application.application_id
            )
    print(f"Sheets sync complete: success={success}, failed={len(applications) - success}")


if __name__ == "__main__":
    asyncio.run(run())
