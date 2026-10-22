"""Run the strategies on the questions and save everything to outputs/.

Examples:
    python run.py --run q09-test --questions Q-09 --strategies S3
    python run.py --run 1
    python run.py --run 2
"""

import argparse
import json
import statistics
from datetime import datetime, timezone
from pathlib import Path

from openai import AuthenticationError, NotFoundError, PermissionDeniedError

import strategies

QUESTIONS_PATH = Path(__file__).parent / "data" / "questions.json"

# USD per 1 million tokens. Fill these in from the OpenAI pricing page for your model.
PRICE_INPUT_PER_1M = 0.20
PRICE_OUTPUT_PER_1M = 1.20

# RULE FOR A CORRECT ANSWER (write the same rule in SUBMISSION.md before the first full run):
# the name must equal the expected name (case does not matter), and the number rounded to the
# question's `decimals` must be within 1 in the last digit of the expected value.


def is_correct(answer, question):
    if answer is None:
        return False
    name, number = answer
    if name.strip().lower() != question["answer"].strip().lower():
        return False
    decimals = question["decimals"]
    tolerance = 10 ** -decimals
    return abs(round(number, decimals) - question["value"]) <= tolerance * 1.0001


def cost_usd(input_tokens, output_tokens):
    if PRICE_INPUT_PER_1M is None or PRICE_OUTPUT_PER_1M is None:
        return None
    return input_tokens / 1e6 * PRICE_INPUT_PER_1M + output_tokens / 1e6 * PRICE_OUTPUT_PER_1M


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", required=True, help="label of this run, e.g. 1, 2 or q09-test")
    parser.add_argument("--strategies", nargs="+", default=["S1", "S2", "S3"], choices=list(strategies.STRATEGIES))
    parser.add_argument("--questions", nargs="+", help="question ids, default: all twenty")
    parser.add_argument("--out", default="outputs")
    args = parser.parse_args()

    questions = json.loads(QUESTIONS_PATH.read_text(encoding="utf-8"))
    if args.questions:
        questions = [q for q in questions if q["id"] in args.questions]
        if not questions:
            raise SystemExit("none of those question ids exist")

    client = strategies.get_client()

    for name in args.strategies:
        run_function = strategies.STRATEGIES[name]
        folder = Path(args.out) / f"run-{args.run}" / name
        folder.mkdir(parents=True, exist_ok=True)
        rows = []
        for q in questions:
            try:
                result = run_function(client, q["question"])
                result["error"] = None
            except (AuthenticationError, NotFoundError, PermissionDeniedError):
                raise  # wrong key or model not available: stop, do not burn through all questions
            except Exception as exc:  # one bad question must not kill the whole run
                result = strategies._new_result(name)
                result["error"] = f"{type(exc).__name__}: {exc}"
            result["question_id"] = q["id"]
            result["question"] = q["question"]
            result["expected"] = {"answer": q["answer"], "value": q["value"], "decimals": q["decimals"]}
            result["correct"] = is_correct(result["answer"], q)
            (folder / f"{q['id']}.json").write_text(
                json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
            rows.append(result)
            mark = "OK " if result["correct"] else "BAD"
            extra = f" rounds={result['rounds']}" if "rounds" in result else ""
            print(f"{name} {q['id']} {mark} answer={result['answer']} "
                  f"tokens={result['input_tokens']}/{result['output_tokens']} "
                  f"{result['seconds']:.1f}s{extra}" + (f" ERROR={result['error']}" if result["error"] else ""))

        input_tokens = sum(r["input_tokens"] for r in rows)
        output_tokens = sum(r["output_tokens"] for r in rows)
        summary = {
            "run": args.run,
            "strategy": name,
            "questions": len(rows),
            "correct": sum(r["correct"] for r in rows),
            "unanswered": sum(r["unanswered"] for r in rows),
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "median_seconds_per_question": round(statistics.median(r["seconds"] for r in rows), 2),
            "total_seconds": round(sum(r["seconds"] for r in rows), 1),
            "cost_usd": cost_usd(input_tokens, output_tokens),
            "settings": {
                "model": strategies.MODEL,
                "temperature": strategies.temperature_in_use(),
                "s2_k": strategies.S2_K,
                "max_rounds": strategies.MAX_ROUNDS,
            },
            "finished_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        (folder / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
        print(f"== {name}: {summary['correct']}/{summary['questions']} correct, "
              f"unanswered {summary['unanswered']}, tokens {input_tokens}/{output_tokens}, "
              f"median {summary['median_seconds_per_question']}s, total {summary['total_seconds']}s, "
              f"cost {summary['cost_usd']}")


if __name__ == "__main__":
    main()