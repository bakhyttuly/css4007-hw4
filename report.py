"""Print the tables for SUBMISSION.md from the saved results in outputs/.

    python report.py 1        summary rows, per-question table and wrong answers for run 1
    python report.py 1 2      summary rows for runs 1 and 2 (the per-question part uses the first run)
"""

import json
import sys
from pathlib import Path

OUT = Path("outputs")
QUESTIONS = json.loads((Path(__file__).parent / "data" / "questions.json").read_text(encoding="utf-8"))
LABELS = {"S1": "S1 direct", "S2": "S2 think and vote (k = 5)", "S3": "S3 tools"}


def load(run, strategy, name):
    path = OUT / f"run-{run}" / strategy / name
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def main():
    runs = sys.argv[1:] or ["1"]

    print("| Run | Strategy | Correct /20 | Unanswered | Input tokens | Output tokens | "
          "Median seconds per question | Total seconds | Cost ($) |")
    print("|---|---|---:|---:|---:|---:|---:|---:|---:|")
    for run in runs:
        for s in ("S1", "S2", "S3"):
            d = load(run, s, "summary.json")
            if d is None:
                print(f"| {run} | {LABELS[s]} | (no results) | | | | | | |")
                continue
            cost = "n/a" if d["cost_usd"] is None else f"{d['cost_usd']:.4f}"
            print(f"| {run} | {LABELS[s]} | {d['correct']} | {d['unanswered']} | {d['input_tokens']} | "
                  f"{d['output_tokens']} | {d['median_seconds_per_question']} | {d['total_seconds']} | {cost} |")

    first = runs[0]
    print(f"\nPer question (run {first}):\n")
    print("| Question | S1 | S2 | S3 |")
    print("|---|:---:|:---:|:---:|")
    wrong = []
    for q in QUESTIONS:
        marks = []
        for s in ("S1", "S2", "S3"):
            d = load(first, s, f"{q['id']}.json")
            if d is None:
                marks.append("-")
            elif d["correct"]:
                marks.append("✓")
            else:
                marks.append("✗")
                wrong.append((s, d, q))
        print(f"| {q['id']} | {marks[0]} | {marks[1]} | {marks[2]} |")

    print(f"\nWrong answers in run {first} (strategy, question, what the model said, expected, rounds):")
    for s, d, q in wrong:
        rounds = d.get("rounds", "")
        print(f"  {s} {q['id']}  model={d['answer']}  expected=[{q['answer']}, {q['value']}]  "
              f"rounds={rounds}  error={d.get('error')}")


if __name__ == "__main__":
    main()