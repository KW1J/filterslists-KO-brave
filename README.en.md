<p align="center">
  <a href="README.md"><img src="https://img.shields.io/badge/lang-%ED%95%9C%EA%B5%AD%EC%96%B4-blue" alt="한국어"></a>
  <a href="README.en.md"><img src="https://img.shields.io/badge/lang-English-red" alt="English"></a>
</p>

# filterslists-KO for Brave

An unofficial build that converts the uBlock Origin distribution of
[`filterslists-KO`](https://github.com/FilteringDev/filterslists-KO) (a Korean ad/tracker blocking filter list)
into something that **actually works in Brave (Shields, the brave/adblock-rust engine)**, and refreshes it
automatically with GitHub Actions.

- Source: `dist/resolved/filterslist-uBlockOrigin/ubo-chromium.txt` from the `@filteringdev/filterslists-ko` npm package
- Updates: GitHub Actions fetches the upstream list every 6 hours, converts it, and auto-commits only `dist/`
- Verification: every converted rule is parsed with **the same parser Brave ships (adblock-rust 0.13.5)**; zero rejections

## Subscribe

Open `brave://settings/shields/filters` in Brave and paste the URL below into **Add filter list by URL**.

```
https://raw.githubusercontent.com/KW1J/filterslists-KO-brave/main/dist/filterslists-KO-brave.txt
```

Alternative URL through a CDN cache (faster, but may lag behind by minutes to hours):

```
https://cdn.jsdelivr.net/gh/KW1J/filterslists-KO-brave@main/dist/filterslists-KO-brave.txt
```

> **Avoid double filtering (optional)**
> If Brave's built-in **Korean website ad blocker** (`brave://settings/shields/filters` → Content filters) is also
> enabled, the same sites get filtered twice. Nothing breaks, but filter debugging becomes harder, so it is
> recommended to turn the built-in Korean list off while using this one.

## Why a conversion is needed

filterslists-KO uses uBlock Origin syntax. Brave's engine (adblock-rust) supports uBO's procedural operators
(`:has-text`, `:matches-css`, `:upward`, `:remove()`, `:style()`, ...), but it rejects uBO's **style injection
notation** (`#$#`) and **procedural-body notation** (`#$?#`) at parse time. Pasting the upstream list as-is
therefore silently drops 268 style/element-removal rules.

This repository mechanically rewrites them into the equivalent ABP/Brave notation.

| Upstream (uBO) | Converted (Brave) | Rules |
|---|---|---:|
| `host#$#sel { color: red !important; }` | `host##sel:style(color: red !important;)` | 247 |
| `host#$?#sel { remove: true; }` | `host##sel:remove()` | 21 |
| `host#@$#…` / `host#@$?#…` | `host#@#sel:style(…)` / `:remove()` | 0 (none in the current upstream list) |

- Multiple declarations are joined on one line in their original order (`calc()`, `!important`, quotes preserved).
- Comma-separated selector lists are split into separate rules with the host repeated — otherwise
  `:style()`/`:remove()` would only bind to the last selector.
- Commas/braces inside parentheses or attribute values (`:has(a, b)`, `[data-x="a,b"]`,
  `:matches-css(/^[0-9]{2,3}/)`) are left alone.

## Verification (adblock-rust 0.13.5, real parsing)

| | Upstream uBO | This build |
|---|---:|---:|
| Rules | 4,176 | 4,176 |
| Parsed successfully | 3,736 (89.5%) | **4,004 (95.9%)** |
| Parse failures | 440 (10.5%) | **172 (4.1%)** |
| Rejected converted rules | — | **0** |

The remaining 172 rules cannot be converted without guessing domains, so they are kept **verbatim**
(Brave silently ignores such lines):

| Count | Reason |
|---:|---|
| 92 | Regex hostnames (`/site[0-9]+\.tv/##…`) — adblock-rust does not allow regexes in the hostname |
| 58 | `$domain=/regex/` — option domains cannot be regexes either |
| 18 | Regex filters ending in `$`, which gets mis-parsed as an option separator |
| 2 | `$denyallow` not implemented |
| 1 | `$header` not implemented |
| 1 | `##^` HTML filtering unsupported |

In other words this build is a **superset** of upstream: every rule Brave understands is still there, plus 268
rules that now work. No rule that does not exist upstream is invented.

## Building locally

```bash
python3 scripts/build.py                 # fetch from jsDelivr and write dist/
python3 scripts/build.py --source-file ubo-chromium.txt   # offline / specific file
python3 -m unittest discover -s tests -v                  # converter unit tests
```

If the download fails it automatically falls back to the npm registry tarball. No third-party dependencies
(standard library only).

### Engine validation (optional, needs Rust)

```bash
cd ci/brave_check
cargo run --release -- ../../dist/filterslists-KO-brave.txt 250
```

`brave_check` parses the list line by line with adblock-rust and exits 1 if (1) any `:style(...)`/`:remove()`
rule produced by the converter is rejected, or (2) the total number of rejected rules exceeds the budget
(default 250). CI runs the same check, so a syntax change upstream that breaks the conversion fails the build.

## Repository layout

```
scripts/build.py          converter + downloader (stdlib only)
tests/test_convert.py     unit tests for the conversion rules
ci/brave_check/           adblock-rust based validator (Cargo)
dist/filterslists-KO-brave.txt   the published list (generated, do not edit by hand)
.github/workflows/build.yml     build, validate and commit every 6 hours
```

## License and attribution

- Upstream filter list: [FilteringDev/filterslists-KO](https://github.com/FilteringDev/filterslists-KO) — **GPL-3.0-only**
- The conversion code and build output in this repository are likewise **GPL-3.0-only** (see `LICENSE`).
- All trademarks and copyrights belong to their respective owners. This repository is an **unofficial port**,
  unaffiliated with the upstream project.
- The upstream project officially supports only AdGuard and uBlock Origin. This repository does not guarantee
  behaviour in Brave, and please do not file Brave-related issues against the upstream project.
