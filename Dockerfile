# Python 3.12 yengil konteyneri
FROM python:3.12-slim

# Tizim shriftlari va curl o'rnatish (Pillow yuqori sifatli PDF va rasm chizishi uchun)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    fonts-dejavu-core \
    fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

# Ishchi katalog
WORKDIR /app

# Kutubxonalarni o'rnatish
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Loyiha fayllarini nusxalash
COPY . .

# Generatsiya qilinadigan fayllar va rasm kesh uchun papkalar
RUN mkdir -p generated_slides image_cache

# Standart port (Render o'zi PORT muhit o'zgaruvchisini beradi)
ENV PORT=8080

# Botni ishga tushirish
CMD ["python", "bot.py"]
