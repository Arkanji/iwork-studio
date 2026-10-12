#!/bin/sh
# Render the README demo from this HyperFrames composition.
#   ../demo.mp4  1920x1080, 30 fps, H.264 (posts)
#   ../demo.gif  960x540, 15 fps, looped, ~3 MB (README)
# Needs: node 22+, ffmpeg. HyperFrames finds (or downloads) its own headless Chrome;
# point it elsewhere with HYPERFRAMES_BROWSER_PATH / PUPPETEER_EXECUTABLE_PATH.
set -eu
cd "$(dirname "$0")"
HF="npx --yes hyperframes@0.8.149"

./setup.sh
$HF check .
$HF render . -o renders/demo.mp4 --fps 30 --quality delivery

# web-friendly MP4 (moov atom first)
ffmpeg -v error -y -i renders/demo.mp4 -c copy -movflags +faststart ../demo.mp4

# GIF: downscale with lanczos, one global palette, ordered dither (stable frame to frame,
# so unchanged pixels compress away), then gifsicle lossy optimisation.
ffmpeg -v error -y -i renders/demo.mp4 -vf "fps=15,scale=960:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=256:stats_mode=diff[p];[b][p]paletteuse=dither=bayer:bayer_scale=4:diff_mode=rectangle" -loop 0 renders/demo-raw.gif
npx --yes -p gifsicle@7.0.1 gifsicle -O3 --lossy=30 renders/demo-raw.gif -o ../demo.gif

ls -la ../demo.mp4 ../demo.gif
