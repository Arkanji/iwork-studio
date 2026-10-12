#!/bin/sh
# Fetch the composition's third-party assets into gitignored folders:
#   vendor/gsap.min.js   (GSAP, from the npm registry)
#   fonts/*.woff2 + fonts/fonts.css (IBM Plex Sans / Sans Arabic / Mono, OFL, from Google Fonts;
#                                    latin + arabic subsets only)
# Run once before `hyperframes preview|check|render`. Idempotent.
set -eu
cd "$(dirname "$0")"

GSAP_VERSION=3.13.0
UA="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"

mkdir -p vendor fonts
if [ ! -s vendor/gsap.min.js ]; then
  tmp=$(mktemp -d)
  curl -fsSL "https://registry.npmjs.org/gsap/-/gsap-${GSAP_VERSION}.tgz" | tar -xz -C "$tmp"
  cp "$tmp/package/dist/gsap.min.js" vendor/gsap.min.js
  rm -rf "$tmp"
fi

if [ ! -s fonts/fonts.css ]; then
  css_url="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&family=IBM+Plex+Sans+Arabic:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500&display=block"
  curl -fsSL -A "$UA" "$css_url" > fonts/google.css
  # Keep only the latin and arabic subsets, download them, rewrite to local URLs.
  python3 - <<'PY'
import re, urllib.request, pathlib
src = pathlib.Path("fonts/google.css").read_text()
blocks = re.findall(r"/\* ([a-z-]+) \*/\s*(@font-face \{.*?\})", src, re.S)
out = []
for subset, block in blocks:
    if subset not in ("latin", "arabic"):
        continue
    fam = re.search(r"font-family: '([^']+)'", block).group(1)
    wght = re.search(r"font-weight: (\d+)", block).group(1)
    url = re.search(r"url\((https://[^)]+)\)", block).group(1)
    name = f"{fam.replace(' ', '')}-{wght}-{subset}.woff2"
    dest = pathlib.Path("fonts") / name
    if not dest.exists():
        urllib.request.urlretrieve(url, dest)
    out.append(f"/* {subset} */\n" + block.replace(url, name))
pathlib.Path("fonts/fonts.css").write_text("\n".join(out) + "\n")
pathlib.Path("fonts/google.css").unlink()
print(f"fonts: {len(out)} faces")
PY
fi
echo "assets ready: vendor/gsap.min.js, fonts/fonts.css"
