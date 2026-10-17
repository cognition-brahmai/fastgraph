"""Aggregate raw benchmark samples without inventing distributions or deleting outliers."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import statistics


def quantile(values, q):
    ordered = sorted(values)
    position = (len(ordered) - 1) * q
    left = int(position)
    right = min(left + 1, len(ordered) - 1)
    return ordered[left] + (ordered[right] - ordered[left]) * (position - left)


def summarize(values):
    average = statistics.mean(values)
    deviation = statistics.stdev(values) if len(values) > 1 else 0.0
    return {
        "n": len(values),
        "median": statistics.median(values),
        "mean": average,
        "min": min(values),
        "max": max(values),
        "q25": quantile(values, 0.25),
        "q75": quantile(values, 0.75),
        "stddev": deviation,
        "cv_percent": deviation / average * 100 if average else None,
    }


def aggregate(sources):
    groups = {}
    samples = []
    replacements = {}
    for source in sources:
        data = json.loads(source.read_text(encoding="utf-8"))
        for sample in data["samples"]:
            job = sample["job"]
            identity = job["case"], job["engine"], job["repeat"]
            replacements[identity] = sample
            samples.append(sample)
    retained = list(replacements.values())
    for sample in retained:
        if sample["status"] != "ok":
            continue
        job = sample["job"]
        group = groups.setdefault(
            (job["case"], job["engine"]),
            {
                "case": job["case"],
                "engine": job["engine"],
                "kind": job["kind"],
                "options": {
                    key: value
                    for key, value in job.items()
                    if key not in {"repeat", "scratch", "started_utc", "engine", "kind", "case"}
                },
                "raw": [],
            },
        )
        group["raw"].append(sample)
    output = []
    rows = []
    for group in groups.values():
        raw = group.pop("raw")
        fields = {}
        for sample in raw:
            for name, metric in sample["metrics"].items():
                for key, value in metric.items():
                    if isinstance(value, (float, int)) and not isinstance(value, bool):
                        fields.setdefault((name, key), []).append(value)
                for stage in ("memory_before", "memory_after"):
                    for key, value in metric.get(stage, {}).items():
                        fields.setdefault((name, stage + "." + key), []).append(value)
            for key, value in sample["details"].items():
                if isinstance(value, (float, int)) and not isinstance(value, bool):
                    fields.setdefault(("details", key), []).append(value)
                if isinstance(value, dict):
                    for field, item in value.items():
                        if isinstance(item, (float, int)) and not isinstance(item, bool):
                            fields.setdefault(("details", key + "." + field), []).append(item)
            fields.setdefault(("process", "import_ms"), []).append(sample["import_ms"])
            fields.setdefault(("process", "worker_wall_s"), []).append(sample["worker_wall_s"])
        group["sample_count"] = len(raw)
        group["statistics"] = {}
        for (metric, value), values in fields.items():
            stats = summarize(values)
            group["statistics"].setdefault(metric, {})[value] = stats
            rows.append(
                {
                    "case": group["case"],
                    "kind": group["kind"],
                    "engine": group["engine"],
                    "metric": metric,
                    "field": value,
                    **stats,
                }
            )
        output.append(group)
    return output, rows, retained, len(samples) - len(retained)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sources", nargs="+", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    groups, rows, samples, superseded = aggregate(args.sources)
    statuses = {
        status: sum(sample["status"] == status for sample in samples)
        for status in sorted({sample["status"] for sample in samples})
    }
    result = {
        "sources": [str(path) for path in args.sources],
        "sample_statuses": statuses,
        "fresh_processes": len(samples),
        "superseded_samples": superseded,
        "replacement_policy": "Later sources replace same case/engine/repeat; original raw files retained",
        "groups": groups,
    }
    (args.output / "summary.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    with (args.output / "summary.csv").open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(
        json.dumps(
            {
                "samples": statuses,
                "groups": len(groups),
                "scalar_statistics": len(rows),
                "output": str(args.output),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
