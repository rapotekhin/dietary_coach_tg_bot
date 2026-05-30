from __future__ import annotations

from datetime import datetime

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.db.session import get_sessionmaker
from app.keyboards.onboarding import confirm_kb
from app.services import measurement_service, user_service
from app.states.measurements import AddMeasurements
from app.utils.validators import parse_positive_float

router = Router(name="measurements")


@router.message(Command("add_measurements"))
async def cmd_add_measurements(message: Message, state: FSMContext) -> None:
    assert message.from_user is not None
    sm = get_sessionmaker()
    async with sm() as session:
        if not await user_service.user_exists(session, message.from_user.id):
            await message.answer("Сначала настрой профиль: /start")
            return
    await state.clear()
    await state.set_state(AddMeasurements.shoulders)
    await message.answer("Обхват <b>плеч</b> в см:", parse_mode="HTML")


@router.message(AddMeasurements.shoulders)
async def on_shoulders(message: Message, state: FSMContext) -> None:
    v = parse_positive_float(message.text or "", 30, 250)
    if v is None:
        await message.answer("Введи число в см (30–250).")
        return
    await state.update_data(shoulders=v)
    await state.set_state(AddMeasurements.waist)
    await message.answer("Обхват <b>талии</b> в см:", parse_mode="HTML")


@router.message(AddMeasurements.waist)
async def on_waist(message: Message, state: FSMContext) -> None:
    v = parse_positive_float(message.text or "", 30, 250)
    if v is None:
        await message.answer("Введи число в см (30–250).")
        return
    await state.update_data(waist=v)
    await state.set_state(AddMeasurements.hips)
    await message.answer("Обхват <b>бёдер</b> в см:", parse_mode="HTML")


@router.message(AddMeasurements.hips)
async def on_hips(message: Message, state: FSMContext) -> None:
    v = parse_positive_float(message.text or "", 30, 250)
    if v is None:
        await message.answer("Введи число в см (30–250).")
        return
    await state.update_data(hips=v)
    await state.set_state(AddMeasurements.weight)
    await message.answer("Текущий <b>вес</b> в кг:", parse_mode="HTML")


@router.message(AddMeasurements.weight)
async def on_weight(message: Message, state: FSMContext) -> None:
    v = parse_positive_float(message.text or "", 20, 400)
    if v is None:
        await message.answer("Введи число в кг (20–400).")
        return
    await state.update_data(weight=v)
    data = await state.get_data()
    summary = (
        "📝 <b>Проверь замеры:</b>\n\n"
        f"Плечи: <code>{data['shoulders']} см</code>\n"
        f"Талия: <code>{data['waist']} см</code>\n"
        f"Бёдра: <code>{data['hips']} см</code>\n"
        f"Вес: <code>{data['weight']} кг</code>"
    )
    await state.set_state(AddMeasurements.confirm)
    await message.answer(summary, parse_mode="HTML", reply_markup=confirm_kb("measurements"))


@router.callback_query(AddMeasurements.confirm, F.data == "measurements:save")
async def on_confirm_save(callback: CallbackQuery, state: FSMContext) -> None:
    assert callback.from_user is not None and callback.message is not None
    data = await state.get_data()
    sm = get_sessionmaker()
    async with sm() as session:
        await measurement_service.add_measurement(
            session,
            user_id=callback.from_user.id,
            shoulders_cm=float(data["shoulders"]),
            waist_cm=float(data["waist"]),
            hips_cm=float(data["hips"]),
            weight_kg=float(data["weight"]),
            measured_at=datetime.utcnow(),
        )
    await state.clear()
    await callback.message.edit_text("✅ Замеры сохранены.", parse_mode="HTML")
    await callback.answer()


@router.callback_query(AddMeasurements.confirm, F.data == "measurements:cancel")
async def on_confirm_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    assert callback.message is not None
    await state.clear()
    await callback.message.edit_text("Отменено.")
    await callback.answer()
