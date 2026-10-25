"""Render synthetic «screenshots» for the SafeNet KZ demo (text inside images).

    python backend/scripts/make_demo_screenshots.py   # -> docs/demo_screenshots/*.png

All content is invented. Needs Pillow and a font with Cyrillic + Kazakh glyphs
(Arial / DejaVu Sans are picked automatically).
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).resolve().parents[2] / "docs" / "demo_screenshots"
FONTS = ["C:/Windows/Fonts/arialbd.ttf", "C:/Windows/Fonts/arial.ttf",
         "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]

CARDS = {
    "lottery_kz.png": ("#2b1055", "#ffffff", [
        "ҰТЫС ОЙЫНЫ", "Бас жүлде: iPhone 16 Pro", "Қатысу: 1000 ₸", "Барлығы 150 нөмір",
        "Kaspi: +7 747 123 45 67", "Жеңімпазды рандомайзер анықтайды", "Тікелей эфир: жексенбі 20:00"]),
    "casino_withdrawal.png": ("#0b3d2e", "#e8fff4", [
        "ВЫВОД СРЕДСТВ", "Сумма: 350 000 ₸", "Статус: Выполнено", "Lucky Jet",
        "Промокод: SHYM777", "Ссылка в шапке профиля"]),
    "pyramid_card.png": ("#0c2a4d", "#ffffff", [
        "ИНВЕСТ-КЛУБ «БЕРЕКЕ»", "Вложи 10 000 ₸ — получи 30 000 ₸", "Доход 3% в день",
        "Пригласи друга: +10% с его вклада", "Осталось 5 мест!", "Перевод на Kaspi Gold"]),
    "bank_deposit_clean.png": ("#f2f5f9", "#0b2545", [
        "ДЕПОЗИТ «ОНЛАЙН»", "до 15% годовых", "Вклады гарантированы КФГД", "Откройте в приложении банка"]),
}


def font(size: int):
    for f in FONTS:
        if Path(f).exists():
            return ImageFont.truetype(f, size)
    return ImageFont.load_default()


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for name, (bg, fg, lines) in CARDS.items():
        img = Image.new("RGB", (1080, 1080), bg)
        d = ImageDraw.Draw(img)
        y = 140
        for i, line in enumerate(lines):
            f = font(72 if i == 0 else 50)
            w = d.textlength(line, font=f)
            d.text(((1080 - w) / 2, y), line, font=f, fill=fg)
            y += 130 if i == 0 else 105
        img.save(OUT / name)
        print("wrote", OUT / name)


if __name__ == "__main__":
    main()
