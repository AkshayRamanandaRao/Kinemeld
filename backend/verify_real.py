"""Verify physical results from the configured real MBDyn solver."""

import copy
import json
from pathlib import Path

import models
import solver


def main():
    info = solver.status()
    assert info["available"], info
    report = {"solver": info, "checks": [], "ok": False}
    baseline = [e for e in models.EXAMPLES if e["id"] in ("pendulum", "mass-spring", "double-pendulum")]
    for example in baseline:
        for variant in (False, True):
            model = copy.deepcopy(example["model"])
            if variant:
                model["simulation"]["step"] = 0.0025
                if model["kind"] == "pendulum":
                    model["parameters"].update(mass=2.3,length=1.7, angle=12)
                elif model["kind"] == "double-pendulum":
                    model["parameters"].update(mass1=0.8,mass2=0.35,length1=1.7,length2=0.9,angle1=-10,angle2=35)
                else:
                    model["parameters"].update(mass=2.3,stiffness=75, damping=1.2, displacement=0.17)
            result, code = solver.run(model)
            item = {"kind":model["kind"],"variant":variant,"runId":result.get("runId"),"httpStatus":code,"ok":result["ok"]}
            report["checks"].append(item)
            if not result["ok"]:
                print(json.dumps(result,indent=2))
                break
            reference = models.preview(model)
            actual = result["samples"]
            initial_field = {"pendulum":"angle","double-pendulum":"angle1","mass-spring":"displacement"}[model["kind"]]
            assert abs(actual[0]["value"] - model["parameters"][initial_field]) < 0.001
            errors = []
            errors2 = []
            for q in actual:
                nearest = min(reference,key=lambda r:abs(r["time"]-q["time"]))
                if abs(nearest["time"]-q["time"]) < model["simulation"]["step"]*0.1:
                    errors.append(abs(nearest["value"]-q["value"]))
                    if model["kind"] == "double-pendulum":
                        errors2.append(abs(nearest["value2"]-q["value2"]))
            assert errors, "No shared solver/reference sample times"
            item["maxReferenceError"] = max(errors)
            item["unit"] = result["metrics"]["valueUnit"]
            limit = 0.006 if model["kind"] == "mass-spring" else 0.7
            assert max(errors) < limit, item
            if errors2:
                item["maxSecondAngleErrorDeg"] = max(errors2)
                assert max(errors2) < limit, item
                assert abs(actual[0]["value2"]-model["parameters"]["angle2"]) < 0.001
            assert actual[-1]["time"] >= model["simulation"]["duration"]-1e-8
            if model["kind"] != "mass-spring":
                assert result["metrics"]["maxConstraintError"] < 1e-5
            else:
                assert result["metrics"]["finalEnergy"] < result["metrics"]["initialEnergy"]
                item["relativeToInitialDisplacement"] = max(errors)/abs(model["parameters"]["displacement"])
                item["withinOnePercentTarget"] = item["relativeToInitialDisplacement"] <= 0.01
                assert item["withinOnePercentTarget"], item
    report["ok"] = len(report["checks"]) == 2*len(baseline) and all(item["ok"] for item in report["checks"])
    destination = Path(__file__).with_name("evidence") / "real-solver-verification.json"
    destination.write_text(json.dumps(report,indent=2),encoding="utf-8")
    print(json.dumps(report,indent=2))
    assert report["ok"], "See solver logs and evidence for incomplete checks"


if __name__ == "__main__":
    main()
