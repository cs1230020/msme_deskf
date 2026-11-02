"""Small, permissive text helpers used by the VERIFIER (not by the regex baseline)."""
import re
import unicodedata
from datetime import date

MONTHS = {m: i + 1 for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july", "august",
     "september", "october", "november", "december"])}
MONTHS.update({k[:3]: v for k, v in list(MONTHS.items())})
MONTHS["sept"] = 9

_DEV_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")


def norm(s: str) -> str:
    """Normalise for quote matching: NFKC, Devanagari digits -> ASCII, collapse whitespace, casefold."""
    s = unicodedata.normalize("NFKC", s or "").translate(_DEV_DIGITS)
    s = s.replace("’", "'").replace("–", "-").replace("—", "-")
    return re.sub(r"\s+", " ", s).strip().casefold()


def dates_in(text: str, default_years=(2025, 2026)):
    """Every calendar date a human would read in `text` (several formats, year optional)."""
    t = norm(text)
    found = set()

    def add(y, m, d):
        try:
            found.add(date(y, m, d))
        except ValueError:
            pass

    for d, m, y in re.findall(r"\b(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{4})\b", t):
        add(int(y), int(m), int(d))
    for y, m, d in re.findall(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b", t):
        add(int(y), int(m), int(d))
    mon = "|".join(sorted(MONTHS, key=len, reverse=True))
    for d, m, y in re.findall(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?(?:\s+of)?\s+({mon})\.?,?(?:\s+(\d{{4}}))?", t):
        for yy in ([int(y)] if y else default_years):
            add(yy, MONTHS[m], int(d))
    for m, d, y in re.findall(rf"\b({mon})\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?,?(?:\s+(\d{{4}}))?", t):
        for yy in ([int(y)] if y else default_years):
            add(yy, MONTHS[m], int(d))
    return found


_UNITS = {"zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
          "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13,
          "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
          "nineteen": 19}
_TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70,
         "eighty": 80, "ninety": 90}
_HINDI = {"पंद्रह": 15, "तीस": 30, "पैंतालीस": 45, "साठ": 60, "नब्बे": 90, "सात": 7, "इक्कीस": 21}


def numbers_in(text: str):
    """Integers written as digits, English words (up to 99) or common Hindi words."""
    t = norm(text)
    out = {int(n) for n in re.findall(r"\b(\d{1,3})\b", t)}
    for tens, unit in re.findall(r"\b(" + "|".join(_TENS) + r")(?:[\s\-]+(" + "|".join(_UNITS) + r"))?\b", t):
        out.add(_TENS[tens] + (_UNITS[unit] if unit else 0))
    for w, v in _UNITS.items():
        if re.search(rf"\b{w}\b", t):
            out.add(v)
    for w, v in _HINDI.items():
        if w in t:
            out.add(v)
    return out


def rupees(x):
    """Indian digit grouping: Rs 12,34,567."""
    if x is None:
        return "-"
    n = str(int(x))
    if len(n) <= 3:
        return "Rs " + n
    head, tail, parts = n[:-3], n[-3:], []
    while len(head) > 2:
        parts.insert(0, head[-2:])
        head = head[:-2]
    if head:
        parts.insert(0, head)
    return "Rs " + ",".join(parts + [tail])
