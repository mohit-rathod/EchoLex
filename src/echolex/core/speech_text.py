from __future__ import annotations

import re

_LATEX_COMMANDS = {
    r"\alpha": "alpha",
    r"\beta": "beta",
    r"\gamma": "gamma",
    r"\delta": "delta",
    r"\epsilon": "epsilon",
    r"\theta": "theta",
    r"\lambda": "lambda",
    r"\mu": "mu",
    r"\sigma": "sigma",
    r"\phi": "phi",
    r"\omega": "omega",
    r"\pi": "pi",
    r"\sum": "the sum of",
    r"\prod": "the product of",
    r"\infty": "infinity",
    r"\leq": "less than or equal to",
    r"\geq": "greater than or equal to",
    r"\neq": "not equal to",
    r"\approx": "approximately",
    r"\times": "times",
    r"\cdot": "times",
    r"\pm": "plus or minus",
}


def _replace_latex_fraction(text: str) -> str:
    pattern = re.compile(r"\\frac\s*\{([^{}]+)\}\s*\{([^{}]+)\}")
    for _ in range(5):
        updated = pattern.sub(
            lambda match: f"{match.group(1)} divided by {match.group(2)}",
            text,
        )
        if updated == text:
            break
        text = updated
    return text


def _replace_superscripts(text: str) -> str:
    text = re.sub(r"([A-Za-z0-9]+)\^\{?2\}?", r"\1 squared", text)
    text = re.sub(r"([A-Za-z0-9]+)\^\{?3\}?", r"\1 cubed", text)
    return re.sub(
        r"([A-Za-z0-9]+)\^\{?([^{}\s]+)\}?",
        r"\1 to the power of \2",
        text,
    )


def _replace_spaced_operator(text: str, symbol: str, spoken: str) -> str:
    """Replace operators only when written as math, not punctuation in normal prose."""
    escaped = re.escape(symbol)
    text = re.sub(rf"\s+{escaped}\s+", f" {spoken} ", text)
    text = re.sub(
        rf"(?<=\d)\s*{escaped}\s*(?=\d)",
        f" {spoken} ",
        text,
    )
    return text


def prepare_text_for_speech(text: str) -> str:
    """Convert common Markdown/LaTeX fragments into safer spoken text."""
    if not text:
        return text

    result = text
    for delimiter in ("$$", r"\[", r"\]", r"\(", r"\)", "$"):
        result = result.replace(delimiter, " ")

    result = _replace_latex_fraction(result)
    result = re.sub(r"\\sqrt\s*\{([^{}]+)\}", r"the square root of \1", result)
    result = _replace_superscripts(result)

    for latex, spoken in _LATEX_COMMANDS.items():
        result = result.replace(latex, f" {spoken} ")

    result = _replace_spaced_operator(result, "=", "equals")
    result = _replace_spaced_operator(result, "+", "plus")
    result = _replace_spaced_operator(result, "-", "minus")
    result = _replace_spaced_operator(result, "/", "divided by")

    result = re.sub(r"\\[A-Za-z]+", " ", result)
    result = result.replace("{", " ").replace("}", " ")
    result = re.sub(r"`([^`]*)`", r"\1", result)
    result = re.sub(r"[*_#]", "", result)
    result = re.sub(r"\s+", " ", result)
    return result.strip()
