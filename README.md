# ABU SUB BOT

Telegram obunachi almashish boti: foydalanuvchi coin sarflab o'z kanal/guruhiga **haqiqiy obunachi** buyurtma qiladi,
boshqalar esa vazifalar kanalidagi postlar orqali obuna bo'lib **coin ishlaydi**.
Python 3.12 · aiogram 3 · PostgreSQL (asyncpg) · Render.

## Imkoniyatlar
- **Menyu:** 👥 Obunachi buyurtma · 🪙 Coin ishlash · 👛 Balansim · 📦 Buyurtmalarim · 👥 Referal · 👤 Profil
- **Buyurtma:** son → havola (`@username`, `t.me/...`, `-100...` ID yoki kanaldan forward) → bot admin ekani va buyurtmachi admin ekani tekshiriladi → coin yechiladi. Coin yetmasa «Coin ishlash»ga yo'naltiriladi.
- **Vazifalar kanali:** har buyurtma avtomatik post bo'ladi (kanal rasmi, nomi, ID, buyurtma/bajarildi/qoldi, havola; tugmalar: Kanalga kirish · Tasdiqlash · Botimiz). Sonlar avtomatik yangilanadi, to'liq bajarilganda post o'chadi va egasiga xabar boradi.
- **Coin himoyasi:** `earnings(user_id, chat_id)` UNIQUE → bir foydalanuvchi bir kanal/guruhdan umrida **bir marta** coin oladi (boshqa buyurtma tushsa ham, qayta obuna bo'lsa ham). Chiqib ketsa −1 coin (balans manfiy bo'lishi mumkin), faqat bir marta. Hammasi PostgreSQL tranzaksiyalari + `FOR UPDATE` + UNIQUE bilan (parallel bosishga chidamli, testlangan). Barcha harakatlar `transactions` jadvalida.
- **Obuna nazorati:** `chat_member` yangilanishlari orqali chiqib ketish darhol aniqlanadi; bundan tashqari fon ishchisi har `recheck_hours` (standart 6 soat) da `getChatMember` bilan qayta tekshiradi.
- **Referal:** `t.me/<bot>?start=ref_<id>`. Do'st yangi foydalanuvchi bo'lishi va kamida 1 ta obunachi buyurtma qilishi kerak — shundan keyin taklif qilganga +1 coin (bir marta). O'zini o'zi taklif qilish va mavjud foydalanuvchini referal qilish bloklangan.
- **Admin / VIP:** `ADMIN_IDS` dagilar va VIP berilganlar uchun cheksiz coin, buyurtmada coin yechilmaydi.
- **Admin panel** (`/admin`): statistika, foydalanuvchilar (balans +/−, VIP, ban), vazifalar kanali, majburiy obuna kanali, narx va sozlamalar, premium emoji ID lari, loglar.

## Ishga tushirish (lokal)
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env     # to'ldiring va export qiling
python main.py           # migratsiyalar avtomatik bajariladi
```
Testlar (PostgreSQL kerak, test bazasi **tozalanadi**):
```bash
TEST_DATABASE_URL=postgresql://user:pass@localhost/absub_test pytest
```

## Telegramda sozlash
1. @BotFather'dan token oling → `BOT_TOKEN`; o'zingizning ID'ingiz → `ADMIN_IDS`.
2. Alohida **vazifalar kanali** oching, botni admin qiling (*xabar joylash, tahrirlash, o'chirish*), so'ng botda `/admin → Coin kanali` orqali kanalni ulang (yoki `TASKS_CHANNEL_ID` env).
3. Buyurtmachi o'z kanal/guruhida botni **admin** qilishi kerak (kanalda obunachilarni ko'rish uchun shart; yopiq kanalda «taklif qilish» huquqi ham).
4. (Ixtiyoriy) `/admin → Majburiy kanal` — «Coin ishlash» uchun rasmiy kanalga obuna talabi.

## Render'ga joylash
1. Kodni GitHub'ga yuklang → Render'da **New → Blueprint** → repo'ni tanlang (`render.yaml` web servis va PostgreSQL yaratadi).
2. `BOT_TOKEN`, `ADMIN_IDS` (va xohlasangiz `TASKS_CHANNEL_ID`) ni kiriting. `DATABASE_URL` avtomatik ulanadi.

Eslatmalar: bot long-polling rejimida ishlaydi va Render talab qilgani uchun `/health` portini ochadi. Bepul web servis 15 daqiqa so'rovsiz qolsa uxlaydi — bot buning oldini olish uchun o'zini har 10 daqiqada pinglaydi (`RENDER_EXTERNAL_URL`), lekin barqaror ishlash uchun pullik reja tavsiya etiladi. Render'ning bepul PostgreSQL bazasi cheklangan muddatli.

## Premium Custom Emoji — Telegram cheklovlari (muhim)
Hamma xabar, menyu va tugmalar emoji kalitlari orqali quriladi (`/admin → Premium emoji`: premium emoji yuborsangiz ID o'zi olinadi, `0` — o'chirish). Matnlarda `<tg-emoji>`, tugmalarda Bot API'ning `icon_custom_emoji_id` va `style` maydonlari ishlatiladi.
Telegram hujjatiga ko'ra tugma ikonkasi (`icon_custom_emoji_id`) faqat **bot egasida Telegram Premium bo'lsa** (va xabar private/guruh/supergroup chatga yuborilsa) yoki botga **Fragment'da qo'shimcha username** sotib olingan bo'lsa ishlaydi. Kanal postlarida (vazifalar kanali) odatda bu ishlamasligi mumkin. Telegram rad etsa, bot **avtomatik oddiy emojiga qaytadi** (xabar yo'qolmaydi). Bu cheklovni kod aylanib o'ta olmaydi.

## Muhim qarorlar va cheklovlar
- **Yangi obuna talabi (`strict_join`, standart yoqilgan):** kanalda avvaldan a'zo bo'lganlar coin ola olmaydi (buyurtmachi pul to'lagan obuna yangi bo'lishi kerak). Bot `chat_member` yangilanishidan qo'shilishni qayd qiladi. Admin panelda o'chirish mumkin.
- **Narx:** standart 1 obunachi = 1 coin, minimal buyurtma 10 ta (admin paneldan o'zgaradi). Obuna uchun mukofot 1 coin.
- **Buyurtma bekor qilish:** «Buyurtmalarim» dan; bajarilmagan qism uchun coin qaytariladi.
- Yopiq `t.me/+...` taklif havolasidan kanalni aniqlab bo'lmaydi (Telegram API bunga yo'l qo'ymaydi) — forward yoki ID so'raladi. Guruhda `/id` (faqat adminlar) ID ni ko'rsatadi.
- Chiqib ketgan foydalanuvchi uchun faol buyurtmada o'rin qayta bo'shaydi; yakunlangan buyurtma o'zgarmaydi.
- Bot kanalda admin huquqini yo'qotsa, jarima berilmaydi, buyurtma egasiga ogohlantirish yuboriladi.
- FSM holatlari xotirada (qayta ishga tushganda suhbat bosqichi tiklanadi); pul va buyurtmalar — faqat bazada.

## Tuzilma
```
main.py  bot.py  config.py  database.py  admin.py
handlers/  menu, order, earn, account, events, middleware
services/  coins, orders, chats, users, tasks (post ishchisi), checker, emoji, keyboards, fallback, settings, logs
migrations/001_init.sql   tests/   render.yaml   .env.example   requirements.txt
```
