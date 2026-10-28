"""Original reduced engineering models; displacements and forces are physical SI values."""

import math

EXAMPLES = [
    {"id": "suspension", "title": "Quarter-car road bump", "description": "Body and wheel dynamics, suspension travel, tire load and ride acceleration over a smooth bump.",
     "presentation": {"axis": "z", "positionReference": "equilibrium", "primaryChannel": "zSprung", "secondaryChannel": "zUnsprung", "valueUnit": "m", "forceLaw": "Linear suspension and tire; perturbations about loaded equilibrium."},
     "model": {"kind": "suspension", "name": "Quarter-car road bump", "parameters": {"sprungMass": 300., "unsprungMass": 40., "suspensionStiffness": 18000., "suspensionDamping": 1500., "tireStiffness": 180000., "bumpHeight": .05, "bumpDuration": .25, "bumpStart": .5, "gravity": 9.81}, "simulation": {"duration": 3., "step": .0005}}},
    {"id": "landing-gear-drop", "title": "Landing-gear drop test", "description": "A falling sprung mass and wheel, quadratic strut damping, and tire contact that releases on rebound.",
     "presentation": {"axis": "z", "positionReference": "absolute", "primaryChannel": "zSprung", "secondaryChannel": "zUnsprung", "valueUnit": "m", "forceLaw": "Equivalent linear gas spring, quadratic hydraulic damping, unilateral elastic tire."},
     "model": {"kind": "landing-gear-drop", "name": "Landing-gear drop test", "parameters": {"sprungMass": 600., "unsprungMass": 35., "strutStiffness": 45000., "strutDamping": 2500., "tireStiffness": 350000., "strutLength": .8, "dropHeight": .04, "sinkVelocity": 1.5, "gravity": 9.81}, "simulation": {"duration": 1.5, "step": .00025}}},
]

RANGES = {
    "suspension": {"sprungMass": (50, 5000), "unsprungMass": (5, 500), "suspensionStiffness": (1000, 300000), "suspensionDamping": (0, 30000), "tireStiffness": (10000, 3000000), "bumpHeight": (0, .2), "bumpDuration": (.03, 3), "bumpStart": (.01, 10), "gravity": (.1, 20)},
    "landing-gear-drop": {"sprungMass": (50, 10000), "unsprungMass": (5, 1000), "strutStiffness": (5000, 1000000), "strutDamping": (0, 100000), "tireStiffness": (20000, 5000000), "strutLength": (.2, 2), "dropHeight": (0, .5), "sinkVelocity": (0, 5), "gravity": (.1, 20)},
}


def extra_validation(model):
    p, s, kind = model["parameters"], model["simulation"], model["kind"]
    issues = []
    def issue(field, message, level="error"):
        issues.append({"level": level, "field": field, "message": message})
    ms, mu, kt = p["sprungMass"], p["unsprungMass"], p["tireStiffness"]
    ks = p["suspensionStiffness"] if kind == "suspension" else p["strutStiffness"]
    # Exact undamped eigenfrequencies of the two-mass linearized system.
    trace = ks/ms + (ks+kt)/mu
    discriminant = max(0., trace*trace - 4*ks*kt/(ms*mu))
    high = math.sqrt((trace+math.sqrt(discriminant))/2)
    low = math.sqrt((trace-math.sqrt(discriminant))/2)
    rate = high
    summary = {"degreesOfFreedom": 2, "bodies": 2, "structuralNodes": 3, "naturalFrequenciesHz": [low/(2*math.pi),high/(2*math.pi)], "positionReference": "equilibrium" if kind == "suspension" else "absolute"}
    if kind == "suspension":
        rate = max(rate, p["suspensionDamping"]*(1/ms+1/mu), 2*math.pi/p["bumpDuration"])
        if p["bumpStart"]+p["bumpDuration"] > s["duration"]:
            issue("simulation.duration", "Include the complete road bump: duration must reach bump start plus bump duration.")
        if s["duration"] < p["bumpStart"]+p["bumpDuration"]+1/low:
            issue("simulation.duration", "Extend the run to observe suspension settling after the bump.", "warning")
        summary["staticTireLoad"] = (ms+mu)*p["gravity"]
    else:
        g, length, sink, height = (p[k] for k in ("gravity","strutLength","sinkVelocity","dropHeight"))
        energy = .5*(ms+mu)*sink*sink + g*(ms*(length+height)+mu*height)
        # Minimum potential on c=.8L over all wheel positions; damping cannot add energy.
        barrier = .5*ks*(.8*length)**2 + ms*g*.2*length - ((ms+mu)*g)**2/(2*kt)
        if energy >= barrier:
            issue("parameters.strutLength", "This combination can exceed 80% strut compression in the conservative energy bound. Increase strut length/stiffness or reduce drop energy.")
        max_relative_speed = math.sqrt(max(0.,2*(energy+((ms+mu)*g)**2/(2*kt)+.5*(ms*g)**2/ks)*(1/ms+1/mu)))
        nonlinear_rate = 2*p["strutDamping"]*max_relative_speed*(1/ms+1/mu)
        # MBDyn is implicit; the reference RK4 uses four substeps. This separate
        # conservative bound keeps a reference substep below 0.25 damping scale.
        if s["step"]*nonlinear_rate > 1:
            issue("simulation.step", f"Resolve the conservative quadratic damping bound: use a step no larger than {1/nonlinear_rate:.6g} s.")
        elif s["step"]*nonlinear_rate > .5:
            issue("simulation.step", "Strong quadratic damping: compare half the step for force-peak accuracy.", "warning")
        contact_time = (math.sqrt(sink*sink+2*g*height)-sink)/g
        summary["freeFallContactTime"] = contact_time
        if s["duration"] < contact_time+.1:
            issue("simulation.duration", "Run at least 0.1 s beyond the predicted first tire contact.")
    if s["step"]*rate > .2:
        issue("simulation.step", f"Resolve the fastest elastic/damping scale: use a step no larger than {.2/rate:.6g} s.")
    elif s["step"]*rate > .08:
        issue("simulation.step", "Compare a smaller step to check peak acceleration and contact-force sensitivity.", "warning")
    return issues, summary


def road(model, time):
    if model["kind"] != "suspension":
        return 0.
    p = model["parameters"]
    phase = (time-p["bumpStart"])/p["bumpDuration"]
    return p["bumpHeight"]*.5*(1-math.cos(2*math.pi*phase)) if 0 < phase < 1 else 0.


def sample(model, time, state):
    """Forces are derived from the documented constitutive laws and solver state."""
    zs,zu,vs,vu = state
    p, kind = model["parameters"], model["kind"]
    r = road(model,time)
    if kind == "suspension":
        travel = zs-zu
        force = -p["suspensionStiffness"]*travel-p["suspensionDamping"]*(vs-vu)
        tire_dynamic = p["tireStiffness"]*(r-zu)
        tire = tire_dynamic+(p["sprungMass"]+p["unsprungMass"])*p["gravity"]
        a_s,a_u = force/p["sprungMass"], (-force+tire_dynamic)/p["unsprungMass"]
    else:
        travel = zs-zu-p["strutLength"]
        force = -p["strutStiffness"]*travel-p["strutDamping"]*(vs-vu)*abs(vs-vu)
        tire = p["tireStiffness"]*max(0.,-zu)
        a_s,a_u = force/p["sprungMass"]-p["gravity"], (-force+tire)/p["unsprungMass"]-p["gravity"]
    value = {"time":time,"x":0.,"y":0.,"z":zs,"angle":0.,"velocity":vs,"value":zs,
             "zSprung":zs,"zUnsprung":zu,"vSprung":vs,"vUnsprung":vu,"aSprung":a_s,"aUnsprung":a_u,"road":r,
             "suspensionTravel":travel,"suspensionForce":force,"tireForce":tire}
    if kind == "landing-gear-drop":
        value.update(strutCompression=-travel,tireCompression=max(0.,-zu),contact=1 if zu < 0 else 0)
    return value


def preview(model):
    p,s = model["parameters"],model["simulation"]
    if model["kind"] == "suspension":
        state = [0.,0.,0.,0.]
    else:
        state = [p["strutLength"]+p["dropHeight"],p["dropHeight"],-p["sinkVelocity"],-p["sinkVelocity"]]
    def derivative(t,q):
        value = sample(model,t,q)
        return [q[2],q[3],value["aSprung"],value["aUnsprung"]]
    values = [sample(model,0.,state)]
    count = math.ceil(s["duration"]/s["step"])
    previous = 0.
    for i in range(1,count+1):
        time = min(i*s["step"],s["duration"])
        # Substep contact corners independently of MBDyn's implicit integrator.
        h = (time-previous)/4
        for j in range(4):
            t = previous+j*h
            k1 = derivative(t,state)
            k2 = derivative(t+h/2,[a+h*b/2 for a,b in zip(state,k1)])
            k3 = derivative(t+h/2,[a+h*b/2 for a,b in zip(state,k2)])
            k4 = derivative(t+h,[a+h*b for a,b in zip(state,k3)])
            state = [a+h*(b+2*c+2*d+e)/6 for a,b,c,d,e in zip(state,k1,k2,k3,k4)]
        values.append(sample(model,time,state))
        previous = time
    return values


def deck(model,header):
    p,kind = model["parameters"],model["kind"]
    n = lambda value: format(float(value),".14g")
    drop = kind == "landing-gear-drop"
    zs,zu,v = (p["dropHeight"]+p["strutLength"],p["dropHeight"],-p["sinkVelocity"]) if drop else (0.,0.,0.)
    functions = f'scalar function: "tire_contact", multilinear, -1, {n(-p["tireStiffness"])}, 0,0, 1,0;\n' if drop else ""
    base = header+f"""# Vertical two-body engineering model; constrained X/Y and all rotations.
{functions}begin: control data;
    max iterations: 30;
    initial stiffness: 1.e12;
    structural nodes: 3;
    rigid bodies: 2;
    joints: 7;
    {'gravity;' if drop else ''}
end: control data;
begin: nodes;
    structural: 0, static, null, eye, null, null;
    structural: 1, dynamic, 0,0,{n(zs)}, eye, 0,0,{n(v)}, null;
    structural: 2, dynamic, 0,0,{n(zu)}, eye, 0,0,{n(v)}, null;
end: nodes;
begin: elements;
    body: 1, 1, {n(p['sprungMass'])}, null, diag, 1,1,1;
    body: 2, 2, {n(p['unsprungMass'])}, null, diag, 1,1,1;
    joint: 1, clamp, 0, node, node;
    joint: 2, in line, 0, position, null, orientation, eye, 1, offset, null;
    joint: 3, prismatic, 0, 1;
    joint: 4, in line, 0, position, null, orientation, eye, 2, offset, null;
    joint: 5, prismatic, 0, 2;
"""
    if drop:
        length = p['strutLength']
        return base+f"""    # Rod strain is relative length change: scale physical K by L, C by L squared.
    joint: 6, rod, 2, position, null, 1, position, null, {n(length)},
        turbulent viscoelastic, {n(p['strutStiffness']*length)}, {n(p['strutDamping']*length*length)};
    joint: 7, deformable displacement joint,
        0, position, null, 2, position, null,
        scalar function elastic orthotropic, null, null, "tire_contact";
    gravity: uniform, 0,0,-1, const, {n(p['gravity'])};
end: elements;
"""
    return base+f"""    joint: 6, deformable displacement joint,
        2, position, null, 1, position, null,
        linear viscoelastic generic, diag, 0,0,{n(p['suspensionStiffness'])},
        diag, 0,0,{n(p['suspensionDamping'])};
    # Tire strain is wheel displacement minus prescribed road height.
    joint: 7, deformable displacement joint,
        0, position, null, 2, position, null,
        linear elastic generic, diag, 0,0,{n(p['tireStiffness'])},
        prestrain, component, const,0, const,0,
        cosine, {n(p['bumpStart'])}, {n(2*math.pi/p['bumpDuration'])}, {n(p['bumpHeight']/2)}, one, 0;
end: elements;
"""


def metrics(model, samples):
    p, kind = model["parameters"],model["kind"]
    def energy(q):
        kinetic = .5*p["sprungMass"]*q["vSprung"]**2 + .5*p["unsprungMass"]*q["vUnsprung"]**2
        if kind == "suspension":
            return kinetic + .5*p["suspensionStiffness"]*q["suspensionTravel"]**2 + .5*p["tireStiffness"]*(q["zUnsprung"]-q["road"])**2
        return kinetic+.5*p["strutStiffness"]*q["strutCompression"]**2+.5*p["tireStiffness"]*q["tireCompression"]**2 + p["gravity"]*(p["sprungMass"]*q["zSprung"]+p["unsprungMass"]*q["zUnsprung"])
    result = {"sampleCount":len(samples),"duration":samples[-1]["time"],"peakValue":max(abs(q["value"]) for q in samples),"valueUnit":"m","velocityUnit":"m/s","initialEnergy":energy(samples[0]),"finalEnergy":energy(samples[-1]),"energyUnit":"J",
              "peakSprungAcceleration":max(abs(q["aSprung"]) for q in samples), "rmsSprungAcceleration": math.sqrt(sum(q["aSprung"]**2 for q in samples)/len(samples)),
              "peakSuspensionTravel":max(abs(q["suspensionTravel"]) for q in samples),"peakSuspensionForce":max(abs(q["suspensionForce"]) for q in samples), "peakTireForce":max(q["tireForce"] for q in samples), "minimumTireForce":min(q["tireForce"] for q in samples),
              "derivedChannels":"Force and acceleration reconstructed from documented laws and solver positions/velocities; not independently measured loads."}
    if kind == "suspension":
        result["contactAssumptionViolated"] = result["minimumTireForce"] < 0
    else:
        result["maxStrutCompression"] = max(q["strutCompression"] for q in samples)
        result["maxTireCompression"] = max(q["tireCompression"] for q in samples)
        result["firstContactTime"] = next((q["time"] for q in samples if q["contact"]),None)
        result["contactReleaseCount"] = sum(a["contact"] == 1 and b["contact"] == 0 for a,b in zip(samples,samples[1:]))
    return result
