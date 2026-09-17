# ans-dl

**`ans-dl` is a manga chapter image downloader for [Ani: New Stage](https://aninewstage.org).**

> Downloads manga chapter images from aninewstage.org — single command, no browser.
> Handles both flat (full-page) and tiled (2×2 panel-split) chapter formats.
> Tiled chapters are automatically composited back into full pages.

### Platforms

| Platform | Install command (copy/paste) |
|----------|------------------------------|
| [macOS](#macos) | One-line in Terminal |
| [Windows](#windows) | One-line in PowerShell/cmd |
| [Linux](#linux) | One-line in terminal |
| [Termux](#termux) | One-line in Termux |

---

## What it does

- Fetches a chapter page or post page from aninewstage.org
- Extracts image URLs from the SSR HTML (`slides: JSON.parse(...)`)
- Downloads all images with numbered filenames
- Detects tiled chapters (4 panels per page) and remuxes them into single composite PNGs
- Saves to `~/Downloads/<slug>/chapter-NN/page-NN.ext` by default
- Supports parallel multi-chapter downloads (`-p N`)
- Resumable — skips already-downloaded files
- Ctrl+C cancels cleanly — no empty folders left behind

### Usage

```bash
ans-dl "https://aninewstage.org/view/<slug>/chapter/<N>"     # single chapter
ans-dl "https://aninewstage.org/view/<slug>"                  # all chapters
ans-dl "https://aninewstage.org/view/<slug>" -p 6             # 6 chapters in parallel
```

### Dependencies

- Python 3.9+
- Pillow (for tiled chapter remuxing — flat chapters work without it)

---

## macOS

**`https://github.com/RellikJaeger/ans-dl`**

`ans-dl` for macOS is a manga chapter image downloader for aninewstage.org.

> Downloads manga chapter images — single command, no browser.
> Handles both flat (full-page) and tiled (2×2 panel-split) chapter formats.

### Tips

- Move the `ans-dl` launcher and `ans-dl.py` into `$HOME/.local/bin` or `/usr/local/bin`.
- Run `ans-dl` in different terminal sessions to download multiple chapters in parallel.

### Setup example for macOS

- Copy and paste this into Terminal.

```shell
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)" && brew update && brew upgrade -y && brew install git python && pip3 install pillow && brew cleanup --prune=all && cd "$HOME" && rm -rf "./ans-dl/" && git clone -b main --depth 1 https://github.com/RellikJaeger/ans-dl && mkdir -p "$HOME/.local/bin" && source "$HOME/.zshrc" && mv "./ans-dl/ans-dl" "./ans-dl/ans-dl.py" "$HOME/.local/bin/" && chmod a+x "$HOME/.local/bin/ans-dl" && rm -rf "./ans-dl/" && clear && ans-dl --help
```

### Usage example

- Copy and paste this into Terminal.

```shell
ans-dl "https://aninewstage.org/view/to-save-seven-villainesses-i-went-full-harem/chapter/1"
```

### Download multiple chapters in series

```shell
ans-dl "https://aninewstage.org/view/to-save-seven-villainesses-i-went-full-harem/chapter/1" "https://aninewstage.org/view/to-save-seven-villainesses-i-went-full-harem/chapter/2"
```

### Output file path

- Default: `~/Downloads/<slug>/chapter-NN/`
- Custom: pass an output directory as the second argument

```
/Users/<Username>/Downloads/<slug>/chapter-01/page-01.png
```

---

## Windows

**`https://github.com/RellikJaeger/ans-dl`**

`ans-dl` for Windows is a manga chapter image downloader for aninewstage.org.

> Downloads manga chapter images — single command, no browser.
> Handles both flat (full-page) and tiled (2×2 panel-split) chapter formats.

### Tips

- Move the `ans-dl.bat` launcher and `ans-dl.py` into `C:\Windows`.
- Run `ans-dl` in different cmd sessions to download multiple chapters in parallel.

### Setup example for Windows

- Copy and paste this into PowerShell or cmd.

```powershell
powershell -c "Set-ExecutionPolicy RemoteSigned -Scope CurrentUser; irm https://get.scoop.sh | iex; exit" && scoop install git python sudo && pip install pillow && cd $env:UserProfile && rm -rf ".\ans-dl\" && git clone -b main https://github.com/RellikJaeger/ans-dl && sudo cmd /c move /y ".\ans-dl\ans-dl.bat" ".\ans-dl\ans-dl.py" "%SystemRoot%\" && rm -rf ".\ans-dl\" && start /i cmd /k "ans-dl --help" && exit
```

### Usage example

- Copy and paste this into cmd.

```cmd
ans-dl "https://aninewstage.org/view/to-save-seven-villainesses-i-went-full-harem/chapter/1"
```

### Download multiple chapters in series

```cmd
ans-dl "https://aninewstage.org/view/to-save-seven-villainesses-i-went-full-harem/chapter/1" "https://aninewstage.org/view/to-save-seven-villainesses-i-went-full-harem/chapter/2"
```

### Output file path

- Default: `C:\Users\<Username>\Downloads\<slug>\chapter-NN\`
- Custom: pass an output directory as the second argument

```
C:\Users\<Username>\Downloads\<slug>\chapter-01\page-01.png
```

---

## Linux

**`https://github.com/RellikJaeger/ans-dl`**

`ans-dl` for Linux is a manga chapter image downloader for aninewstage.org.

> Downloads manga chapter images — single command, no browser.
> Handles both flat (full-page) and tiled (2×2 panel-split) chapter formats.

### Tips

- Move the `ans-dl` launcher and `ans-dl.py` into `$HOME/.local/bin`.
- Run `ans-dl` in different terminal sessions to download multiple chapters in parallel.

### Setup example for Linux

- Copy and paste this into Terminal.

```shell
sudo apt update && sudo apt install -y git python3-full python3-pil && cd "$HOME" && rm -rf "./ans-dl/" && git clone -b main --depth 1 https://github.com/RellikJaeger/ans-dl && mkdir -p "$HOME/.local/bin" && mv "./ans-dl/ans-dl" "./ans-dl/ans-dl.py" "$HOME/.local/bin/" && chmod a+x "$HOME/.local/bin/ans-dl" && rm -rf "./ans-dl/" && clear && ans-dl --help
```

### Usage example

- Copy and paste this into Terminal.

```shell
ans-dl "https://aninewstage.org/view/to-save-seven-villainesses-i-went-full-harem/chapter/1"
```

### Output file path

- Default: `~/Downloads/<slug>/chapter-NN/`
- Custom: pass an output directory as the second argument

```
/home/<username>/Downloads/<slug>/chapter-01/page-01.png
```

---

## Termux

**`https://github.com/RellikJaeger/ans-dl`**

`ans-dl` for Termux is a manga chapter image downloader for aninewstage.org.

> Downloads manga chapter images — single command, no browser.
> Handles both flat (full-page) and tiled (2×2 panel-split) chapter formats.
> Tiled chapters are composited using Pillow.

### Tips

- Move the `ans-dl` launcher and `ans-dl.py` into `$PREFIX/bin`.
- Run `ans-dl` in different Termux sessions to download multiple chapters in parallel.

### Setup example for Termux

- Copy and paste this into Termux.

```bash
yes | (pkg up && pkg in git python python-pip ffmpeg && pip install --upgrade pillow && git clone -b main --depth 1 https://github.com/RellikJaeger/ans-dl && chmod a+x ans-dl/ans-dl && mv ans-dl/ans-dl ans-dl/ans-dl.py $PREFIX/bin && rm -rf ans-dl && mkdir -p $HOME/bin && if [ -x "$HOME/bin/termux-url-opener" ]; then if grep -q "aninewstage" "$HOME/bin/termux-url-opener"; then echo "Existing termux-url-opener already handles aninewstage.org — leaving it alone"; else cp "$HOME/bin/termux-url-opener" "$HOME/bin/termux-url-opener-orig"; cat > "$HOME/bin/termux-url-opener" << 'EOF'
#!/bin/bash
remaining=()
for url in "$@"; do
    case "$url" in
        http://aninewstage.org/*|https://aninewstage.org/*)
            ans-dl "$url"
            ;;
        *)
            remaining+=("$url")
            ;;
    esac
done
if [ ${#remaining[@]} -gt 0 ]; then
    "$HOME/bin/termux-url-opener-orig" "${remaining[@]}"
fi
EOF
    fi; else if command -v yt >/dev/null 2>&1; then cat > "$HOME/bin/termux-url-opener" << 'EOF'
#!/bin/bash
remaining=()
for url in "$@"; do
    case "$url" in
        http://aninewstage.org/*|https://aninewstage.org/*)
            ans-dl "$url"
            ;;
        *)
            remaining+=("$url")
            ;;
    esac
done
if [ ${#remaining[@]} -gt 0 ]; then
    yt "${remaining[@]}"
fi
EOF
else cat > "$HOME/bin/termux-url-opener" << 'EOF'
#!/bin/bash
for url in "$@"; do
    case "$url" in
        http://aninewstage.org/*|https://aninewstage.org/*)
            ans-dl "$url"
            ;;
    esac
done
EOF
fi; fi && chmod a+x "$HOME/bin/termux-url-opener") && rm -rf $HOME/bin/ans-dl $HOME/.local/bin/ans-dl && if ! grep -qxF "export PATH=\$HOME/bin:\$PATH" "$HOME/.bashrc"; then echo "export PATH=\$HOME/bin:\$PATH" >> "$HOME/.bashrc"; fi && source "$HOME/.bashrc" && clear && ans-dl --help
```

### Usage example

- Copy and paste this into Termux.

```bash
ans-dl "https://aninewstage.org/view/to-save-seven-villainesses-i-went-full-harem/chapter/1"
```

### Download multiple chapters in series

```bash
ans-dl "https://aninewstage.org/view/to-save-seven-villainesses-i-went-full-harem/chapter/1" "https://aninewstage.org/view/to-save-seven-villainesses-i-went-full-harem/chapter/2"
```

### Output file path

- Default: `~/Downloads/<slug>/chapter-NN/`
- Custom: pass an output directory as the second argument

```
/storage/emulated/0/Download/<slug>/chapter-01/page-01.png
```

---

## Options

| Flag | Description |
|------|-------------|
| `-p N` / `--parallel N` | Download up to N chapters in parallel (default: 4, multi-chapter only) |
| `-h` / `--help` | Show this help (via Python `__doc__`) |

> **Note:** `ans-dl` doesn't have a dedicated `--help` flag — it uses Python's docstring. Run `ans-dl` with no arguments to see the full usage.

---

## How it works

### Image extraction

Chapter images are embedded directly in the SSR HTML as:

```javascript
slides: JSON.parse('[\\u0022https://files.aninewstage.org/...\\u0022, ...]')
```

The script extracts this JSON, decodes the escape sequences (`\\u0022` → `"`, `\\\\/` → `/`), and parses the URL list. No browser, no API, no JavaScript rendering needed.

### Two chapter formats

1. **Flat** — each page is a single full image URL. Downloaded directly as-is, preserving the original extension (PNG/JPG/WebP).

2. **Tiled** — each page is split into 4 panel tiles arranged in a 2×2 grid (田 shape). The script downloads all 4 tiles, composites them into a single page PNG using Pillow, and saves the result. Tile order: top-left, top-right, bottom-left, bottom-right.

### CDN

Images are served from `files.aninewstage.org` which allows any origin — no CORS issues.

---

## Project structure

```
ans-dl/
  ans-dl          # macOS/Linux launcher (bash)
  ans-dl.bat      # Windows launcher (cmd)
  ans-dl.py       # Python 3 downloader (stdlib + Pillow)
  README.md       # This file
```

---

## Verified

- Tested on [to-save-seven-villainesses-i-went-full-harem](https://aninewstage.org/view/to-save-seven-villainesses-i-went-full-harem) (flat format, 49 images/chapter)
- Tested on [alya-sometimes-hides-her-feelings-in-russian](https://aninewstage.org/view/alya-sometimes-hides-her-feelings-in-russian) (tiled format, 25 composite pages/chapter)

---

## License

[MIT](LICENSE)
