from aiogram import Dispatcher

from app.bot.handlers.candidate import build_candidate_router
from app.bot.handlers.errors import build_error_router
from app.bot.handlers.hr import build_hr_router
from app.bot.handlers.start import build_start_router
from app.config import Settings
from app.db.repository import Repository
from app.services.application_flow import ApplicationFlowService
from app.services.google_sheets import GoogleSheetsService


def create_dispatcher(
    repository: Repository,
    flow: ApplicationFlowService,
    sheets: GoogleSheetsService,
    settings: Settings,
) -> Dispatcher:
    dispatcher = Dispatcher()
    dispatcher.include_router(build_start_router(repository, settings))
    dispatcher.include_router(build_hr_router(repository, sheets, settings))
    dispatcher.include_router(build_candidate_router(repository, flow, settings))
    dispatcher.include_router(build_error_router())
    return dispatcher
