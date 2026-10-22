"""Tables and numbers for SUBMISSION.md, built from the saved results in outputs/.

    python report.py 1 2

Writes outputs/report.md (UTF-8) with the summary table and the per-question tables.
Everything else (wrong answers, differences between runs, rounds, costs) is printed on screen.
"""

import json
import sys
from pathlib import Path

OUT = Path("outputs")
QUESTIONS = json.loads((Path(__file__).parent / "data" / "questions.json").read_text(encoding="utf-8"))
LABELS = {"S1": "S1 direct", "S2": "S2 think and vote (k = 5)", "S3": "S3 tools"}
STRATEGIES = ("S1", "S2", "S3")


def load(run, strategy, name):
    path = OUT / f"run-{run}" / strategy / name
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def correct_map(run, strategy):
    """question id -> True/False (None if there is no result file)."""
    result = {}
    for q in QUESTIONS:
        d = load(run, strategy, f"{q['id']}.json")
        result[q["id"]] = None if d is None else bool(d["correct"])
    return result


def build_markdown(runs):
    md = ["| Run | Strategy | Correct /20 | Unanswered | Input tokens | Output tokens | "
          "Median seconds per question | Total seconds | Cost ($) |",
          "|---|---|---:|---:|---:|---:|---:|---:|---:|"]
    for run in runs:
        for s in STRATEGIES:
            d = load(run, s, "summary.json")
            if d is None:
                md.append(f"| {run} | {LABELS[s]} | (no results) | | | | | | |")
                continue
            cost = "n/a" if d["cost_usd"] is None else f"{d['cost_usd']:.4f}"
            md.append(f"| {run} | {LABELS[s]} | {d['correct']} | {d['unanswered']} | {d['input_tokens']} | "
                      f"{d['output_tokens']} | {d['median_seconds_per_question']} | {d['total_seconds']} | {cost} |")
    for run in runs:
        marks = {s: correct_map(run, s) for s in STRATEGIES}
        md += ["", f"**Per question (run {run}):**", "", "| Question | S1 | S2 | S3 |", "|---|:---:|:---:|:---:|"]
        for q in QUESTIONS:
            cells = []
            for s in STRATEGIES:
                m = marks[s][q["id"]]
                cells.append("-" if m is None else ("✓" if m else "✗"))
            md.append(f"| {q['id']} | {cells[0]} | {cells[1]} | {cells[2]} |")
    return "\n".join(md) + "\n"


def print_extras(runs):
    print("\n--- WRONG ANSWERS (strategy, run, question, model said, expected, rounds)")
    for run in runs:
        for s in STRATEGIES:
            for q in QUESTIONS:
                d = load(run, s, f"{q['id']}.json")
                if d is not None and not d["correct"]:
                    print(f"  run {run} {s} {q['id']}  model={d['answer']}  "
                          f"expected=[{q['answer']}, {q['value']}]  rounds={d.get('rounds', '')}")

    print("\n--- COST (S2 compared with S1)")
    for run in runs:
        s1, s2 = load(run, "S1", "summary.json"), load(run, "S2", "summary.json")
        if s1 and s2 and s1["cost_usd"] and s2["cost_usd"]:
            print(f"  run {run}: S1 ${s1['cost_usd']:.4f}  S2 ${s2['cost_usd']:.4f}  "
                  f"S2/S1 cost = {s2['cost_usd'] / s1['cost_usd']:.1f}x, "
                  f"input tokens = {s2['input_tokens'] / s1['input_tokens']:.1f}x")

    print("\n--- S3 ROUNDS (most rounds per run)")
    for run in runs:
        rounds = {}
        for q in QUESTIONS:
            d = load(run, "S3", f"{q['id']}.json")
            if d is not None:
                rounds[q["id"]] = d.get("rounds", 0)
        if rounds:
            top = max(rounds.values())
            who = [qid for qid, r in rounds.items() if r == top]
            print(f"  run {run}: max {top} rounds, questions: {', '.join(who)}   (min {min(rounds.values())})")

    if len(runs) >= 2:
        a, b = runs[0], runs[1]
        print(f"\n--- DIFFERENCE BETWEEN RUN {a} AND RUN {b} (questions whose right/wrong mark changed)")
        for s in STRATEGIES:
            ma, mb = correct_map(a, s), correct_map(b, s)
            changed = [qid for qid in ma if ma[qid] is not None and mb[qid] is not None and ma[qid] != mb[qid]]
            print(f"  {s}: {len(changed)} changed {changed}")

    print("\n--- S2 vs S3 ON THE SAME QUESTIONS (per run)")
    for run in runs:
        m2, m3 = correct_map(run, "S2"), correct_map(run, "S3")
        both = sum(1 for q in m2 if m2[q] and m3[q])
        only3 = [q for q in m2 if m3[q] and m2[q] is False]
        only2 = [q for q in m2 if m2[q] and m3[q] is False]
        neither = [q for q in m2 if m2[q] is False and m3[q] is False]
        print(f"  run {run}: both right {both}, only S3 right {len(only3)} {only3}, "
              f"only S2 right {len(only2)} {only2}, both wrong {len(neither)} {neither}")


def main():
    runs = sys.argv[1:] or ["1"]
    OUT.mkdir(exist_ok=True)
    path = OUT / "report.md"
    path.write_text(build_markdown(runs), encoding="utf-8")
    print(f"Tables written to {path} (open it in VS Code, select all, copy).")
    print_extras(runs)


if __name__ == "__main__":
    main()