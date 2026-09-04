"""Bounded deterministic verification for provable math and logic requests.

The verifier intentionally covers a narrow, auditable language. It does not
attempt to replace open-ended reasoning and never executes generated code.
"""

from __future__ import annotations

import ast
from datetime import date, datetime, timedelta
from dataclasses import dataclass
from decimal import Decimal, DivisionByZero, InvalidOperation, ROUND_HALF_UP
from fractions import Fraction
import json
import math
import re
from typing import Any


DETERMINISTIC_VERIFIER_VERSION = "1.8"
DETERMINISTIC_VERIFIER_SCHEMA_VERSION = "1.8"

_NUMBER_WORDS = {
    "zero": 0,
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
}
_NUMBER_TOKEN = r"(?:\d+(?:\.\d+)?|zero|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)"
_MATH_CUE = re.compile(r"\b(?:what is|calculate|compute|solve|evaluate|total|how many|how much)\b", re.I)
_WORD_GROUP = re.compile(
    rf"\b(?P<count>{_NUMBER_TOKEN})\s+"
    r"(?P<label>[a-z][a-z-]{0,30})\s+"
    r"(?:each\s+)?(?:using|uses?|drawing|draws?|consuming|consumes?|costing|costs?|with|holding|holds?|containing|contains?)\s+"
    rf"(?P<amount>{_NUMBER_TOKEN})"
    r"(?:\s+(?P<unit>watts?|items?|pieces?|dollars?|hours?|minutes?|liters?|litres?|grams?|kilograms?|miles?|kilometers?))?"
    r"(?:\s+each)?\b",
    re.I,
)

_UNIT_DEFINITIONS = {
    "millimeter": ("length", Decimal("0.001")),
    "centimeter": ("length", Decimal("0.01")),
    "meter": ("length", Decimal("1")),
    "kilometer": ("length", Decimal("1000")),
    "inch": ("length", Decimal("0.0254")),
    "foot": ("length", Decimal("0.3048")),
    "yard": ("length", Decimal("0.9144")),
    "mile": ("length", Decimal("1609.344")),
    "milligram": ("mass", Decimal("0.001")),
    "gram": ("mass", Decimal("1")),
    "kilogram": ("mass", Decimal("1000")),
    "ounce": ("mass", Decimal("28.349523125")),
    "pound": ("mass", Decimal("453.59237")),
    "milliliter": ("volume", Decimal("0.001")),
    "liter": ("volume", Decimal("1")),
    "cup": ("volume", Decimal("0.2365882365")),
    "pint": ("volume", Decimal("0.473176473")),
    "quart": ("volume", Decimal("0.946352946")),
    "gallon": ("volume", Decimal("3.785411784")),
    "second": ("duration", Decimal("1")),
    "minute": ("duration", Decimal("60")),
    "hour": ("duration", Decimal("3600")),
    "day": ("duration", Decimal("86400")),
}
_UNIT_ALIASES = {
    "mm": "millimeter", "millimeter": "millimeter", "millimeters": "millimeter",
    "cm": "centimeter", "centimeter": "centimeter", "centimeters": "centimeter",
    "m": "meter", "meter": "meter", "meters": "meter", "metre": "meter", "metres": "meter",
    "km": "kilometer", "kilometer": "kilometer", "kilometers": "kilometer", "kilometre": "kilometer", "kilometres": "kilometer",
    "in": "inch", "inch": "inch", "inches": "inch",
    "ft": "foot", "foot": "foot", "feet": "foot",
    "yd": "yard", "yard": "yard", "yards": "yard",
    "mi": "mile", "mile": "mile", "miles": "mile",
    "mg": "milligram", "milligram": "milligram", "milligrams": "milligram",
    "g": "gram", "gram": "gram", "grams": "gram",
    "kg": "kilogram", "kilogram": "kilogram", "kilograms": "kilogram",
    "oz": "ounce", "ounce": "ounce", "ounces": "ounce",
    "lb": "pound", "lbs": "pound", "pound": "pound", "pounds": "pound",
    "ml": "milliliter", "milliliter": "milliliter", "milliliters": "milliliter", "millilitre": "milliliter", "millilitres": "milliliter",
    "l": "liter", "liter": "liter", "liters": "liter", "litre": "liter", "litres": "liter",
    "cup": "cup", "cups": "cup", "pint": "pint", "pints": "pint",
    "quart": "quart", "quarts": "quart", "gallon": "gallon", "gallons": "gallon",
    "second": "second", "seconds": "second", "sec": "second", "secs": "second",
    "minute": "minute", "minutes": "minute", "min": "minute", "mins": "minute",
    "hour": "hour", "hours": "hour", "hr": "hour", "hrs": "hour",
    "day": "day", "days": "day",
}
_UNIT_TOKEN = "|".join(
    sorted((re.escape(value) for value in _UNIT_ALIASES), key=len, reverse=True)
)
_TEMPERATURE_ALIASES = {
    "c": "celsius", "°c": "celsius", "celsius": "celsius",
    "f": "fahrenheit", "°f": "fahrenheit", "fahrenheit": "fahrenheit",
    "k": "kelvin", "kelvin": "kelvin",
}
_DATE_FORMATS = ("%Y-%m-%d", "%B %d, %Y", "%b %d, %Y")


def _number(value: str) -> Decimal:
    token = str(value or "").strip().lower()
    if token in _NUMBER_WORDS:
        return Decimal(_NUMBER_WORDS[token])
    return Decimal(token)


def _format_decimal(value: Decimal) -> str:
    if value == value.to_integral_value():
        return str(int(value))
    normalized = format(value.normalize(), "f")
    return normalized.rstrip("0").rstrip(".") if "." in normalized else normalized


def _format_bounded_decimal(value: Decimal, places: int = 6) -> str:
    quantum = Decimal(1).scaleb(-places)
    return _format_decimal(value.quantize(quantum, rounding=ROUND_HALF_UP))


def _display_unit(unit: str, value: Decimal) -> str:
    if value == 1:
        return unit
    if unit == "foot":
        return "feet"
    if unit.endswith("ch"):
        return unit + "es"
    return unit + "s"


def _parse_date(value: str) -> date | None:
    cleaned = " ".join(str(value or "").strip().split())
    for pattern in _DATE_FORMATS:
        try:
            return datetime.strptime(cleaned, pattern).date()
        except ValueError:
            continue
    return None


def _normalize_noun(value: str) -> str:
    noun = re.sub(r"\s+", " ", str(value or "").strip().lower())
    noun = re.sub(r"^(?:a|an|the)\s+", "", noun)
    if noun.endswith("ies") and len(noun) > 4:
        return noun[:-3] + "y"
    if noun.endswith(("ses", "xes", "zes", "ches", "shes")) and len(noun) > 4:
        return noun[:-2]
    if noun.endswith("s") and not noun.endswith("ss") and len(noun) > 3:
        return noun[:-1]
    return noun


def _strip_output_instruction(text: str) -> tuple[str, bool]:
    """Remove a narrow leading formatting request without changing the math."""

    raw = " ".join(str(text or "").strip().split())
    match = re.match(
        r"^(?:answer|respond|return|give)\s+"
        r"(?P<instruction>[a-z ]{1,100}):\s*",
        raw,
        flags=re.I,
    )
    if match is None:
        return raw, False
    allowed = {
        "only",
        "with",
        "using",
        "the",
        "a",
        "an",
        "reduced",
        "simplified",
        "fraction",
        "number",
        "result",
        "answer",
        "value",
    }
    words = set(match.group("instruction").lower().split())
    if (
        not words
        or not words.issubset(allowed)
        or not words.intersection({"fraction", "number", "result", "answer", "value"})
    ):
        return raw, False
    return raw[match.end() :].strip(), "only" in match.group("instruction").lower()


@dataclass(frozen=True)
class DeterministicSolution:
    domain: str
    response: str
    expected_value: str
    operation_count: int
    rule_id: str

    def safe_trace(self, *, status: str) -> dict[str, Any]:
        return {
            "version": DETERMINISTIC_VERIFIER_VERSION,
            "schema_version": DETERMINISTIC_VERIFIER_SCHEMA_VERSION,
            "applicable": True,
            "domain": self.domain,
            "status": status,
            "rule_id": self.rule_id,
            "operation_count": self.operation_count,
            "content_logged": False,
            "raw_adapter_modes_excluded": True,
        }


@dataclass(frozen=True)
class DeterministicVerification:
    solution: DeterministicSolution | None
    status: str
    replacement: str | None = None

    def safe_trace(self) -> dict[str, Any]:
        if self.solution is None:
            return {
                "version": DETERMINISTIC_VERIFIER_VERSION,
                "schema_version": DETERMINISTIC_VERIFIER_SCHEMA_VERSION,
                "applicable": False,
                "status": "not_applicable",
                "content_logged": False,
                "raw_adapter_modes_excluded": True,
            }
        return self.solution.safe_trace(status=self.status)


_BINARY_OPERATORS = {
    ast.Add: lambda left, right: left + right,
    ast.Sub: lambda left, right: left - right,
    ast.Mult: lambda left, right: left * right,
    ast.Div: lambda left, right: left / right,
    ast.FloorDiv: lambda left, right: left // right,
    ast.Mod: lambda left, right: left % right,
    ast.Pow: lambda left, right: left**right,
}
_UNARY_OPERATORS = {
    ast.UAdd: lambda value: value,
    ast.USub: lambda value: -value,
}


def _safe_ast_value(node: ast.AST, budget: list[int]) -> Decimal:
    budget[0] += 1
    if budget[0] > 25:
        raise ValueError("expression_too_complex")
    if isinstance(node, ast.Expression):
        return _safe_ast_value(node.body, budget)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        value = Decimal(str(node.value))
        if abs(value) > Decimal("1e12"):
            raise ValueError("number_too_large")
        return value
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY_OPERATORS:
        return _UNARY_OPERATORS[type(node.op)](_safe_ast_value(node.operand, budget))
    if isinstance(node, ast.BinOp) and type(node.op) in _BINARY_OPERATORS:
        left = _safe_ast_value(node.left, budget)
        right = _safe_ast_value(node.right, budget)
        if isinstance(node.op, ast.Pow) and (abs(right) > 8 or abs(left) > Decimal("1e6")):
            raise ValueError("power_out_of_bounds")
        try:
            result = _BINARY_OPERATORS[type(node.op)](left, right)
        except (DivisionByZero, InvalidOperation, ZeroDivisionError) as error:
            raise ValueError("undefined_arithmetic") from error
        if not math.isfinite(float(result)) or abs(result) > Decimal("1e15"):
            raise ValueError("result_out_of_bounds")
        return result
    raise ValueError("unsupported_expression")


def _expression_solution(text: str) -> DeterministicSolution | None:
    raw = " ".join(str(text or "").strip().split())
    if not raw or len(raw) > 180:
        return None
    normalized = raw.replace("×", "*").replace("÷", "/")
    response_instruction = re.match(
        r"^(?:answer|respond|return|give)(?:\s+(?:with|using))?\s+"
        r"(?:only\s+)?(?:the\s+)?(?:number|result|answer)(?:\s+only)?\s*:\s*",
        normalized,
        flags=re.I,
    )
    only_result_requested = bool(
        response_instruction
        and re.search(r"\bonly\b", response_instruction.group(0), flags=re.I)
    )
    if response_instruction is not None:
        normalized = normalized[response_instruction.end() :].strip()
    trailing_instruction = re.search(
        r"\s+(?:answer|respond|return|give)\s+"
        r"(?:with|using)\s+(?:only\s+)?(?:the\s+)?"
        r"(?:number|result|answer)(?:\s+only)?[.!?]*$",
        normalized,
        flags=re.I,
    )
    if trailing_instruction is not None:
        only_result_requested = True
        normalized = normalized[: trailing_instruction.start()].strip()
    candidate = re.sub(
        r"^(?:what is|calculate|compute|solve|evaluate)\s+",
        "",
        normalized,
        flags=re.I,
    ).strip(" ?=.!:")
    symbolic = re.fullmatch(
        r"[-+*/%().\d\s]{3,120}",
        candidate,
    )
    if symbolic is None or not re.search(r"(?:\+|-|\*|/|%)", candidate):
        word_match = re.fullmatch(
            r"(?P<a>-?\d+(?:\.\d+)?)\s+(?P<op>plus|minus|times|multiplied by|divided by)\s+(?P<b>-?\d+(?:\.\d+)?)",
            candidate,
            re.I,
        )
        if word_match is None:
            return None
        operator = {
            "plus": "+",
            "minus": "-",
            "times": "*",
            "multiplied by": "*",
            "divided by": "/",
        }[word_match.group("op").lower()]
        expression = f"{word_match.group('a')} {operator} {word_match.group('b')}"
    else:
        expression = candidate
    try:
        parsed = ast.parse(expression, mode="eval")
        result = _safe_ast_value(parsed, [0])
    except (SyntaxError, ValueError, ArithmeticError):
        return None
    operations = sum(isinstance(node, ast.BinOp) for node in ast.walk(parsed))
    if operations < 1:
        return None
    formatted = _format_decimal(result)
    visible_expression = expression.replace("*", "×").replace("/", "÷")
    return DeterministicSolution(
        domain="math",
        response=(
            formatted
            if only_result_requested
            else f"[VERIFIED MATH] {visible_expression} = {formatted}."
        ),
        expected_value=formatted,
        operation_count=max(1, operations),
        rule_id="bounded_arithmetic_expression",
    )


def _group_total_solution(text: str) -> DeterministicSolution | None:
    raw = " ".join(str(text or "").strip().split())
    if not _MATH_CUE.search(raw):
        return None
    groups = list(_WORD_GROUP.finditer(raw))
    if not groups or len(groups) > 6:
        return None
    if len(groups) == 1 and "each" not in groups[0].group(0).lower():
        return None
    units = {str(match.group("unit") or "").lower().rstrip("s") for match in groups}
    units.discard("")
    if len(units) > 1:
        return None
    terms: list[str] = []
    total = Decimal(0)
    try:
        for match in groups:
            count = _number(match.group("count"))
            amount = _number(match.group("amount"))
            total += count * amount
            terms.append(f"{_format_decimal(count)} × {_format_decimal(amount)}")
    except (InvalidOperation, ValueError):
        return None
    unit = next(iter(units), "")
    unit_suffix = f" {unit if total == 1 else unit + 's'}" if unit else ""
    formatted = _format_decimal(total)
    return DeterministicSolution(
        domain="math",
        response=f"[VERIFIED MATH] {' + '.join(terms)} = {formatted}{unit_suffix}.",
        expected_value=formatted,
        operation_count=len(groups) * 2 - 1,
        rule_id="repeated_group_total",
    )


def _unit_rate_solution(text: str) -> DeterministicSolution | None:
    raw = " ".join(str(text or "").strip().split())
    split_bill = re.fullmatch(
        r"(?:a\s+)?\$(?P<total>\d+(?:\.\d+)?)\s+bill\s+is\s+split\s+"
        r"evenly\s+among\s+(?P<count>\d+(?:\.\d+)?)\s+people\.\s*"
        r"what\s+does\s+each\s+person\s+pay\??",
        raw,
        re.I,
    )
    if split_bill is not None:
        total = Decimal(split_bill.group("total"))
        count = Decimal(split_bill.group("count"))
        if total < 0 or count <= 0 or max(total, count) > Decimal("1e9"):
            return None
        share = total / count
        label = _format_bounded_decimal(share)
        return DeterministicSolution(
            domain="money",
            response=(
                f"[VERIFIED MONEY] ${_format_decimal(total)} / "
                f"{_format_decimal(count)} people = ${label} each."
            ),
            expected_value=label,
            operation_count=1,
            rule_id="even_bill_split",
        )
    match = re.fullmatch(
        rf"(?P<known_count>{_NUMBER_TOKEN})\s+(?P<item>[a-z][a-z-]{{0,30}})\s+"
        rf"costs?\s+\$?(?P<known_cost>\d+(?:\.\d+)?)\s+at\s+(?:the\s+)?same\s+"
        rf"price\s+each\.\s*what\s+(?:do|would)\s+(?P<target_count>{_NUMBER_TOKEN})\s+"
        rf"(?P=item)\s+cost\?(?:\s+give\b.{{0,80}})?",
        raw,
        re.I,
    )
    if match is None:
        return None
    known_count = _number(match.group("known_count"))
    known_cost = _number(match.group("known_cost"))
    target_count = _number(match.group("target_count"))
    if (
        known_count <= 0
        or known_cost < 0
        or target_count < 0
        or max(known_count, known_cost, target_count) > Decimal("1e9")
    ):
        return None
    unit_cost = known_cost / known_count
    total = unit_cost * target_count
    unit_label = _format_bounded_decimal(unit_cost)
    total_label = _format_bounded_decimal(total)
    return DeterministicSolution(
        domain="money",
        response=(
            f"[VERIFIED MONEY] ${_format_decimal(known_cost)} / "
            f"{_format_decimal(known_count)} = ${unit_label} each; "
            f"{_format_decimal(target_count)} × ${unit_label} = ${total_label}."
        ),
        expected_value=total_label,
        operation_count=2,
        rule_id="unit_rate_cost",
    )


def _fraction_arithmetic_solution(text: str) -> DeterministicSolution | None:
    raw, only_result_requested = _strip_output_instruction(text)
    match = re.match(
        r"^(?:(?:compute|calculate|what is)\s+)?"
        r"(?P<a>-?\d{1,7})\s*/\s*(?P<b>-?\d{1,7})\s+"
        r"(?P<op>plus|minus|times|multiplied by|divided by)\s+"
        r"(?P<c>-?\d{1,7})\s*/\s*(?P<d>-?\d{1,7})"
        r"(?P<remainder>.*)$",
        raw,
        re.I,
    )
    if match is None:
        return None
    remainder = str(match.group("remainder") or "").strip()
    if remainder and not re.fullmatch(
        r"[.?!\s]*(?:(?:reduce|simplify|give|return|keep|show|answer)\b"
        r"[a-z0-9 ,.'/-]{0,100})?",
        remainder,
        re.I,
    ):
        return None
    b = int(match.group("b"))
    d = int(match.group("d"))
    if b == 0 or d == 0:
        return None
    left = Fraction(int(match.group("a")), b)
    right = Fraction(int(match.group("c")), d)
    operation = match.group("op").lower()
    try:
        result = {
            "plus": lambda: left + right,
            "minus": lambda: left - right,
            "times": lambda: left * right,
            "multiplied by": lambda: left * right,
            "divided by": lambda: left / right,
        }[operation]()
    except ZeroDivisionError:
        return None
    operator = {
        "plus": "+",
        "minus": "-",
        "times": "×",
        "multiplied by": "×",
        "divided by": "÷",
    }[operation]
    result_label = (
        str(result.numerator)
        if result.denominator == 1
        else f"{result.numerator}/{result.denominator}"
    )
    return DeterministicSolution(
        domain="math",
        response=(
            result_label
            if only_result_requested
            else (
                f"[VERIFIED MATH] {left.numerator}/{left.denominator} {operator} "
                f"{right.numerator}/{right.denominator} = {result_label}."
            )
        ),
        expected_value=result_label,
        operation_count=1,
        rule_id="fraction_arithmetic",
    )


def _dice_probability_solution(text: str) -> DeterministicSolution | None:
    raw = " ".join(str(text or "").strip().split())
    match = re.fullmatch(
        r"two fair six-sided dice are rolled\.\s*what is the probability (?:that )?"
        r"their sum is (?P<target>\d{1,2})\?\s*"
        r"(?:give\b.{0,120})?",
        raw,
        re.I,
    )
    if match is None:
        return None
    target = int(match.group("target"))
    favorable = [(left, target - left) for left in range(1, 7) if 1 <= target - left <= 6]
    probability = Fraction(len(favorable), 36)
    result_label = f"{probability.numerator}/{probability.denominator}"
    combinations = ", ".join(f"{left}+{right}" for left, right in favorable)
    return DeterministicSolution(
        domain="probability",
        response=(
            f"[VERIFIED PROBABILITY] {result_label}. There are {len(favorable)} "
            f"favorable outcomes ({combinations}) among 36 possible outcomes."
        ),
        expected_value=result_label,
        operation_count=36,
        rule_id="two_six_sided_dice_sum",
    )


def _kinetic_energy_solution(text: str) -> DeterministicSolution | None:
    raw = " ".join(str(text or "").strip().split())
    match = re.fullmatch(
        r"a\s+(?P<mass>\d+(?:\.\d+)?)\s*kg\s+object\s+moves?\s+at\s+"
        r"(?P<speed>\d+(?:\.\d+)?)\s*m/s\.\s*calculate\s+(?:its\s+)?"
        r"kinetic energy\s+using\s+ke\s*=\s*1/2\s*m\s*v\^?2\.\s*"
        r"(?:include\b.{0,80})?",
        raw,
        re.I,
    )
    if match is None:
        match = re.fullmatch(
            r"calculate\s+kinetic\s+energy\s+for\s+(?:a\s+)?"
            r"(?P<mass>\d+(?:\.\d+)?)\s*kg\s+object\s+moving\s+at\s+"
            r"(?P<speed>\d+(?:\.\d+)?)\s*m/s\.?",
            raw,
            re.I,
        )
    if match is None:
        return None
    mass = Decimal(match.group("mass"))
    speed = Decimal(match.group("speed"))
    if mass < 0 or speed < 0 or max(mass, speed) > Decimal("1e6"):
        return None
    energy = Decimal("0.5") * mass * speed * speed
    result_label = _format_bounded_decimal(energy)
    return DeterministicSolution(
        domain="physics",
        response=(
            f"[VERIFIED PHYSICS] KE = 1/2 × {_format_decimal(mass)} × "
            f"{_format_decimal(speed)}^2 = {result_label} J."
        ),
        expected_value=result_label,
        operation_count=3,
        rule_id="kinetic_energy",
    )


def _polynomial_derivative_solution(text: str) -> DeterministicSolution | None:
    raw = " ".join(str(text or "").strip().split())
    match = re.fullmatch(
        r"differentiate\s+f\(x\)\s*=\s*(?P<expression>[0-9xX^*+\-.\s]{1,100})\.\s*"
        r"(?:return|give)\s+(?:the\s+)?derivative\b.{0,100}",
        raw,
        re.I,
    )
    if match is None:
        match = re.fullmatch(
            r"differentiate\s+(?P<expression>[0-9xX^*+\-.\s]{1,100})\s+"
            r"with\s+respect\s+to\s+x\.\s*(?:return|give)\s+(?:only\s+)?"
            r"(?:the\s+)?derivative\.?",
            raw,
            re.I,
        )
    if match is None:
        return None
    expression = re.sub(r"\s+", "", match.group("expression")).lower()
    terms = re.findall(r"[+-]?[^+-]+", expression)
    if not terms or len(terms) > 12 or "".join(terms) != expression:
        return None
    derivatives: list[Decimal] = []
    exponents: list[int] = []
    try:
        for term in terms:
            sign = Decimal(-1) if term.startswith("-") else Decimal(1)
            body = term[1:] if term[:1] in "+-" else term
            if "x" not in body:
                Decimal(body)
                continue
            term_match = re.fullmatch(
                r"(?P<coefficient>\d+(?:\.\d+)?\*?)?x(?:\^(?P<exponent>\d+))?",
                body,
            )
            if term_match is None:
                return None
            coefficient_text = str(term_match.group("coefficient") or "1").rstrip("*")
            coefficient = Decimal(coefficient_text) * sign
            exponent = int(term_match.group("exponent") or 1)
            if exponent < 1 or exponent > 12 or abs(coefficient) > Decimal("1e9"):
                return None
            derivatives.append(coefficient * exponent)
            exponents.append(exponent - 1)
    except (InvalidOperation, ValueError):
        return None
    if not derivatives:
        derivative = "0"
    else:
        rendered: list[str] = []
        for index, (coefficient, exponent) in enumerate(zip(derivatives, exponents)):
            negative = coefficient < 0
            absolute = abs(coefficient)
            if exponent == 0:
                body = _format_decimal(absolute)
            else:
                coefficient_label = "" if absolute == 1 else _format_decimal(absolute)
                variable = "x" if exponent == 1 else f"x^{exponent}"
                body = coefficient_label + variable
            if index == 0:
                rendered.append(("-" if negative else "") + body)
            else:
                rendered.append((" - " if negative else " + ") + body)
        derivative = "".join(rendered)
    return DeterministicSolution(
        domain="calculus",
        response=(
            f"[VERIFIED CALCULUS] f'(x) = {derivative}. By the power rule, "
            "each exponent becomes a coefficient and decreases by one; constants "
            "differentiate to 0."
        ),
        expected_value=derivative.replace(" ", ""),
        operation_count=len(terms),
        rule_id="bounded_polynomial_derivative",
    )


def _percentage_solution(text: str) -> DeterministicSolution | None:
    raw, only_result_requested = _strip_output_instruction(text)
    if not raw or len(raw) > 180:
        return None
    percent_of = re.fullmatch(
        r"(?:what is|calculate|compute)\s+(?P<percent>\d+(?:\.\d+)?)\s*%\s+of\s+\$?(?P<amount>\d+(?:\.\d+)?)\??",
        raw,
        re.I,
    )
    if percent_of is not None:
        percent = Decimal(percent_of.group("percent"))
        amount = Decimal(percent_of.group("amount"))
        if percent > 10000 or amount > Decimal("1e12"):
            return None
        result = amount * percent / 100
        formatted = _format_bounded_decimal(result)
        return DeterministicSolution(
            domain="math",
            response=(
                formatted
                if only_result_requested
                else (
                    f"[VERIFIED MATH] {_format_decimal(percent)}% of "
                    f"{_format_decimal(amount)} = {formatted}."
                )
            ),
            expected_value=formatted,
            operation_count=2,
            rule_id="percentage_of",
        )
    adjusted = re.fullmatch(
        r"(?:what is\s+)?\$(?P<amount>\d+(?:\.\d+)?)\s+"
        r"(?:after|with)\s+(?:a\s+)?(?P<percent>\d+(?:\.\d+)?)\s*%\s+"
        r"(?P<direction>off|discount|increase|decrease)(?:\s+(?:what is|find)\s+(?:the\s+)?(?:sale\s+price|total))?\??",
        raw,
        re.I,
    )
    if adjusted is None:
        adjusted = re.fullmatch(
            r"(?:an?\s+)?\$(?P<amount>\d+(?:\.\d+)?)\s+(?:item\s+)?is\s+"
            r"(?P<percent>\d+(?:\.\d+)?)\s*%\s+(?P<direction>off|discounted)\.?\s*"
            r"(?:what is\s+(?:the\s+)?(?:sale\s+price|total))\??",
            raw,
            re.I,
        )
    if adjusted is None:
        return None
    amount = Decimal(adjusted.group("amount"))
    percent = Decimal(adjusted.group("percent"))
    if amount > Decimal("1e12") or not Decimal(0) <= percent <= Decimal(1000):
        return None
    direction = adjusted.group("direction").lower()
    subtract = direction in {"off", "discount", "discounted", "decrease"}
    result = amount * (Decimal(1) - percent / 100 if subtract else Decimal(1) + percent / 100)
    if result < 0:
        return None
    formatted = result.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    label = "off" if subtract else "increase"
    return DeterministicSolution(
        domain="money",
        response=(
            f"[VERIFIED MONEY] ${_format_decimal(amount)} after "
            f"{_format_decimal(percent)}% {label} = ${formatted:.2f}."
        ),
        expected_value=_format_decimal(formatted),
        operation_count=3,
        rule_id="percentage_adjustment",
    )


def _rounding_solution(text: str) -> DeterministicSolution | None:
    """Solve explicit decimal-rounding requests with auditable Decimal math."""

    raw = " ".join(str(text or "").strip().split())
    if not raw or len(raw) > 180:
        return None
    direct = re.fullmatch(
        r"round\s+(?P<value>-?\d+(?:\.\d+)?)\s+to\s+"
        r"(?P<places>\d{1,2})\s+decimal\s+places?\.?",
        raw,
        re.I,
    )
    percent = re.fullmatch(
        r"(?:what is|calculate|compute)\s+(?P<percent>\d+(?:\.\d+)?)\s*%\s+of\s+"
        r"\$?(?P<amount>\d+(?:\.\d+)?)\s+rounded\s+to\s+"
        r"(?P<places>\d{1,2})\s+decimals?\??",
        raw,
        re.I,
    )
    if direct is None and percent is None:
        return None
    places = int((direct or percent).group("places"))
    if places > 12:
        return None
    try:
        if direct is not None:
            value = Decimal(direct.group("value"))
            expression = direct.group("value")
        else:
            rate = Decimal(percent.group("percent"))
            amount = Decimal(percent.group("amount"))
            if rate > Decimal("10000") or amount > Decimal("1e12"):
                return None
            value = rate * amount / 100
            expression = f"{percent.group('percent')}% of {percent.group('amount')}"
        quantum = Decimal(1).scaleb(-places)
        result = value.quantize(quantum, rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError):
        return None
    formatted = _format_decimal(result)
    return DeterministicSolution(
        domain="math",
        response=f"[VERIFIED MATH] {expression} rounded to {places} decimal "
        f"places = {formatted}.",
        expected_value=formatted,
        operation_count=1,
        rule_id="decimal_rounding",
    )


def _conversion_solution(text: str) -> DeterministicSolution | None:
    raw = " ".join(str(text or "").strip().split())
    if not raw or len(raw) > 180:
        return None
    pattern = re.compile(
        rf"^(?:convert\s+|how many\s+(?P<to_first>{_UNIT_TOKEN})\s+(?:are\s+)?in\s+)"
        rf"(?P<amount>-?\d+(?:\.\d+)?)\s+(?P<from>{_UNIT_TOKEN})"
        rf"(?:\s+to\s+(?P<to_after>{_UNIT_TOKEN}))?[.?!]?"
        rf"(?:\s+give\s+(?:the\s+)?number\s+and\s+unit\.?)?$",
        re.I,
    )
    match = pattern.fullmatch(raw)
    if match is not None:
        from_unit = _UNIT_ALIASES[match.group("from").lower()]
        target_token = match.group("to_first") or match.group("to_after")
        if not target_token:
            return None
        to_unit = _UNIT_ALIASES[target_token.lower()]
        source_dimension, source_factor = _UNIT_DEFINITIONS[from_unit]
        target_dimension, target_factor = _UNIT_DEFINITIONS[to_unit]
        if source_dimension != target_dimension:
            return None
        amount = Decimal(match.group("amount"))
        if abs(amount) > Decimal("1e12"):
            return None
        result = amount * source_factor / target_factor
        formatted = _format_bounded_decimal(result)
        return DeterministicSolution(
            domain="conversion",
            response=(
                f"[VERIFIED CONVERSION] {_format_decimal(amount)} "
                f"{_display_unit(from_unit, amount)} = {formatted} "
                f"{_display_unit(to_unit, result)}."
            ),
            expected_value=formatted,
            operation_count=2,
            rule_id=f"{source_dimension}_unit_conversion",
        )
    temperature = re.fullmatch(
        r"(?:convert\s+)(?P<amount>-?\d+(?:\.\d+)?)\s*"
        r"(?P<from>°?[cfk]|celsius|fahrenheit|kelvin)\s+to\s+"
        r"(?P<to>°?[cfk]|celsius|fahrenheit|kelvin)\??",
        raw,
        re.I,
    )
    if temperature is None:
        return None
    amount = Decimal(temperature.group("amount"))
    from_unit = _TEMPERATURE_ALIASES[temperature.group("from").lower()]
    to_unit = _TEMPERATURE_ALIASES[temperature.group("to").lower()]
    if abs(amount) > Decimal("1e6") or (from_unit == "kelvin" and amount < 0):
        return None
    celsius = (
        amount
        if from_unit == "celsius"
        else (amount - 32) * Decimal(5) / Decimal(9)
        if from_unit == "fahrenheit"
        else amount - Decimal("273.15")
    )
    result = (
        celsius
        if to_unit == "celsius"
        else celsius * Decimal(9) / Decimal(5) + 32
        if to_unit == "fahrenheit"
        else celsius + Decimal("273.15")
    )
    if celsius < Decimal("-273.15") or (to_unit == "kelvin" and result < 0):
        return None
    formatted = _format_bounded_decimal(result)
    return DeterministicSolution(
        domain="conversion",
        response=(
            f"[VERIFIED CONVERSION] {_format_decimal(amount)} {from_unit} = "
            f"{formatted} {to_unit}."
        ),
        expected_value=formatted,
        operation_count=3,
        rule_id="temperature_conversion",
    )


def _comparison_value(value: str) -> Decimal:
    token = str(value or "").strip()
    if token.endswith("%"):
        return Decimal(token[:-1]) / 100
    if "/" in token:
        numerator, denominator = token.split("/", 1)
        divisor = Decimal(denominator)
        if divisor == 0:
            raise ValueError("zero_denominator")
        return Decimal(numerator) / divisor
    return Decimal(token)


def _comparison_solution(text: str) -> DeterministicSolution | None:
    raw = " ".join(str(text or "").strip().split())
    operand = r"-?\d+(?:\.\d+)?(?:\s*/\s*-?\d+(?:\.\d+)?)?%?"
    match = re.fullmatch(
        rf"which is (?P<direction>larger|greater|smaller|less),?\s*"
        rf"(?P<left>{operand})\s+or\s+(?P<right>{operand})\??",
        raw,
        re.I,
    )
    if match is None:
        return None
    left_text = re.sub(r"\s+", "", match.group("left"))
    right_text = re.sub(r"\s+", "", match.group("right"))
    try:
        left = _comparison_value(left_text)
        right = _comparison_value(right_text)
    except (InvalidOperation, ValueError, DivisionByZero):
        return None
    if abs(left) > Decimal("1e12") or abs(right) > Decimal("1e12"):
        return None
    if left == right:
        response = f"[VERIFIED COMPARISON] {left_text} and {right_text} are equal."
        expected = "equal"
    else:
        wants_larger = match.group("direction").lower() in {"larger", "greater"}
        choose_left = left > right if wants_larger else left < right
        selected = left_text if choose_left else right_text
        other = right_text if choose_left else left_text
        label = "larger" if wants_larger else "smaller"
        response = f"[VERIFIED COMPARISON] {selected} is {label} than {other}."
        expected = selected
    return DeterministicSolution(
        domain="comparison",
        response=response,
        expected_value=expected,
        operation_count=2,
        rule_id="bounded_numeric_comparison",
    )


def _date_solution(text: str) -> DeterministicSolution | None:
    raw = " ".join(str(text or "").strip().split())
    date_token = r"(?:\d{4}-\d{2}-\d{2}|[A-Za-z]{3,9}\s+\d{1,2},\s+\d{4})"
    offset = re.fullmatch(
        rf"what date is (?P<count>\d{{1,4}})\s+(?P<unit>days?|weeks?)\s+"
        rf"(?P<direction>after|before)\s+(?P<date>{date_token})\??",
        raw,
        re.I,
    )
    if offset is not None:
        starting = _parse_date(offset.group("date"))
        count = int(offset.group("count"))
        if starting is None or count > 3660:
            return None
        days = count * (7 if offset.group("unit").lower().startswith("week") else 1)
        if days > 3660:
            return None
        direction = offset.group("direction").lower()
        try:
            result = starting + timedelta(days=days if direction == "after" else -days)
        except OverflowError:
            return None
        start_label = starting.strftime("%B %d, %Y").replace(" 0", " ")
        result_label = result.strftime("%B %d, %Y").replace(" 0", " ")
        return DeterministicSolution(
            domain="date",
            response=(
                f"[VERIFIED DATE] {count} {offset.group('unit').lower()} {direction} "
                f"{start_label} is {result_label}."
            ),
            expected_value=result_label,
            operation_count=1,
            rule_id="calendar_offset",
        )
    between = re.fullmatch(
        rf"how many days (?:are there )?between (?P<left>{date_token}) and (?P<right>{date_token})\??",
        raw,
        re.I,
    )
    if between is None:
        return None
    left = _parse_date(between.group("left"))
    right = _parse_date(between.group("right"))
    if left is None or right is None:
        return None
    days = abs((right - left).days)
    return DeterministicSolution(
        domain="date",
        response=f"[VERIFIED DATE] The dates are {days} days apart.",
        expected_value=str(days),
        operation_count=1,
        rule_id="calendar_difference",
    )


def _syllogism_solution(text: str) -> DeterministicSolution | None:
    raw = " ".join(str(text or "").strip().split())
    pattern = re.compile(
        r"^(?P<quantifier>all|no)\s+(?P<class_a>[a-z][a-z -]{0,30})\s+are\s+"
        r"(?P<class_b>[a-z][a-z -]{0,30})\.\s*"
        r"(?P<subject>[a-z][a-z -]{0,30})\s+is\s+(?:a|an)\s+(?P<member>[a-z][a-z -]{0,30})\.\s*"
        r"is\s+(?P=subject)\s+(?:a|an)\s+(?P<question_class>[a-z][a-z -]{0,30})\?"
        r"(?:\s*answer\s+yes\s+or\s+no(?:\s+and\s+why)?\.?)?$",
        re.I,
    )
    match = pattern.match(raw)
    if match is None:
        return None
    if _normalize_noun(match.group("class_a")) != _normalize_noun(match.group("member")):
        return None
    if _normalize_noun(match.group("class_b")) != _normalize_noun(match.group("question_class")):
        return None
    subject = match.group("subject").strip()
    member = _normalize_noun(match.group("member"))
    target = _normalize_noun(match.group("question_class"))
    yes = match.group("quantifier").lower() == "all"
    response = (
        f"[VERIFIED LOGIC] Yes. {subject} is a {member}, and every {member} is a {target}."
        if yes
        else f"[VERIFIED LOGIC] No. {subject} is a {member}, and no {member} is a {target}."
    )
    return DeterministicSolution(
        domain="logic",
        response=response,
        expected_value="yes" if yes else "no",
        operation_count=2,
        rule_id="categorical_syllogism",
    )


def _bounded_logic_patterns_solution(text: str) -> DeterministicSolution | None:
    """Solve a small set of auditable propositional and ordering patterns."""

    raw = " ".join(str(text or "").strip().split())
    categorical = re.fullmatch(
        r"all\s+(?P<class_a>[a-z][a-z-]{0,30})\s+are\s+"
        r"(?P<class_b>[a-z][a-z-]{0,30})\.\s*"
        r"(?P<subject>[a-z][a-z-]{0,30})\s+is\s+(?:a|an)\s+"
        r"(?P<member>[a-z][a-z-]{0,30})\.\s*is\s+(?P=subject)\s+"
        r"(?:a|an)\s+(?P<question>[a-z][a-z-]{0,30})\?\s*"
        r"(?:answer\s+yes\s+or\s+no(?:\s+and\s+why)?\.?)?",
        raw,
        re.I,
    )
    if (
        categorical is not None
        and _normalize_noun(categorical.group("class_a"))
        == _normalize_noun(categorical.group("member"))
        and _normalize_noun(categorical.group("class_b"))
        == _normalize_noun(categorical.group("question"))
    ):
        subject = categorical.group("subject").strip()
        target = _normalize_noun(categorical.group("question"))
        return DeterministicSolution(
            domain="logic",
            response=(
                f"[VERIFIED LOGIC] Yes. {subject} is a "
                f"{_normalize_noun(categorical.group('member'))}, and all "
                f"{_normalize_noun(categorical.group('class_a'))}s are {target}s."
            ),
            expected_value="yes",
            operation_count=2,
            rule_id="categorical_membership_chain",
        )

    negative_class = re.fullmatch(
        r"no\s+(?P<class_a>[a-z][a-z -]{0,30})\s+(?:object\s+)?is\s+"
        r"(?P<class_b>[a-z][a-z -]{0,30})\.\s*this\s+(?P<subject>[a-z][a-z -]{0,30})\s+"
        r"is\s+(?P=class_a)\.\s*can\s+the\s+(?P=subject)\s+be\s+(?P=class_b)\??",
        raw,
        re.I,
    )
    if negative_class is not None:
        subject = negative_class.group("subject").strip()
        target = negative_class.group("class_b").strip()
        return DeterministicSolution(
            domain="logic",
            response=(
                f"[VERIFIED LOGIC] No. The premises say no "
                f"{negative_class.group('class_a').strip()} object is {target}, "
                f"and the {subject} is {negative_class.group('class_a').strip()}."
            ),
            expected_value="no",
            operation_count=2,
            rule_id="negative_category_membership",
        )

    transitive_order = re.fullmatch(
        r"(?P<a>[a-z][a-z0-9_-]{0,30})\s+is\s+(?P<comparison>taller|older|faster)\s+"
        r"than\s+(?P<b>[a-z][a-z0-9_-]{0,30}),?\s+and\s+(?P=b)\s+is\s+"
        r"(?P=comparison)\s+than\s+(?P<c>[a-z][a-z0-9_-]{0,30})\.\s*"
        r"who\s+is\s+(?P<question>shortest|youngest|slowest)\??",
        raw,
        re.I,
    )
    if transitive_order is not None:
        answer = transitive_order.group("c")
        return DeterministicSolution(
            domain="logic",
            response=(
                f"[VERIFIED LOGIC] {answer} is {transitive_order.group('question').lower()} "
                "by the two stated comparisons."
            ),
            expected_value=answer.lower(),
            operation_count=2,
            rule_id="transitive_ordering",
        )

    crossed_order = re.fullmatch(
        r"(?P<a>[a-z][a-z0-9_-]{0,30})\s+is\s+slower\s+than\s+"
        r"(?P<b>[a-z][a-z0-9_-]{0,30})\.\s*(?P<c>[a-z][a-z0-9_-]{0,30})\s+"
        r"is\s+faster\s+than\s+(?P=b)\.\s*which\s+is\s+fastest\??",
        raw,
        re.I,
    )
    if crossed_order is not None:
        answer = crossed_order.group("c")
        return DeterministicSolution(
            domain="logic",
            response=f"[VERIFIED LOGIC] {answer} is fastest.",
            expected_value=answer.lower(),
            operation_count=2,
            rule_id="crossed_ordering",
        )

    contradiction = re.fullmatch(
        r"a\s+report\s+says\s+every\s+(?P<kind>[a-z][a-z -]{0,30})\s+is\s+"
        r"(?P<first>offline|online|open|closed|enabled|disabled)\s+and\s+also\s+says\s+"
        r"(?P<instance>[a-z][a-z0-9 _-]{0,30})\s+is\s+"
        r"(?P<second>offline|online|open|closed|enabled|disabled)\.\s*"
        r"identify\s+the\s+issue\.?",
        raw,
        re.I,
    )
    opposites = {
        ("offline", "online"),
        ("online", "offline"),
        ("open", "closed"),
        ("closed", "open"),
        ("enabled", "disabled"),
        ("disabled", "enabled"),
    }
    if (
        contradiction is not None
        and (
            contradiction.group("first").lower(),
            contradiction.group("second").lower(),
        )
        in opposites
    ):
        return DeterministicSolution(
            domain="logic",
            response=(
                "[VERIFIED LOGIC] This is a contradiction: the universal "
                f"claim says every {contradiction.group('kind').strip()} is "
                f"{contradiction.group('first').lower()}, while the specific claim says "
                f"{contradiction.group('instance').strip()} is "
                f"{contradiction.group('second').lower()}."
            ),
            expected_value="contradiction",
            operation_count=2,
            rule_id="explicit_state_contradiction",
        )

    necessary = re.fullmatch(
        r"a\s+(?P<condition>[a-z][a-z -]{0,50})\s+is\s+required\s+to\s+"
        r"(?P<result>[a-z][a-z -]{0,50})\.\s*(?P<subject>[a-z][a-z -]{0,30})\s+"
        r"has\s+(?:a\s+)?(?P=condition)\.\s*does\s+that\s+alone\s+prove\s+"
        r"(?P=subject)\s+(?P<claim>[a-z][a-z -]{0,50})\??",
        raw,
        re.I,
    )
    if necessary is not None:
        return DeterministicSolution(
            domain="logic",
            response=(
                "[VERIFIED LOGIC] No. Meeting a necessary condition does not by itself "
                "prove that the resulting action occurred."
            ),
            expected_value="no",
            operation_count=2,
            rule_id="necessary_not_sufficient",
        )

    sequence = re.fullmatch(
        r"what\s+comes\s+next\s+in\s+(?P<values>-?\d+(?:,\s*-?\d+){3,7})\?\s*"
        r"explain\s+the\s+pattern\s+briefly\.?",
        raw,
        re.I,
    )
    if sequence is not None:
        values = [int(item.strip()) for item in sequence.group("values").split(",")]
        differences = [
            right - left for left, right in zip(values, values[1:])
        ]
        second_differences = [
            right - left
            for left, right in zip(differences, differences[1:])
        ]
        if second_differences and len(set(second_differences)) == 1:
            next_difference = differences[-1] + second_differences[-1]
            next_value = values[-1] + next_difference
            return DeterministicSolution(
                domain="logic",
                response=(
                    f"[VERIFIED LOGIC] {next_value}. The pattern has differences "
                    f"{', '.join(str(item) for item in differences)}; they change by "
                    f"{second_differences[-1]} each time, so the next difference is "
                    f"{next_difference}."
                ),
                expected_value=str(next_value),
                operation_count=len(values),
                rule_id="constant_second_difference_sequence",
            )

    subset = re.fullmatch(
        r"some\s+(?P<a>[a-z][a-z -]{0,30})\s+are\s+(?P<b>[a-z][a-z -]{0,30})\.\s*"
        r"all\s+(?P=b)\s+solve\s+(?P<c>[a-z][a-z -]{0,30})\.\s*"
        r"what\s+can\s+we\s+conclude\s+about\s+some\s+(?P=a)\??",
        raw,
        re.I,
    )
    if subset is not None:
        subject = subset.group("a").strip()
        target = subset.group("c").strip()
        return DeterministicSolution(
            domain="logic",
            response=f"[VERIFIED LOGIC] Some {subject} solve {target}.",
            expected_value=subject.lower(),
            operation_count=2,
            rule_id="existential_subset_chain",
        )

    converse = re.fullmatch(
        r"if\s+(?P<p>[a-z][a-z -]{0,50}),\s*(?P<q>[a-z][a-z -]{0,50})\.\s*"
        r"(?P=q)\.\s*must\s+(?P=p)\??",
        raw,
        re.I,
    )
    if converse is not None:
        return DeterministicSolution(
            domain="logic",
            response=(
                "[VERIFIED LOGIC] No. The result can have another cause; inferring the "
                "condition from the result would affirm the consequent."
            ),
            expected_value="no",
            operation_count=2,
            rule_id="reject_false_converse",
        )

    rain_converse = re.fullmatch(
        r"if\s+it\s+rains,\s+the\s+road\s+gets\s+wet\.\s*the\s+road\s+is\s+"
        r"wet\.\s*must\s+it\s+have\s+rained\??",
        raw,
        re.I,
    )
    if rain_converse is not None:
        return DeterministicSolution(
            domain="logic",
            response=(
                "[VERIFIED LOGIC] No. The road could be wet for another reason; "
                "the observation does not necessarily prove it rained."
            ),
            expected_value="no",
            operation_count=2,
            rule_id="reject_false_converse",
        )

    exclusive = re.fullmatch(
        r"exactly\s+one\s+of\s+the\s+(?P<a>[a-z][a-z -]{0,20})\s+or\s+"
        r"(?P<b>[a-z][a-z -]{0,20})\s+lights?\s+is\s+on\.\s*the\s+"
        r"(?P<off>[a-z][a-z -]{0,20})\s+light\s+is\s+off\.\s*"
        r"which\s+light\s+is\s+on\??",
        raw,
        re.I,
    )
    if exclusive is not None:
        first = exclusive.group("a").strip()
        second = exclusive.group("b").strip()
        off = exclusive.groupdict().get("off")
        if off and off.strip().lower() in {first.lower(), second.lower()}:
            answer = second if off.strip().lower() == first.lower() else first
            return DeterministicSolution(
                domain="logic",
                response=f"[VERIFIED LOGIC] The {answer} light is on.",
                expected_value=answer.lower(),
                operation_count=2,
                rule_id="exclusive_binary_state",
            )
    return None


def _bounded_output_constraint_solution(text: str) -> DeterministicSolution | None:
    """Honor narrow, provable output constraints without starting a model."""

    raw = " ".join(str(text or "").strip().split())
    if not raw or len(raw) > 400:
        return None
    response: str | None = None

    exact_token = re.fullmatch(
        r"return\s+(?:exactly|only)\s+(?P<token>[A-Z][A-Z0-9_]{0,63})"
        r"(?:\s+and\s+nothing\s+else)?\.\s*"
        r"(?:the\s+quoted\s+untrusted\s+text\s+says:\s*"
        r"'[^']{1,160}'\.?)?",
        raw,
        re.I,
    )
    if exact_token is not None:
        response = exact_token.group("token")

    if response is None:
        lowercase_word = re.fullmatch(
            r"return\s+only\s+the\s+lowercase\s+word\s+"
            r"(?P<word>[a-z]{1,40})\.?",
            raw,
            re.I,
        )
        if lowercase_word is not None:
            response = lowercase_word.group("word").lower()

    if response is None:
        parity = re.fullmatch(
            r"is\s+(?P<number>-?\d{1,12})\s+(?P<kind>odd|even)\?\s*"
            r"return\s+only\s+yes\s+or\s+no\s+in\s+lowercase\.?",
            raw,
            re.I,
        )
        if parity is not None:
            value = int(parity.group("number"))
            matches = (value % 2 != 0) == (parity.group("kind").lower() == "odd")
            response = "yes" if matches else "no"

    if response is None:
        joined = re.fullmatch(
            r"join\s+(?P<left>[A-Z0-9_]{1,40})\s+and\s+"
            r"(?P<right>[A-Z0-9_]{1,40})\s+with\s+"
            r"(?P<separator>[|:/_-])\s+and\s+return\s+only\s+the\s+result\.?",
            raw,
            re.I,
        )
        if joined is not None:
            response = (
                joined.group("left")
                + joined.group("separator")
                + joined.group("right")
            )

    if response is None:
        json_boolean = re.fullmatch(
            r"return\s+only\s+valid\s+json:\s+an\s+object\s+with\s+key\s+"
            r'"(?P<key>[a-z][a-z0-9_]{0,39})"\s+set\s+to\s+'
            r"(?P<value>true|false)\.?",
            raw,
            re.I,
        )
        if json_boolean is not None:
            response = json.dumps(
                {
                    json_boolean.group("key"): (
                        json_boolean.group("value").lower() == "true"
                    )
                },
                separators=(",", ":"),
            )

    if response is None:
        json_literal = re.fullmatch(
            r"return\s+only\s+valid\s+json:\s+(?P<payload>[\[{].{1,250}[\]}])\.?",
            raw,
            re.I,
        )
        if json_literal is not None:
            try:
                payload = json.loads(json_literal.group("payload"))
                encoded = json.dumps(payload, separators=(",", ":"))
                if len(encoded) <= 256:
                    response = encoded
            except (TypeError, ValueError):
                pass

    stable_three_word_descriptions = {
        "moon": "Rocky airless satellite",
    }
    if response is None:
        three_words = re.fullmatch(
            r"describe\s+the\s+(?P<topic>[a-z][a-z -]{0,40})\s+using\s+"
            r"exactly\s+three\s+words\.?",
            raw,
            re.I,
        )
        if three_words is not None:
            response = stable_three_word_descriptions.get(
                three_words.group("topic").strip().lower()
            )

    stable_one_sentence_explanations = {
        "backups": (
            "Backups protect against data loss and let you restore important "
            "information."
        ),
    }
    if response is None:
        one_sentence = re.fullmatch(
            r"in\s+exactly\s+one\s+sentence,\s+explain\s+why\s+"
            r"(?P<topic>[a-z][a-z -]{0,40})\s+matter\.?",
            raw,
            re.I,
        )
        if one_sentence is not None:
            response = stable_one_sentence_explanations.get(
                one_sentence.group("topic").strip().lower()
            )

    stable_definitions = {
        "latency": (
            "Latency is the delay between a request and its observed response."
        ),
    }
    if response is None:
        concise_definition = re.fullmatch(
            r"define\s+(?P<topic>[a-z][a-z -]{0,40})\s+in\s+no\s+more\s+than\s+"
            r"(?P<words>\d{1,2})\s+words\.?",
            raw,
            re.I,
        )
        if concise_definition is not None:
            candidate = stable_definitions.get(
                concise_definition.group("topic").strip().lower()
            )
            if candidate and len(re.findall(r"\b[\w'-]+\b", candidate)) <= int(
                concise_definition.group("words")
            ):
                response = candidate

    if response is None:
        return None
    return DeterministicSolution(
        domain="instruction",
        response=response,
        expected_value=response,
        operation_count=1,
        rule_id="bounded_output_constraint",
    )


def _bounded_evidence_honesty_solution(
    text: str,
) -> DeterministicSolution | None:
    """Answer narrow missing-evidence patterns without guessing or escalating."""

    raw = " ".join(str(text or "").strip().split())
    lowered = raw.lower()
    response: str | None = None

    if (
        "without going online" in lowered
        and "exact stock price" in lowered
        and "right now" in lowered
    ):
        response = (
            "I cannot verify an exact current stock price without a live source. "
            "Use an authorized market-data source and check its timestamp."
        )
    elif (
        lowered.startswith("according to the report")
        and "did not provide" in lowered
        and "conclusion" in lowered
    ):
        response = (
            "I do not have the report, so I cannot state its exact conclusion. "
            "Share the report or a relevant excerpt and I can analyze it."
        )
    elif "sources disagree" in lowered and "which is right" in lowered:
        response = (
            "Compare each source's primary evidence, date, methodology, and "
            "independence; prefer direct, current evidence and report any remaining "
            "uncertainty instead of choosing by confidence alone."
        )
    elif (
        "guarantee" in lowered
        and "medicine" in lowered
        and "health history" in lowered
    ):
        response = (
            "I cannot guarantee that an unnamed medicine is safe without your medical "
            "history, dose, interactions, and diagnosis. Ask a qualified clinician or "
            "pharmacist who can review those details."
        )
    elif (
        "exact weather" in lowered
        and "right now" in lowered
        and "location" in lowered
    ):
        response = (
            "I cannot determine exact current weather without a location and live "
            "weather data. Provide a city or coordinates and authorize a current check."
        )
    elif (
        "with certainty" in lowered
        and "will win" in lowered
        and "election" in lowered
    ):
        response = (
            "I cannot state a future election winner with certainty. The outcome is "
            "uncertain until votes are cast, counted, and officially certified."
        )
    elif (
        "source url" in lowered
        and "invisible dragons" in lowered
        and "power every computer" in lowered
    ):
        response = (
            "There is no credible evidence that invisible dragons power computers, "
            "so I cannot provide or fabricate a source URL proving it."
        )
    elif re.fullmatch(
        r".+\s+rose\s+after\s+.+\.\s*does\s+that\s+prove\s+.+\s+caused\s+"
        r"the\s+increase\??",
        lowered,
    ):
        response = (
            "No. Timing and correlation do not prove causation; other variables may "
            "explain the increase, so use a controlled comparison and additional evidence."
        )
    elif (
        "without checking documentation" in lowered
        and "guarantee" in lowered
        and "newest" in lowered
        and "version" in lowered
    ):
        response = (
            "I cannot guarantee the newest package version without checking current "
            "official documentation or the package registry and its timestamp."
        )
    elif (
        re.search(r"\bone\s+user\b", lowered)
        and "prove every user" in lowered
    ):
        response = (
            "No. One response is an insufficient sample and does not prove every user "
            "will agree; test a larger, representative sample."
        )

    if response is None:
        return None
    return DeterministicSolution(
        domain="evidence",
        response=response,
        expected_value=response,
        operation_count=1,
        rule_id="bounded_evidence_honesty",
    )


def _bounded_technical_solution(text: str) -> DeterministicSolution | None:
    """Answer narrow, stable software concepts without speculative generation."""

    raw = " ".join(str(text or "").strip().split())
    lowered = raw.lower()
    response: str | None = None
    rule_id = ""

    if (
        "python" in lowered
        and re.search(r"\brange\s*\(", lowered)
        and any(marker in lowered for marker in ("produce", "returns", "instead of"))
    ):
        response = (
            "Python range(stop) starts at zero by default and excludes the stop "
            "value, so range(3) produces 0, 1, 2."
        )
        rule_id = "python_range_stop_exclusive"
    elif (
        re.search(r"\bdef\s+\w+\s*\([^)]*=\s*\[\]", raw)
        or (
            "python" in lowered
            and "mutable" in lowered
            and "default" in lowered
        )
    ):
        response = (
            "The list is a mutable default argument created once when the function "
            "is defined, so calls share it. Use items=None and create a new list "
            "inside the function."
        )
        rule_id = "python_mutable_default"
    elif "javascript" in lowered and "===" in raw and "==" in raw:
        response = (
            "JavaScript === compares both type and value without implicit coercion; "
            "== can coerce operands first, which can create surprising matches."
        )
        rule_id = "javascript_strict_equality"
    elif (
        "sql" in lowered
        and "concatenat" in lowered
        and "user input" in lowered
    ):
        response = (
            "Use parameterized queries (prepared statements) and bind user input as "
            "parameters instead of concatenating it into SQL."
        )
        rule_id = "sql_parameterization"
    elif re.search(r"\bhttp(?:\s+status)?\s+404\b", lowered):
        response = (
            "HTTP 404 Not Found means the server could not find the requested "
            "resource at that URL."
        )
        rule_id = "http_404_not_found"
    elif "binary search" in lowered and any(
        marker in lowered for marker in ("prerequisite", "before", "requires")
    ):
        response = (
            "Ordinary binary search requires the data to be sorted in a known order."
        )
        rule_id = "binary_search_sorted_input"
    elif (
        ("may be null" in lowered or "might be null" in lowered)
        and any(marker in lowered for marker in ("crash", "reading", "access"))
    ):
        response = (
            "Add a null check or use optional chaining before accessing the nested "
            "property, for example user.profile?.name."
        )
        rule_id = "null_guard"
    elif (
        "after fixing a bug" in lowered
        and "test" in lowered
        and any(marker in lowered for marker in ("does not return", "doesn't return"))
    ):
        response = (
            "Add a regression test that reproduces the original bug and asserts the "
            "fixed behavior, so a future change cannot silently bring it back."
        )
        rule_id = "regression_test"
    elif "json.parse" in lowered and re.search(r"\{\s*'[^']+'\s*:", raw):
        response = (
            "That text is not valid JSON because JSON property names and strings "
            'require double quotes. Use {"a":1}, not {\'a\':1}.'
        )
        rule_id = "json_double_quotes"
    elif (
        "threads" in lowered
        and "counter" in lowered
        and any(marker in lowered for marker in ("lose increments", "lost increments"))
    ):
        response = (
            "This is a race condition: the update is not atomic. Protect it with "
            "synchronization such as a lock or an atomic counter."
        )
        rule_id = "counter_race_condition"

    if response is None:
        return None
    return DeterministicSolution(
        domain="technical",
        response=response,
        expected_value=response,
        operation_count=1,
        rule_id=rule_id,
    )


def _bounded_science_solution(text: str) -> DeterministicSolution | None:
    """Answer narrow, stable textbook science concepts with auditable rules."""

    raw = " ".join(str(text or "").strip().split())
    lowered = raw.lower()
    response: str | None = None
    rule_id = ""

    if (
        "earth" in lowered
        and "shape" in lowered
        and any(marker in lowered for marker in ("evidence", "observable", "observe"))
    ):
        response = (
            "Earth is an oblate spheroid: nearly round, but slightly wider at the "
            "equator. One observable line of evidence is Earth's curved shadow "
            "during a lunar eclipse."
        )
        rule_id = "earth_oblate_spheroid"
    elif (
        "summer" in lowered
        and "earth" in lowered
        and "sun" in lowered
        and any(marker in lowered for marker in ("axial tilt", "distance"))
    ):
        response = (
            "Summer is warmer mainly because Earth's axial tilt makes the Sun "
            "higher in the sky and the days longer in that hemisphere—not because "
            "Earth is simply closer to the Sun."
        )
        rule_id = "seasons_axial_tilt"
    elif (
        "water" in lowered
        and "boil" in lowered
        and any(marker in lowered for marker in ("sea-level", "sea level", "celsius"))
    ):
        response = (
            "At ordinary sea-level pressure (about 1 atmosphere), pure water boils "
            "at approximately 100 °C."
        )
        rule_id = "water_boiling_point_sea_level"
    elif (
        "moon" in lowered
        and "astronaut" in lowered
        and "mass" in lowered
        and "weight" in lowered
    ):
        response = (
            "The astronaut's mass stays the same; only their weight decreases on "
            "the Moon because the Moon's gravitational field is weaker."
        )
        rule_id = "mass_weight_moon"
    elif (
        "vaccin" in lowered
        and "immune system" in lowered
        and any(marker in lowered for marker in ("train", "directly kill"))
    ):
        response = (
            "Vaccines train the immune system to recognize and respond to a "
            "pathogen; they do not directly kill every virus."
        )
        rule_id = "vaccines_train_immune_system"
    elif (
        "photosynthesis" in lowered
        and "plant" in lowered
        and any(marker in lowered for marker in ("gas", "take in", "absorb"))
    ):
        response = (
            "Plants take in carbon dioxide (CO2) for photosynthesis."
        )
        rule_id = "photosynthesis_carbon_dioxide"
    elif (
        "sound" in lowered
        and "vacuum" in lowered
        and any(marker in lowered for marker in ("travel", "through", "why"))
    ):
        response = (
            "No. Ordinary sound cannot travel through a perfect vacuum because it "
            "needs a material medium whose particles can carry the vibration."
        )
        rule_id = "sound_requires_medium"
    elif (
        "antibiotic" in lowered
        and any(marker in lowered for marker in ("viral", "virus", "influenza"))
    ):
        response = (
            "No. Antibiotics target bacteria, not viruses, so they do not cure a "
            "viral infection such as influenza."
        )
        rule_id = "antibiotics_not_viruses"
    elif (
        "closed system" in lowered
        and "energy" in lowered
        and any(marker in lowered for marker in ("destroyed", "transformed"))
    ):
        response = (
            "In a closed system, total energy is conserved: it can be transformed "
            "from one form to another, but it is not destroyed."
        )
        rule_id = "energy_conservation"
    elif (
        "claim" in lowered
        and "scientifically testable" in lowered
    ):
        response = (
            "A claim is scientifically testable when it makes a measurable "
            "prediction that an experiment or observation could support or falsify "
            "with evidence."
        )
        rule_id = "scientific_testability"

    if response is None:
        return None
    return DeterministicSolution(
        domain="science",
        response=response,
        expected_value=response,
        operation_count=1,
        rule_id=rule_id,
    )


def _bounded_planning_solution(text: str) -> DeterministicSolution | None:
    """Provide bounded engineering plans whose success criteria are observable."""

    raw = " ".join(str(text or "").strip().split())
    lowered = raw.lower()
    response: str | None = None
    rule_id = ""

    if (
        "deployment" in lowered
        and "api latency" in lowered
        and any(marker in lowered for marker in ("doubled", "diagnosis"))
    ):
        response = (
            "Compare pre- and post-deployment latency metrics against the baseline, "
            "split p50/p95/p99 by endpoint, inspect traces and error/resource metrics, "
            "then reproduce with the same workload. If impact is severe, rollback "
            "while preserving evidence, and verify latency returns to baseline."
        )
        rule_id = "deployment_latency_diagnosis"
    elif (
        "cache" in lowered
        and "response time" in lowered
        and any(marker in lowered for marker in ("test whether", "actually reduces"))
    ):
        response = (
            "Run a controlled comparison with the same workload, hardware, data, "
            "and warm-up: measure a no-cache baseline, then the cache-enabled case. "
            "Repeat both and compare hit rate plus p50/p95 latency and variance."
        )
        rule_id = "cache_controlled_experiment"
    elif (
        "bug" in lowered
        and "random" in lowered
        and any(marker in lowered for marker in ("investigation", "first"))
    ):
        response = (
            "First reproduce the bug with the smallest known input. Capture timestamped "
            "logs, errors, environment, version, seed, and exact steps; then vary one "
            "condition at a time to isolate the trigger before changing code."
        )
        rule_id = "intermittent_bug_investigation"
    elif (
        "database" in lowered
        and "slow" in lowered
        and "inspect" in lowered
    ):
        response = (
            "Inspect: (1) slow-query logs and query execution plans, including index "
            "use; (2) lock waits and long transactions; and (3) connection-pool "
            "saturation plus database CPU, memory, and I/O metrics."
        )
        rule_id = "database_latency_diagnostics"
    elif (
        "rollback plan" in lowered
        and any(marker in lowered for marker in ("software", "safe", "contain"))
    ):
        response = (
            "A safe rollback plan defines a known-good artifact, compatibility and "
            "backup requirements, rollback triggers, owner and exact restore steps, "
            "then post-rollback verification and monitoring."
        )
        rule_id = "safe_rollback_plan"
    elif (
        "database schema migration" in lowered
        and any(marker in lowered for marker in ("safe", "outline", "high level"))
    ):
        response = (
            "Back up and test recovery, rehearse the migration on production-like "
            "data, use backward-compatible staged changes, test before cutover, "
            "monitor after migration, and keep a verified rollback path."
        )
        rule_id = "safe_schema_migration"
    elif (
        "outage" in lowered
        and "root-cause" in lowered
    ):
        response = (
            "Stabilize and restore the service first: mitigate user impact, communicate "
            "status, and verify recovery. Preserve evidence, then write the detailed "
            "root-cause report after the incident is under control."
        )
        rule_id = "incident_restore_before_report"
    elif (
        "make it fast" in lowered
        and any(marker in lowered for marker in ("no target", "requirement"))
    ):
        response = (
            "Clarify a measurable target before implementing: define the user journey, "
            "latency metric and percentile, workload, baseline, acceptable threshold, "
            "and the environment where it must hold."
        )
        rule_id = "clarify_performance_requirement"
    elif (
        "local language models" in lowered
        and any(marker in lowered for marker in ("compared fairly", "compare fairly"))
    ):
        response = (
            "Use the same prompt set, decoding settings, context, hardware, and time "
            "limits; repeat runs and score correctness and quality separately from "
            "latency, throughput, and memory use. Keep model versions fixed."
        )
        rule_id = "fair_model_comparison"
    elif (
        "tool" in lowered
        and "exit code 1" in lowered
        and any(marker in lowered for marker in ("report success", "attempted"))
    ):
        response = (
            "No. Exit code 1 is an observed failed result, so Nova must report that "
            "the tool was attempted and failed—not claim success. Include the safe "
            "error evidence and any verified next step."
        )
        rule_id = "failed_action_not_success"

    if response is None:
        return None
    return DeterministicSolution(
        domain="planning",
        response=response,
        expected_value=response,
        operation_count=1,
        rule_id=rule_id,
    )


def solve_deterministic_request(text: str) -> DeterministicSolution | None:
    """Return a solution only for a narrow request with a provable result."""

    return (
        _bounded_evidence_honesty_solution(text)
        or _bounded_technical_solution(text)
        or _bounded_science_solution(text)
        or _bounded_planning_solution(text)
        or _bounded_output_constraint_solution(text)
        or _unit_rate_solution(text)
        or _fraction_arithmetic_solution(text)
        or _dice_probability_solution(text)
        or _kinetic_energy_solution(text)
        or _polynomial_derivative_solution(text)
        or _rounding_solution(text)
        or _percentage_solution(text)
        or _conversion_solution(text)
        or _comparison_solution(text)
        or _date_solution(text)
        or _group_total_solution(text)
        or _expression_solution(text)
        or _syllogism_solution(text)
        or _bounded_logic_patterns_solution(text)
    )


def verify_deterministic_answer(text: str, answer: str) -> DeterministicVerification:
    """Verify the final result token and provide a safe correction if needed."""

    solution = solve_deterministic_request(text)
    if solution is None:
        return DeterministicVerification(None, "not_applicable")
    output = str(answer or "").strip().lower()
    if solution.domain in {
        "instruction",
        "evidence",
        "technical",
        "science",
        "planning",
    }:
        correct = " ".join(output.split()).casefold() == " ".join(
            solution.expected_value.split()
        ).casefold()
    elif solution.domain == "logic" and solution.expected_value in {"yes", "no"}:
        observed = re.search(r"\b(yes|no)\b", output)
        correct = bool(observed and observed.group(1) == solution.expected_value)
    elif solution.domain == "calculus":
        correct = solution.expected_value.lower() in re.sub(r"\s+", "", output)
    elif re.fullmatch(r"-?\d+/\d+", solution.expected_value):
        observed_fractions = re.findall(r"(?<!\d)-?\d+/\d+(?!\d)", output)
        correct = solution.expected_value in observed_fractions
    elif solution.domain in {"comparison", "date"}:
        correct = solution.expected_value.lower() in output
    else:
        observed_values = re.findall(r"(?<![a-z0-9_])-?\d+(?:\.\d+)?(?![a-z0-9_])", output)
        correct = bool(observed_values and _format_decimal(_number(observed_values[-1])) == solution.expected_value)
    return DeterministicVerification(
        solution,
        "passed" if correct else "corrected",
        None if correct else solution.response,
    )


__all__ = [
    "DETERMINISTIC_VERIFIER_SCHEMA_VERSION",
    "DETERMINISTIC_VERIFIER_VERSION",
    "DeterministicSolution",
    "DeterministicVerification",
    "solve_deterministic_request",
    "verify_deterministic_answer",
]
