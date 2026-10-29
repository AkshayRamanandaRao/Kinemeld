"""Show that the constraint-rank diagnostic predicts MBDyn's behaviour on closed loops.

Usage: python -B backend/verify_constraint_analysis.py
"""
import constraint_analysis
import solver
from test_constraint_analysis import four_bar


def main():
    for closing, expected in (("revolute", False), ("spherical", False), ("universal", True)):
        model = four_bar(closing)
        analysis = constraint_analysis.analyse(model)
        result, _ = solver.run(model)
        predicted = not analysis["redundant"]
        if bool(result.get("ok")) != expected or predicted != expected:
            raise AssertionError(f"{closing} closure: analysis predicted {'success' if predicted else 'failure'}, MBDyn ok={result.get('ok')}")
        print(f"PASS four-bar with {closing} closure: Grübler {analysis['grubler']}, rank mobility {analysis['dof']}, "
              f"{len(analysis['redundant'])} redundant row(s); MBDyn {'solved' if result.get('ok') else 'rejected'} it as predicted.")


if __name__ == "__main__":
    main()
