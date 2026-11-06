#!/usr/bin/env python3
"""Build a Brave-compatible version of the Korean ad-block list filterslists-KO.

Reads the fully preprocessed uBO list published in the npm package
``@filteringdev/filterslists-ko`` (dist/resolved/filterslist-uBlockOrigin/ubo-chromium.txt)
and rewrites the uBO-only cosmetic syntax into the Adblock Plus / adblock-rust
syntax that Brave actually implements:

    host#$#selector { declarations }        ->  host##selector:style(declarations)
    host#$?#selector { remove: true; }      ->  host##selector:remove()
    host#$?#selector { declarations }       ->  host##selector:style(declarations)
    host#@$#...  /  host#@$?#...            ->  host#@#selector:pseudo(...)

Everything else (network filters, scriptlets, regex hostnames, ...) is passed
through untouched.  Rules that Brave cannot parse are silently ignored by
Brave, so keeping them is harmless and keeps this build a faithful superset.

Stdlib only, Python 3.9+ (GitHub Actions ubuntu runner ships 3.12).
"""

from __future__ import annotations

import argparse
import io
import os
import re
import sys
import tarfile
import urllib.request

PKG = "@filteringdev/filterslists-ko"
SRC_PATH = "dist/resolved/filterslist-uBlockOrigin/ubo-chromium.txt"
JSDELIVR = "https://cdn.jsdelivr.net/npm/%s@latest/%s" % (PKG, SRC_PATH)
REGISTRY = "https://registry.npmjs.org/%s" % PKG.replace("/", "%2F")

HOME = "https://github.com/KW1J/filterslists-KO-brave"
UPSTREAM = "https://github.com/FilteringDev/filterslists-KO"

# Header lines of the upstream file that we replace with our own.
_REPLACED_META = re.compile(r"^!\s*(title|description|version|expires|homepage|homepage|licen[cs]e|last modified|redirect)\s*:", re.I)

# uBO cosmetic markers, longest first so "#$?#" wins over "#$#".
_MARKERS = (
    ("#@$?#", "#@#", True),
    ("#@$#", "#@#", True),
    ("#$?#", "##", False),
    ("#$#", "##", False),
)

_REMOVE_ONLY = re.compile(r"^\s*remove\s*:\s*true\s*;?\s*$", re.I)


def split_top_level(text: str, sep: str = ",") -> list[str]:
    """Split on ``sep`` at bracket/quote depth 0 (commas in :has(), [a="b,c"] …)."""
    parts, cur, depth, quote = [], [], 0, None
    for ch in text:
        if quote:
            cur.append(ch)
            if ch == quote:
                quote = None
            continue
        if ch in "\"'":
            quote = ch
        elif ch in "([":
            depth += 1
        elif ch in ")]":
            depth = max(0, depth - 1)
        if ch == sep and depth == 0:
            parts.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
    parts.append("".join(cur))
    return [p.strip() for p in parts if p.strip()]


def clean_style(body: str) -> str:
    """Normalise a uBO style body into a single-line :style() argument."""
    body = re.sub(r"\s*\n\s*", " ", body)
    body = re.sub(r"[ \t]+", " ", body).strip()
    body = re.sub(r"\s*;\s*", "; ", body)
    body = body.strip(" ;")
    return body + ";"


def convert_rule(line: str):
    """Return (new_line, kind) or (None, reason) if the line is not convertible.

    kind is one of: "style", "remove", "exception-style", "exception-remove".
    """
    for marker, replacement, is_exception in _MARKERS:
        idx = line.find(marker)
        if idx <= 0:
            continue
        # A cosmetic marker must be preceded by a hostname part; network filters
        # with "$" options never contain these sequences, so this is unambiguous.
        head, rest = line[:idx], line[idx + len(marker):]
        rest = rest.rstrip()
        if not rest.endswith("}"):
            return None, "no-brace-body"
        brace = rest.rfind("{")
        if brace <= 0:
            return None, "no-brace-body"
        selector = rest[:brace].strip()
        body = rest[brace + 1: -1].strip()
        if not selector:
            return None, "empty-selector"
        if not body:
            return None, "empty-body"

        remove = bool(_REMOVE_ONLY.match(body))
        if not remove:
            body = clean_style(body)
            if not body.strip("; "):
                return None, "empty-body"

        # Split comma-separated selector lists so :style()/:remove() applies to
        # every selector (a trailing pseudo-class would only bind the last one).
        selectors = split_top_level(selector)
        if not selectors:
            return None, "empty-selector"

        suffix = ":remove()" if remove else ":style(%s)" % body
        out = ", ".join(head + replacement + sel + suffix for sel in selectors)
        kind = ("exception-" if is_exception else "") + ("remove" if remove else "style")
        return out, kind
    return None, "no-marker"


def fetch(url: str, timeout: int = 60) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "filterslists-KO-brave/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def download_source() -> tuple[str, str]:
    """Return (text, where_it_came_from). Falls back to the npm tarball."""
    try:
        text = fetch(JSDELIVR).decode("utf-8")
        if "! Version:" in text:
            return text, JSDELIVR
        raise ValueError("unexpected payload from jsDelivr")
    except Exception as exc:  # noqa: BLE001 - any failure -> tarball fallback
        print("jsDelivr failed (%s), falling back to npm registry" % exc, file=sys.stderr)

    import json

    meta = json.loads(fetch(REGISTRY).decode("utf-8"))
    version = meta["dist-tags"]["latest"]
    tar_bytes = fetch(meta["versions"][version]["dist"]["tarball"], timeout=120)
    with tarfile.open(fileobj=io.BytesIO(tar_bytes), mode="r:gz") as tf:
        member = tf.extractfile("package/" + SRC_PATH)
        if member is None:
            raise RuntimeError("%s missing from npm tarball" % SRC_PATH)
        return member.read().decode("utf-8"), "npm:%s (%s)" % (PKG, version)


def source_version(lines: list[str]) -> str | None:
    for ln in lines:
        m = re.match(r"^!\s*Version\s*:\s*(\S+)", ln, re.I)
        if m:
            return m.group(1)
    return None


def build(text: str, version_override: str | None = None):
    lines = text.splitlines()
    version = version_override or source_version(lines) or "unknown"

    stats = {
        "rules_in": 0,
        "comments_in": 0,
        "converted_style": 0,
        "converted_remove": 0,
        "converted_exception_style": 0,
        "converted_exception_remove": 0,
        "kept_unconverted": 0,
        "unconverted_reasons": {},
        "unchanged": 0,
        "rules_out": 0,
    }

    body: list[str] = []
    for raw in lines:
        ln = raw.rstrip()
        if not ln.strip():
            continue
        if ln.startswith("!") or ln.startswith("["):
            if _REPLACED_META.match(ln):
                continue
            stats["comments_in"] += 1
            body.append(ln)
            continue

        stats["rules_in"] += 1
        if "#$" not in ln:
            stats["unchanged"] += 1
            body.append(ln)
            continue

        new_line, kind = convert_rule(ln)
        if new_line is None:
            stats["kept_unconverted"] += 1
            reasons = stats["unconverted_reasons"]
            reasons[kind] = reasons.get(kind, 0) + 1
            body.append(ln)
            continue
        stats["converted_" + kind.replace("-", "_").replace(" ", "_")] += 1
        body.append(new_line)

    stats["rules_out"] = sum(
        stats[k] for k in ("converted_style", "converted_remove", "converted_exception_style",
                           "converted_exception_remove", "unchanged", "kept_unconverted")
    )

    header = [
        "! Title: filterslists-KO (Brave)",
        "! Description: 한국어권 웹 사이트의 광고·트래커·방해 요소를 차단하는 필터 리스트 (Brave/adblock-rust 호환 빌드)",
        "! Version: %s" % version,
        "! Expires: 1 day",
        "! Homepage: %s" % HOME,
        "! Source: %s (GPL-3.0-only)" % UPSTREAM,
        "! Licence: https://github.com/FilteringDev/filterslists-KO/blob/master/LICENSE",
        "!",
        "! Brave build of %s %s" % (PKG, version),
        "! Generated by scripts/build.py - do not edit dist/ by hand.",
        "! Converted: %d style injection (#$# -> :style()), %d procedural remove (#$?# -> :remove()), %d exception(s)"
        % (stats["converted_style"], stats["converted_remove"],
           stats["converted_exception_style"] + stats["converted_exception_remove"]),
        "! Rules that need uBO-only syntax adblock-rust cannot parse (regex hostnames,",
        "! $domain=/re/, $denyallow, $replace, ##^ ...) are kept verbatim; Brave skips them.",
        "! Engine: brave/adblock-rust (same parser as Brave Shields)",
    ]
    return "\n".join(header + body) + "\n", stats, version


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", default="dist/filterslists-KO-brave.txt", help="output path")
    ap.add_argument("--source-file", help="use a local file instead of downloading")
    ap.add_argument("--version", help="override the ! Version: header value")
    args = ap.parse_args(argv)

    if args.source_file:
        with open(args.source_file, encoding="utf-8") as fh:
            text = fh.read()
        origin = args.source_file
    else:
        text, origin = download_source()

    out_text, stats, version = build(text, args.version)

    out_path = args.out
    parent = os.path.dirname(out_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(out_path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(out_text)

    print("source: %s" % origin)
    print("version: %s" % version)
    print("output: %s" % out_path)
    for key in ("rules_in", "converted_style", "converted_remove", "converted_exception_style",
                "converted_exception_remove", "kept_unconverted", "unchanged", "rules_out"):
        print("%-20s %d" % (key, stats[key]))
    for reason, count in sorted(stats["unconverted_reasons"].items(), key=lambda kv: -kv[1]):
        print("unconverted[%s] %d" % (reason, count))
    return 0


if __name__ == "__main__":
    sys.exit(main())
