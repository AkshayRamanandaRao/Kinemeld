# Simulation demo recordings

The four homepage previews show the actual Kinemeld browser interface and
MBDyn solver results for the linked STEP projects. The recordings contain no
audio. Each six-second clip walks through 72 selected result samples; the
label **SLOW PLAYBACK** distinguishes the recording's playback rate from the
simulation's time. Each GIF is a smaller looping preview of its MP4.

| Demo | Simulated interval | What to watch |
| --- | --- | --- |
| [Aircraft nose gear](demos/aircraft-nose-gear.mp4) | 0.5 s | Prescribed strut travel, linkage motion and the slider-position plot. The model title states its kinematic-only limits. |
| [Double-wishbone suspension](demos/double-wishbone.mp4) | 0.15 s | Motion of the source STEP arms, knuckle and wheel, alongside the wheel position plot. |
| [Wheel-end torque](demos/wheel-end.mp4) | 0.5 s | Wheel motion and the angular-velocity response to the applied torque. |
| [Oleo strut](demos/oleo-strut.mp4) | About 1 s | Prescribed wheel-end travel and the native gas-pressure response of the illustrative strut. |

The recordings demonstrate the models as authored, not verified physical
equipment. See each example's engineering guide on the homepage for source
rights, assumed joints and properties, numerical checks and applicability.

## Recreate the recordings

Install the project dependencies and configure MBDyn and STEP import as described
in the [main README](../README.md). Install Playwright's Chromium and ensure an
FFmpeg executable is available. The recorder uses the `FFMPEG` environment
variable when set; otherwise it looks for the executable from Python's
`imageio-ffmpeg` package. Start the application service, then run:

```powershell
$env:MBDYN_STUDIO_URL = 'http://127.0.0.1:8766'
node tests/record-demo-videos.mjs
```

The recorder loads each saved project, runs MBDyn, verifies that the expected
STEP attachments and solver samples are present, steps through the result
timeline and encodes the frames as H.264 MP4 and animated GIF. It decodes each
completed file to check for playback errors. To regenerate one demo, append its
name: `aircraft-nose-gear`, `double-wishbone`, `wheel-end` or `oleo-strut`.
Temporary screenshots are removed after encoding; saved project and model
files are not modified. The process requires a running service and a working
solver; no preview trajectory is substituted for a failed solve.
