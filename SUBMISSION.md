# HW4 — submission

**AI assistance:** I used Claude (Anthropic) in this homework. It helped me read the assignment, draft the Part A plan, write the code (`tools.py`, `strategies.py`, `run.py`, `report.py`, `measure_tools.py`) and the tests, and write first drafts of the answers in Parts B and C. I ran everything myself with my own API key, checked the numbers against my own logs in `outputs/`, and edited the text.

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

The design did not change. One thing I had not planned: with its default reasoning setting the model refused function tools (HTTP 400), so I set `reasoning_effort = "none"` for all three strategies (see B4).

### B2 — Tests

```
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
```


### B3 — The loop

- Round limit, and why: 10 model calls per question. Q-09 needed 4 (one round of 4 parallel lookups, one round of 2 calculations, one calculation for the difference, then the final answer). The model sends independent calls together, so the longest chain is lookup, calculate, calculate, answer; the hardest questions (three districts, several formulas) should need about 4 to 6. 10 leaves room for a retry after a tool error but stops an endless loop and caps the cost per question. A question that hits the limit is marked unanswered. In the two full runs the most any question used was 4 rounds (the fewest was 3), so the limit was never reached.
- Where the logs are: outputs/run-<label>/S3/Q-xx.json (tool_log with every call, its raw arguments, result and seconds; model_calls with tokens per round; conversation with the full message list). The Q-09 test run is in outputs/run-q09-test/S3/Q-09.json.
- Real Q-09 conversation compared with my A3 version, what is different: The first two rounds are identical to A3 (same four lookups in one round, same two divisions in the next). Round 3 differs: A3 subtracted the two results from round 2, but the model sent one expression built from the original numbers, 37203 / 758.6 - 44675 / 921.4, and got 0.5556561156405735. So the real run used 7 tool calls in 4 model calls, the same count as A3. The final text also differs: A3 ended with 0.6, the model wrote 0.556 (the prompt allows up to 3 decimals and I did not ask for rounding to 1 decimal), which my scoring rule accepts. The tool_call ids are generated by the API, not call_1 to call_7. No tool returned an error. Tokens for this question: 3474 input, 224 output, 8.6 s.

### B4 — Three strategies

**What I kept the same:**

Model gpt-5.6-luna through the Chat Completions API for all three strategies. temperature = 1.0 for all (the model accepted it). reasoning_effort = "none" for all: with the default reasoning the model refused function tools (HTTP 400), so S1 and S2 use it too, to keep the strategies comparable. S2 uses k = 5, five separate calls per question. Same 20 questions in the same order, same base system prompt and the same final line, `ANSWER: <name or yes/no> | <number>`, with at most 3 decimals. Only the short strategy suffix differs: S1 "Answer directly", S2 "Think step by step", S3 "use the tools". S1 and S2 get all 17 documents in the prompt, S3 gets none and only the two tools. S3 stops after 10 model calls.

**My rule for a correct answer** (written before the first full run):

The name must match the expected name exactly (case does not matter). The number, rounded to the question's number of decimals, must be within 1 in the last digit of the expected value. A reply without a valid ANSWER line counts as unanswered and as wrong. In S2 the answer is the majority of the 5 samples; two samples agree if the name is the same and the numbers differ by at most 1%; a tie goes to the group that appeared first.

**Why twenty questions and this rule:**

I used the twenty questions from the course because that is the set I was given. They are enough to see a big gap (S1 against the other two) but too small to see a small one (see C4). Each question has one exact answer, so the rule asks for the right name and a number within 1 in the last digit: it ignores harmless rounding differences but never accepts a wrong value.

**Cost:** input tokens x $0.20 + output tokens x $1.20, per million tokens. I did not model any discount for cached input.

**Summary of both runs:**

| Run | Strategy | Correct /20 | Unanswered | Input tokens | Output tokens | Median seconds per question | Total seconds | Cost ($) |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| 1 | S1 direct | 2 | 0 | 44479 | 251 | 1.58 | 31.9 | 0.0092 |
| 1 | S2 think and vote (k = 5) | 16 | 0 | 222895 | 13698 | 12.04 | 239.3 | 0.0610 |
| 1 | S3 tools | 18 | 0 | 61305 | 4416 | 7.03 | 141.7 | 0.0176 |
| 2 | S1 direct | 3 | 0 | 44479 | 249 | 1.59 | 33.2 | 0.0092 |
| 2 | S2 think and vote (k = 5) | 17 | 0 | 222895 | 13684 | 11.9 | 262.1 | 0.0610 |
| 2 | S3 tools | 18 | 0 | 58154 | 4378 | 6.34 | 131.7 | 0.0169 |

**Per question (run 1):**

| Question | S1 | S2 | S3 |
|---|:---:|:---:|:---:|
| Q-01 | ✗ | ✓ | ✓ |
| Q-02 | ✗ | ✓ | ✓ |
| Q-03 | ✗ | ✓ | ✗ |
| Q-04 | ✗ | ✓ | ✓ |
| Q-05 | ✗ | ✗ | ✓ |
| Q-06 | ✗ | ✓ | ✓ |
| Q-07 | ✗ | ✓ | ✓ |
| Q-08 | ✗ | ✓ | ✓ |
| Q-09 | ✗ | ✓ | ✓ |
| Q-10 | ✓ | ✓ | ✓ |
| Q-11 | ✗ | ✓ | ✓ |
| Q-12 | ✗ | ✗ | ✓ |
| Q-13 | ✗ | ✓ | ✓ |
| Q-14 | ✗ | ✓ | ✗ |
| Q-15 | ✗ | ✓ | ✓ |
| Q-16 | ✓ | ✓ | ✓ |
| Q-17 | ✗ | ✗ | ✓ |
| Q-18 | ✗ | ✓ | ✓ |
| Q-19 | ✗ | ✓ | ✓ |
| Q-20 | ✗ | ✗ | ✓ |

**Per question (run 2):**

| Question | S1 | S2 | S3 |
|---|:---:|:---:|:---:|
| Q-01 | ✗ | ✓ | ✓ |
| Q-02 | ✗ | ✓ | ✓ |
| Q-03 | ✗ | ✓ | ✓ |
| Q-04 | ✗ | ✓ | ✓ |
| Q-05 | ✗ | ✗ | ✓ |
| Q-06 | ✗ | ✓ | ✓ |
| Q-07 | ✗ | ✓ | ✓ |
| Q-08 | ✗ | ✓ | ✓ |
| Q-09 | ✗ | ✓ | ✓ |
| Q-10 | ✓ | ✓ | ✓ |
| Q-11 | ✗ | ✓ | ✗ |
| Q-12 | ✗ | ✗ | ✓ |
| Q-13 | ✓ | ✓ | ✓ |
| Q-14 | ✗ | ✓ | ✗ |
| Q-15 | ✗ | ✓ | ✓ |
| Q-16 | ✓ | ✓ | ✓ |
| Q-17 | ✗ | ✓ | ✓ |
| Q-18 | ✗ | ✓ | ✓ |
| Q-19 | ✗ | ✓ | ✓ |
| Q-20 | ✗ | ✗ | ✓ |


---

## Part C — Explain and choose (Hard)

### C1 — Does the tool description matter?

| Question | Calls (your description) | Calls (vague) | Answer (yours) | Answer (vague) |
|---|---:|---:|---|---|
| Q-01 | 7 | 5 | Ossbridge, 4.57 (correct) | Ossbridge, 4.570 (correct) |
| Q-03 | 5 | 5 | Lindenmoor, 5340.159 (wrong; run 2: 5.34, correct) | yes, 5340.159 (wrong) |
| Q-08 | 4 | 4 | Brightwater, 72.456 (correct) | Brightwater, 72.456 (correct) |
| Q-09 | 7 | 7 | Millbrook, 0.556 (correct) | Millbrook, 0.556 (correct) |
| Q-15 | 5 | 5 | Redfen, 17.609 (correct) | Redfen, 17.609 (correct) |

With one vague line (`Looks things up.`) instead of the full lookup description, and everything else unchanged, 4 of the 5 answers were identical to the ones with the full description, and the same four were correct. No tool call returned an error in any of the 15 S3 logs I compared (5 questions in 3 runs). The number of tool calls changed on one question only: Q-01 went from 7 calls to 5. Q-08, Q-09 and Q-15 had the same calls and the same inputs. Input tokens dropped by about 430 to 570 per question when the call count stayed the same (for example Q-09: 3474 to 2902), because the long description is sent again in every round; Q-01 dropped by 1501 because it also made two fewer calls. Q-03 was wrong with both descriptions in the same way: the same formula with the extra `*1000`, giving 5340.159, so the description did not cause it. In the vague run the sentence named Lindenmoor but the final line said `yes | 5340.159`, so the name was wrong as well.

Why the effect is so small: the traps are handled in the code of `lookup` (archived profiles are never returned, NR-16 is applied, Lindenmoor's cubic metres are converted to megalitres), not in the description. I also did not change the parameter schema, so the field names (`water_use_2025_ml`, `area_km2`), the `enum` of allowed fields and the parameter text "or 'region' for the water tariff" still told the model how to call the tool, and every question names its districts. A description matters most when the model must choose between tools or guess the arguments without other hints. Limits: 5 questions and one sample per condition, so this shows that there is no large effect here, not that there is none.

### C2 — Three mistakes explained

**S1, Q-09, run 1.** The model answered `ANSWER: Brightwater | 1.06`; the expected answer is Millbrook, 0.6. S1 is told to reply with only the final line, so the model has no room to write any working: it must divide 44,675 by the area, divide 37,203 by 758.6 and subtract, all inside one forward pass, generating the digits one token at a time. That is why S1 got only 2/20 in run 1 and 3/20 in run 2. The questions it solved in both runs (Q-10 and Q-16) need a single subtraction or addition of small numbers.

**S2, Q-05, run 1.** All five samples agreed: the log shows `votes = {'coldharbour | 14231.523': 5}`, and the answer is wrong (expected 14235). The model wrote "2,884,600,000 ÷ 14,926 = 193,276.147" but the true value is 193,260.083, and "2,366,900,000 ÷ 11,407 = 207,507.669" where the true value is 207,495.398. So its difference was 14,231.523 instead of 14,235.314. Voting lowers variance: random slips differ between samples and the majority cancels them. It cannot remove a systematic error. Here the same long division went wrong the same way in all five samples, even at temperature 1.0, and the vote only confirmed it. It also cost five times the tokens: 222,895 input tokens against 44,479 for S1 in run 1.

**S3, Q-14, run 1 and run 2 (same wrong answer both times).** The model asked `calculate` for `5207*1000000/71388/365*1000`, which gave 199834.05, and `4390*1000000/58760/365*1000`, which gave 204686.82. It multiplied by 1,000,000 and then by 1,000 again, although one megalitre is already 1,000,000 litres. The calculator did exactly what it was told, so the 1000x slip stayed in the formula, and the answer was 4852.761 instead of about 4.85. The model did not notice that about 200,000 litres per resident per day is absurd. A calculator removes errors of arithmetic, like the long divisions that broke S2 on Q-05, because it computes exactly and the same way every time. It cannot repair a wrong formula or a wrong choice of numbers. Another S3 error shows this in run 2 (Q-11): the three divisions were right (314.7, 368.2, 370.8), but the model subtracted Ashgrove minus Redfen, then answered `Ashgrove | 2.592`, a number that no calculate call returned (it is 370.8 - 368.2, the Q-04 gap, done in its head).


**Rounds and tokens in S3.** In the Q-09 test run the loop needed 4 model calls for 7 tool calls: first the four lookups (independent, so the model sent them together), then the two divisions (they need the lookup values), then the subtraction (it needs both division results), then the final answer. The number of rounds is the length of the longest chain of dependent steps, not the number of tool calls. Each round costs more input tokens because the API keeps no memory: every request sends the whole conversation again, with all earlier tool calls and their results. The log (`model_calls`) shows 599, 877, 972 and 1026 input tokens for rounds 1 to 4 (3474 in total), while the output stayed small: 103, 57, 31 and 33 tokens.

### C3 — Which strategy I would use, and what would change it

I would use S3 (tools). It got 18/20 in both runs, for about $0.017 and a median of about 6 to 7 seconds per question.

I did not choose S1: it is the cheapest ($0.0092) and the fastest (about 1.6 s), but it got only 2 and 3 out of 20, because it must answer with no room to calculate. I did not choose S2: it got 16 and 17 out of 20, cost $0.0610 (about 3.5 times S3) and took about 12 s per question.

The principles behind this: S2 samples 5 times, which reduces random variance (a slip in one sample gets outvoted), but it costs 5 times the input tokens and does nothing against an error that every sample shares, as in Q-05. The calculator makes arithmetic exact, so what is left for the model is choosing the numbers and the formula, but the tool does not check that choice (Q-14).

What would change my choice:

1. With no arithmetic and a small budget or a strict time limit I would use S1, because there the calculator gives nothing.
2. With 1000 times more documents, S1 and S2 could not fit them in the prompt, so I would use S3 with a real search index behind `lookup`.
3. With many unit questions like Q-14 (4852.761 instead of 4.9 in both runs) I would add a units check to S3 and compare it with S2 again.

### C4 — How sure I can be

Between run 1 and run 2 the right/wrong mark changed for 1 question in S1 (Q-13), 1 in S2 (Q-17) and 2 in S3 (Q-03, Q-11). S1 against the other two is far outside this noise (2 to 3 correct against 16 to 18). S3 against S2 is not: S3 was ahead by 2 questions in run 1 and by 1 in run 2, the same size as the run-to-run change, and it depends on the question (S3 only was right on Q-05, Q-12 and Q-20 in both runs, S2 only was right on Q-14 in both runs). So I can say S3 is cheaper (about 3.5 times) and faster, but not that it is more accurate than S2.

To trust a gap of one question in twenty I would need about 100 questions and 3 to 5 runs per strategy (my own estimate). Limits: 20 questions about one invented region, two runs, one model with reasoning switched off and temperature 1.0, my own scoring rule (S2 passes Q-14 with 4.829 against 4.9 only because of the 1-in-the-last-digit tolerance), and no cached-input discount in the costs.

### Final questions

1. Nothing has run yet. The model only sent a request to call a function; my code runs the function (`execute_tool_call`) and sends the result back as a `tool` message with the same `tool_call_id`.
2. The model produces text, so `arguments` is a JSON string and the API does not check it. If I pass it straight into the function, broken JSON or wrong argument names crash the loop, so I use `json.loads` in try/except, check the names and send an error message back to the model.
3. The two definitions add 443 tokens (572 with them, 129 without, measured with `measure_tools.py`). S3 sends them again in every round (3 to 4 per question), so about 1,300 to 1,800 tokens per question.
4. S2 cost $0.0610 and S1 cost $0.0092, so S2 was 6.6 times more expensive. It makes 5 calls with all documents (5.0 times the input tokens) and it also writes its reasoning, and output tokens cost more than input tokens.
5. The most was 4 rounds, with many ties (for example Q-09). In Q-09 round 1 was four lookups, round 2 two density calculations, round 3 the difference and round 4 the answer; the model used an extra round because it calculated the parts first and the difference after.
6. I would parse the documents once into an index (district, field, value, source id) instead of at every call. I would also use a real search (BM25 or embeddings) for names instead of `difflib`, and handle archived profiles, corrections and units when building the index.
7. `calculate` uses `ast` and accepts only numbers, + - * / ** and brackets, so `__import__(...)` and `(1).__class__` are refused, and the limits on exponent (100) and result (1e18) stop `9**9**9`. The model can still send a valid but wrong formula, as in Q-14 where the answer was 4852.761 instead of 4.9.
8. Tools helped most with long arithmetic: on Q-05, Q-12 and Q-20 S3 was right in both runs and S2 was wrong. They did not help when the mistake was in the formula or units: in Q-14 (both runs) and Q-03 (run 1) S3 gave an answer 1000 times too big.