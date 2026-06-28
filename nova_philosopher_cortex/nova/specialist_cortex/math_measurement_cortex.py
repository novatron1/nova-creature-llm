"""Math & Measurement Cortex - mathematical reasoning and calculation."""
import re
from nova.specialist_cortex.base import SpecialistCortex
from nova.schema import MeaningPacket, SpecialistResult, UncertaintyLevel


class MathMeasurementCortex(SpecialistCortex):
    name = "math_cortex"

    def analyze(self, packet: MeaningPacket) -> SpecialistResult:
        result = SpecialistResult(
            module_name=self.name,
            uncertainty=UncertaintyLevel.HIGH_CONFIDENCE,
        )

        text = packet.cleaned_text
        extracted = self._extract_problem(text)
        result.findings.append("Math problem type: %s" % extracted["type"])

        # Try to solve
        solution = self._solve(extracted)
        if solution:
            result.analysis = solution
            result.confidence = 0.95

        return result

    def _extract_problem(self, text: str) -> dict:
        """Extract math problem parameters from text."""
        problem = {"type": "unknown", "numbers": [], "units": []}

        # Speed/distance/time problems
        speed_match = re.search(
            r'(\d+[.,]?\d*)\s*(miles|km|kilometers|meters)\s+'
            r'(in|per|over|for|within|after)\s+'
            r'(\d+[.,]?\d*)\s*(hours|minutes|seconds|hrs|hr|h)',
            text.lower()
        )
        if speed_match:
            problem["type"] = "speed_distance_time"
            problem["distance"] = float(speed_match.group(1).replace(",", ""))
            problem["distance_unit"] = speed_match.group(2)
            problem["time"] = float(speed_match.group(4).replace(",", ""))
            problem["time_unit"] = speed_match.group(5)
            problem["unknown"] = "speed"
            return problem

        # Direct speed question
        travel_match = re.search(
            r'travels?\s+(\d+[.,]?\d*)\s*(miles|km|kilometers)\s+'
            r'in\s+(\d+[.,]?\d*)\s*(hours|minutes|hrs)',
            text.lower()
        )
        if travel_match:
            problem["type"] = "speed_distance_time"
            problem["distance"] = float(travel_match.group(1).replace(",", ""))
            problem["distance_unit"] = travel_match.group(2)
            problem["time"] = float(travel_match.group(3).replace(",", ""))
            problem["time_unit"] = travel_match.group(4)
            problem["unknown"] = "speed"
            return problem

        # Look for any numbers with units for simpler problems
        numbers = re.findall(r'(\d+[.,]?\d*)', text)
        problem["numbers"] = [float(n.replace(",", "")) for n in numbers]

        unit_keywords = ["miles", "km", "kilometers", "meters", "hours", "minutes",
                         "seconds", "kg", "g", "lbs", "mph", "kmh", "dollars", "$"]
        problem["units"] = [u for u in unit_keywords if u in text.lower()]

        return problem

    def _solve(self, problem: dict) -> str:
        """Solve the extracted problem."""
        if problem["type"] == "speed_distance_time":
            return self._solve_speed(problem)
        return ""

    def _solve_speed(self, problem: dict) -> str:
        """Solve speed = distance / time, with correct unit singularization."""
        distance = problem.get("distance", 0)
        time = problem.get("time", 1)
        dist_unit = problem.get("distance_unit", "units")
        time_unit = problem.get("time_unit", "hours")

        if time == 0:
            return "Error: time cannot be zero."

        speed = distance / time

        # Singularize time unit for speed: "miles/hour" not "miles/hours"
        time_unit_singular = time_unit.rstrip("s") if time_unit.endswith("s") else time_unit
        speed_unit = "%s/%s" % (dist_unit, time_unit_singular)

        lines = [
            "=== Math & Measurement Analysis ===",
            "",
            "Problem: Calculate speed from distance and time",
            "",
            "Formula: speed = distance / time",
            "",
            "Given:",
            "  distance = %g %s" % (distance, dist_unit),
            "  time = %g %s" % (time, time_unit),
            "",
            "Calculation:",
            "  speed = %g / %g" % (distance, time),
            "  speed = %g %s" % (speed, speed_unit),
            "",
            "Answer: %g %s" % (speed, speed_unit),
        ]
        return "\n".join(lines)
