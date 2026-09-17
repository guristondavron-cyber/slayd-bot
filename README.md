# 🚀 Gemini AI Telegram Slide Generator Bot (24/7 Ishlash Rejimi)

Ushbu loyiha sizga foydalanuvchi yuborgan ixtiyoriy mavzu bo'yicha eng ilg'or **Google Gemini 3.8 Flash** sun'iy intellekti orqali professional va jozibali **PowerPoint (.pptx)** taqdimotlar tayyorlab beradigan Telegram bot hisoblanadi.

Slaydlar oddiy zerikarli matnlardan iborat emas — zamonaviy 16:9 Widescreen nisbatda, infografika kartochkalari, statistika va raqamlar bloklari, solishtirish jadvallari, timeline bosqichlari va chiroyli ranglar palitrasi asosida chiziladi.

---

## 🌟 Asosiy Imkoniyatlar

- 🧠 **Gemini AI Integratsiyasi:** Mavzuni chuqur tahlil qilib, slaydlar rejasini strukturalangan (JSON) formatda mukammal tuzadi.
- 🎨 **5 ta Professional Dizayn Mavzusi:**
  - 🌙 **Dark Tech:** Neon moviy elementlar, IT va startaplar uchun to'q zamonaviy uslub.
  - 💼 **Corporate Blue:** Qirollik ko'k va oq fon, rasmiy biznes va bank uslubi.
  - 🌿 **Emerald Green:** Zumrad yashil, ta'lim, ekologiya va barqaror o'sish mavzulari.
  - 🌅 **Modern Sunset:** Koral va to'q sariq aksentlar, ijodiy va marketing taqdimotlari.
  - ⚪ **Clean Minimal:** Oq va binafsha urg'ular, minimalist toza dizayn.
- 📐 **Boy Layout Turlari:**
  - `title_slide` — Katta ta'sirchan sarlavha va kirish kartochkasi.
  - `cards_grid` — 3 yoki 4 ta zamonaviy kartochka (afzalliklar, tushunchalar).
  - `stats_metrics` — Katta raqamlar, foizlar va statistika infografikasi.
  - `comparison` — Ikki tomonlama solishtirish (an'anaviy vs yangi yechim).
  - `timeline_steps` — Ketma-ket bosqichlar va yo'l xaritasi.
  - `conclusion` — Asosiy xulosa va harakatga chaqiriq (Call to Action).
- 📱 **Universallik:** Yaratilgan `.pptx` fayllar telefonlarda (WPS Office, PowerPoint) va kompyuterlarda to'liq ochiladi hamda tahrirlanadi.
- 🔄 **24/7 Uzluksiz Ishlash:** Server yoki kompyuter o'chib-yonsa, avtomatik qayta tiklanish (Docker, Systemd, Bat supervisor).

---

## 🔑 1-QADAM: Kerakli Kalitlarni Olish

### 1. Telegram Bot Token:
1. Telegramda [@BotFather](https://t.me/BotFather) botiga kiring.
2. `/newbot` buyrug'ini yuboring.
3. Botingizga nom va username bering (masalan: `MeningSlaydBotim_bot`).
4. BotFather sizga bergan **API token**ni nusxalab oling (masalan: `7891234567:AAH...`).

### 2. Google Gemini API Kaliti:
1. [Google AI Studio](https://aistudio.google.com/) saytiga kiring.
2. **"Get API key"** -> **"Create API key"** tugmasini bosing.
3. Chiqqan `AIzaSy...` kalitini nusxalab oling (Gemini API tekinga taqdim etiladi).

---

## ⚙️ 2-QADAM: Sozlash (.env fayli)

Loyiha papkasidagi `.env.example` faylidan nusxa olib, yangi `.env` fayli yarating:

```env
BOT_TOKEN=7891234567:AAH_SIZNING_TELEGRAM_TOKENINGIZ
GEMINI_API_KEY=AIzaSy_SIZNING_GEMINI_API_KALITINGIZ
GEMINI_MODEL=gemini-3.8-flash
```

---

## 🖥 3-QADAM: Mahalliy Kompyuterda Ishga Tushirish

### Windows da:
Loyiha papkasida tayyor `run_24_7.bat` faylini ikki marta bosib ishga tushiring. U virtual muhitdagi Python orqali botni yoqadi va agar internet uzilsa yoki xatolik bo'lsa, avtomatik qayta tiklaydi.

Yoki terminalda:
```powershell
.venv\Scripts\python.exe bot.py
```

---

## 🌐 4-QADAM: Botni 24/7 Serverda Ishlatish Usullari

Bot doim ishlab turishi uchun uni quyidagi usullardan birida serverga qo'yish mumkin:

### 1-USUL: Bepul Cloud Xizmatlar (Render.com / Railway.app)
Kompyuteringizni yoqib qo'yishni xohlamasangiz, eng yaxshi yo'li — bepul bulutli serverlar:

**Render.com da ishga tushirish:**
1. Loyihani o'zingizning GitHub akkauntingizga yuklang (`git push`).
2. [Render.com](https://render.com) ga kiring va ro'yxatdan o'ting.
3. **"New +"** -> **"Background Worker"** ni tanlang.
4. GitHub repozitoriyangizni ulang.
5. Sozlamalar:
   - **Runtime:** `Python 3`
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `python bot.py`
6. **Environment Variables** bo'limiga `BOT_TOKEN` va `GEMINI_API_KEY` ni qo'shing.
7. **"Create Work"** tugmasini bosing. Bot endi 24/7 internetda doimiy ishlaydi!

---

### 2-USUL: Linux VPS Serverda Docker Orqali (Tavsiya etiladi)
Agar sizda arzon Linux VPS (masalan Ubuntu 22.04/24.04) bo'lsa:

```bash
# 1. Loyihani serverga nusxalang
cd /root/slide_generator_bot

# 2. .env faylini to'ldiring
nano .env

# 3. Docker orqali fonda 24/7 ishga tushirish:
docker compose up -d --build
```
`restart: always` parametri sababli server o'chib yonsa ham bot avtomatik ishlab ketadi!

---

### 3-USUL: Linux VPS da Systemd Xizmati Sifatida
Loyiha ichida tayyor `bot.service` fayli mavjud:

```bash
# 1. Xizmat faylini tizimga nusxalash
sudo cp bot.service /etc/systemd/system/bot.service

# 2. Xizmatni yangilash va yoqish
sudo systemctl daemon-reload
sudo systemctl enable bot
sudo systemctl start bot

# 3. Bot holatini ko'rish:
sudo systemctl status bot

# 4. Loglarni real vaqtda kuzatish:
journalctl -u bot -f
```

---

## 📱 Botdan Foydalanish Qo'llanmasi

1. Botga `/start` yuborasiz.
2. **"🚀 Yangi Slayd Yaratish"** tugmasini bosing.
3. Taqdimot mavzusini yozing (masalan: *"Sun'iy intellekt kelajagi"*).
4. Slaydlar sonini tanlang (3, 5, 7 yoki 10 ta).
5. Ranglar mavzusini tanlang (masalan, *🌙 Dark Tech*).
6. 10-15 soniya kuting — bot tayyor PowerPoint (`.pptx`) faylini yuklab beradi!
7. Shaxsiy Gemini API kalitini bot ichida kiritish uchun `/setkey AIzaSy...` buyrug'idan foydalanishingiz mumkin.

Muvaffaqiyatli taqdimotlar tilaymiz! 🎉
