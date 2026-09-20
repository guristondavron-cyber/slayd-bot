# Python 3.12 yengil konteyneri
FROM python:3.12-slim

# Tizim paketlarini yangilash va LibreOffice headless o'rnatish
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    fonts-dejavu-core \
    fonts-liberation \
    libreoffice-impress-nogui \
    libreoffice-common \
    && rm -rf /var/lib/apt/lists/*

# Ishchi katalog
WORKDIR /app

# Kutubxonalarni o'rnatish
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Loyiha fayllarini nusxalash
COPY . .

# Generatsiya qilinadigan fayllar uchun papka
RUN mkdir -p generated_slides

# Botni ishga tushirish
CMD ["python", "bot.py"]
