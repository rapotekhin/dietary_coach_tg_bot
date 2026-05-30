from __future__ import annotations

from datetime import datetime

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.db.models import WEIGHT_GOALS, Gender, GoalCode
from app.db.session import get_sessionmaker
from app.keyboards.onboarding import confirm_kb, gender_kb, goals_kb
from app.services import user_service
from app.states.onboarding import Onboarding
from app.utils.labels import GENDER_LABELS, GOAL_LABELS
from app.utils.time_utils import fmt_dt
from app.utils.validators import is_valid_tz, parse_positive_float, parse_positive_int

router = Router(name="start")

HELP_TEXT = (
    "📘 <b>Памятка</b>\n\n"
    "<b>Как пользоваться:</b>\n"
    "• Покушал → скинул фото/текст в чат → выбрал тип, голод, насыщение кнопками.\n"
    "• Раз в 2 недели — /add_measurements (плечи, талия, бёдра, вес).\n"
    "• Периодически — /get_report для PDF-отчёта по периоду.\n\n"
    "<b>Шкала голода (1-5):</b>\n"
    "1 = сыт, нет чувства голода\n"
    "2 = чуть проголодался\n"
    "3 = ощутимый голод, пора есть\n"
    "4 = сильный голод\n"
    "5 = очень голоден, тяжело терпеть\n\n"
    "<b>Шкала насыщения (1-5):</b>\n"
    "1 = не наелся\n"
    "2 = чуть-чуть\n"
    "3 = норм, насытился\n"
    "4 = переел, тяжесть\n"
    "5 = очень переел\n\n"
    "<b>Гарвардская тарелка (правило 1/2 + 1/4 + 1/4):</b>\n"
    "• ½ — овощи и фрукты\n"
    "• ¼ — цельные злаки\n"
    "• ¼ — белок (рыба, птица, бобовые)\n"
    "• Полезные жиры в небольшом количестве, вода вместо сладких напитков.\n\n"
    "<b>Замеры тела:</b> измеряйте утром натощак, сантиметровой лентой без натяжения. "
    "Плечи — самая широкая часть, талия — на уровне пупка, бёдра — самая широкая часть ягодиц.\n\n"
    "<b>Команды:</b>\n"
    "/start — показать профиль\n"
    "/add_measurements — добавить замеры\n"
    "/get_report — PDF-отчёт за период"
)


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    assert message.from_user is not None
    sm = get_sessionmaker()
    async with sm() as session:
        user = await user_service.get_user(session, message.from_user.id)
    if user is not None:
        goals = ", ".join(GOAL_LABELS.get(g.code, g.code) for g in user.goals) or "—"
        await message.answer(
            f"<b>Профиль уже настроен.</b>\n\n"
            f"Рост: <code>{user.height_cm} см</code>\n"
            f"Возраст: <code>{user.age}</code>\n"
            f"Пол: <code>{GENDER_LABELS.get(user.gender, user.gender)}</code>\n"
            f"Часовой пояс: <code>{user.timezone}</code>\n"
            f"Цели: {goals}\n\n"
            "Повторная настройка профиля запрещена.\n\n"
            "Чтобы скинуть приём пищи — просто отправь фото или текст в этот чат.\n"
            "Замеры — /add_measurements, отчёт — /get_report.",
            parse_mode="HTML",
        )
        return

    await state.clear()
    await state.set_state(Onboarding.height)
    await message.answer(
        "👋 Привет! Давай настроим профиль.\n\n"
        "Введи <b>рост</b> в сантиметрах (например: 178):",
        parse_mode="HTML",
    )


@router.message(Onboarding.height)
async def on_height(message: Message, state: FSMContext) -> None:
    v = parse_positive_float(message.text or "", 80, 250)
    if v is None:
        await message.answer("Не понял. Введи рост числом в см (от 80 до 250).")
        return
    await state.update_data(height=v)
    await state.set_state(Onboarding.age)
    await message.answer("Введи <b>возраст</b> (полных лет):", parse_mode="HTML")


@router.message(Onboarding.age)
async def on_age(message: Message, state: FSMContext) -> None:
    v = parse_positive_int(message.text or "", 5, 120)
    if v is None:
        await message.answer("Введи возраст целым числом (5–120).")
        return
    await state.update_data(age=v)
    await state.set_state(Onboarding.gender)
    await message.answer("Выбери <b>пол</b>:", parse_mode="HTML", reply_markup=gender_kb())


@router.callback_query(Onboarding.gender, F.data.startswith("gender:"))
async def on_gender(callback: CallbackQuery, state: FSMContext) -> None:
    assert callback.data is not None and callback.message is not None
    gender = callback.data.split(":", 1)[1]
    if gender not in (Gender.MALE.value, Gender.FEMALE.value):
        await callback.answer("Неизвестный пол", show_alert=True)
        return
    await state.update_data(gender=gender)
    await state.set_state(Onboarding.weight)
    await callback.message.edit_text(f"Пол: <b>{GENDER_LABELS[gender]}</b>", parse_mode="HTML")
    await callback.message.answer("Введи текущий <b>вес</b> в кг (например: 72.5):", parse_mode="HTML")
    await callback.answer()


@router.message(Onboarding.weight)
async def on_weight(message: Message, state: FSMContext) -> None:
    v = parse_positive_float(message.text or "", 20, 400)
    if v is None:
        await message.answer("Введи вес числом в кг (20–400).")
        return
    await state.update_data(weight=v)
    await state.set_state(Onboarding.timezone)
    await message.answer(
        "Введи свой <b>часовой пояс</b> в формате IANA (например: <code>Europe/Moscow</code>, "
        "<code>Asia/Novosibirsk</code>, <code>Europe/Berlin</code>):",
        parse_mode="HTML",
    )


@router.message(Onboarding.timezone)
async def on_timezone(message: Message, state: FSMContext) -> None:
    tz = (message.text or "").strip()
    if not is_valid_tz(tz):
        await message.answer(
            "Не похоже на корректный TZ. Используй формат вида <code>Europe/Moscow</code>.",
            parse_mode="HTML",
        )
        return
    await state.update_data(timezone=tz, selected_goals=[])
    await state.set_state(Onboarding.goals)
    await message.answer(
        "Выбери <b>цели</b> (можно несколько; снижение / набор / удержание веса — взаимоисключающие):",
        parse_mode="HTML",
        reply_markup=goals_kb(set()),
    )


@router.callback_query(Onboarding.goals, F.data.startswith("goal:toggle:"))
async def on_goal_toggle(callback: CallbackQuery, state: FSMContext) -> None:
    assert callback.data is not None and callback.message is not None
    code = callback.data.split(":", 2)[2]
    data = await state.get_data()
    selected: set[str] = set(data.get("selected_goals", []))
    if code in selected:
        selected.discard(code)
    else:
        if code in {g.value for g in WEIGHT_GOALS}:
            # снимаем другие weight-цели
            selected -= {g.value for g in WEIGHT_GOALS}
        selected.add(code)
    await state.update_data(selected_goals=list(selected))
    await callback.message.edit_reply_markup(reply_markup=goals_kb(selected))
    await callback.answer()


@router.callback_query(Onboarding.goals, F.data == "goal:done")
async def on_goals_done(callback: CallbackQuery, state: FSMContext) -> None:
    assert callback.message is not None
    data = await state.get_data()
    selected: list[str] = list(data.get("selected_goals", []))
    if not selected:
        await callback.answer("Выбери хотя бы одну цель", show_alert=True)
        return
    await state.set_state(Onboarding.confirm)

    goals_text = "\n".join(f"• {GOAL_LABELS[c]}" for c in selected)
    summary = (
        "📝 <b>Проверь данные:</b>\n\n"
        f"Рост: <code>{data['height']} см</code>\n"
        f"Возраст: <code>{data['age']}</code>\n"
        f"Пол: <code>{GENDER_LABELS[data['gender']]}</code>\n"
        f"Вес: <code>{data['weight']} кг</code>\n"
        f"Часовой пояс: <code>{data['timezone']}</code>\n\n"
        f"<b>Цели:</b>\n{goals_text}\n\n"
        "<i>Замеры тела (плечи, талия, бёдра) можно добавить позже командой /add_measurements.</i>"
    )
    await callback.message.edit_text(summary, parse_mode="HTML", reply_markup=confirm_kb("onboarding"))
    await callback.answer()


@router.callback_query(Onboarding.confirm, F.data == "onboarding:save")
async def on_confirm_save(callback: CallbackQuery, state: FSMContext) -> None:
    assert callback.from_user is not None and callback.message is not None
    data = await state.get_data()
    sm = get_sessionmaker()
    async with sm() as session:
        if await user_service.user_exists(session, callback.from_user.id):
            await callback.answer("Профиль уже сохранён ранее", show_alert=True)
            await state.clear()
            return
        await user_service.create_user(
            session,
            user_id=callback.from_user.id,
            height_cm=float(data["height"]),
            age=int(data["age"]),
            gender=data["gender"],
            timezone=data["timezone"],
            goal_codes=list(data["selected_goals"]),
            weight_kg=float(data["weight"]),
            measured_at=datetime.utcnow(),
        )
    await state.clear()
    await callback.message.edit_text("✅ Профиль сохранён.", parse_mode="HTML")
    await callback.message.answer(HELP_TEXT, parse_mode="HTML")
    await callback.answer()


@router.callback_query(Onboarding.confirm, F.data == "onboarding:cancel")
async def on_confirm_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    assert callback.message is not None
    await state.clear()
    await callback.message.edit_text("Отменено. Запусти /start заново, чтобы повторить.")
    await callback.answer()
