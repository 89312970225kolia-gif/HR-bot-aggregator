from pydantic import BaseModel

from app.db.models import ApplicationStage


class ApplicationSummary(BaseModel):
    application_id: str
    telegram_user_id: int
    vacancy_id: str
    stage: ApplicationStage
