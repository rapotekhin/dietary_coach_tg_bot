from aiogram.fsm.state import State, StatesGroup


class EditMealTime(StatesGroup):
    pick_date = State()
    pick_time = State()
