"""Generate the SafeNet KZ synthetic DEV dataset (used to tune the lexicon).

Deterministic (seed 42). Templates cover the three tracks in Russian, Kazakh,
RU/KZ mix and translit, plus HARD NEGATIVES that share vocabulary with the schemes
(free giveaways, bank deposits, shop sales with «успей», sports news about bets,
anti-fraud warnings, job ads). Random obfuscation (leet, spaced letters, homoglyphs,
emoji, translit) is applied to part of the positives — the «главная сложность».

The held-out TEST set (app/services/safenet/data/test.jsonl) is hand-written
separately and is NOT produced by this script.

    python -m scripts.generate_safenet_dataset          # writes data/dev.jsonl
"""
from __future__ import annotations

import json
import random
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "app" / "services" / "safenet" / "data" / "dev.jsonl"
RNG = random.Random(42)

PRIZES_RU = ["iPhone 15 Pro", "AirPods Pro", "PlayStation 5", "50 000 тг", "100 000 тенге", "Samsung S24",
             "золотые серьги", "Chevrolet Cobalt", "мультиварку", "телевизор LG", "путевку в Турцию"]
PRIZES_KK = ["iPhone 15", "AirPods", "50 000 теңге", "алтын сырға", "көлік", "теледидар", "100 000 теңге"]
FEES = [300, 500, 700, 1000, 1500, 2000, 3000, 5000]
INVEST = [2000, 5000, 10000, 15000, 20000, 50000, 100000]
PHONES = ["+7 701 555 12 34", "8 747 123 45 67", "+7 777 900 11 22", "8 705 321 00 99"]
CARDS = ["4400 4301 2345 6789", "4405 6398 1122 3344", "4400 4301 9876 5437"]
BRANDS = ["1xBet", "Mostbet", "Pin-Up", "Vavada", "1win", "Melbet", "Lucky Jet", "Aviator", "Joycasino"]
CODES = ["WIN500", "KZBONUS", "LUCKY777", "ASTANA24", "MEGA300", "SHYM100"]
LINKS = ["bit.ly/kz-win7", "clck.ru/3Ab9x", "cutt.ly/lucky-kz", "t.me/lucky_signals_kz",
         "goo.su/w1nkz", "https://play-kz.top/?ref=7781", "vavada-mirror.xyz"]
TG = ["@invest_club_kz", "@kurator_aigerim", "@profit_team_almaty", "@dengi_kz_vip"]
CITIES = ["Шымкент", "Алматы", "Астана", "Тараз", "Караганда"]
NAMES = ["Айгерим", "Данияр", "Асель", "Ерлан", "Мадина", "Нурлан"]


def pick(xs):
    return RNG.choice(xs)


def fmt(n: int) -> str:
    return f"{n:,}".replace(",", " ")


# --- obfuscation -------------------------------------------------------------
_LEET = {"а": "@", "о": "0", "з": "3", "a": "@", "o": "0"}
_HOMO = {"а": "a", "о": "o", "е": "e", "с": "c", "р": "p", "к": "k", "х": "x"}
_RU2LAT = {"а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "yo", "ж": "zh", "з": "z",
           "и": "i", "й": "y", "к": "k", "л": "l", "м": "m", "н": "n", "о": "o", "п": "p", "р": "r",
           "с": "s", "т": "t", "у": "u", "ф": "f", "х": "h", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "sch",
           "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
           # Kazakh letters as people type them in Latin
           "ә": "a", "ғ": "g", "қ": "k", "ң": "n", "ө": "o", "ұ": "u", "ү": "u", "һ": "h", "і": "i"}
KEYWORDS = ["казино", "розыгрыш", "ставки", "доход", "каспи", "слоты", "выигрыш", "прибыль", "взнос",
            "участие", "вложи", "получи", "Казино", "Розыгрыш", "промокод", "бонус"]


def leet(word: str) -> str:
    return "".join(_LEET.get(c, c) if RNG.random() < 0.5 else c for c in word)


def spaced(word: str) -> str:
    return " ".join(word)


def homoglyph(word: str) -> str:
    return "".join(_HOMO.get(c, c) if RNG.random() < 0.5 else c for c in word)


def translit(text: str) -> str:
    out = []
    for ch in text:
        low = ch.lower()
        lat = _RU2LAT.get(low)
        if lat is None:
            out.append(ch)
        else:
            out.append(lat.upper() if ch.isupper() and lat else lat)
    return "".join(out)


def obfuscate(text: str) -> tuple[str, str]:
    mode = pick(["leet", "spaced", "homoglyph", "translit", "emoji"])
    if mode == "translit":
        return translit(text), mode
    if mode == "emoji":
        return text.replace("казино", "🎰").replace("Казино", "🎰").replace("деньги", "💸"), mode
    fn = {"leet": leet, "spaced": spaced, "homoglyph": homoglyph}[mode]
    for kw in KEYWORDS:
        if kw in text:
            return text.replace(kw, fn(kw), 1), mode
    return text, "none"


# --- templates ---------------------------------------------------------------
def lottery_pos():
    prize, fee, left = pick(PRIZES_RU), pick(FEES), RNG.randint(3, 40)
    total = RNG.choice([50, 100, 150, 200])
    t = pick([
        f"🎁 РОЗЫГРЫШ {prize}! Участие — {fee} тг. Перевод на Kaspi {pick(PHONES)}. Победителя выберем рандомайзером в прямом эфире в пятницу. Осталось {left} номеров!",
        f"Разыгрываем {prize} 🔥 Цена одного номера {fee} тг, всего {total} номеров. Как только наберем — крутим колесо фортуны в лайве",
        f"Лотерея среди подписчиков! Билет {fee} тг, оплата на карту {pick(CARDS)}. Главный приз — {prize}. Жеребьевка в эфире",
        f"Розыгрыш №{RNG.randint(2, 30)}: {prize}. Займи свой номер — {fee}₸. Свободные номера в комментариях, после продажи всех мест выберем победителя через random.org",
        f"Друзья, новый розыгрыш {prize}! Чтобы участвовать, скиньте {fee} тг на Kaspi Gold и пришлите чек в директ. Победитель определится рандомом",
        f"Еженедельный розыгрыш! Номер = {fee} тг. Осталось {left} мест. Призовой фонд {fmt(fee * total)} тг. Крутим барабан в прямом эфире",
        f"Продажа слотов на розыгрыш {prize} открыта ✨ {total} мест по {fee} тг. Комиссия организатора 20%. Победителя выберет колесо",
        f"ГИВ на {prize}!!! вход {fee}тг, переводи на каспи {pick(PHONES)}, все номера почти проданы, завтра рандомайзер на стриме",
        f"Внимание! Платный розыгрыш {prize}. Стоимость участия {fee} тг. Победитель случайным выбором в эфире. Каждую субботу новый розыгрыш",
    ])
    return t, "ru"


def lottery_pos_kk():
    prize, fee, left = pick(PRIZES_KK), pick(FEES), RNG.randint(3, 30)
    t = pick([
        f"Ұтыс ойыны! {prize} ойнатамыз. Қатысу ақылы — {fee} тг, Kaspi-ге аударыңыз {pick(PHONES)}. Жеңімпазды тікелей эфирде кездейсоқ анықтаймыз",
        f"{prize} ұтып алыңыз! Бір нөмір {fee} теңге. {left} орын қалды. Жеребе тікелей эфирде",
        f"Жаңа ұтыс! Қатысу құны {fee} тг. Билет сатып алу үшін каспиге аударыңыз. Бас жүлде — {prize}. Рандомайзер арқылы таңдаймыз",
        f"Розыгрыш {prize}! Қатысу үшін {fee} тг аударыңыз Kaspi Gold картаға. Жеңімпазды рандомайзер анықтайды, апта сайын жаңа ұтыс",
    ])
    lang = "mixed" if "Розыгрыш" in t or "Kaspi Gold" in t else "kk"
    return t, lang


def casino_pos():
    brand, code, link = pick(BRANDS), pick(CODES), pick(LINKS)
    win = pick(["150к", "300 000 тг", "1.2 млн", "500к", "80 000 тенге", "2 000 000 тг"])
    t = pick([
        f"Как я поднял {win} за вечер в {brand} 🚀 Промокод {code}, ссылка в шапке профиля",
        f"Мой выигрыш сегодня {win}! Вывод пришел за 5 минут. Регистрируйся по ссылке {link} и вводи промокод {code}",
        f"Стрим в 21:00 — крутим слоты, ловим заносы недели! Бонус 200% на первый депозит по коду {code}. Ссылка в описании",
        f"Рабочее зеркало {brand}: {link} — без VPN, бонус новичкам 500% + 250 фриспинов",
        f"Сигналы для Lucky Jet в моем тг-канале, вчера сделал x40 🔥 вывел {win}. Подробности: {link}",
        f"Скрин вывода с {brand} 👇 {win} за час. Проверенная стратегия, промокод {code} даёт +100% к пополнению",
        f"Казино без верификации, моментальный вывод на Kaspi. Жми на ссылку в био и забирай бонус {code}",
        f"Легкие деньги в Aviator: поднял {win} с 5000 тг. Бот сигналов бесплатно, переходи по ссылке {link}",
        f"Ставки на спорт с кэфом 3.5 — договорные матчи! Пиши в лс, ссылка на {brand} в профиле, промокод {code}",
        f"Live: крутим Gates of Olympus, депнул 20к — занос x500! Ссылка на казино в закрепе 🎰",
    ])
    return t, "ru"


def casino_pos_kk():
    brand, code, link = pick(BRANDS), pick(CODES), pick(LINKS)
    t = pick([
        f"Бүгін {brand}-та 300 000 теңге ұттым! Промокод {code}, сілтеме профильде",
        f"Казинода қалай ақша табуға болады? Мен 1 кеште 200к шығарып алдым. Тіркеліңіз: {link}",
        f"Тікелей эфирде слоттар ойнаймыз! Бонус 200% бірінші депозитке, промокод {code}. Сілтеме биода",
        f"Lucky Jet сигналдары тегін, менің телеграм каналымда. Кеше x30 жасадым, ұттым 150к! {link}",
    ])
    return t, ("mixed" if "Lucky" in t else "kk")


def pyramid_pos():
    a = pick(INVEST)
    mult = pick([2, 2, 3, 1.5, 5])
    b = int(a * mult)
    t = pick([
        f"Вложи {fmt(a)} тг — через неделю получишь {fmt(b)} тг! Гарантированный доход, без риска. Осталось {RNG.randint(2, 9)} мест, пиши куратору {pick(TG)}",
        f"Инвест-клуб «Береке»: доход 3% в день, выплаты каждый день на Kaspi. Пригласи друга — получи 10% с его вклада. Успей до конца недели!",
        f"Девочки, я уже третий месяц в проекте 🙌 вложила {fmt(a)}, вывожу по {fmt(int(a * 0.3))} каждую неделю. Скрины выплат в сторис. Наставник добавит в закрытый чат",
        f"Удвоим ваши деньги за 10 дней! Минимальный вход {fmt(a)} тг. Перевод на карту {pick(CARDS)}. Только сегодня бонус за каждого приглашенного",
        f"Пассивный доход 40% в месяц. Схема проверена, выплаты пришли всем участникам. Переводи на Kaspi Gold {pick(PHONES)}, куратор подскажет",
        f"Набор в команду закрывается! 1-я линия — 15%, 2-я линия — 7%. Твоя структура работает на тебя. Вход от {fmt(a)} тг, реферальный бонус",
        f"Ежедневные начисления 5% от вклада. Вложи {fmt(a)}, через месяц на руках {fmt(a * 2)}. Отзывы участников в нашем WhatsApp: chat.whatsapp.com/AbCd123",
        f"Финансовая свобода за 30 дней! Закинь {fmt(a)} тенге, получи {fmt(b)} тенге. Мест ограничено, пишите в лс",
    ])
    return t, "ru"


def pyramid_pos_kk():
    a = pick(INVEST)
    b = a * pick([2, 3])
    t = pick([
        f"{fmt(a)} тг салсаңыз, бір аптада {fmt(b)} тг аласыз! Кепілдендірілген табыс. Досыңды шақыр — бонус. Асығыңыз, {RNG.randint(2, 9)} орын қалды",
        f"Күніне 3% табыс! Ақша салып, күнде пайда табыңыз. Kaspi-ге аударыңыз {pick(PHONES)}, куратор жазады",
        f"Тәуекелсіз табыс! {fmt(a)} теңге салсаң, {fmt(b)} теңге аласың. Бүгін ғана! Шақырған әр досың үшін 10%",
        f"Девочки, салым салдым {fmt(a)}, бір аптада екі есе! Төлем түсті, скрин стористе 💸 Жабық топқа қосыламын, жеке хабарлама жазыңыз",
    ])
    return t, ("mixed" if "Девочки" in t else "kk")


NEGATIVES = [
    # free giveaways (hard)
    lambda: (f"🎁 РОЗЫГРЫШ {pick(PRIZES_RU)}! Условия: подпишись на наш аккаунт, поставь лайк и отметь 2 друзей. Победителя выберем рандомайзером в пятницу. Участие бесплатное!", "ru", "free_giveaway"),
    lambda: (f"Конкурс от магазина «{pick(['Арзан', 'Береке', 'Медина'])}»: сделай репост и оставь комментарий — разыграем {pick(PRIZES_RU)} среди подписчиков. Ничего платить не нужно", "ru", "free_giveaway"),
    lambda: (f"Ұтыс! {pick(PRIZES_KK)} ойнатамыз. Шарттары: парақшаға жазылыңыз, лайк басыңыз, досыңызды белгілеңіз. Қатысу тегін! Жеңімпазды рандомайзер анықтайды", "kk", "free_giveaway"),
    lambda: (f"Гив на {pick(PRIZES_RU)} 🎉 без оплаты и взноса, просто подпишись на 3 аккаунта спонсоров. Итоги в прямом эфире", "ru", "free_giveaway"),
    # bank / legal finance
    lambda: (f"Halyk Bank: депозит «Онлайн» до {pick([13, 14, 15, 16])}% годовых. Вклады гарантированы КФГД. Откройте в приложении Homebank", "ru", "bank"),
    lambda: (f"Kaspi Депозит — {pick([12, 14, 15])}% годовых, пополнение и снятие без ограничений", "ru", "bank"),
    lambda: (f"Процентная ставка по ипотеке «Отау» снизилась до {pick([5, 7, 9])}%. Нацбанк сохранил базовую ставку", "ru", "bank"),
    lambda: (f"Kaspi Red: рассрочка 0-0-12 на технику в Kaspi магазине. Успей до конца месяца!", "ru", "shop"),
    lambda: (f"Облигации Минфина РК: купонная доходность {pick([12, 13, 14])}% годовых, покупка через Freedom Broker", "ru", "bank"),
    # shop sales with urgency
    lambda: (f"Распродажа в {pick(CITIES)}! Скидки до 50% только сегодня, успейте — осталось {RNG.randint(3, 20)} пар обуви. Доставка бесплатно", "ru", "shop"),
    lambda: (f"Жеңілдік! Бүгін ғана барлық киімге 30% жеңілдік. Асығыңыз, тауар саны шектеулі", "kk", "shop"),
    lambda: (f"Приглашаем друзей на открытие кофейни! Пригласи друга — получи кофе в подарок 😊", "ru", "shop"),
    # sports news / gambling mentions w/o promotion
    lambda: (f"Букмекеры принимают ставки на финал Лиги чемпионов: фаворит — «Реал»", "ru", "news"),
    lambda: (f"Смотрели фильм «Казино Рояль» вчера — Дэниел Крейг лучший Бонд", "ru", "news"),
    lambda: (f"В {pick(CITIES)} полиция закрыла подпольное казино, задержаны 12 человек", "ru", "news"),
    # anti-fraud warnings (hard)
    lambda: (f"Осторожно, мошенники! АФМ предупреждает: финансовые пирамиды обещают 30% в месяц и бонус за приглашенных. Не переводите деньги незнакомцам", "ru", "warning"),
    lambda: (f"Алаяқтардан сақ болыңыз! Күніне 5% табыс уәде ететін топтар — қаржы пирамидасы. Ақша аудармаңыз", "kk", "warning"),
    lambda: (f"Как распознать платный розыгрыш: если просят перевести деньги за участие на карту — это лотерея без лицензии. Будьте бдительны", "ru", "warning"),
    lambda: (f"Блогеры рекламируют казино через «мой выигрыш» и промокоды — рассказываем, как это работает и почему не стоит вестись", "ru", "warning"),
    # jobs / everyday
    lambda: (f"Вакансия: продавец-консультант, {pick(CITIES)}. Заработная плата от 250 000 тг, график 5/2", "ru", "job"),
    lambda: (f"Продам iPhone 13, 128 гб, цена 220 000 тг, торг. Перевод на Kaspi или наличные", "ru", "shop"),
    lambda: (f"Сбор на лечение Айсулу: любая сумма поможет, Kaspi {pick(PHONES)}. Спасибо всем неравнодушным", "ru", "charity"),
    lambda: (f"Стоимость участия в семинаре по бухгалтерии — 15 000 тг, оплата на счет ТОО. Сертификат выдается", "ru", "event"),
    lambda: (f"Бүгін кешке достармен футбол ойнаймыз, кім келеді? Ставка жоқ, жай ойын 😄", "kk", "everyday"),
    lambda: (f"Мы с мужем открыли депозит, 14% годовых — для подушки безопасности норм", "ru", "bank"),
    lambda: (f"Наша команда ищет кураторов детского лагеря на лето, оплата 180 000 тг", "ru", "job"),
    lambda: (f"Kaspi.kz/shop — заказ доставлен. Оплата Kaspi QR прошла успешно", "ru", "shop"),
    lambda: (f"Онлайн-курс по Python: первый урок бесплатно, дальше 25 000 тг в месяц. Регистрация по ссылке в профиле", "ru", "event"),
    lambda: (f"Сыйлық ұтыс ойыны мектепте өтті, балалар қуанды! Барлығы тегін болды", "kk", "free_giveaway"),
    lambda: (f"Друзья, напоминаю: наш благотворительный забег — участие бесплатное, взнос не нужен", "ru", "event"),
]


def main() -> None:
    rows = []
    gens = [
        ("lottery", lottery_pos, 70), ("lottery", lottery_pos_kk, 30),
        ("casino", casino_pos, 70), ("casino", casino_pos_kk, 30),
        ("pyramid", pyramid_pos, 70), ("pyramid", pyramid_pos_kk, 30),
    ]
    for track, gen, n in gens:
        for _ in range(n):
            text, lang = gen()
            obf = "none"
            if RNG.random() < 0.25:
                text, obf = obfuscate(text)
                if obf == "translit":
                    lang = "translit"
            rows.append({"text": text, "label": 1, "track": track, "lang": lang,
                         "obfuscation": obf, "hard_negative": False, "category": track})
    for _ in range(10):
        for gen in NEGATIVES:
            text, lang, cat = gen()
            rows.append({"text": text, "label": 0, "track": "none", "lang": lang, "obfuscation": "none",
                         "hard_negative": cat in ("free_giveaway", "bank", "warning", "news", "shop", "charity", "event"),
                         "category": cat})
    # dedupe identical texts, keep order
    seen, out = set(), []
    for r in rows:
        if r["text"] not in seen:
            seen.add(r["text"])
            out.append(r)
    RNG.shuffle(out)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8") as fh:
        for i, r in enumerate(out, 1):
            fh.write(json.dumps({"id": f"dev-{i:04d}", **r}, ensure_ascii=False) + "\n")
    pos = sum(r["label"] for r in out)
    print(f"wrote {len(out)} rows ({pos} positive, {len(out) - pos} negative) -> {OUT}")


if __name__ == "__main__":
    main()
