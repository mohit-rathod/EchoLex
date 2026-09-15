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


def _replace_latex_fraction(
    text: str,
) -> str:

    pattern = re.compile(
        r"\\frac\s*"
        r"\{([^{}]+)\}"
        r"\s*"
        r"\{([^{}]+)\}"
    )

    for _ in range(5):

        updated = pattern.sub(
            lambda match: (
                f"{match.group(1)} "
                f"divided by "
                f"{match.group(2)}"
            ),
            text,
        )

        if updated == text:
            break

        text = updated

    return text


def _replace_superscripts(
    text: str,
) -> str:

    text = re.sub(
        r"([A-Za-z0-9]+)"
        r"\^\{?2\}?",
        r"\1 squared",
        text,
    )

    text = re.sub(
        r"([A-Za-z0-9]+)"
        r"\^\{?3\}?",
        r"\1 cubed",
        text,
    )

    text = re.sub(
        r"([A-Za-z0-9]+)"
        r"\^\{?([^{}\s]+)\}?",
        r"\1 to the power of \2",
        text,
    )

    return text


def prepare_text_for_speech(
    text: str,
) -> str:
    """
    Last-line-of-defense cleanup before TTS.

    The LLM should already produce spoken-friendly
    text. This function prevents raw LaTeX and common
    math syntax from being read literally.
    """

    if not text:
        return text

    result = text

    #
    # Remove display-math delimiters.
    #
    result = result.replace(
        "$$",
        " ",
    )

    result = result.replace(
        r"\[",
        " ",
    )

    result = result.replace(
        r"\]",
        " ",
    )

    result = result.replace(
        r"\(",
        " ",
    )

    result = result.replace(
        r"\)",
        " ",
    )

    result = result.replace(
        "$",
        " ",
    )

    #
    # Common LaTeX structures.
    #
    result = _replace_latex_fraction(
        result
    )

    result = re.sub(
        r"\\sqrt\s*\{([^{}]+)\}",
        r"the square root of \1",
        result,
    )

    result = _replace_superscripts(
        result
    )

    #
    # Greek symbols and operators.
    #
    for latex, spoken in (
        _LATEX_COMMANDS.items()
    ):
        result = result.replace(
            latex,
            f" {spoken} ",
        )

    #
    # Simple mathematical operators.
    #
    result = re.sub(
        r"\s*=\s*",
        " equals ",
        result,
    )

    result = re.sub(
        r"\s*\+\s*",
        " plus ",
        result,
    )

    result = re.sub(
        r"\s*-\s*",
        " minus ",
        result,
    )

    result = re.sub(
        r"\s*/\s*",
        " divided by ",
        result,
    )

    #
    # Remove remaining LaTeX command names rather
    # than making TTS pronounce backslashes.
    #
    result = re.sub(
        r"\\[A-Za-z]+",
        " ",
        result,
    )

    #
    # Remove braces commonly left by LaTeX.
    #
    result = result.replace(
        "{",
        " ",
    )

    result = result.replace(
        "}",
        " ",
    )

    #
    # Markdown cleanup.
    #
    result = re.sub(
        r"`([^`]*)`",
        r"\1",
        result,
    )

    result = re.sub(
        r"[*_#]",
        "",
        result,
    )

    result = re.sub(
        r"\s+",
        " ",
        result,
    )

    return result.strip()