# Simulation demo recordings

The homepage clips show the actual Kinemeld interface in presentation mode playing back
real MBDyn 1.7.3 solutions of the [featured studies](featured-studies.md). Each recording
is captured frame by frame at 30 fps from the solver's output samples; the caption in the
viewport states the playback rate (real time down to 0.2×). The clips have no audio. Each
GIF is a smaller 15 fps preview of its MP4. GitHub plays GIFs in the README but not MP4 files
from the repository, so the longer session recordings below also have an 800 px, 8 fps GIF
made with `scripts/demo_gif.sh`.

| Demo | Simulated interval | Playback | What to watch |
| --- | --- | --- | --- |
| [Robot arm](demos/robot-arm.mp4) | 6 s | real time | Turret, shoulder and elbow following their drives; shoulder motor torque in the plot |
| [Quarter-car](demos/quarter-car.mp4) | 2.5 s | 0.5× | Arms swinging through ±60 mm; knuckle camber (X) and toe (Z) in the plot |
| [Gear drop test](demos/gear-drop.mp4) | 1.2 s | 0.2× | Touchdown, strut stroke and the gas / orifice / stop force components |
| [Aircraft nose gear](demos/aircraft-nose-gear.mp4) | 2 s | 0.5× | 80 mm strut stroke folding the torque links; slider position in the plot |
| [Oleo strut fixture](demos/oleo-strut.mp4) | 1 s | 0.25× | 50 mm stroke; gas, hydraulic and stop force components |
| [Wheel-end drop test](demos/wheel-end-drop.mp4) | 1.5 s | 0.25× | Free fall, three tyre impacts and the knuckle swinging about the hub |
| [Slider-crank](demos/slider-crank.mp4) | 4 s | 0.5× | Crank speed running up and rippling twice per revolution |
| [Gyroscopic top](demos/gyroscopic-top.mp4) | 4 s | 0.5× | Precession of the axis with nutation cusps traced by the trail |
| [Tumbling T-handle](demos/tumbling-handle.mp4) | 12 s | real time | Periodic flips; spin component in body axes reversing sign |
| [Chaotic pendulums](demos/chaotic-pendulums.mp4) | 14 s | real time | Two pendulums 0.001° apart separating after about two seconds |

The studies are teaching models with representative parameters, not validated hardware.

## End to end: aircraft nose gear

[`demos/workflow-nose-gear.mp4`](demos/workflow-nose-gear.mp4) builds the open-source
aircraft nose gear from its [eleven STEP part files](../examples/open-aircraft-nose-gear/parts)
in one continuous session:

1. A new 3D assembly, named; the parts imported one by one with **Add STEP files**.
2. Six bodies with their frames on the pivots: strut, piston and axle, upper and lower torque
   links, two wheels. The strut is welded to ground; the piston slides in it; the torque
   links turn on revolute, spherical and universal joints that close the scissor loop
   without redundant constraints; the wheels turn on revolute bearings.
3. Every part attached to its body, then every joint placed with **Place from CAD**: the
   slide on the piston's cylinder, the torque-link pins on their pin bolts' rims and the
   wheel bearings on the wheel bores.
4. Mass, centre of mass and inertia computed from the solids (2700 kg/m³ structure,
   1100 kg/m³ wheels), and an 80 mm cosine stroke over 2 s prescribed on the slide.
5. Validation, the MBDyn run, and post-processing: the stroke, the torque-link fold played
   in real time, and the axial reaction on the slide.

Held frames replace waiting time. `node tests/record-nose-gear-workflow.mjs` recreates it.

## End-to-end workflow: wheel-end drop test

[`demos/workflow-wheel-end.mp4`](demos/workflow-wheel-end.mp4) records one continuous session
that builds the wheel-end drop test from the original STEP files: new 3D assembly, STEP
import, bodies with a revolute bearing and a weld, CAD attachment, mass and inertia from the
solids (steel 7850 kg/m³, rubber 1100 kg/m³), tyre contact, initial conditions, validation,
the MBDyn run and post-processing. Captions name each step and an orange outline marks the
control being used. Held frames replace waiting time; the playback section runs at 0.25×.

## AI-assisted set-up

[`demos/ai-assistant-setup.mp4`](demos/ai-assistant-setup.mp4) starts from the wheel-end STEP
parts with mass computed from the solids but no links, contact or drop conditions, and asks the
assistant — a real `qwen3.5:4b` model in a local Ollama — to add them. The request, the
proposal, the field-by-field review, Apply, the MBDyn run and the result are shown as they
happened; the caption states how long the model took on the recording machine (a 4-core CPU
without a GPU) and that waiting is condensed. While waiting, the recorder holds the page's
animation frames so the headless browser's software rendering does not compete with the model
for the CPU. Model output is not edited or scripted.

## Parameter study

[`demos/study-gear-drop.mp4`](demos/study-gear-drop.mp4) opens the landing-gear drop test
from the featured studies, shows its preloaded sink-speed study, runs the four cases through
MBDyn, compares them on the plot and in the table, and plays the 3 m/s case at 0.25×. The
peak loads in the captions are read from the running application.

## Contact friction

[`demos/study-spin-up.mp4`](demos/study-spin-up.mp4) opens the landing-gear spin-up drag
study, shows the tyre contact's friction, runs the friction study through MBDyn, compares
the drag of the three cases, plays the touchdown at 1/25 real time framed on the wheel, and
plots the axle's fore-aft reaction. The peak drags in the captions are read from the
running application.

## Recreate the recordings

Start the service with a working MBDyn (`python start.py --no-browser`), make sure FFmpeg
is on `PATH` (or set `FFMPEG`), then run:

```bash
node tests/record-demo-videos.mjs
node tests/record-workflow-demo.mjs
node tests/record-nose-gear-workflow.mjs
node tests/record-study-demo.mjs
node tests/record-friction-demo.mjs
AI_MODEL=qwen3.5:4b node tests/record-ai-demo.mjs   # needs Ollama with the model installed
scripts/demo_gif.sh docs/demos/workflow-nose-gear.mp4 docs/demos/study-gear-drop.mp4 docs/demos/study-spin-up.mp4 docs/demos/ai-assistant-setup.mp4
```

Append a study name (`robot-arm`, `quarter-car`, `gear-drop`, `aircraft-nose-gear`, `oleo-strut`,
`wheel-end-drop`, `slider-crank`, `gyroscopic-top`, `tumbling-handle` or
`chaotic-pendulums`) to record one. The recorder opens each featured
study, runs MBDyn, switches to presentation mode, steps the timeline at the stated rate,
encodes H.264 MP4 and a palette-optimised GIF, and decodes both to check for errors. No
preview trajectory is substituted for a failed solve; saved project files are not modified.
