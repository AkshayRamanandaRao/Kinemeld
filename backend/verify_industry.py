"""Actual MBDyn industry cases, independent dynamics, output forces and refinement."""
import copy
import json
from pathlib import Path

import industry_models
import models
import solver


def check_case(model,label):
    result,code = solver.run(model)
    assert result["ok"], result
    directory = solver.RUNS/result["runId"]
    actual = solver.parse_output(directory,model)
    reference = models.preview(model)
    step = model["simulation"]["step"]
    channels = ["zSprung","zUnsprung","aSprung","tireForce","suspensionForce"]
    errors = {key:0. for key in channels}
    for q in actual:
        if q["time"] > reference[-1]["time"]+1e-8:
            continue
        r = reference[min(round(q["time"]/step),len(reference)-1)]
        for key in channels:
            errors[key] = max(errors[key],abs(q[key]-r[key]))
    assert errors["zSprung"] < .0002 and errors["zUnsprung"] < .0002, errors
    for channel in ("tireForce","suspensionForce"):
        assert errors[channel] < .02*max(1.,max(abs(q[channel]) for q in reference)), errors
    # Compare state-law reconstruction to MBDyn's own .jnt global Z forces.
    joints = {6:[],7:[]}
    for line in (directory/"result.jnt").read_text().splitlines():
        row = [float(v) for v in line.split()]
        if int(row[0]) in joints:
            joints[int(row[0])].append(row)
    assert all(len(rows) == len(actual) for rows in joints.values())
    force_errors = {"suspensionForce":0.,"tireForce":0.}
    p = model["parameters"]
    static_load = (p["sprungMass"]+p["unsprungMass"])*p["gravity"] if model["kind"] == "suspension" else 0.
    for q,j6,j7 in zip(actual,joints[6],joints[7]):
        force_errors["suspensionForce"] = max(force_errors["suspensionForce"],abs(q["suspensionForce"]+j6[9]))
        force_errors["tireForce"] = max(force_errors["tireForce"],abs(q["tireForce"]+j7[9]-static_load))
    assert max(force_errors.values()) < .1, force_errors
    if model["kind"] == "landing-gear-drop":
        expected = ( (p["sinkVelocity"]**2+2*p["gravity"]*p["dropHeight"])**.5-p["sinkVelocity"])/p["gravity"]
        assert abs(result["metrics"]["firstContactTime"]-expected) <= step*1.1
        assert min(q["tireForce"] for q in actual) >= 0
        assert all(q["tireForce"] == 0 for q in actual if q["zUnsprung"] >= 0)
        assert result["metrics"]["finalEnergy"] < result["metrics"]["initialEnergy"]
    return {"label":label,"kind":model["kind"],"parameters":p,"step":step,"runId":result["runId"],"deckSha256":result["deckSha256"],"httpStatus":code,"maxReferenceError":errors,"maxSolverJointForceDisagreementN":force_errors,"metrics":result["metrics"],"ok":True}


def main():
    report = {"solver":solver.status(),"checks":[],"refinement":[],"ok":False}
    for example in industry_models.EXAMPLES:
        base = copy.deepcopy(example["model"])
        standard = check_case(base,"default")
        report["checks"].append(standard)
        fine = copy.deepcopy(base)
        fine["simulation"]["step"] /= 2
        refined = check_case(fine,"half step")
        report["checks"].append(refined)
        improvement = {}
        for key in ("zSprung","zUnsprung","tireForce"):
            improvement[key] = standard["maxReferenceError"][key]/max(refined["maxReferenceError"][key],1e-15)
            assert improvement[key] > 1.2, (key,improvement)
        report["refinement"].append({"kind":base["kind"],"errorReductionFactors":improvement})
        edited = copy.deepcopy(base)
        if base["kind"] == "suspension":
            edited["parameters"].update(sprungMass=450,unsprungMass=55,suspensionStiffness=24000,suspensionDamping=2200,tireStiffness=220000,bumpHeight=.035,bumpDuration=.4)
        else:
            edited["parameters"].update(sprungMass=450,unsprungMass=30,strutStiffness=60000,strutDamping=150,strutLength=.9,dropHeight=.05,sinkVelocity=2.)
        variant = check_case(edited,"changed parameters" if base["kind"] == "suspension" else "changed parameters and rebound")
        report["checks"].append(variant)
        if base["kind"] == "landing-gear-drop":
            assert variant["metrics"]["contactReleaseCount"] > 0, variant
    report["ok"] = len(report["checks"]) == 6 and all(q["ok"] for q in report["checks"])
    path = Path(__file__).with_name("evidence")/"industry-verification.json"
    path.write_text(json.dumps(report,indent=2,allow_nan=False),encoding="utf-8")
    print(json.dumps(report,indent=2,allow_nan=False))


if __name__ == "__main__":
    main()
