from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from io import BytesIO

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import seaborn as sns  # noqa: E402
from matplotlib import font_manager  # noqa: E402
from matplotlib.ticker import FormatStrFormatter, MaxNLocator  # noqa: E402
from reportlab.lib import colors  # noqa: E402
from reportlab.lib.enums import TA_CENTER, TA_LEFT  # noqa: E402
from reportlab.lib.pagesizes import A4  # noqa: E402
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet  # noqa: E402
from reportlab.lib.units import cm, mm  # noqa: E402
from reportlab.pdfbase import pdfmetrics  # noqa: E402
from reportlab.pdfbase.ttfonts import TTFont  # noqa: E402
from reportlab.platypus import (  # noqa: E402
    Image,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.db.models import GoalCode, Meal, Measurement, MealType
from app.services.medical_metrics import Metric, compute_metrics
from app.utils.labels import GOAL_LABELS, MAIN_MEAL_TYPES, MEAL_TYPE_LABELS
from app.utils.time_utils import fmt_date

# ===== Шрифты с кириллицей =====
_FONT = "DejaVuSans"
_FONT_BOLD = "DejaVuSans-Bold"
_FONT_MONO = "DejaVuSansMono"
_FONTS_REGISTERED = False


def _register_fonts() -> None:
    global _FONTS_REGISTERED
    if _FONTS_REGISTERED:
        return
    regular = font_manager.findfont("DejaVu Sans")
    bold = font_manager.findfont("DejaVu Sans:bold")
    mono = font_manager.findfont("DejaVu Sans Mono")
    pdfmetrics.registerFont(TTFont(_FONT, regular))
    pdfmetrics.registerFont(TTFont(_FONT_BOLD, bold))
    pdfmetrics.registerFont(TTFont(_FONT_MONO, mono))
    pdfmetrics.registerFontFamily(_FONT, normal=_FONT, bold=_FONT_BOLD, italic=_FONT, boldItalic=_FONT_BOLD)
    plt.rcParams["font.family"] = "DejaVu Sans"
    plt.rcParams["axes.unicode_minus"] = False
    _FONTS_REGISTERED = True


# ===== Цвета (hex-строки; для reportlab оборачиваем в colors.HexColor) =====
PALETTE = {
    "primary": "#2563eb",       # blue-600
    "primary_dark": "#1e3a8a",
    "accent": "#0ea5e9",
    "success": "#16a34a",
    "success_bg": "#dcfce7",
    "danger": "#dc2626",
    "danger_bg": "#fee2e2",
    "warning": "#d97706",
    "neutral_bg": "#f1f5f9",
    "neutral_border": "#e2e8f0",
    "text_main": "#0f172a",
    "text_muted": "#64748b",
    "card_bg": "#f8fafc",
    "table_head": "#0f172a",
}


def C(key: str) -> colors.Color:
    return colors.HexColor(PALETTE[key])

MEAL_COLORS = {
    MealType.BREAKFAST.value: "#f59e0b",       # amber
    MealType.LUNCH.value: "#ef4444",           # red
    MealType.DINNER.value: "#3b82f6",          # blue
    MealType.SNACK.value: "#94a3b8",           # slate
    MealType.SPORTS_NUTRITION.value: "#10b981",  # emerald
}

WEIGHT_EPS_KG = 0.3
CM_EPS = 0.5


# ===== Данные =====

@dataclass
class GoalEvaluation:
    label: str
    value: str
    success: bool | None


@dataclass
class ReportData:
    period_start: datetime
    period_end: datetime
    goals: set[str]
    meals: list[Meal]
    measurements: list[Measurement]
    prev_measurement: Measurement | None
    height_cm: float
    age: int = 0
    gender: str = ""
    user_label: str = ""
    evaluations: list[GoalEvaluation] = field(default_factory=list)


# ===== Метрики =====

def _main_meals_by_day(meals: list[Meal]) -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    for m in meals:
        if m.meal_type in MAIN_MEAL_TYPES:
            out.setdefault(m.occurred_at.strftime("%Y-%m-%d"), set()).add(m.meal_type)
    return out


def _times_minutes(meals: list[Meal], meal_type: str) -> list[int]:
    return [
        m.occurred_at.hour * 60 + m.occurred_at.minute
        for m in meals if m.meal_type == meal_type
    ]


def _stddev(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    return (sum((v - mean) ** 2 for v in values) / (len(values) - 1)) ** 0.5


def _days_in_period(report: ReportData) -> int:
    return max((report.period_end.date() - report.period_start.date()).days + 1, 1)


def _delta(report: ReportData, field_name: str) -> tuple[float, float, float] | None:
    """Возвращает (delta, start_value, end_value) или None если данных недостаточно."""
    last = report.measurements[-1] if report.measurements else None
    base = report.prev_measurement or (report.measurements[0] if report.measurements else None)
    if last is None or base is None or last is base:
        return None
    a = getattr(base, field_name)
    b = getattr(last, field_name)
    if a is None or b is None:
        return None
    return b - a, a, b


# ===== Оценка целей =====

def evaluate_goals(report: ReportData) -> list[GoalEvaluation]:
    out: list[GoalEvaluation] = []
    g = report.goals

    if g & {GoalCode.WEIGHT_LOSS.value, GoalCode.WEIGHT_GAIN.value, GoalCode.WEIGHT_MAINTAIN.value}:
        d = _delta(report, "weight_kg")
        labels = {
            GoalCode.WEIGHT_LOSS.value: "Снижение веса",
            GoalCode.WEIGHT_GAIN.value: "Набор веса",
            GoalCode.WEIGHT_MAINTAIN.value: "Удержание веса",
        }
        label = next(labels[k] for k in labels if k in g)
        if d is None:
            out.append(GoalEvaluation(label, "нет данных", None))
        else:
            delta, _, _ = d
            arrow = "↓" if delta < 0 else ("↑" if delta > 0 else "→")
            value = f"{arrow} {delta:+.1f} кг"
            if abs(delta) < WEIGHT_EPS_KG:
                success = GoalCode.WEIGHT_MAINTAIN.value in g or None
            elif GoalCode.WEIGHT_LOSS.value in g:
                success = delta < 0
            elif GoalCode.WEIGHT_GAIN.value in g:
                success = delta > 0
            else:
                success = False
            out.append(GoalEvaluation(label, value, success))

    for code, fld, label, direction in (
        (GoalCode.WAIST_REDUCE.value, "waist_cm", "Уменьшение талии", "down"),
        (GoalCode.SHOULDERS_INCREASE.value, "shoulders_cm", "Увеличение плеч", "up"),
        (GoalCode.HIPS_INCREASE.value, "hips_cm", "Увеличение бёдер", "up"),
    ):
        if code not in g:
            continue
        d = _delta(report, fld)
        if d is None:
            out.append(GoalEvaluation(label, "нет данных", None))
            continue
        delta, _, _ = d
        arrow = "↓" if delta < 0 else ("↑" if delta > 0 else "→")
        if abs(delta) < CM_EPS:
            success = None
        else:
            success = (delta < 0) if direction == "down" else (delta > 0)
        out.append(GoalEvaluation(label, f"{arrow} {delta:+.1f} см", success))

    if GoalCode.REGULAR_TIMING.value in g:
        parts = []
        worst = 0.0
        any_data = False
        for mt in (MealType.BREAKFAST.value, MealType.LUNCH.value, MealType.DINNER.value):
            times = _times_minutes(report.meals, mt)
            if len(times) < 2:
                continue
            std_min = _stddev([float(t) for t in times])
            worst = max(worst, std_min)
            parts.append(f"{MEAL_TYPE_LABELS[mt]} ±{std_min:.0f} мин")
            any_data = True
        if not any_data:
            out.append(GoalEvaluation("Регулярное питание", "мало данных", None))
        else:
            out.append(GoalEvaluation("Регулярное питание", " · ".join(parts), worst <= 60))

    if GoalCode.NO_SKIP_MAIN.value in g:
        days = _days_in_period(report)
        by_day = _main_meals_by_day(report.meals)
        full = sum(1 for s in by_day.values() if s == MAIN_MEAL_TYPES)
        share = full / days
        out.append(
            GoalEvaluation(
                "Не пропускать основные приёмы",
                f"{full}/{days} полных дней ({share:.0%})",
                share >= 0.8,
            )
        )

    if GoalCode.FEWER_SNACKS.value in g:
        days = _days_in_period(report)
        total = sum(1 for m in report.meals if m.meal_type == MealType.SNACK.value)
        per_day = total / days
        out.append(
            GoalEvaluation(
                "Меньше перекусов",
                f"{total} всего · {per_day:.1f} в день",
                per_day <= 1.0,
            )
        )

    if GoalCode.NO_OVEREAT.value in g:
        scored = [m for m in report.meals if m.satiety is not None]
        if not scored:
            out.append(GoalEvaluation("Не переедать", "нет оценок", None))
        else:
            n = sum(1 for m in scored if m.satiety >= 4)
            share = n / len(scored)
            out.append(
                GoalEvaluation(
                    "Не переедать",
                    f"{n} из {len(scored)} приёмов с насыщением 4–5 ({share:.0%})",
                    share <= 0.2,
                )
            )

    if GoalCode.NO_HUNGER.value in g:
        scored = [m for m in report.meals if m.hunger is not None]
        if not scored:
            out.append(GoalEvaluation("Не быть сильно голодным", "нет оценок", None))
        else:
            n = sum(1 for m in scored if m.hunger >= 4)
            share = n / len(scored)
            out.append(
                GoalEvaluation(
                    "Не быть сильно голодным",
                    f"{n} из {len(scored)} приёмов с голодом 4–5 ({share:.0%})",
                    share <= 0.2,
                )
            )

    if GoalCode.REGULAR_SPORTS_NUTRITION.value in g:
        days = _days_in_period(report)
        days_with = len({
            m.occurred_at.strftime("%Y-%m-%d")
            for m in report.meals if m.meal_type == MealType.SPORTS_NUTRITION.value
        })
        share = days_with / days
        out.append(
            GoalEvaluation(
                "Регулярный спортпит",
                f"{days_with}/{days} дней ({share:.0%})",
                share >= 0.8,
            )
        )

    return out


# ===== Графики =====

def _setup_seaborn() -> None:
    sns.set_theme(style="whitegrid", font="DejaVu Sans")
    plt.rcParams.update({
        "axes.edgecolor": "#cbd5e1",
        "axes.labelcolor": "#334155",
        "axes.titleweight": "bold",
        "axes.titlesize": 13,
        "axes.titlecolor": "#0f172a",
        "axes.titlepad": 12,
        "xtick.color": "#475569",
        "ytick.color": "#475569",
        "grid.color": "#e2e8f0",
        "grid.linestyle": "-",
        "grid.linewidth": 0.8,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "figure.facecolor": "white",
        "axes.facecolor": "white",
        "font.size": 10,
    })


def _save_fig(fig, dpi: int = 150) -> BytesIO:
    buf = BytesIO()
    fig.savefig(buf, format="png", dpi=dpi, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    buf.seek(0)
    return buf


def chart_weight(measurements: list[Measurement]) -> BytesIO | None:
    pts = [(m.measured_at, m.weight_kg) for m in measurements if m.weight_kg is not None]
    if len(pts) < 2:
        return None
    xs, ys = zip(*pts)
    fig, ax = plt.subplots(figsize=(8, 3.2))
    ax.fill_between(xs, ys, min(ys) - 0.5, color=PALETTE["primary"], alpha=0.10)
    ax.plot(xs, ys, marker="o", color=PALETTE["primary"], linewidth=2.4, markersize=7,
            markerfacecolor="white", markeredgewidth=2)
    # подписи на концах
    ax.annotate(f"{ys[0]:.1f} кг", xy=(xs[0], ys[0]), xytext=(8, 16),
                textcoords="offset points", fontsize=10, color=PALETTE["text_main"],
                fontweight="bold", ha="left", va="bottom")
    ax.annotate(f"{ys[-1]:.1f} кг", xy=(xs[-1], ys[-1]), xytext=(-8, -18),
                textcoords="offset points", fontsize=10, color=PALETTE["primary"],
                fontweight="bold", ha="right", va="top")
    ax.set_title("Динамика веса")
    ax.set_ylabel("кг")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%d.%m"))
    ax.margins(x=0.05, y=0.25)
    fig.autofmt_xdate()
    return _save_fig(fig)


def chart_measurement_single(measurements: list[Measurement], field_name: str, title: str, color: str) -> BytesIO | None:
    pts = [(m.measured_at, getattr(m, field_name)) for m in measurements if getattr(m, field_name) is not None]
    if len(pts) < 2:
        return None
    xs, ys = zip(*pts)
    fig, ax = plt.subplots(figsize=(5.0, 4.5))
    ax.fill_between(xs, ys, min(ys) - 0.4, color=color, alpha=0.12)
    ax.plot(xs, ys, marker="o", color=color, linewidth=2.2, markersize=6,
            markerfacecolor="white", markeredgewidth=1.8)
    ax.annotate(f"{ys[0]:.1f}", xy=(xs[0], ys[0]), xytext=(5, 12),
                textcoords="offset points", fontsize=10, color=PALETTE["text_main"],
                fontweight="bold", ha="left", va="bottom")
    ax.annotate(f"{ys[-1]:.1f}", xy=(xs[-1], ys[-1]), xytext=(-5, -16),
                textcoords="offset points", fontsize=10, color=color,
                fontweight="bold", ha="right", va="top")
    ax.set_title(title, fontsize=12)
    ax.set_ylabel("см", fontsize=10)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%d.%m"))
    ax.yaxis.set_major_locator(MaxNLocator(nbins=5))
    ax.yaxis.set_major_formatter(FormatStrFormatter("%.1f"))
    ax.tick_params(axis="both", labelsize=9)
    ax.margins(x=0.05, y=0.25)
    fig.autofmt_xdate()
    return _save_fig(fig)


def chart_meal_times_single(meals: list[Meal], meal_type: str, label: str, color: str) -> BytesIO | None:
    """Scatter времени приёмов одного типа за период — на всю ширину страницы."""
    pts = [
        (m.occurred_at, m.occurred_at.hour + m.occurred_at.minute / 60)
        for m in meals if m.meal_type == meal_type
    ]
    if not pts:
        return None
    xs, ys = zip(*pts)
    fig, ax = plt.subplots(figsize=(8.5, 2.4))
    ax.scatter(xs, ys, color=color, alpha=0.75, s=22, edgecolor="white", linewidth=0.5)
    ax.set_ylim(4, 24)
    ax.set_yticks([6, 9, 12, 15, 18, 21, 24])
    ax.set_yticklabels(["06:00", "09:00", "12:00", "15:00", "18:00", "21:00", "24:00"])
    ax.set_title(f"{label}  ·  {len(pts)} шт.", fontsize=12)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%d.%m"))
    ax.tick_params(axis="both", labelsize=9)
    ax.margins(x=0.02)
    fig.autofmt_xdate()
    return _save_fig(fig)


def _week_key(d: datetime) -> tuple[int, int]:
    iso = d.isocalendar()
    return (iso.year, iso.week)


def _week_anchor(year: int, week: int) -> datetime:
    """Понедельник ISO-недели."""
    return datetime.fromisocalendar(year, week, 1)


def chart_weekly_meals(meals: list[Meal], start: datetime, end: datetime) -> BytesIO | None:
    """Стакнутый бар: количество приёмов каждого типа по неделям."""
    if not meals:
        return None
    weeks: dict[tuple[int, int], dict[str, int]] = {}
    # инициализируем все недели в периоде
    cur = start
    while cur <= end:
        weeks.setdefault(_week_key(cur), {mt.value: 0 for mt in MealType})
        cur += timedelta(days=7)
    weeks.setdefault(_week_key(end), {mt.value: 0 for mt in MealType})

    for m in meals:
        if not m.meal_type:
            continue
        k = _week_key(m.occurred_at)
        weeks.setdefault(k, {mt.value: 0 for mt in MealType})
        weeks[k][m.meal_type] += 1

    keys = sorted(weeks)
    anchors = [_week_anchor(y, w) for (y, w) in keys]
    fig, ax = plt.subplots(figsize=(8, 3.0))
    bottoms = [0] * len(keys)
    for mt in MealType:
        vals = [weeks[k][mt.value] for k in keys]
        ax.bar(anchors, vals, bottom=bottoms, label=MEAL_TYPE_LABELS[mt.value],
               color=MEAL_COLORS[mt.value], width=5.5, edgecolor="white", linewidth=0.6)
        bottoms = [b + v for b, v in zip(bottoms, vals)]
    ax.set_title("Приёмы пищи по неделям")
    ax.set_ylabel("шт.")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%d.%m"))
    ax.legend(loc="upper left", bbox_to_anchor=(1.01, 1.0), frameon=False, fontsize=9)
    fig.autofmt_xdate()
    return _save_fig(fig)


def chart_time_consistency(meals: list[Meal]) -> BytesIO | None:
    """Тренд разброса времени основных приёмов по неделям. Чем ниже — тем стабильнее."""
    if not meals:
        return None
    series: dict[str, dict[tuple[int, int], list[int]]] = {
        mt: {} for mt in (MealType.BREAKFAST.value, MealType.LUNCH.value, MealType.DINNER.value)
    }
    for m in meals:
        if m.meal_type not in series:
            continue
        k = _week_key(m.occurred_at)
        series[m.meal_type].setdefault(k, []).append(m.occurred_at.hour * 60 + m.occurred_at.minute)

    fig, ax = plt.subplots(figsize=(8, 3.0))
    any_plotted = False
    for mt, color in (
        (MealType.BREAKFAST.value, MEAL_COLORS[MealType.BREAKFAST.value]),
        (MealType.LUNCH.value, MEAL_COLORS[MealType.LUNCH.value]),
        (MealType.DINNER.value, MEAL_COLORS[MealType.DINNER.value]),
    ):
        weekly = series[mt]
        keys = sorted(weekly)
        xs = [_week_anchor(y, w) for (y, w) in keys]
        ys = [_stddev([float(t) for t in weekly[k]]) for k in keys if len(weekly[k]) >= 2]
        xs = [_week_anchor(y, w) for (y, w) in keys if len(weekly[(y, w)]) >= 2]
        if len(ys) >= 2:
            ax.plot(xs, ys, marker="o", label=MEAL_TYPE_LABELS[mt], color=color,
                    linewidth=2.0, markersize=5, markerfacecolor="white", markeredgewidth=1.5)
            any_plotted = True
    if not any_plotted:
        plt.close(fig)
        return None
    # Целевой коридор: ±60 мин
    ax.axhspan(0, 60, color="#16a34a", alpha=0.07)
    ax.axhline(60, color="#16a34a", linestyle="--", linewidth=1, alpha=0.5)
    ax.set_title("Разброс времени основных приёмов (по неделям)")
    ax.set_ylabel("ст. откл., мин")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%d.%m"))
    ax.legend(loc="upper left", bbox_to_anchor=(1.01, 1.0), frameon=False, fontsize=9)
    ax.set_ylim(bottom=0)
    fig.autofmt_xdate()
    return _save_fig(fig)


def chart_hunger_satiety(meals: list[Meal]) -> BytesIO | None:
    hungers = [m.hunger for m in meals if m.hunger is not None]
    sats = [m.satiety for m in meals if m.satiety is not None]
    if not hungers and not sats:
        return None
    fig, axes = plt.subplots(1, 2, figsize=(8, 3.0))
    for ax, vals, title, color in (
        (axes[0], hungers, "Распределение голода", "#ef4444"),
        (axes[1], sats, "Распределение насыщения", "#3b82f6"),
    ):
        counts = [vals.count(i) for i in range(1, 6)]
        total = sum(counts) or 1
        shares = [100 * c / total for c in counts]
        bars = ax.bar(range(1, 6), shares, color=color, alpha=0.85, edgecolor="white", width=0.7)
        ax.set_title(title)
        ax.set_ylabel("% приёмов")
        ax.set_xticks(range(1, 6))
        ax.set_ylim(0, max(shares + [10]) * 1.2)
        for bar, c in zip(bars, counts):
            if c > 0:
                ax.annotate(f"{c}", xy=(bar.get_x() + bar.get_width() / 2, bar.get_height()),
                            xytext=(0, 3), textcoords="offset points",
                            ha="center", fontsize=9, color=PALETTE["text_muted"])
    fig.tight_layout()
    return _save_fig(fig)


# ===== Сборка PDF =====

def _styles():
    base = getSampleStyleSheet()
    h1 = ParagraphStyle("H1", parent=base["Title"], fontName=_FONT_BOLD, fontSize=22,
                        leading=26, alignment=TA_LEFT, textColor=C("text_main"),
                        spaceAfter=4)
    sub = ParagraphStyle("Sub", parent=base["Normal"], fontName=_FONT, fontSize=11,
                         leading=14, textColor=C("text_muted"), spaceAfter=10)
    h2 = ParagraphStyle("H2", parent=base["Heading2"], fontName=_FONT_BOLD, fontSize=13,
                        leading=17, textColor=C("text_main"), spaceBefore=2,
                        spaceAfter=6)
    h3 = ParagraphStyle("H3", parent=base["Heading3"], fontName=_FONT_BOLD, fontSize=11,
                        leading=14, textColor=C("text_main"), spaceBefore=2,
                        spaceAfter=4)
    body = ParagraphStyle("Body", parent=base["Normal"], fontName=_FONT, fontSize=10,
                          leading=14, textColor=C("text_main"))
    muted = ParagraphStyle("Muted", parent=base["Normal"], fontName=_FONT, fontSize=9,
                           leading=12, textColor=C("text_muted"))
    formula = ParagraphStyle("Formula", parent=base["Normal"], fontName=_FONT_MONO, fontSize=9,
                             leading=12, textColor=C("text_main"),
                             leftIndent=8, spaceBefore=1, spaceAfter=1)
    ref = ParagraphStyle("Ref", parent=base["Normal"], fontName=_FONT, fontSize=8,
                         leading=10, textColor=C("text_muted"),
                         leftIndent=8, spaceBefore=1, spaceAfter=4)
    kpi_value = ParagraphStyle("KPIVal", parent=base["Normal"], fontName=_FONT_BOLD,
                               fontSize=20, leading=22, textColor=C("primary_dark"),
                               alignment=TA_LEFT)
    kpi_label = ParagraphStyle("KPILab", parent=base["Normal"], fontName=_FONT, fontSize=8,
                               leading=10, textColor=C("text_muted"), alignment=TA_LEFT)
    return {
        "h1": h1, "sub": sub, "h2": h2, "h3": h3, "body": body, "muted": muted,
        "formula": formula, "ref": ref,
        "kpi_value": kpi_value, "kpi_label": kpi_label,
    }


def _kpi_tile(value: str, label: str, styles, accent_hex: str | None = None):
    accent_hex = accent_hex or PALETTE["primary"]
    inner = Table(
        [[Paragraph(value, styles["kpi_value"])],
         [Paragraph(label, styles["kpi_label"])]],
        colWidths=[None],
    )
    inner.setStyle(TableStyle([
        ("LEFTPADDING", (0, 0), (-1, -1), 12),
        ("RIGHTPADDING", (0, 0), (-1, -1), 12),
        ("TOPPADDING", (0, 0), (-1, 0), 14),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 2),
        ("TOPPADDING", (0, 1), (-1, 1), 0),
        ("BOTTOMPADDING", (0, 1), (-1, 1), 12),
        ("BACKGROUND", (0, 0), (-1, -1), C("card_bg")),
        ("BOX", (0, 0), (-1, -1), 0.6, C("neutral_border")),
        ("LINEBEFORE", (0, 0), (0, -1), 3, colors.HexColor(accent_hex)),
    ]))
    return inner


def _kpis_for_report(report: ReportData, days: int, styles) -> list:
    """Формирует список KPI-плиток в зависимости от данных и целей."""
    tiles = []
    total = len(report.meals)
    days_with_records = len({m.occurred_at.strftime("%Y-%m-%d") for m in report.meals})
    snacks = sum(1 for m in report.meals if m.meal_type == MealType.SNACK.value)
    sport_days = len({
        m.occurred_at.strftime("%Y-%m-%d")
        for m in report.meals if m.meal_type == MealType.SPORTS_NUTRITION.value
    })

    tiles.append(_kpi_tile(str(total), "Всего приёмов пищи", styles, PALETTE["primary"]))
    tiles.append(_kpi_tile(f"{days_with_records}/{days}", "Дней с записями", styles, PALETTE["accent"]))
    tiles.append(_kpi_tile(f"{snacks / days:.1f}", "Перекусов в день (среднее)", styles, "#94a3b8"))

    d_weight = _delta(report, "weight_kg")
    if d_weight:
        delta, _, end_v = d_weight
        sign = "+" if delta >= 0 else ""
        accent = PALETTE["success"] if delta < 0 and GoalCode.WEIGHT_LOSS.value in report.goals else (
            PALETTE["success"] if delta > 0 and GoalCode.WEIGHT_GAIN.value in report.goals else
            PALETTE["primary"]
        )
        tiles.append(_kpi_tile(f"{sign}{delta:.1f} кг", f"Вес: сейчас {end_v:.1f} кг", styles, accent))

    d_waist = _delta(report, "waist_cm")
    if d_waist:
        delta, _, end_v = d_waist
        sign = "+" if delta >= 0 else ""
        accent = PALETTE["success"] if delta < 0 and GoalCode.WAIST_REDUCE.value in report.goals else PALETTE["primary"]
        tiles.append(_kpi_tile(f"{sign}{delta:.1f} см", f"Талия: сейчас {end_v:.1f} см", styles, accent))

    tiles.append(_kpi_tile(f"{sport_days}/{days}", "Дней со спортпитом", styles, "#10b981"))
    return tiles


def _grid_of_tiles(tiles, cols: int = 3):
    rows = []
    for i in range(0, len(tiles), cols):
        rows.append(tiles[i:i + cols] + [""] * (cols - len(tiles[i:i + cols])))
    t = Table(rows, colWidths=[(17 / cols) * cm] * cols)
    t.setStyle(TableStyle([
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    return t


def _goals_table(evaluations: list[GoalEvaluation], styles):
    if not evaluations:
        return None
    rows = []
    for ev in evaluations:
        rows.append([
            Paragraph(f"<b>{ev.label}</b>", styles["body"]),
            Paragraph(ev.value, styles["body"]),
        ])
    t = Table(rows, colWidths=[6.5 * cm, 10.5 * cm])
    style = [
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 9),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
        ("LINEBELOW", (0, 0), (-1, -2), 0.4, C("neutral_border")),
    ]
    for i, ev in enumerate(evaluations):
        if ev.success is True:
            style.append(("BACKGROUND", (0, i), (-1, i), colors.HexColor("#ecfdf5")))
            style.append(("LINEBEFORE", (0, i), (0, i), 3, colors.HexColor("#16a34a")))
        elif ev.success is False:
            style.append(("BACKGROUND", (0, i), (-1, i), colors.HexColor("#fef2f2")))
            style.append(("LINEBEFORE", (0, i), (0, i), 3, colors.HexColor("#dc2626")))
        else:
            style.append(("LINEBEFORE", (0, i), (0, i), 3, colors.HexColor("#cbd5e1")))
    t.setStyle(TableStyle(style))
    return t


def _methodology_flowables(styles) -> list:
    """Описание формул и источников расчётов мед-показателей."""
    items: list[tuple[str, list[str], str]] = [
        (
            "ИМТ (индекс массы тела)",
            ["BMI = вес (кг) / рост² (м²)",
             "Классификация ВОЗ: &lt; 18.5 дефицит · 18.5–24.9 норма · 25.0–29.9 избыток · ≥ 30.0 ожирение."],
            "WHO. <i>Obesity and overweight</i>, fact sheet, 2024. "
            "<font color='#2563eb'>https://www.who.int/news-room/fact-sheets/detail/obesity-and-overweight</font>",
        ),
        (
            "Талия / рост (WHtR)",
            ["WHtR = талия (см) / рост (см)",
             "Пороги: &lt; 0.4 пониженный · 0.4–0.5 здоровый · 0.5–0.6 повышенный риск · ≥ 0.6 высокий риск."],
            "Ashwell M., Hsieh S.D. <i>Six reasons why the waist-to-height ratio is a rapid and effective "
            "global indicator</i>. Int J Food Sci Nutr, 2005. doi:10.1080/09637480500195066",
        ),
        (
            "Талия / бёдра (WHR)",
            ["WHR = талия (см) / бёдра (см)",
             "Пороги ВОЗ: мужчины &lt; 0.90 норма · ≥ 1.00 высокий риск; женщины &lt; 0.85 норма · ≥ 0.85 высокий риск."],
            "WHO Expert Consultation. <i>Waist Circumference and Waist–Hip Ratio</i>, Geneva, 2008. "
            "<font color='#2563eb'>https://www.who.int/publications/i/item/9789241501491</font>",
        ),
        (
            "BMR — базальный метаболизм (Mifflin–St Jeor)",
            ["Мужчины: BMR = 10·вес + 6.25·рост − 5·возраст + 5",
             "Женщины: BMR = 10·вес + 6.25·рост − 5·возраст − 161",
             "Единицы: ккал/день. Точнее формулы Харриса–Бенедикта (NIH рекомендует Mifflin–St Jeor)."],
            "Mifflin M.D., St Jeor S.T., Hill L.A., et al. <i>A new predictive equation for resting energy "
            "expenditure in healthy individuals</i>. Am J Clin Nutr, 1990; 51(2):241–247. PMID:2305711",
        ),
        (
            "TDEE — суточный расход (поддержание веса)",
            ["TDEE = BMR × коэффициент активности",
             "В отчёте используется ×1.4 (сидячая работа / низкая активность). "
             "Прочие уровни: ×1.55 умеренная · ×1.725 высокая · ×1.9 очень высокая."],
            "Harris–Benedict revised activity multipliers; см. также Roza A.M., Shizgal H.M., "
            "Am J Clin Nutr, 1984; 40(1):168–182.",
        ),
        (
            "Процент жира — оценка по формуле Deurenberg",
            ["BF% = 1.20·BMI + 0.23·возраст − 10.8·пол − 5.4",
             "Пол: 1 = мужчина, 0 = женщина. Стандартная ошибка ≈ ±4%. Для точной оценки — биоимпеданс или DEXA."],
            "Deurenberg P., Weststrate J.A., Seidell J.C. <i>Body mass index as a measure of body fatness: "
            "age- and sex-specific prediction formulas</i>. Br J Nutr, 1991; 65(2):105–114. "
            "PMID:2043597",
        ),
    ]
    out: list = []
    for title, formulas, source in items:
        out.append(Paragraph(title, styles["h3"]))
        for f in formulas:
            out.append(Paragraph(f, styles["formula"]))
        out.append(Paragraph("Источник: " + source, styles["ref"]))
    return out


def _medical_metrics_table(metrics: list[Metric], styles):
    if not metrics:
        return None
    head_style = ParagraphStyle(
        "MMHead", parent=styles["body"], fontName=_FONT_BOLD,
        textColor=colors.white, fontSize=10, leading=12,
    )
    norm_style = ParagraphStyle(
        "MMNorm", parent=styles["body"], textColor=C("text_muted"),
        fontSize=10, leading=12,
    )
    rows = [
        [Paragraph("Показатель", head_style),
         Paragraph("Значение", head_style),
         Paragraph("Норма", head_style)],
    ]
    for m in metrics:
        rows.append([
            Paragraph(f"<b>{m.label}</b>", styles["body"]),
            Paragraph(m.value, styles["body"]),
            Paragraph(m.norm, norm_style),
        ])
    t = Table(rows, colWidths=[6.0 * cm, 6.5 * cm, 4.5 * cm])
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), C("table_head")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LINEBELOW", (0, 0), (-1, -2), 0.4, C("neutral_border")),
    ]
    for i, m in enumerate(metrics, start=1):
        if m.success is True:
            style.append(("BACKGROUND", (0, i), (-1, i), colors.HexColor("#ecfdf5")))
            style.append(("LINEBEFORE", (0, i), (0, i), 3, colors.HexColor("#16a34a")))
        elif m.success is False:
            style.append(("BACKGROUND", (0, i), (-1, i), colors.HexColor("#fef2f2")))
            style.append(("LINEBEFORE", (0, i), (0, i), 3, colors.HexColor("#dc2626")))
        else:
            style.append(("LINEBEFORE", (0, i), (0, i), 3, colors.HexColor("#cbd5e1")))
    t.setStyle(TableStyle(style))
    return t


def _measurements_table(measurements: list[Measurement], styles):
    rows = [["Дата", "Плечи", "Талия", "Бёдра", "Вес"]]
    for m in measurements:
        rows.append([
            fmt_date(m.measured_at),
            f"{m.shoulders_cm:.1f}" if m.shoulders_cm is not None else "—",
            f"{m.waist_cm:.1f}" if m.waist_cm is not None else "—",
            f"{m.hips_cm:.1f}" if m.hips_cm is not None else "—",
            f"{m.weight_kg:.1f}" if m.weight_kg is not None else "—",
        ])
    t = Table(rows, colWidths=[3.4 * cm, 3.0 * cm, 3.0 * cm, 3.0 * cm, 3.0 * cm])
    t.setStyle(TableStyle([
        ("FONT", (0, 0), (-1, 0), _FONT_BOLD, 10),
        ("FONT", (0, 1), (-1, -1), _FONT, 9),
        ("BACKGROUND", (0, 0), (-1, 0), C("table_head")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("ALIGN", (0, 0), (0, -1), "LEFT"),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, C("neutral_bg")]),
    ]))
    return t


def _executive_summary(report: ReportData) -> str:
    """Короткая выжимка автоматом."""
    successes = sum(1 for ev in report.evaluations if ev.success is True)
    failures = sum(1 for ev in report.evaluations if ev.success is False)
    parts = []
    if successes and not failures:
        parts.append(f"Все {successes} активных целей выполняются.")
    elif successes and failures:
        parts.append(f"В цели: {successes}; отстаём: {failures}.")
    elif failures:
        parts.append(f"Отстаём по {failures} целям, фокус — на них.")
    else:
        parts.append("Недостаточно данных для оценки целей.")
    d = _delta(report, "weight_kg")
    if d:
        delta, _, _ = d
        if delta < -WEIGHT_EPS_KG:
            parts.append(f"Вес снизился на {abs(delta):.1f} кг за период.")
        elif delta > WEIGHT_EPS_KG:
            parts.append(f"Вес вырос на {delta:.1f} кг за период.")
    return " ".join(parts)


def _section_chart(title: str, img: BytesIO, styles, width_cm: float = 17, height_cm: float = 6.8):
    parts = [Paragraph(title, styles["h2"])]
    if img is not None:
        parts.append(Image(img, width=width_cm * cm, height=height_cm * cm))
    parts.append(Spacer(1, 0.4 * cm))
    return KeepTogether(parts)


def build_pdf(report: ReportData) -> BytesIO:
    _register_fonts()
    _setup_seaborn()

    report.evaluations = evaluate_goals(report)
    styles = _styles()
    days = _days_in_period(report)

    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=2 * cm, rightMargin=2 * cm,
        topMargin=1.8 * cm, bottomMargin=1.8 * cm,
        title="Дневник питания — отчёт",
    )
    story: list = []

    # ----- Cover -----
    story.append(Paragraph("Дневник питания", styles["h1"]))
    period_str = f"{fmt_date(report.period_start)} — {fmt_date(report.period_end)} · {days} {_dni(days)}"
    story.append(Paragraph(period_str, styles["sub"]))

    summary = _executive_summary(report)
    story.append(Paragraph(summary, styles["body"]))
    story.append(Spacer(1, 0.3 * cm))

    tiles = _kpis_for_report(report, days, styles)
    story.append(_grid_of_tiles(tiles, cols=3))
    story.append(Spacer(1, 0.4 * cm))

    # ----- Цели -----
    if report.evaluations:
        story.append(Paragraph("Прогресс по целям", styles["h2"]))
        gt = _goals_table(report.evaluations, styles)
        if gt is not None:
            story.append(gt)
        story.append(Spacer(1, 0.3 * cm))

    # ----- Замеры -----
    if report.measurements:
        story.append(PageBreak())

        # Мед-показатели по последнему замеру в периоде
        latest = report.measurements[-1] if report.measurements else None
        med = compute_metrics(
            height_cm=report.height_cm,
            age=report.age,
            gender=report.gender,
            latest=latest,
        )
        if med.metrics:
            story.append(Paragraph("Медицинские показатели", styles["h2"]))
            mt = _medical_metrics_table(med.metrics, styles)
            if mt is not None:
                story.append(mt)
                story.append(Paragraph(
                    "Рассчитано по последнему замеру в периоде. Формулы и источники — "
                    "в разделе «Методология» в конце отчёта.",
                    styles["muted"],
                ))
                story.append(Spacer(1, 0.4 * cm))

        w = chart_weight(report.measurements)
        if w is not None:
            story.append(Image(w, width=17 * cm, height=6.6 * cm))
            story.append(Spacer(1, 0.3 * cm))

        # три отдельных графика: плечи, талия, бёдра
        sh = chart_measurement_single(report.measurements, "shoulders_cm", "Плечи", "#8b5cf6")
        wa = chart_measurement_single(report.measurements, "waist_cm", "Талия", "#f59e0b")
        hi = chart_measurement_single(report.measurements, "hips_cm", "Бёдра", "#10b981")
        cells = [
            Image(img, width=5.7 * cm, height=4.6 * cm) if img is not None else ""
            for img in (sh, wa, hi)
        ]
        if any(c != "" for c in cells):
            row = Table([cells], colWidths=[5.7 * cm, 5.7 * cm, 5.7 * cm])
            row.setStyle(TableStyle([
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ]))
            story.append(row)
            story.append(Spacer(1, 0.3 * cm))

        story.append(KeepTogether([
            Paragraph("История замеров", styles["h2"]),
            _measurements_table(report.measurements, styles),
        ]))

    # ----- Дневник питания -----
    story.append(Spacer(1, 0.4 * cm))
    story.append(Paragraph("Дневник питания", styles["h2"]))

    # Время приёмов: 5 мини-scatter по типам (Завтрак / Обед / Ужин / Перекус / Спортпит)
    meal_panels: list[tuple[str, str, str]] = [
        (MealType.BREAKFAST.value, "Завтрак", MEAL_COLORS[MealType.BREAKFAST.value]),
        (MealType.LUNCH.value, "Обед", MEAL_COLORS[MealType.LUNCH.value]),
        (MealType.DINNER.value, "Ужин", MEAL_COLORS[MealType.DINNER.value]),
        (MealType.SNACK.value, "Перекус", MEAL_COLORS[MealType.SNACK.value]),
        (MealType.SPORTS_NUTRITION.value, "Спортпит", MEAL_COLORS[MealType.SPORTS_NUTRITION.value]),
    ]
    panel_imgs = [chart_meal_times_single(report.meals, mt, lbl, col) for mt, lbl, col in meal_panels]
    rendered = [img for img in panel_imgs if img is not None]
    if rendered:
        story.append(Paragraph("Время приёмов пищи по типам", styles["h3"]))
        for img in panel_imgs:
            if img is None:
                continue
            story.append(Image(img, width=17 * cm, height=4.8 * cm))
            story.append(Spacer(1, 0.2 * cm))
        story.append(Spacer(1, 0.2 * cm))

    weekly = chart_weekly_meals(report.meals, report.period_start, report.period_end)
    if weekly is not None:
        story.append(Image(weekly, width=17 * cm, height=5.4 * cm))
        story.append(Spacer(1, 0.25 * cm))

    consistency = chart_time_consistency(report.meals)
    if consistency is not None:
        story.append(Image(consistency, width=17 * cm, height=5.4 * cm))
        story.append(Spacer(1, 0.25 * cm))

    hs_chart = chart_hunger_satiety(report.meals)
    if hs_chart is not None:
        story.append(Image(hs_chart, width=17 * cm, height=5.4 * cm))

    # ----- Методология (приложение) -----
    if report.measurements:
        story.append(PageBreak())
        story.append(Paragraph("Методология расчёта показателей", styles["h2"]))
        story.append(Paragraph(
            "Метрики рассчитываются по последнему замеру в выбранном периоде "
            "и постоянным данным профиля (рост, возраст, пол).",
            styles["muted"],
        ))
        story.append(Spacer(1, 0.3 * cm))
        for fl in _methodology_flowables(styles):
            story.append(fl)

    doc.build(story)
    buf.seek(0)
    return buf


def _dni(n: int) -> str:
    if 11 <= n % 100 <= 14:
        return "дней"
    last = n % 10
    if last == 1:
        return "день"
    if 2 <= last <= 4:
        return "дня"
    return "дней"
