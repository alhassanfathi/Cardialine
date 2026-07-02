import argparse
import csv
from statistics import mean


LOW_BLOOD_SUGAR_THRESHOLD = 70.0
HIGH_BLOOD_SUGAR_THRESHOLD = 180.0


def _parse_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def read_blood_sugar_levels(csv_path):
    levels = []
    with open(csv_path, newline="", encoding="utf-8") as csv_file:
        reader = csv.DictReader(csv_file)
        if reader.fieldnames and "blood_sugar" in reader.fieldnames:
            for row in reader:
                value = row.get("blood_sugar")
                if value in (None, ""):
                    continue
                parsed_value = _parse_float(value)
                if parsed_value is None:
                    continue
                levels.append(parsed_value)
            return levels

        csv_file.seek(0)
        fallback_reader = csv.reader(csv_file)
        for row in fallback_reader:
            if not row:
                continue
            parsed_value = _parse_float(row[0])
            if parsed_value is None:
                continue
            levels.append(parsed_value)
    return levels


def find_unusual_values(levels):
    return [
        {"index": index, "value": value}
        for index, value in enumerate(levels, start=1)
        if value < LOW_BLOOD_SUGAR_THRESHOLD or value > HIGH_BLOOD_SUGAR_THRESHOLD
    ]


def calculate_metrics(levels):
    if not levels:
        return {"count": 0, "average": None, "minimum": None, "maximum": None}

    return {
        "count": len(levels),
        "average": mean(levels),
        "minimum": min(levels),
        "maximum": max(levels),
    }


def analyze_blood_sugar(csv_path):
    levels = read_blood_sugar_levels(csv_path)
    metrics = calculate_metrics(levels)
    unusual_values = find_unusual_values(levels)
    return {"levels": levels, "metrics": metrics, "unusual_values": unusual_values}


def display_results(analysis):
    metrics = analysis["metrics"]
    print("Blood sugar analysis")
    print("--------------------")
    print(f"Readings count: {metrics['count']}")

    if metrics["count"] == 0:
        print("No blood sugar readings found.")
        return

    print(f"Average: {metrics['average']:.2f}")
    print(f"Minimum: {metrics['minimum']:.2f}")
    print(f"Maximum: {metrics['maximum']:.2f}")
    print("")
    print("Unusual values (outside 70-180 mg/dL):")

    unusual_values = analysis["unusual_values"]
    if not unusual_values:
        print("None")
        return

    for entry in unusual_values:
        print(f"- Reading {entry['index']}: {entry['value']:.2f}")


def main():
    parser = argparse.ArgumentParser(
        description="Read blood sugar levels from a CSV file and analyze them."
    )
    parser.add_argument("csv_path", help="Path to the CSV file.")
    args = parser.parse_args()

    analysis = analyze_blood_sugar(args.csv_path)
    display_results(analysis)


if __name__ == "__main__":
    main()
