import logging

from aiogram import Router
from aiogram.types import ErrorEvent

LOGGER = logging.getLogger(__name__)


def build_error_router() -> Router:
    router = Router(name="errors")

    @router.error()
    async def global_error_handler(event: ErrorEvent) -> bool:
        error = event.exception
        LOGGER.error(
            "Unhandled Telegram update error",
            exc_info=(type(error), error, error.__traceback__),
        )
        message = getattr(event.update, "message", None)
        if message is not None:
            try:
                await message.answer(
                    "Произошла техническая ошибка. Попробуйте ещё раз немного позже."
                )
            except Exception:
                LOGGER.exception("Unable to send user-friendly error")
        return True

    return router
