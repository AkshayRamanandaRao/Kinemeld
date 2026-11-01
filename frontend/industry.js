// Presentation metadata for the explicitly supported engineering templates.
const bodyMotion = {
  title: "Body / wheel displacement",
  unit: "m",
  channels: [
    ["zSprung", "Body"],
    ["zUnsprung", "Wheel"],
  ],
};
const loads = {
  title: "Strut / tire force",
  unit: "N",
  channels: [
    ["suspensionForce", "Strut"],
    ["tireForce", "Tire"],
  ],
};
const acceleration = {
  title: "Body / wheel acceleration",
  unit: "m/s²",
  channels: [
    ["aSprung", "Body"],
    ["aUnsprung", "Wheel"],
  ],
};

export const industry = {
  "flexible-link": {
    category: "ROBOTICS · FLEXIBLE LINK", title: "FLEXIBLE ROBOT LINK",
    description: "A clamped uniform link bends and vibrates under a smoothly applied tip force.",
    badge: "Native beam elements · flexible nodes",
    assumptions: "Illustrative uniform beam, clamped at its root, with explicit section stiffness and nodal mass/rotary inertia. Small tip deflections; no plasticity, CAD section inference, rigid-link coupling or hardware calibration. Displayed nodes follow native MBDyn output at actual scale.",
    fields: [
      ["length", "Link length", "m", .05, .05], ["linearDensity", "Mass per length", "kg/m", .001, .1],
      ["axialStiffness", "Axial stiffness EA", "N", 1, 1000], ["shearStiffness", "Shear stiffness GA", "N", 1, 1000],
      ["bendingStiffness", "Bending stiffness EI", "N·m²", .001, 1], ["torsionalStiffness", "Torsional stiffness GJ", "N·m²", .001, 1],
      ["rotaryInertia", "Rotary inertia per length", "kg·m", 1e-10, .00001], ["dampingTime", "Stiffness damping time", "s", 0, .001],
      ["tipLoad", "Tip load Z", "N", -1e6, .1], ["rampTime", "Load ramp time", "s", .001, .01], ["nodes", "Mesh nodes (3, 5 or 9)", "", 3, 2],
    ],
    bodies: [["ground", "ground", "Root support", "Fixed"], ["body", "cube", "Flexible link", "Native nodes"]],
    connections: [["joint", "joint", "Root clamp", "6 constraints"], ["beam", "wave", "Beam mesh", "Flexible"]],
    excitation: [["load", "force", "Ramped tip load", "Z"]],
    topology: [["Root support", "Clamped"], ["Beam mesh", "Native beam3 elements"], ["Tip", "Ramped transverse load"]],
    signals: [
      { title: "Tip deflection (native)", unit: "m", channels: [["tipDeflection", "Deflection"]] },
      { title: "Tip velocity (native)", unit: "m/s", channels: [["tipVelocity", "Velocity"]] },
      { title: "Tip slope (native)", unit: "rad", channels: [["tipSlope", "Slope"]] },
      { title: "Applied tip load", unit: "N", channels: [["appliedForce", "Load"]] },
      { title: "Root force (native)", unit: "N", channels: [["rootForce", "Force Z"]] },
      { title: "Root moment (native)", unit: "N·m", channels: [["rootMoment", "Moment Y"]] },
    ], tutorial: "robot-flexible-link.md",
  },
  "gear-deployment": {
    category: "SPACEPLANE · LINKAGE DEPLOYMENT",
    title: "SHUTTLE-STYLE GEAR DEPLOYMENT",
    description:
      "A main strut and folding brace form a closed mechanism as the gear deploys.",
    badge: "3 moving links · closed four-bar · driven",
    assumptions:
      "Original shuttle-inspired four-bar mechanism with prescribed main-strut rotation. Dimensions and masses are illustrative. Actuator length is a geometric demand; hydraulics, door linkage, contact, downlock and flight qualification are not modelled.",
    fields: [
      ["mainLength", "Main strut length", "m", 0.1, 0.05],
      ["braceAttachment", "Brace attachment from pivot", "m", 0.05, 0.05],
      ["upperBraceLength", "Brace B–C length", "m", 0.05, 0.05],
      ["lowerBraceLength", "Brace C–D length", "m", 0.05, 0.05],
      ["groundX", "Fixed brace pin X", "m", -10, 0.05],
      ["groundZ", "Fixed brace pin Z", "m", -10, 0.05],
      ["actuatorAnchorX", "Actuator anchor X", "m", -10, 0.05],
      ["actuatorAnchorZ", "Actuator anchor Z", "m", -10, 0.05],
      ["mainMass", "Main strut mass", "kg", 0.1, 1],
      ["upperBraceMass", "Brace B–C mass", "kg", 0.01, 0.5],
      ["lowerBraceMass", "Brace C–D mass", "kg", 0.01, 0.5],
      ["initialAngle", "Stowed angle from down", "°", -150, 1],
      ["finalAngle", "Deployed angle from down", "°", -150, 1],
      ["gravity", "Gravity", "m/s²", 0, 0.01],
    ],
    bodies: [
      ["ground", "ground", "Airframe / bay", "Fixed"],
      ["body", "cube", "Main strut", ""],
      ["body2", "cube", "Brace B–C", ""],
      ["body3", "cube", "Brace C–D", ""],
    ],
    connections: [["joint", "joint", "Four-bar loop A–B–C–D", "Closed"]],
    excitation: [
      ["drive", "wave", "Prescribed deployment", "Angle"],
      ["load", "gravity", "Gravity", ""],
    ],
    topology: [
      ["Airframe A / D", "Two fixed pivots"],
      ["Main strut A–B–W", "Prescribed angle; wheel at W"],
      ["Brace B–C", "First moving brace"],
      ["Brace C–D", "Second brace closes loop to D"],
    ],
    signals: [
      {
        title: "Main strut angle",
        unit: "deg",
        channels: [["angle", "Strut"]],
      },
      {
        title: "Actuator length demand",
        unit: "m",
        channels: [["actuatorLength", "Length"]],
      },
      {
        title: "Loop closure residual",
        unit: "m",
        channels: [["closureError", "Residual"]],
      },
    ],
    tutorial: "industry-gear-deployment.md",
  },
  suspension: {
    category: "AUTOMOTIVE · ROAD RESPONSE",
    title: "QUARTER-CAR SUSPENSION",
    description:
      "A road bump excites the tire, wheel assembly and vehicle body.",
    badge: "2 moving masses · 2 vertical DOF",
    assumptions:
      "Quarter-car model about static equilibrium: linear suspension and tire, two vertical degrees of freedom, prescribed road bump. Wheel geometry is illustrative; lateral geometry, steering and tire lift-off are outside this model.",
    fields: [
      ["sprungMass", "Sprung mass", "kg", 50, 10],
      ["unsprungMass", "Wheel assembly mass", "kg", 5, 1],
      ["suspensionStiffness", "Suspension stiffness", "N/m", 1000, 1000],
      ["suspensionDamping", "Suspension damping", "N·s/m", 0, 100],
      ["tireStiffness", "Tire stiffness", "N/m", 10000, 10000],
      ["bumpHeight", "Bump height", "m", 0, 0.01],
      ["bumpDuration", "Bump duration", "s", 0.03, 0.05],
      ["bumpStart", "Bump start", "s", 0.01, 0.1],
      ["gravity", "Gravity", "m/s²", 0.1, 0.01],
    ],
    bodies: [
      ["ground", "ground", "Road input", "Prescribed"],
      ["body", "cube", "Sprung body", ""],
      ["body2", "cube", "Wheel assembly", ""],
    ],
    connections: [
      ["joint", "joint", "Vertical guides", "2 DOF"],
      ["spring", "wave", "Suspension + tire", ""],
    ],
    excitation: [["load", "wave", "Raised-cosine bump", ""]],
    topology: [
      ["Sprung body", "Vertical displacement zₛ"],
      ["Suspension", "Linear spring + damper"],
      ["Wheel assembly", "Vertical displacement zᵤ"],
      ["Tire", "Linear compliance"],
      ["Road", "Prescribed bump zᵣ(t)"],
    ],
    signals: [
      bodyMotion,
      {
        title: "Suspension travel / road",
        unit: "m",
        channels: [
          ["suspensionTravel", "Travel"],
          ["road", "Road"],
        ],
      },
      {
        title: "Dynamic suspension / total tire load",
        unit: "N",
        channels: [
          ["suspensionForce", "Dynamic"],
          ["tireForce", "Tire total"],
        ],
      },
      acceleration,
    ],
    tutorial: "industry-suspension.md",
  },
  "landing-gear-drop": {
    category: "AEROSPACE · TOUCHDOWN LOADS",
    title: "LANDING-GEAR DROP TEST",
    description:
      "Follow touchdown, strut compression and the load transferred to the airframe.",
    badge: "2 masses · nonlinear damping · contact",
    assumptions:
      "Generic vertical drop rig: equivalent linear strut spring, quadratic hydraulic damping, and unilateral elastic tire contact. Original illustrative parameters; no manufacturer data, flexible structure, brake, tire spin-up or certification model.",
    fields: [
      ["sprungMass", "Supported airframe mass", "kg", 50, 25],
      ["unsprungMass", "Wheel assembly mass", "kg", 5, 1],
      ["strutStiffness", "Equivalent strut stiffness", "N/m", 5000, 1000],
      ["strutDamping", "Quadratic strut damping", "N·s²/m²", 0, 100],
      ["tireStiffness", "Tire contact stiffness", "N/m", 20000, 10000],
      ["strutLength", "Uncompressed strut length", "m", 0.2, 0.05],
      ["dropHeight", "Initial tire clearance", "m", 0, 0.01],
      ["sinkVelocity", "Initial sink speed", "m/s", 0, 0.1],
      ["gravity", "Gravity", "m/s²", 0.1, 0.01],
    ],
    bodies: [
      ["ground", "ground", "Runway", "Fixed"],
      ["body", "cube", "Airframe mass", ""],
      ["body2", "cube", "Wheel assembly", ""],
    ],
    connections: [
      ["joint", "joint", "Vertical guides", "2 DOF"],
      ["spring", "wave", "Shock strut", "Nonlinear"],
      ["contact", "joint", "Tire contact", "Unilateral"],
    ],
    excitation: [["load", "gravity", "Gravity + sink velocity", ""]],
    topology: [
      ["Airframe mass", "Gravity + initial sink speed"],
      ["Shock strut", "Spring + quadratic damping"],
      ["Wheel assembly", "Vertical motion"],
      ["Tire contact", "Compression only"],
      ["Runway", "Fixed ground"],
    ],
    signals: [
      { ...bodyMotion, title: "Body / wheel position" },
      {
        title: "Strut / tire compression",
        unit: "m",
        channels: [
          ["strutCompression", "Strut"],
          ["tireCompression", "Tire"],
        ],
      },
      loads,
      acceleration,
    ],
    tutorial: "industry-landing-drop.md",
  },
};

export function signalsFor(kind) {
  if (industry[kind]) return industry[kind].signals;
  if (kind === "double-pendulum")
    return [
      {
        title: "Link angles · 1 / 2",
        unit: "deg",
        channels: [
          ["angle", "Link 1"],
          ["angle2", "Link 2"],
        ],
      },
    ];
  if (kind === "pendulum")
    return [
      {
        title: "Angular displacement",
        unit: "deg",
        channels: [["angle", "Angle"]],
      },
    ];
  return [
    { title: "Linear displacement", unit: "m", channels: [["x", "Position"]] },
  ];
}

export const industryCsvUnits = {
  tipDeflection: "tipDeflection_m", tipVelocity: "tipVelocity_m_s", tipSlope: "tipSlope_rad",
  appliedForce: "appliedForce_N", rootForce: "rootForce_N", rootMoment: "rootMoment_Nm",
  bx: "brace_B_x_m",
  bz: "brace_B_z_m",
  cx: "brace_C_x_m",
  cz: "brace_C_z_m",
  wheelX: "wheel_x_m",
  wheelZ: "wheel_z_m",
  actuatorLength: "actuator_length_m",
  closureError: "closure_error_m",
  zSprung: "body_position_m",
  zUnsprung: "wheel_position_m",
  vSprung: "body_velocity_m_s",
  vUnsprung: "wheel_velocity_m_s",
  aSprung: "body_acceleration_m_s2",
  aUnsprung: "wheel_acceleration_m_s2",
  road: "road_displacement_m",
  suspensionTravel: "suspension_travel_m",
  suspensionForce: "strut_force_N",
  tireForce: "tire_force_N",
  strutCompression: "strut_compression_m",
  tireCompression: "tire_compression_m",
  contact: "tire_in_contact",
};
