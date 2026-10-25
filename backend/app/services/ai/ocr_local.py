"""On-prem OCR (Tesseract rus+kaz+eng) and an OCR chain with fallback.

Screenshots are where schemes hide text («информация в скриншотах вместо текста»).
Tesseract runs inside the container — no external API, no GPU — so screenshot
analysis keeps working on-prem, in offline/mock mode, or when the cloud provider is
out of quota. The chain tries engines in order and returns the first non-empty text.
"""
from __future__ import annotations

import io
import logging

log = logging.getLogger("afm.ai")

LANGS = "rus+kaz+eng"


def tesseract_available() -> bool:
    try:
        import pytesseract
        pytesseract.get_tesseract_version()
        return True
    except Exception:  # noqa: BLE001 — binary or package missing
        return False


class TesseractOCR:
    def ocr(self, image: bytes) -> str:
        import pytesseract
        from PIL import Image, ImageOps

        img = Image.open(io.BytesIO(image))
        img = ImageOps.exif_transpose(img).convert("L")
        if img.width < 1000:                      # upscale small screenshots for accuracy
            scale = 1000 / max(1, img.width)
            img = img.resize((int(img.width * scale), int(img.height * scale)))
        try:
            text = pytesseract.image_to_string(img, lang=LANGS)
        except pytesseract.TesseractError:        # language pack missing -> default model
            text = pytesseract.image_to_string(img)
        return "\n".join(line.strip() for line in text.splitlines() if line.strip())


class ChainOCR:
    """Try each OCR engine in order; first non-empty result wins, failures are skipped."""

    def __init__(self, engines: list):
        self.engines = [e for e in engines if e is not None]

    def ocr(self, image: bytes) -> str:
        for engine in self.engines:
            try:
                text = (engine.ocr(image) or "").strip()
            except Exception as exc:  # noqa: BLE001 — try the next engine
                log.info("OCR engine %s failed: %s", type(engine).__name__, exc)
                continue
            if text:
                return text
        return ""
