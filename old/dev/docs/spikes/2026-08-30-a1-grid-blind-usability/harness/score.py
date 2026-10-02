"""Score a blind run's answer against the ground truth.

Usage: score.py <truth.json> <task-id> <answer-file>

A `region` task is scored as a SET: precision, recall, F1 over actor names, plus exact-match.
A `locate` task is scored by hand — this prints the truth cell so the reader can judge the prose.
"""

import json
import sys
from pathlib import Path


def main(truth_path: str, task_id: str, answer_path: str) -> None:
    truth = set(json.loads(Path(truth_path).read_text())[task_id])
    raw = Path(answer_path).read_text().strip()
    if raw == "UNKNOWN":
        print(f"{task_id}: UNKNOWN (no answer) — truth n={len(truth)}")
        return

    got = {ln.strip() for ln in raw.splitlines() if ln.strip()}
    hit = got & truth
    precision = len(hit) / len(got) if got else 0.0
    recall = len(hit) / len(truth) if truth else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    print(f"{task_id}: exact={got == truth}  P={precision:.2f} R={recall:.2f} F1={f1:.2f}"
          f"  (got {len(got)}, truth {len(truth)})")
    if missed := sorted(truth - got):
        print(f"  missed: {missed}")
    if spurious := sorted(got - truth):
        print(f"  spurious: {spurious}")


if __name__ == "__main__":
    main(*sys.argv[1:4])
