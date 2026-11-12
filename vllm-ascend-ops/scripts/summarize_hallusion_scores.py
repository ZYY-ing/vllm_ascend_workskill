"""Summarize completed HallusionBench judge caches without API calls or dependencies."""
import argparse
import csv
import json
from pathlib import Path

ID_FIELDS = ("category", "subcategory", "set_id", "figure_id", "question_id")


def identity(row):
    return tuple(str(row[k]) for k in ID_FIELDS)


def load_rows(path):
    rows = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(rows, list):
        raise ValueError(f"Expected a JSON array: {path}")
    return rows


def summarize(evaluation_dir):
    base = Path(evaluation_dir)
    expected = load_rows(base / "HallusionBench_result.json")
    cached = load_rows(base / "hallusion_output_vd_model.json")
    cached += load_rows(base / "hallusion_output_vs_model.json")
    if not expected:
        raise ValueError("Empty inference result")
    expected_by_id = {identity(row): row for row in expected}
    cached_by_id = {identity(row): row for row in cached}
    if len(expected_by_id) != len(expected) or len(cached_by_id) != len(cached):
        raise ValueError("Duplicate sample IDs in inference results or judge caches")
    if expected_by_id.keys() != cached_by_id.keys():
        raise ValueError("Judge cache is incomplete or belongs to different sample IDs")
    for key, row in cached_by_id.items():
        if row["model_prediction"] != expected_by_id[key]["model_prediction"]:
            raise ValueError("Judge cache belongs to different model predictions")
        for field in ("question", "gt_answer_details", "gt_answer", "visual_input"):
            if field in expected_by_id[key] and row.get(field) != expected_by_id[key][field]:
                raise ValueError(f"Judge cache differs from the input dataset: {field}")
        if row["category"] not in ("VS", "VD"):
            raise ValueError("Unrecognized HallusionBench category")
        if not isinstance(row["gpt4v_output_gpt_check"], (str, int)):
            raise ValueError("Invalid judge correctness label")
        label = int(row["gpt4v_output_gpt_check"])
        if label not in (0, 1, 2):
            raise ValueError("Invalid judge correctness label")
        # Official assign_correctness accepts uncertainty for VS no-figure baselines.
        row["correct"] = int(label == 1 or (
            row["category"] == "VS" and int(row["figure_id"]) == 0 and label == 2))
    groups = ["overall"] + [c for c in ("VS", "VD") if any(r["category"] == c for r in cached)]
    groups += sorted({r["category"] + "_" + r["subcategory"] for r in cached})
    scores, details = {}, []
    for group in groups:
        rows = [r for r in cached if group == "overall" or r["category"] == group
                or r["category"] + "_" + r["subcategory"] == group]
        correct = sum(r["correct"] for r in rows)
        value = 100 * correct / len(rows)
        scores[group] = round(value, 2)
        details.append(dict(split=group, correct=correct, total=len(rows), aAcc=round(value, 4)))
    (base / "scores.json").write_text(json.dumps(scores, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    metadata = dict(metric="aAcc", samples=len(cached),
                    no_visual_samples=sum(int(r["visual_input"]) == 0 for r in cached), rows=details,
                    note="Uses existing judge labels; completeness is relative to this inference run, not a fixed full dataset size. Judge identity must be recorded separately.")
    (base / "scores_details.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    with (base / "scores.csv").open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=["split", "correct", "total", "aAcc"])
        writer.writeheader()
        writer.writerows(details)
    return scores


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evaluation-dir", type=Path, default=Path("."),
                        help="Directory with inference result and both completed judge-cache JSON files")
    args = parser.parse_args()
    print(json.dumps(summarize(args.evaluation_dir), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
