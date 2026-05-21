import re
from datetime import datetime

_ROMAN_VALUES = {
    "I": 1,
    "V": 5,
    "X": 10,
    "L": 50,
    "C": 100,
    "D": 500,
    "M": 1000,
}

_SMALL_NUMBER_WORDS = {
    1: "One",
    2: "Two",
    3: "Three",
    4: "Four",
    5: "Five",
    6: "Six",
    7: "Seven",
    8: "Eight",
    9: "Nine",
    10: "Ten",
    11: "Eleven",
    12: "Twelve",
    13: "Thirteen",
    14: "Fourteen",
    15: "Fifteen",
    16: "Sixteen",
    17: "Seventeen",
    18: "Eighteen",
    19: "Nineteen",
    20: "Twenty",
}

_MONTH_NAMES = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)


def clean_tts_text(text: str) -> str:
    """Make LLM output easier for TTS engines to read aloud."""
    text = _strip_markdown(str(text))
    text = _normalize_dates(text)
    text = _normalize_roman_numerals(text)
    text = _normalize_symbols(text)
    return re.sub(r"\s+", " ", text).strip()


def _strip_markdown(text: str) -> str:
    text = re.sub(r"```(?:\w+)?\s*([\s\S]*?)```", r"\1", text)
    text = re.sub(r"`([^`]*)`", r"\1", text)
    text = re.sub(r"!\[([^\]]*)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"^\s{0,3}#{1,6}\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\s{0,3}>\s?", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\s*[-*+]\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\s*\d+\.\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"([*_~]{1,3})(.*?)\1", r"\2", text)
    text = text.replace("|", " ")
    return text


def _normalize_dates(text: str) -> str:
    text = re.sub(
        r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b",
        lambda match: _format_date(
            int(match.group(3)), int(match.group(2)), int(match.group(1))
        ),
        text,
    )
    text = re.sub(
        r"\b(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})\b",
        lambda match: _format_numeric_date(match),
        text,
    )
    text = re.sub(
        r"\b(\d{1,2})(st|nd|rd|th)\s+("
        + "|".join(_MONTH_NAMES)
        + r")\s*,?\s*(\d{4})\b",
        r"\1 \3 \4",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r"\b("
        + "|".join(_MONTH_NAMES)
        + r")\s+(\d{1,2})(st|nd|rd|th)\s*,?\s*(\d{4})\b",
        r"\1 \2 \4",
        text,
        flags=re.IGNORECASE,
    )
    return text


def _format_numeric_date(match: re.Match[str]) -> str:
    first = int(match.group(1))
    second = int(match.group(2))
    year = int(match.group(3))
    if year < 100:
        year += 2000 if year < 50 else 1900

    # Prefer day/month for ambiguous dates; it matches this assistant's locale.
    if first > 12:
        return _format_date(first, second, year)
    if second > 12:
        return _format_date(second, first, year)
    return _format_date(first, second, year)


def _format_date(day: int, month: int, year: int) -> str:
    try:
        parsed = datetime(year, month, day)
    except ValueError:
        return f"{day}-{month}-{year}"
    return f"{parsed.day} {_MONTH_NAMES[parsed.month - 1]} {parsed.year}"


def _normalize_roman_numerals(text: str) -> str:
    roman_pattern = (
        r"(?=[MDCLXVI])M{0,3}(?:CM|CD|D?C{0,3})(?:XC|XL|L?X{0,3})(?:IX|IV|V?I{0,3})"
    )

    def replace(match: re.Match[str]) -> str:
        roman = match.group("roman")
        value = _roman_to_int(roman)
        if not value:
            return match.group(0)
        word = _SMALL_NUMBER_WORDS.get(value, str(value))
        return f"{match.group('prefix')}{word}"

    return re.sub(
        rf"\b(?P<prefix>[A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+){{0,3}}\s+)(?P<roman>{roman_pattern})\b",
        replace,
        text,
    )


def _roman_to_int(roman: str) -> int:
    total = 0
    previous = 0
    for char in reversed(roman):
        value = _ROMAN_VALUES.get(char, 0)
        if value < previous:
            total -= value
        else:
            total += value
            previous = value
    return total


def _normalize_symbols(text: str) -> str:
    replacements = {
        "&": " and ",
        "@": " at ",
        "%": " percent ",
        "*": "",
        "#": "",
        "_": " ",
        "~": "",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)
    text = re.sub(r"([.!?]){2,}", r"\1", text)
    return text
