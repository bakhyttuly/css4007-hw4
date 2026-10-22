"""The three strategies: S1 direct, S2 think and vote, S3 tools.

All three use the same model, the same questions, the same answer format and the
same base system prompt. Only the strategy-specific part changes.
"""

import json
import os
import re
import time
from pathlib import Path

from dotenv import load_dotenv
from openai import BadRequestError, OpenAI

import tools

load_dotenv()

# ------------------------------------------------------------------ settings
MODEL = "gpt-5.6-luna"
TEMPERATURE = 1.0       # same for all strategies; dropped for all if the model refuses it
REASONING_EFFORT = "none"   # this model refuses function tools with hidden reasoning, so all three run without it
S2_K = 5                # number of samples in S2
MAX_ROUNDS = 10         # S3: at most this many model calls per question

CORPUS_PATH = Path(__file__).parent / "data" / "corpus.jsonl"

BASE_SYSTEM_PROMPT = (
    "You answer questions about the Nine Rivers Region. Use only the information you are given. "
    "End your reply with one final line in exactly this format:\n"
    "ANSWER: <name or yes/no> | <number>\n"
    "<name> is a district name, or yes/no for a yes/no question. <number> is a plain number "
    "without thousands separators and without units, with at most 3 decimal places. "
    "Do not round before the final step."
)

S1_SUFFIX = "Answer directly. Reply with only the final ANSWER line."
S2_SUFFIX = "Think step by step and show your calculations, then give the final ANSWER line."
S3_SUFFIX = ("You have no documents. Use the lookup tool to get facts and the calculate tool "
             "for all arithmetic. Then give the final ANSWER line.")

ANSWER_RE = re.compile(r"ANSWER:\s*(.+?)\s*\|\s*(-?[\d,]*\.?\d+)", re.IGNORECASE)

# What each tool must receive, checked before running anything.
EXPECTED_ARGUMENTS = {
    "lookup": {"district", "field"},
    "calculate": {"expression"},
}

_temperature_ok = True


def temperature_in_use():
    return TEMPERATURE if _temperature_ok else None


def get_client():
    if not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit("OPENAI_API_KEY is not set. Put it in .env (see .env.example).")
    return OpenAI()


def documents_block():
    with open(CORPUS_PATH, encoding="utf-8") as f:
        docs = [json.loads(line) for line in f if line.strip()]
    return "\n\n".join(f"[{d['id']}] {d['title']}\n{d['text']}" for d in docs)


def parse_answer(text):
    """Return (name, number) from the last ANSWER line, or None."""
    matches = ANSWER_RE.findall(text or "")
    if not matches:
        return None
    name, number = matches[-1]
    try:
        value = float(number.replace(",", ""))
    except ValueError:
        return None
    return name.strip().strip("*`_ ").strip(), value


def chat(client, messages, tool_definitions=None):
    """One model call. Returns (response, seconds). Drops temperature if the model refuses it."""
    global _temperature_ok
    while True:
        kwargs = {"model": MODEL, "messages": messages, "reasoning_effort": REASONING_EFFORT}
        if tool_definitions:
            kwargs["tools"] = tool_definitions
        if _temperature_ok:
            kwargs["temperature"] = TEMPERATURE
        start = time.perf_counter()
        try:
            response = client.chat.completions.create(**kwargs)
        except BadRequestError as exc:
            if _temperature_ok and "temperature" in str(exc).lower():
                _temperature_ok = False
                print("NOTE: the model does not accept 'temperature'; running without it.")
                continue
            raise
        return response, time.perf_counter() - start


def _new_result(strategy):
    return {
        "strategy": strategy,
        "final_text": "",
        "answer": None,          # [name, number] or None
        "unanswered": True,
        "input_tokens": 0,
        "output_tokens": 0,
        "seconds": 0.0,
    }


def _add_usage(result, response, seconds):
    usage = response.usage
    result["input_tokens"] += usage.prompt_tokens
    result["output_tokens"] += usage.completion_tokens
    result["seconds"] += seconds


# ------------------------------------------------------------------------ S1
def run_s1(client, question):
    result = _new_result("S1")
    messages = [
        {"role": "system", "content": f"{BASE_SYSTEM_PROMPT} {S1_SUFFIX}"},
        {"role": "user", "content": f"Documents:\n\n{documents_block()}\n\nQuestion: {question}"},
    ]
    response, seconds = chat(client, messages)
    _add_usage(result, response, seconds)
    text = response.choices[0].message.content or ""
    answer = parse_answer(text)
    result.update(final_text=text, answer=list(answer) if answer else None, unanswered=answer is None)
    return result


# ------------------------------------------------------------------------ S2
VOTE_TOLERANCE = 0.01   # two samples agree if the name is the same and the numbers differ by <= 1%


def _cluster_samples(samples):
    """Group samples that give the same name and (almost) the same number."""
    clusters = []
    for sample in samples:
        if not sample["answer"]:
            continue
        name, number = sample["answer"]
        for cluster in clusters:
            if (cluster["name"] == name.lower()
                    and abs(number - cluster["number"]) <= VOTE_TOLERANCE * abs(cluster["number"]) + 1e-12):
                cluster["members"].append(sample)
                break
        else:
            clusters.append({"name": name.lower(), "number": number, "members": [sample]})
    return clusters


def run_s2(client, question):
    result = _new_result("S2")
    messages = [
        {"role": "system", "content": f"{BASE_SYSTEM_PROMPT} {S2_SUFFIX}"},
        {"role": "user", "content": f"Documents:\n\n{documents_block()}\n\nQuestion: {question}"},
    ]
    samples = []
    for _ in range(S2_K):
        response, seconds = chat(client, messages)
        _add_usage(result, response, seconds)
        text = response.choices[0].message.content or ""
        answer = parse_answer(text)
        samples.append({"final_text": text, "answer": list(answer) if answer else None})
    result["samples"] = samples

    clusters = _cluster_samples(samples)
    if clusters:
        winner = max(clusters, key=lambda c: len(c["members"]))   # ties: the group seen first wins
        chosen = winner["members"][0]
        result.update(final_text=chosen["final_text"], answer=chosen["answer"], unanswered=False)
        result["votes"] = {f"{c['name']} | {c['number']}": len(c["members"]) for c in clusters}
    return result


# ------------------------------------------------------------------------ S3
def execute_tool_call(tool_call, round_number):
    """Check the arguments, run the tool, return (result_dict, log_entry). Never raises."""
    name = tool_call.function.name
    raw = tool_call.function.arguments
    start = time.perf_counter()
    try:
        arguments = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        arguments = None
        outcome = {"error": "arguments must be a valid JSON object"}
    else:
        if name not in tools.TOOL_FUNCTIONS:
            outcome = {"error": f"unknown tool '{name}'"}
        elif not isinstance(arguments, dict):
            outcome = {"error": "arguments must be a JSON object"}
        elif set(arguments) != EXPECTED_ARGUMENTS[name]:
            expected = ", ".join(sorted(EXPECTED_ARGUMENTS[name]))
            outcome = {"error": f"{name} needs exactly these arguments: {expected}"}
        else:
            outcome = tools.TOOL_FUNCTIONS[name](**arguments)
    entry = {
        "round": round_number,
        "tool_call_id": tool_call.id,
        "tool": name,
        "arguments_raw": raw,
        "result": outcome,
        "seconds": round(time.perf_counter() - start, 6),
    }
    return outcome, entry


def run_s3(client, question):
    result = _new_result("S3")
    messages = [
        {"role": "system", "content": f"{BASE_SYSTEM_PROMPT} {S3_SUFFIX}"},
        {"role": "user", "content": f"Question: {question}"},
    ]
    tool_log = []
    model_calls = []
    rounds = 0
    for round_number in range(1, MAX_ROUNDS + 1):
        rounds = round_number
        response, seconds = chat(client, messages, tools.TOOL_DEFINITIONS)
        _add_usage(result, response, seconds)
        model_calls.append({
            "round": round_number,
            "input_tokens": response.usage.prompt_tokens,
            "output_tokens": response.usage.completion_tokens,
            "seconds": round(seconds, 3),
        })
        message = response.choices[0].message
        messages.append(message)                      # the model's message, unchanged
        if not message.tool_calls:
            text = message.content or ""
            answer = parse_answer(text)
            result.update(final_text=text, answer=list(answer) if answer else None,
                          unanswered=answer is None)
            break
        for tool_call in message.tool_calls:          # every tool_call_id gets a reply
            outcome, entry = execute_tool_call(tool_call, round_number)
            tool_log.append(entry)
            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": json.dumps(outcome),
            })
    else:
        result["hit_round_limit"] = True              # still asking for tools: unanswered
    result["rounds"] = rounds
    result["tool_log"] = tool_log
    result["model_calls"] = model_calls
    result["conversation"] = [_message_as_dict(m) for m in messages]   # to compare with A3
    return result


def _message_as_dict(message):
    """Plain-dict copy of a message, only for saving to the log."""
    if isinstance(message, dict):
        return message
    if hasattr(message, "model_dump"):
        return message.model_dump(exclude_none=True)
    calls = [{"id": c.id, "type": "function",
              "function": {"name": c.function.name, "arguments": c.function.arguments}}
             for c in (message.tool_calls or [])]
    return {"role": "assistant", "content": message.content, **({"tool_calls": calls} if calls else {})}


STRATEGIES = {"S1": run_s1, "S2": run_s2, "S3": run_s3}