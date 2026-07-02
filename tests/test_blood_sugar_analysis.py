import csv
import os
import tempfile
import unittest

from blood_sugar_analysis import analyze_blood_sugar, calculate_metrics, find_unusual_values


class BloodSugarAnalysisTests(unittest.TestCase):
    def test_calculate_metrics(self):
        metrics = calculate_metrics([90.0, 110.0, 130.0])
        self.assertEqual(metrics["count"], 3)
        self.assertEqual(metrics["average"], 110.0)
        self.assertEqual(metrics["minimum"], 90.0)
        self.assertEqual(metrics["maximum"], 130.0)

    def test_find_unusual_values(self):
        unusual = find_unusual_values([65.0, 80.0, 190.0])
        self.assertEqual(
            unusual,
            [
                {"index": 1, "value": 65.0},
                {"index": 3, "value": 190.0},
            ],
        )

    def test_analyze_blood_sugar_reads_csv_with_header(self):
        with tempfile.NamedTemporaryFile("w", newline="", delete=False) as csv_file:
            writer = csv.DictWriter(csv_file, fieldnames=["timestamp", "blood_sugar"])
            writer.writeheader()
            writer.writerow({"timestamp": "08:00", "blood_sugar": "85"})
            writer.writerow({"timestamp": "12:00", "blood_sugar": "200"})
            csv_path = csv_file.name

        try:
            analysis = analyze_blood_sugar(csv_path)
            self.assertEqual(analysis["levels"], [85.0, 200.0])
            self.assertEqual(len(analysis["unusual_values"]), 1)
            self.assertEqual(analysis["unusual_values"][0]["value"], 200.0)
        finally:
            os.remove(csv_path)


if __name__ == "__main__":
    unittest.main()
