# 🇦🇿 USDT P2P AZ Telegram Bot

Emoji-li Telegram bot üçün başlanğıc layihə. Python + aiogram 3 istifadə edir və Render Worker kimi işləmək üçün hazırlanıb.

## Funksiyalar
- `/start` salamlama və düyməli menyu
- 🟢 USDT AL və 🔵 USDT SAT axınları
- AZN məbləğinin avtomatik hesablanması
- Təsdiqlə / ləğv et düymələri
- 3 dəqiqəlik alış qəbzi vaxtı
- Bank seçimi və TRC20 ünvanı göstərilməsi
- İstəyə bağlı şəxsi operator çatına bildiriş
- Admin paneli yoxdur

## Vacib məhdudiyyətlər
Bu başlanğıc versiya bank qəbzlərini avtomatik təsdiqləmir və blokçeyn TXID-ni avtomatik yoxlamır. Şəkil və ya TXID qəbul edilməsi ödənişin tamamlandığı demək deyil. Real istifadə üçün bankın rəsmi API inteqrasiyası və TRON blokçeyn explorer/API yoxlaması əlavə olunmalıdır. USDT/AZN ödənişləri yalnız faktiki təsdiqdən sonra tamamlanmalıdır.

Hazırkı versiya sifariş məlumatlarını restartdan sonra saxlamır; real əməliyyatlar üçün verilənlər bazası (məsələn, PostgreSQL) əlavə edilməlidir. 3 dəqiqəlik müddət istifadəçi növbəti mesaj göndərəndə yoxlanır; davamlı, dəqiq vaxt aşımı üçün background job və ya DB əsaslı scheduler lazımdır.

## 1. Telegram bot yaratmaq
Telegram-da `@BotFather` ilə bot yaradın və token alın. Tokeni heç vaxt GitHub-a commit etməyin.

## 2. GitHub
Bu qovluqdakı faylları yeni GitHub repository-yə yükləyin. `.env` faylını yükləməyin; yalnız `.env.example` saxlayın.

## 3. Render
1. Render-də **New → Blueprint** seçin.
2. GitHub repository-ni qoşun.
3. `render.yaml` faylını oxudun.
4. Environment dəyişənlərini doldurun:
   - `BOT_TOKEN`
   - `BANK_DETAILS`
   - `SELL_TRC20_ADDRESS`
   - istəyə görə `OPERATOR_CHAT_ID`
5. Deploy edin və Logs bölməsində xətaları yoxlayın.

## 4. Qiymət və rekvizitlər
`BUY_RATE`, `SELL_RATE`, `PAYMENT_MINUTES`, `BANK_DETAILS`, `SELL_TRC20_ADDRESS` Render Environment bölməsindən dəyişdirilə bilər.

## Təhlükəsizlik
- Telegram bot tokeni və bank giriş məlumatlarını kodda yazmayın.
- Müştəridən CVV, PIN, SMS kodu və bank tətbiqi şifrəsi istəməyin.
- Kart nömrəsini lazımsız saxlamayın; bu layihə tam nömrəni loglamır.
- Real bank inteqrasiyası olmadan qəbz şəklini avtomatik təsdiqləməyin.
