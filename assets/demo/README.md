# Demo GIF source

A [HyperFrames](https://github.com/heygen-com/hyperframes) composition (HTML + GSAP) that renders
`../demo.gif` (960 px, 15 fps, for the README) and `../demo.mp4` (1080p, for posts).

```sh
./setup.sh     # fetches GSAP from npm and IBM Plex fonts into vendor/ and fonts/ (git-ignored)
./render.sh    # check → render 1080p MP4 → faststart copy → palette GIF → gifsicle
```

All data is synthetic; no company or person names; no Apple logos or app icons.
