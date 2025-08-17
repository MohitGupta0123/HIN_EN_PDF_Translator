from googletrans import Translator
from pathlib import Path
import re

# ------------------ Defaults (overridable via CLI) ------------------
DEFAULT_LANG = "hin+eng"
DEFAULT_DPI = "1000"
DEFAULT_OPTIMIZE = "3"
DEFAULT_TRANSLATE_DIR = "hi->en"   # "hi->en" | "en->hi" | "auto"
DEFAULT_ERASE = "redact"           # "redact" | "mask" | "none"
DEFAULT_REDACT_COLOR = (1, 1, 1)   # white
TR_TIMEOUT = 45

# Fonts (update paths to your TTFs)
FONT_EN_LOGICAL = "NotoSans"
FONT_EN_PATH    = str(Path(__file__).resolve().parent.parent / r"assets/fonts/NotoSans-Regular.ttf")
FONT_HI_LOGICAL = "TiroDevanagariHindi"
FONT_HI_PATH    = str(Path(__file__).resolve().parent.parent / r"assets/fonts/TiroDevanagariHindi-Regular.ttf")
FONT_HI_LOGICAL_2 = "NotoSansDevanagari"
FONT_HI_PATH_2    = str(Path(__file__).resolve().parent.parent / r"assets/fonts/NotoSansDevanagari-Regular.ttf")

_TR = Translator(timeout=TR_TIMEOUT, service_urls=["translate.googleapis.com"])
_DEV = re.compile(r"[\u0900-\u097F]")   # Devanagari
_LAT = re.compile(r"[A-Za-z]")