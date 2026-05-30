from aiogram.fsm.state import State, StatesGroup


class Onboarding(StatesGroup):
    height = State()
    age = State()
    gender = State()
    weight = State()
    timezone = State()
    goals = State()
    confirm = State()
