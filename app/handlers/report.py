from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, Message

from app.db.session import get_sessionmaker
from app.services import meal_service, measurement_service, user_service
from app.services.report_service import ReportData, build_pdf
from app.states.report import ReportFlow
from app.utils.time_utils import parse_period

router = Router(name="report")


@router.message(Command("get_report"))
async def cmd_get_report(message: Message, state: FSMContext) -> None:
    assert message.from_user is not None
    sm = get_sessionmaker()
    async with sm() as session:
        if not await user_service.user_exists(session, message.from_user.id):
            await message.answer("Сначала настрой профиль: /start")
            return
    await state.clear()
    await state.set_state(ReportFlow.period)
    await message.answer(
        "Введи период в формате <code>DDMMYYYY-DDMMYYYY</code>\n"
        "Например: <code>01052025-31052025</code>",
        parse_mode="HTML",
    )


@router.message(ReportFlow.period)
async def on_period(message: Message, state: FSMContext) -> None:
    assert message.from_user is not None
    period = parse_period(message.text or "")
    if period is None:
        await message.answer("Не похоже на корректный период. Жду DDMMYYYY-DDMMYYYY, конец >= начала.")
        return
    start, end = period
    await message.answer("⏳ Готовлю отчёт...")

    sm = get_sessionmaker()
    async with sm() as session:
        user = await user_service.get_user(session, message.from_user.id)
        assert user is not None
        meals = await meal_service.list_meals_in_period(session, user.user_id, start, end)
        measurements = await measurement_service.list_measurements_in_period(
            session, user.user_id, start, end
        )
        prev = await measurement_service.last_measurement_before(session, user.user_id, start)
        goals = await user_service.get_goal_codes(session, user.user_id)

    report = ReportData(
        period_start=start,
        period_end=end,
        goals=goals,
        meals=meals,
        measurements=measurements,
        prev_measurement=prev,
        height_cm=user.height_cm,
        age=user.age,
        gender=user.gender,
    )
    pdf = build_pdf(report)
    filename = f"report_{start.strftime('%Y%m%d')}_{end.strftime('%Y%m%d')}.pdf"
    await message.answer_document(
        BufferedInputFile(pdf.read(), filename=filename),
        caption=f"Отчёт за {start.strftime('%d.%m.%Y')}—{end.strftime('%d.%m.%Y')}",
    )
    await state.clear()
