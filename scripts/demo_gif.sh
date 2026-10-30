#!/bin/sh
# Make the README animation for a demo recording: GitHub plays GIFs inline but not MP4 files
# from the repository, so each recording gets an 880 px, 8 frame/s GIF beside its MP4.
#
#   scripts/demo_gif.sh docs/demos/workflow-nose-gear.mp4   # writes docs/demos/workflow-nose-gear.gif
set -eu
for video in "$@"; do
  ffmpeg -y -loglevel error -i "$video" \
    -vf "fps=8,scale=880:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=128:stats_mode=diff[p];[b][p]paletteuse=dither=bayer:bayer_scale=4:diff_mode=rectangle" \
    "${video%.mp4}.gif"
  echo "${video%.mp4}.gif $(wc -c < "${video%.mp4}.gif") bytes"
done
