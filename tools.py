"""The two tools for HW4: lookup (facts from the corpus) and calculate (safe arithmetic)."""

import ast
import difflib
import functools
import json
import operator
import re
from pathlib import Path

CORPUS_PATH = Path(__file__).parent / "data" / "corpus.jsonl"

DISTRICTS = [
    "Ossbridge", "Ossford", "Tarnvale", "Kelmarsh", "Brightwater", "Stonecairn",
    "Harrowfield", "Lindenmoor", "Redfen", "Ashgrove", "Millbrook", "Coldharbour",
]

FIELDS = [
    "population_2025", "population_2020", "area_km2", "budget_2025_mln_tenge",
    "water_use_2025_ml", "schools", "pupils_2025_26", "paved_road_km",
    "founded_year", "water_tariff_2025",
]

UNITS = {
    "population_2025": "residents",
    "population_2020": "residents",
    "area_km2": "km2",
    "budget_2025_mln_tenge": "million tenge",
    "water_use_2025_ml": "ML",
    "schools": "schools",
    "pupils_2025_26": "pupils",
    "paved_road_km": "km",
    "founded_year": "year",
    "water_tariff_2025": "tenge per m3",
}

_NUM = r"([\d,]+(?:\.\d+)?)"

# The 12 profiles use three sentence templates, so each field has three patterns.
_PATTERNS = {
    "population_2025": [
        rf"2025 census recorded {_NUM} residents",
        rf"Census population: [\d,]+ in 2020 and {_NUM} in 2025",
        rf"2025 census counted {_NUM} residents",
    ],
    "population_2020": [
        rf"2020 census had recorded {_NUM}",
        rf"Census population: {_NUM} in 2020",
        rf"up from {_NUM} at the 2020 census",
    ],
    "area_km2": [
        rf"covers {_NUM} square kilometres",
        rf"over {_NUM} square kilometres",
        rf"area of {_NUM} square kilometres",
    ],
    "budget_2025_mln_tenge": [
        rf"budget for 2025 was set at {_NUM} million tenge",
        rf"2025 budget amounted to {_NUM} million tenge",
        rf"2025 budget was {_NUM} million tenge",
    ],
    "water_use_2025_ml": [
        rf"water use in 2025 came to {_NUM} (megalitres|cubic metres)",
        rf"used {_NUM} (megalitres|cubic metres) of water",
    ],
    "schools": [
        r"There are (\d+) schools",
        r"has (\d+) schools",
        r"runs (\d+) schools",
    ],
    "pupils_2025_26": [
        rf"attended by {_NUM} pupils",
        rf"enrolled {_NUM} pupils",
        rf"with {_NUM} pupils enrolled",
    ],
    "paved_road_km": [
        rf"paved road network is {_NUM} km",
        rf"keeps {_NUM} km of paved road",
        rf"maintains {_NUM} km of paved road",
    ],
    "founded_year": [r"[Ff]ounded in (\d{4})"],
}


def _to_number(text):
    text = text.replace(",", "")
    return float(text) if "." in text else int(text)


@functools.lru_cache(maxsize=1)
def _load():
    """Read the corpus once. Returns (profiles, corrections, tariff).

    ARCHIVED profiles are dropped here, so no later code can ever return them.
    """
    with open(CORPUS_PATH, encoding="utf-8") as f:
        docs = [json.loads(line) for line in f if line.strip()]
    profiles, corrections, tariff = {}, {}, None
    for doc in docs:
        title, text = doc["title"], doc["text"]
        if "ARCHIVED" in title or text.startswith("ARCHIVED"):
            continue
        m = re.match(r"(\w+) district profile", title)
        if m and m.group(1) in DISTRICTS:
            profiles[m.group(1)] = doc
            continue
        m = re.match(r"Correction notice - (\w+)", title)
        if m:
            c = re.search(rf"The correct area is {_NUM} square kilometres", text)
            if c:
                corrections.setdefault(m.group(1), {})["area_km2"] = (_to_number(c.group(1)), doc["id"])
            continue
        m = re.search(rf"tariff is {_NUM} tenge per cubic metre", text)
        if m:
            tariff = (_to_number(m.group(1)), doc["id"])
    return profiles, corrections, tariff


def _resolve(name):
    key = name.strip().lower()
    for d in DISTRICTS + ["region"]:
        if d.lower() == key:
            return d
    return None


def _suggest(name):
    lowered = {d.lower(): d for d in DISTRICTS}
    close = difflib.get_close_matches(name.strip().lower(), list(lowered), n=3, cutoff=0.6)
    return [lowered[c] for c in close]


def _lookup(district, field):
    if not isinstance(district, str) or not district.strip():
        return {"error": "missing required argument 'district' (a district name)"}
    if not isinstance(field, str) or not field.strip():
        return {"error": "missing required argument 'field'"}
    field = field.strip()

    if re.search(r"201\d|archiv", field, re.I):
        return {"error": "2018/2019 figures come from archived profiles (NR-13, NR-14), "
                         "which are superseded and not used; use the 2025 fields"}
    if field not in FIELDS:
        return {"error": f"unknown field '{field}'; valid fields: {', '.join(FIELDS)}"}

    canonical = _resolve(district)
    if canonical is None:
        close = _suggest(district)
        if close:
            return {"error": f"no district named '{district}'; did you mean {' or '.join(close)}?"}
        return {"error": f"no district named '{district}'; valid districts: {', '.join(DISTRICTS)}"}

    profiles, corrections, tariff = _load()

    if field == "water_tariff_2025":
        if tariff is None:
            return {"error": "tariff not found in the documents"}
        value, source = tariff
        return {"district": canonical, "field": field, "value": value,
                "unit": UNITS[field], "source": source}

    if canonical == "region":
        return {"error": "district 'region' only works with field 'water_tariff_2025'"}

    doc = profiles.get(canonical)
    if doc is None:
        return {"error": f"no current profile found for {canonical}"}

    fix = corrections.get(canonical, {}).get(field)
    if fix:
        value, notice = fix
        return {"district": canonical, "field": field, "value": value,
                "unit": UNITS[field], "source": f"{doc['id']}, corrected by {notice}"}

    for pattern in _PATTERNS[field]:
        m = re.search(pattern, doc["text"])
        if m:
            break
    else:
        return {"error": f"could not find '{field}' in the {canonical} profile"}

    value = _to_number(m.group(1))
    source = doc["id"]
    if field == "water_use_2025_ml":
        unit_word = m.group(2)
        if unit_word == "cubic metres":
            source = f"{doc['id']}, converted from {value:,} m3"
            value = round(value / 1000, 6)
        elif unit_word != "megalitres":
            return {"error": f"unknown water unit '{unit_word}' in {doc['id']}"}
    return {"district": canonical, "field": field, "value": value,
            "unit": UNITS[field], "source": source}


def lookup(district, field):
    """Return one fact as a dict. Never raises: problems come back as {"error": ...}."""
    try:
        return _lookup(district, field)
    except Exception as exc:  # last line of defence, the model must always get an answer
        return {"error": f"internal error: {type(exc).__name__}"}


# ---------------------------------------------------------------- calculate

MAX_EXPRESSION_LENGTH = 200
MAX_EXPONENT = 100
MAX_ABS_RESULT = 1e18

_BINARY = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
}
_UNARY = {ast.UAdd: operator.pos, ast.USub: operator.neg}

_NOT_ALLOWED = "only numbers, + - * / ** and parentheses are allowed"


class _CalcError(Exception):
    pass


def _check_size(value):
    if isinstance(value, complex):
        raise _CalcError("result is not a real number")
    if abs(value) > MAX_ABS_RESULT:
        raise _CalcError("number too large")
    return value


def _eval(node):
    if isinstance(node, ast.Constant):
        if type(node.value) in (int, float):  # type(), so True/False and strings are refused
            return _check_size(node.value)
        raise _CalcError(_NOT_ALLOWED)
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY:
        return _UNARY[type(node.op)](_eval(node.operand))
    if isinstance(node, ast.BinOp) and type(node.op) in _BINARY:
        left = _eval(node.left)
        right = _eval(node.right)
        if isinstance(node.op, ast.Div) and right == 0:
            raise _CalcError("division by zero")
        if isinstance(node.op, ast.Pow) and abs(right) > MAX_EXPONENT:
            raise _CalcError("number too large")  # refuses 9**9**9 before computing it
        return _check_size(_BINARY[type(node.op)](left, right))
    raise _CalcError(_NOT_ALLOWED)


def calculate(expression):
    """Evaluate an arithmetic expression without eval/exec. Returns {"result": x} or {"error": ...}."""
    try:
        if not isinstance(expression, str) or not expression.strip():
            return {"error": "missing required argument 'expression'"}
        if len(expression) > MAX_EXPRESSION_LENGTH:
            return {"error": "expression too long"}
        try:
            tree = ast.parse(expression.strip(), mode="eval")
        except (SyntaxError, ValueError, RecursionError, MemoryError):
            return {"error": "could not parse expression"}
        return {"result": _eval(tree.body)}
    except _CalcError as exc:
        return {"error": str(exc)}
    except ZeroDivisionError:
        return {"error": "division by zero"}
    except (OverflowError, RecursionError, MemoryError):
        return {"error": "number too large"}
    except Exception as exc:  # last line of defence
        return {"error": f"internal error: {type(exc).__name__}"}


# ------------------------------------------------------ definitions for the model

LOOKUP_DEFINITION = {
    "type": "function",
    "function": {
        "name": "lookup",
        "description": (
            "Look up ONE fact about ONE district of the Nine Rivers Region from the current 2025 profiles. "
            "Districts: Ossbridge, Ossford, Tarnvale, Kelmarsh, Brightwater, Stonecairn, Harrowfield, "
            "Lindenmoor, Redfen, Ashgrove, Millbrook, Coldharbour. Use the exact name. "
            "Returns the value, its unit and the source document id. Corrections and unit conversions are "
            "already applied (water use is always in megalitres). Archived 2019 profiles are not available. "
            "For the regional water price use district 'region' and field 'water_tariff_2025'. "
            "Make one call per fact. Do not do arithmetic yourself, use the calculate tool."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "district": {
                    "type": "string",
                    "description": "Exact district name, or 'region' for the water tariff.",
                },
                "field": {
                    "type": "string",
                    "enum": FIELDS,
                    "description": "Which fact to return.",
                },
            },
            "required": ["district", "field"],
            "additionalProperties": False,
        },
    },
}

CALCULATE_DEFINITION = {
    "type": "function",
    "function": {
        "name": "calculate",
        "description": (
            "Evaluate one arithmetic expression exactly and return the number. "
            "Allowed: numbers, + - * / ** and parentheses. No variables, no functions, no text. "
            "Use it for EVERY calculation, including differences, percentages and per-resident figures, "
            "with numbers taken from lookup results. The result is not rounded."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "expression": {
                    "type": "string",
                    "description": "For example: 44675 / 921.4",
                },
            },
            "required": ["expression"],
            "additionalProperties": False,
        },
    },
}

TOOL_DEFINITIONS = [LOOKUP_DEFINITION, CALCULATE_DEFINITION]
TOOL_FUNCTIONS = {"lookup": lookup, "calculate": calculate}