from aiogram.fsm.state import State, StatesGroup


class AddMeasurements(StatesGroup):
    shoulders = State()
    waist = State()
    hips = State()
    weight = State()
    confirm = State()
