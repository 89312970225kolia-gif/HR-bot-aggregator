import asyncio

from app.config import get_settings
from app.db.database import Database
from app.db.repository import Repository
from app.vacancies.loader import load_vacancy


async def run() -> None:
    settings = get_settings()
    database = Database(settings.database_path)
    await database.initialize()
    repository = Repository(database)
    await repository.upsert_vacancy(load_vacancy(settings.vacancy_config_path))
    print(f"Database initialized: {settings.database_path}")


if __name__ == "__main__":
    asyncio.run(run())
