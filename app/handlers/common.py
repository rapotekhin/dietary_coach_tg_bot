from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

router = Router(name="common")


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext) -> None:
    if await state.get_state() is None:
        await message.answer("Сейчас ничего отменять не нужно.")
        return
    await state.clear()
    await message.answer("Отменено.")


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(
        "Команды:\n"
        "/start — настройка / просмотр профиля\n"
        "/add_measurements — добавить замеры (плечи, талия, бёдра, вес)\n"
        "/get_report — PDF-отчёт за период (DDMMYYYY-DDMMYYYY)\n"
        "/cancel — отменить текущее действие\n\n"
        "Чтобы записать приём пищи — просто отправь фото или текст в чат."
    )
