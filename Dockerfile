FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Системные зависимости: matplotlib/Pillow тянут libpng, libjpeg; reportlab — freetype.
# В slim-образе уже есть нужные либы как рантайм; build-essential нужен на случай wheels-сборки.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        libfreetype6 \
        libjpeg62-turbo \
        libpng16-16 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install -r requirements.txt \
    && apt-get purge -y --auto-remove build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY app ./app
COPY migrations ./migrations
COPY alembic.ini main.py ./
COPY scripts ./scripts

# База и экспорт лежат в смонтированном volume
ENV DATABASE_URL=sqlite+aiosqlite:////app/data/dietary_coach.db \
    ALEMBIC_DATABASE_URL=sqlite:////app/data/dietary_coach.db

# Миграции прогоняются программно в main.py при старте — отдельный шаг не нужен
CMD ["python", "main.py"]
