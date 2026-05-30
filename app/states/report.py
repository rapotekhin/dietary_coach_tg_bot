from aiogram.fsm.state import State, StatesGroup


class ReportFlow(StatesGroup):
    period = State()
