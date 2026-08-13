import base64

import cv2
import easyocr
import numpy as np


ALLOWLIST = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"

_reader = None


def get_reader():
    global _reader
    if _reader is None:
        print("[OCR] Initializing EasyOCR...")
        _reader = easyocr.Reader(["en"], gpu=False)
    return _reader


def ocr_captcha(base64_data: str) -> str:
    raw = np.frombuffer(base64.b64decode(base64_data), np.uint8)
    img = cv2.imdecode(raw, cv2.IMREAD_COLOR)
    if img is None:
        return ""

    reader = get_reader()

    candidates = []

    def raw(img):
        return img

    def gray(img):
        return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    def otsu(img):
        g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        _, t = cv2.threshold(g, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        return t

    def adaptive(img):
        g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        return cv2.adaptiveThreshold(g, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                     cv2.THRESH_BINARY, 11, 2)

    def upscale(img):
        return cv2.resize(img, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)

    def upscale_otsu(img):
        up = cv2.resize(img, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
        g = cv2.cvtColor(up, cv2.COLOR_BGR2GRAY)
        _, t = cv2.threshold(g, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        return t

    def clahe(img):
        g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        return clahe.apply(g)

    def gray_upscale_otsu(img):
        g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        up = cv2.resize(g, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
        _, t = cv2.threshold(up, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        return t

    methods = [
        ("raw", raw),
        ("gray", gray),
        ("otsu", otsu),
        ("adaptive", adaptive),
        ("clahe", clahe),
        ("upscale+otsu", upscale_otsu),
        ("gray+upscale+otsu", gray_upscale_otsu),
    ]

    for name, fn in methods:
        try:
            processed = fn(img)
            result = reader.readtext(processed, detail=1, allowlist=ALLOWLIST)
            if result:
                candidates.append((result[0][1].strip(), result[0][2], name))
        except Exception:
            pass

    if not candidates:
        return ""

    best = max(candidates, key=lambda c: c[1])
    text, conf, method = best
    cleaned = "".join(ch for ch in text if ch.isalnum())
    print(f"  [OCR] '{cleaned}'  (conf: {conf:.2%}, method: {method})")
    return cleaned
