# Simulation demo recordings

The homepage clips show the actual Kinemeld interface in presentation mode playing back
real MBDyn 1.7.3 solutions of the [featured studies](featured-studies.md). Each recording
is captured frame by frame at 30 fps from the solver's output samples; the caption in the
viewport states the playback rate (real time down to 0.2×). The clips have no audio. Each
GIF is a smaller 15 fps preview of its MP4.

| Demo | Simulated interval | Playback | What to watch |
| --- | --- | --- | --- |
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

## End-to-end workflow

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

## Recreate the recordings

Start the service with a working MBDyn (`python start.py --no-browser`), make sure FFmpeg
is on `PATH` (or set `FFMPEG`), then run:

```bash
node tests/record-demo-videos.mjs
node tests/record-workflow-demo.mjs
AI_MODEL=qwen3.5:4b node tests/record-ai-demo.mjs   # needs Ollama with the model installed
```

Append a study name (`quarter-car`, `gear-drop`, `aircraft-nose-gear`, `oleo-strut`,
`wheel-end-drop`, `slider-crank`, `gyroscopic-top`, `tumbling-handle` or
`chaotic-pendulums`) to record one. The recorder opens each featured
study, runs MBDyn, switches to presentation mode, steps the timeline at the stated rate,
encodes H.264 MP4 and a palette-optimised GIF, and decodes both to check for errors. No
preview trajectory is substituted for a failed solve; saved project files are not modified.
