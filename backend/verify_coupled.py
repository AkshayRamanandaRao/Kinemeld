"""Real two-body verification and oscillator time-step convergence measurement."""

import copy
import json
from pathlib import Path

import models
import solver


def errors_at_shared_times(actual, reference, key):
    indexed = {round(row["time"],8): row for row in reference}
    return [abs(row[key]-indexed[round(row["time"],8)][key]) for row in actual if round(row["time"],8) in indexed]


def main():
    report = {"ok": False, "solver": solver.status(), "coupled": [], "oscillatorRefinement": []}
    for variant in (False, True):
        model = copy.deepcopy(models.DOUBLE_PENDULUM)
        if variant:
            model["parameters"].update(mass1=0.8,mass2=0.35,length1=1.7,length2=0.9,angle1=-10,angle2=35)
            model["simulation"]["step"] = 0.0025
        result, code = solver.run(model)
        assert code == 200 and result["ok"], result
        reference = models.preview(model)
        error1 = max(errors_at_shared_times(result["samples"],reference,"angle"))
        error2 = max(errors_at_shared_times(result["samples"],reference,"angle2"))
        check = {"variant":variant,"runId":result["runId"],"model":model,"maxAngle1ErrorDeg":error1,"maxAngle2ErrorDeg":error2,"maxLinkConstraintErrorM":result["metrics"]["maxConstraintError"],"relativeEnergyChange":abs(result["metrics"]["finalEnergy"]/result["metrics"]["initialEnergy"]-1)}
        assert abs(result["samples"][0]["angle"]-model["parameters"]["angle1"]) < 0.001
        assert abs(result["samples"][0]["angle2"]-model["parameters"]["angle2"]) < 0.001
        assert max(error1,error2) < 1, check
        assert check["maxLinkConstraintErrorM"] < 1e-5, check
        assert check["relativeEnergyChange"] < 0.01, check
        report["coupled"].append(check)
    for step in (0.005, 0.0025):
        model = copy.deepcopy(next(e["model"] for e in models.EXAMPLES if e["id"] == "mass-spring"))
        model["simulation"]["step"] = step
        result, code = solver.run(model)
        assert code == 200 and result["ok"], result
        reference = models.preview(model)
        error = max(errors_at_shared_times(result["samples"],reference,"value"))
        normalized = error/abs(model["parameters"]["displacement"])
        report["oscillatorRefinement"].append({"step":step,"runId":result["runId"],"maxErrorM":error,"relativeToInitialDisplacement":normalized,"withinOnePercentTarget":normalized <= 0.01})
    coarse,fine = report["oscillatorRefinement"]
    report["oscillatorErrorReductionFactor"] = coarse["maxErrorM"]/fine["maxErrorM"]
    assert fine["maxErrorM"] < coarse["maxErrorM"]/2
    report["ok"] = True
    path = Path(__file__).with_name("evidence") / "coupled-and-convergence.json"
    path.write_text(json.dumps(report,indent=2),encoding="utf-8")
    print(json.dumps(report,indent=2))


if __name__ == "__main__":
    main()
