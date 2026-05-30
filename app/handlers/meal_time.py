from __future__ import annotations

import re
from datetime import datetime

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram_calendar import SimpleCalendar, SimpleCalendarCallback

from app.db.session import get_sessionmaker
from app.keyboards.meal import meal_header, meal_kb
from app.services import meal_service
from app.states.meal_time import EditMealTime
from app.utils.time_utils import fmt_dt

router = Router(name="meal_time")

TIME_RE = re.compile(r"^(\d{1,2}):(\d{2})$")


@router.callback_query(F.data.startswith("meal:edit_time:"))
async def on_edit_time(callback: CallbackQuery, state: FSMContext) -> None:
    assert callback.data is not None and callback.message is not None
    meal_id = int(callback.data.split(":", 2)[2])
    await state.set_state(EditMealTime.pick_date)
    await state.update_data(
        meal_id=meal_id,
        card_chat_id=callback.message.chat.id,
        card_message_id=callback.message.message_id,
    )
    calendar = SimpleCalendar(show_alerts=True)
    await callback.message.answer(
        "📅 Выбери дату приёма пищи:", reply_markup=await calendar.start_calendar()
    )
    await callback.answer()


@router.callback_query(EditMealTime.pick_date, SimpleCalendarCallback.filter())
async def on_calendar_select(
    callback: CallbackQuery, callback_data: SimpleCalendarCallback, state: FSMContext
) -> None:
    assert callback.message is not None
    calendar = SimpleCalendar(show_alerts=True)
    selected, date = await calendar.process_selection(callback, callback_data)
    if not selected:
        return
    await state.update_data(picked_year=date.year, picked_month=date.month, picked_day=date.day)
    await state.set_state(EditMealTime.pick_time)
    await callback.message.answer(
        f"Дата: <code>{date.strftime('%d.%m.%Y')}</code>\n\n"
        "Теперь введи время в формате <code>HH:MM</code> (например <code>13:30</code>):",
        parse_mode="HTML",
    )


@router.message(EditMealTime.pick_time, F.text)
async def on_time_input(message: Message, state: FSMContext) -> None:
    assert message.from_user is not None
    m = TIME_RE.match((message.text or "").strip())
    if not m:
        await message.answer("Неверный формат. Жду <code>HH:MM</code>, например <code>13:30</code>.", parse_mode="HTML")
        return
    hour, minute = int(m.group(1)), int(m.group(2))
    if not (0 <= hour < 24 and 0 <= minute < 60):
        await message.answer("Часы 0–23, минуты 0–59. Попробуй ещё раз.")
        return

    data = await state.get_data()
    occurred_at = datetime(
        int(data["picked_year"]),
        int(data["picked_month"]),
        int(data["picked_day"]),
        hour,
        minute,
    )
    sm = get_sessionmaker()
    async with sm() as session:
        meal = await meal_service.update_meal_field(
            session, int(data["meal_id"]), message.from_user.id, occurred_at=occurred_at
        )
    if meal is None:
        await message.answer("Приём не найден.")
        await state.clear()
        return

    # Обновим карточку приёма
    try:
        await message.bot.edit_message_text(
            chat_id=int(data["card_chat_id"]),
            message_id=int(data["card_message_id"]),
            text=meal_header(fmt_dt(meal.occurred_at)),
            parse_mode="HTML",
            reply_markup=meal_kb(meal.id, meal.meal_type, meal.hunger, meal.satiety),
        )
    except Exception:
        pass
    await message.answer(f"✅ Время приёма обновлено: <code>{fmt_dt(occurred_at)}</code>", parse_mode="HTML")
    await state.clear()
