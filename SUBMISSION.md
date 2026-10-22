# HW4 — submission

**AI assistance:** Claude (Anthropic) helped me read the assignment and draft the Part A plan. I reviewed and edited it myself. <!-- EDIT: say exactly what you used and for what, and update this line as you go -->

---


## Part A — Plan on paper (Easy)

> Commit this whole part before any `.py` file exists.

### A1 — The steps

| # | Step | What goes in (types) | What comes out (types) | When it goes wrong | Tool, loop, or model? |
|---|---|---|---|---|---|
| 1 | Understand the question: find the districts, the quantity (density, growth, per-pupil, ...) and the formula | `question: str` | a plan: list of (district, field) facts to fetch and the formula to apply | question is ambiguous or names an unknown district: the model asks `lookup` and reads the error | model |
| 2 | Resolve a district name to one of the 12 canonical districts | `district: str` | `canonical: str` | no exact match: error with up to 3 close names, never a silent guess (Ossbridge and Ossford are one edit apart); empty string: error | tool (inside `lookup`) |
| 3 | Fetch one fact for one district from the current 2025 profile | `canonical: str`, `field: str` (from a fixed list) | `value: float \| int`, `unit: str`, `source: str` | unknown field: error listing valid fields; fact missing from the text: error; two profiles for the district: the ARCHIVED one is dropped (step 4) | tool (`lookup`) |
| 4 | Apply precedence and unit rules: ARCHIVED profiles (NR-13, NR-14) are never used; a correction notice (NR-16) overrides the profile it corrects; water use is normalised to megalitres (Lindenmoor gives m3: 2,151,400 m3 = 2,151.4 ML) | raw value, `unit`, `source` | final `value`, `unit`, `source` string that names the correction or conversion | a request for 2018/2019 data: error saying archived data is not used; unknown unit: error, no number returned | tool (inside `lookup`) |
| 5 | Do the arithmetic (divide, subtract, percent change, tariff times use, ...) | `expression: str` | `result: float` | syntax error, division by zero, disallowed syntax, exponent or result too large: `{"error": ...}` | tool (`calculate`) |
| 6 | Compare, choose the winner, round only now, and write the final line `ANSWER: <name or yes/no> \| <number>` | numbers from step 5, `decimals` implied by the question | final reply `str` | the model rounds too early or gives a unit conversion in its head: this is what S1 and S2 will get wrong | model |
| 7 | Run the loop: parse `arguments` (a JSON string), validate it, call the tool, send back a `tool` message for every `tool_call_id`, stop at the round limit, write the log | model reply with `tool_calls` | new messages for the conversation, a log entry, or `unanswered` | invalid JSON or wrong argument names: send back `{"error": ...}` for that id, do not crash; round limit reached: mark unanswered | my loop |

**How the steps connect:**

```
question
  -> [1 model] plan: which facts, which formula
       -> [7 loop] receives tool_calls
            -> [3 lookup] (district, field)  --uses-->  [2 resolve name] --> [4 precedence + units]
                 -> {value, unit, source}  --(loop sends back by tool_call_id)--> model
            -> [5 calculate] expression built by the model from lookup values
                 -> {result}               --(loop sends back by tool_call_id)--> model
       -> [6 model] compare, round, "ANSWER: name | number"
```

Facts only come from `lookup`, and every number in an expression comes from a `lookup` result or from an earlier `calculate` result.

**What I am assuming:**

- Year: population is the 2025 census, budgets are the 2025 fiscal year, water use is household use over calendar 2025 (from NR-00). The 2020 census is only used when a question asks for growth or a projection.
- ARCHIVED profiles (NR-13, NR-14) are never used, even if the question seems to ask about 2019. NR-00 says they are superseded.
- A correction notice beats the profile it corrects. NR-16 changes Brightwater's area from 912.4 to 921.4 km2. `lookup` applies it, so the model never sees the typo.
- Units: water use is stored in megalitres. Lindenmoor's 2,151,400 m3 is converted (1 ML = 1,000 m3). Per-resident-per-day figures use 365 days (2025 is not a leap year) and 1 ML = 1,000,000 litres.
- Tariff: 142.35 tenge per m3 (2025), not the 2024 value of 131.80.
- Rounding: only in step 6, to the number of decimals that suits the unit. `lookup` and `calculate` never round.
- Most sensitive assumption: the correction and unit handling inside `lookup`. If `lookup` returned the raw Brightwater area, the Q-09 answer would still name Millbrook but the gap would be 0.08 instead of 0.56, so the number would be wrong. If it returned Lindenmoor water in megalitres as 2,151,400, Q-03 would be off by a factor of 1,000.

### A2 — The two tools

#### `lookup`

```json
{
  "type": "function",
  "function": {
    "name": "lookup",
    "description": "Look up ONE fact about ONE district of the Nine Rivers Region from the current 2025 profiles. Districts: Ossbridge, Ossford, Tarnvale, Kelmarsh, Brightwater, Stonecairn, Harrowfield, Lindenmoor, Redfen, Ashgrove, Millbrook, Coldharbour. Use the exact name. Returns the value, its unit and the source document id. Corrections and unit conversions are already applied (water use is always in megalitres). Archived 2019 profiles are not available. For the regional water price use district 'region' and field 'water_tariff_2025'. Make one call per fact. Do not do arithmetic yourself, use the calculate tool.",
    "parameters": {
      "type": "object",
      "properties": {
        "district": {
          "type": "string",
          "description": "Exact district name, or 'region' for the water tariff."
        },
        "field": {
          "type": "string",
          "enum": [
            "population_2025",
            "population_2020",
            "area_km2",
            "budget_2025_mln_tenge",
            "water_use_2025_ml",
            "schools",
            "pupils_2025_26",
            "paved_road_km",
            "founded_year",
            "water_tariff_2025"
          ],
          "description": "Which fact to return."
        }
      },
      "required": ["district", "field"],
      "additionalProperties": false
    }
  }
}
```

| Case | What the tool returns |
|---|---|
| success | `{"district": "Brightwater", "field": "area_km2", "value": 921.4, "unit": "km2", "source": "NR-05, corrected by NR-16"}` |
| unknown or misspelled district | `{"error": "no district named 'Ossbrige'; did you mean 'Ossbridge' or 'Ossford'?"}` |
| unknown field | `{"error": "unknown field 'popluation'; valid fields: population_2025, population_2020, ..."}` |
| request for old data (field or text contains 2018 or 2019) | `{"error": "2018/2019 figures come from archived profiles (NR-13, NR-14), which are superseded and not used; use the 2025 fields"}` |
| missing argument | `{"error": "missing required argument 'field'"}` |
| water use for Lindenmoor | `{"district": "Lindenmoor", "field": "water_use_2025_ml", "value": 2151.4, "unit": "ML", "source": "NR-08, converted from 2,151,400 m3"}` |

**Worst thing it could do with strange or dangerous input:** nothing beyond returning an error. `district` and `field` are only used as dictionary keys. They are never put into a file path, a shell command or a regular expression, and the corpus path is fixed. Output is one short JSON object, so a long or weird string cannot make it return a whole document.

#### `calculate`

```json
{
  "type": "function",
  "function": {
    "name": "calculate",
    "description": "Evaluate one arithmetic expression exactly and return the number. Allowed: numbers, + - * / ** and parentheses. No variables, no functions, no text. Use it for EVERY calculation, including differences, percentages and per-resident figures, with numbers taken from lookup results. The result is not rounded.",
    "parameters": {
      "type": "object",
      "properties": {
        "expression": {
          "type": "string",
          "description": "For example: 44675 / 921.4"
        }
      },
      "required": ["expression"],
      "additionalProperties": false
    }
  }
}
```

| Case | What the tool returns |
|---|---|
| success | `{"result": 48.48599956587801}` |
| division by zero | `{"error": "division by zero"}` |
| syntax error | `{"error": "could not parse expression"}` |
| disallowed syntax (names, calls, attributes, strings, subscripts) | `{"error": "only numbers, + - * / ** and parentheses are allowed"}` |
| exponent larger than 100 in absolute value, or result larger than 1e18 or not finite | `{"error": "number too large"}` |
| expression longer than 200 characters | `{"error": "expression too long"}` |

**Worst thing it could do with strange or dangerous input:** never runs model-written code, because it parses with `ast` and walks the tree with a whitelist of node types (no `eval`, no `exec`). `__import__('os').system('echo hi')` and `(1).__class__` contain calls and attributes, so they are refused. `9**9**9` would try to build a number with hundreds of millions of digits and freeze the process, so the exponent cap refuses it before computing. The worst remaining case is a slow but bounded calculation, because of the length and exponent caps.

### A3 — Q-09 by hand

```json
[
  {"role": "user", "content": "Which district has the higher population density in 2025, Brightwater or Millbrook, and by how many residents per square kilometre?"},
  {"role": "assistant", "content": null, "tool_calls": [
    {"id": "call_1", "type": "function", "function": {"name": "lookup", "arguments": "{\"district\": \"Brightwater\", \"field\": \"population_2025\"}"}},
    {"id": "call_2", "type": "function", "function": {"name": "lookup", "arguments": "{\"district\": \"Brightwater\", \"field\": \"area_km2\"}"}},
    {"id": "call_3", "type": "function", "function": {"name": "lookup", "arguments": "{\"district\": \"Millbrook\", \"field\": \"population_2025\"}"}},
    {"id": "call_4", "type": "function", "function": {"name": "lookup", "arguments": "{\"district\": \"Millbrook\", \"field\": \"area_km2\"}"}}
  ]},
  {"role": "tool", "tool_call_id": "call_1", "content": "{\"district\": \"Brightwater\", \"field\": \"population_2025\", \"value\": 44675, \"unit\": \"residents\", \"source\": \"NR-05\"}"},
  {"role": "tool", "tool_call_id": "call_2", "content": "{\"district\": \"Brightwater\", \"field\": \"area_km2\", \"value\": 921.4, \"unit\": \"km2\", \"source\": \"NR-05, corrected by NR-16\"}"},
  {"role": "tool", "tool_call_id": "call_3", "content": "{\"district\": \"Millbrook\", \"field\": \"population_2025\", \"value\": 37203, \"unit\": \"residents\", \"source\": \"NR-11\"}"},
  {"role": "tool", "tool_call_id": "call_4", "content": "{\"district\": \"Millbrook\", \"field\": \"area_km2\", \"value\": 758.6, \"unit\": \"km2\", \"source\": \"NR-11\"}"},
  {"role": "assistant", "content": null, "tool_calls": [
    {"id": "call_5", "type": "function", "function": {"name": "calculate", "arguments": "{\"expression\": \"44675 / 921.4\"}"}},
    {"id": "call_6", "type": "function", "function": {"name": "calculate", "arguments": "{\"expression\": \"37203 / 758.6\"}"}}
  ]},
  {"role": "tool", "tool_call_id": "call_5", "content": "{\"result\": 48.48599956587801}"},
  {"role": "tool", "tool_call_id": "call_6", "content": "{\"result\": 49.041655681518584}"},
  {"role": "assistant", "content": null, "tool_calls": [
    {"id": "call_7", "type": "function", "function": {"name": "calculate", "arguments": "{\"expression\": \"49.041655681518584 - 48.48599956587801\"}"}}
  ]},
  {"role": "tool", "tool_call_id": "call_7", "content": "{\"result\": 0.5556561156405735}"},
  {"role": "assistant", "content": "Millbrook is denser: about 49.04 residents/km2 against 48.49 for Brightwater (Brightwater's area uses the corrected 921.4 km2 from NR-16), a difference of about 0.6.\nANSWER: Millbrook | 0.6"}
]
```

**My arithmetic:**

- Brightwater (NR-05 with correction NR-16): 44,675 / 921.4 = 48.486 residents/km2
- Millbrook (NR-11): 37,203 / 758.6 = 49.042 residents/km2
- Difference: 49.042 - 48.486 = 0.556, which rounds to 0.6. Millbrook is denser.
- Trap check: with the uncorrected area 912.4, Brightwater would be 44,675 / 912.4 = 48.964, and the gap would be 0.077, which rounds to 0.1. That is why NR-16 must be applied.

### A4 — Why I split it this way

One other split: a single "answer_question" tool, or a search-style `lookup(query)` that returns matching sentences from the documents. I did not choose it because the traps are exactly what free-text search handles badly: a search for "Ossbridge population" can return the Ossford profile, and a search for Tarnvale can return the ARCHIVED 2019 profile with an old number. A structured `lookup(district, field)` makes the exact-name rule, the archive rule, the correction and the unit conversion happen in code I can test, not in the model's reading of text. Another option, one tool per formula (density, growth, per-resident), would mean more tool definitions in every S3 request (more input tokens) and a new tool for every new question type, while one general `calculate` covers all twenty questions.

---

## Part B — Build it and run it (Medium)

### What I changed from Part A while coding

None

### B2 — Tests

============================= test session starts =============================
platform win32 -- Python 3.12.2, pytest-9.1.1, pluggy-1.7.0 -- C:\Users\Asus\css4007-hw4\.venv\Scripts\python.exe
cachedir: .pytest_cache
rootdir: C:\Users\Asus\css4007-hw4
plugins: anyio-4.15.1
collecting ... collected 32 items

tests/test_tools.py::test_lookup_finds_correct_2025_number PASSED        [  3%]
tests/test_tools.py::test_lookup_misspelled_name_suggests_the_right_one PASSED [  6%]
tests/test_tools.py::test_lookup_similar_names_are_not_mixed_up PASSED   [  9%]
tests/test_tools.py::test_lookup_never_uses_archived_profiles PASSED     [ 12%]
tests/test_tools.py::test_lookup_applies_correction_notice PASSED        [ 15%]
tests/test_tools.py::test_lookup_converts_lindenmoor_water_to_megalitres PASSED [ 18%]
tests/test_tools.py::test_lookup_tariff_is_the_2025_one PASSED           [ 21%]
tests/test_tools.py::test_lookup_never_crashes_on_strange_input[district-none] PASSED [ 25%]
tests/test_tools.py::test_lookup_never_crashes_on_strange_input[field-none] PASSED [ 28%]
tests/test_tools.py::test_lookup_never_crashes_on_strange_input[numbers] PASSED [ 31%]
tests/test_tools.py::test_lookup_never_crashes_on_strange_input[empty] PASSED [ 34%]
tests/test_tools.py::test_lookup_never_crashes_on_strange_input[sql-like] PASSED [ 37%]
tests/test_tools.py::test_lookup_never_crashes_on_strange_input[path-like] PASSED [ 40%]
tests/test_tools.py::test_lookup_never_crashes_on_strange_input[very-long-name] PASSED [ 43%]
tests/test_tools.py::test_lookup_never_crashes_on_strange_input[region-wrong-field] PASSED [ 46%]
tests/test_tools.py::test_calculate_multiplication PASSED                [ 50%]
tests/test_tools.py::test_calculate_division PASSED                      [ 53%]
tests/test_tools.py::test_calculate_precedence_and_parentheses PASSED    [ 56%]
tests/test_tools.py::test_calculate_refuses_dangerous_input[__import__('os').system('echo hi')] PASSED [ 59%]
tests/test_tools.py::test_calculate_refuses_dangerous_input[(1).__class__] PASSED [ 62%]
tests/test_tools.py::test_calculate_refuses_dangerous_input[9**9**9] PASSED [ 65%]
tests/test_tools.py::test_calculate_division_by_zero PASSED              [ 68%]
tests/test_tools.py::test_calculate_rejects_non_arithmetic_input[name] PASSED [ 71%]
tests/test_tools.py::test_calculate_rejects_non_arithmetic_input[string] PASSED [ 75%]
tests/test_tools.py::test_calculate_rejects_non_arithmetic_input[bool] PASSED [ 78%]
tests/test_tools.py::test_calculate_rejects_non_arithmetic_input[function-call] PASSED [ 81%]
tests/test_tools.py::test_calculate_rejects_non_arithmetic_input[incomplete] PASSED [ 84%]
tests/test_tools.py::test_calculate_rejects_non_arithmetic_input[empty] PASSED [ 87%]
tests/test_tools.py::test_calculate_rejects_non_arithmetic_input[spaces] PASSED [ 90%]
tests/test_tools.py::test_calculate_rejects_non_arithmetic_input[none] PASSED [ 93%]
tests/test_tools.py::test_calculate_rejects_non_arithmetic_input[too-long] PASSED [ 96%]
tests/test_tools.py::test_calculate_limits_very_large_numbers PASSED     [100%]

============================= 32 passed in 0.05s ==============================


### B3 — The loop

- Round limit, and why:
- Where the logs are:
- Real Q-09 conversation compared with my A3 version, what is different:

### B4 — Three strategies

**What I kept the same:**

<!-- model, temperature, k, prompts, answer format, anything else -->

**My rule for a correct answer** (written before the first full run):

| Run | Strategy | Correct /20 | Unanswered | Input tokens | Output tokens | Median seconds per question | Total seconds | Cost ($) |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| 1 | S1 direct | | | | | | | |
| 1 | S2 think and vote (k = ) | | | | | | | |
| 1 | S3 tools | | | | | | | |
| 2 | S1 direct | | | | | | | |
| 2 | S2 think and vote (k = ) | | | | | | | |
| 2 | S3 tools | | | | | | | |

**Per question (run 1):**

| Question | S1 | S2 | S3 |
|---|:---:|:---:|:---:|
| Q-01 | | | |
| Q-02 | | | |
| Q-03 | | | |
| Q-04 | | | |
| Q-05 | | | |
| Q-06 | | | |
| Q-07 | | | |
| Q-08 | | | |
| Q-09 | | | |
| Q-10 | | | |
| Q-11 | | | |
| Q-12 | | | |
| Q-13 | | | |
| Q-14 | | | |
| Q-15 | | | |
| Q-16 | | | |
| Q-17 | | | |
| Q-18 | | | |
| Q-19 | | | |
| Q-20 | | | |

---

## Part C — Explain and choose (Hard)

### C1 — Does the tool description matter?

| Question | Calls (your description) | Calls (vague) | Answer (yours) | Answer (vague) |
|---|---:|---:|---|---|
| | | | | |

### C2 — Three mistakes explained

### C3 — Which strategy I would use, and what would change it

### C4 — How sure I can be

### Final questions

1.
2.
3.
4.
5.
6.
7.
8.
