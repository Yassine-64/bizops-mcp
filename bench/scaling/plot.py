"""The scaling graph, drawn from bench/results/scaling/scaling.json with the stdlib (no plotting dependency).
Two files, light and dark, for a GitHub <picture> element. Series colours are the reference categorical
slots 1-3, validated for both surfaces; every line is direct-labelled and the README carries the table."""

from __future__ import annotations

import json
import sys
from pathlib import Path

THEMES = {
    "light": {
        "surface": "#fcfcfb",
        "ink": "#0b0b0b",
        "ink2": "#52514e",
        "muted": "#898781",
        "grid": "#e1e0d9",
        "axis": "#c3c2b7",
        "series": ["#2a78d6", "#eb6834", "#1baf7a"],
    },
    "dark": {
        "surface": "#1a1a19",
        "ink": "#f0efec",
        "ink2": "#c3c2b7",
        "muted": "#898781",
        "grid": "#2c2c2a",
        "axis": "#383835",
        "series": ["#3987e5", "#d95926", "#199e70"],
    },
}
SERIES = [
    ("static_tokens", "static: one tool per capability"),
    ("tool_search_tokens", "Anthropic tool search (deferred)"),
    ("discover_tokens", "bizops discover / execute / inspect"),
]
W, H = 760, 420
L, R, T, B = 78, 250, 64, 56


def svg(rows: list[dict[str, float]], theme: str) -> str:
    c = THEMES[theme]
    xs = [r["size"] for r in rows]
    ymax = max(r["static_tokens"] for r in rows) * 1.08
    xmax = max(xs)

    def px(x: float) -> float:
        return L + (W - L - R) * x / xmax

    def py(y: float) -> float:
        return T + (H - T - B) * (1 - y / ymax)

    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" '
        f'font-family="ui-sans-serif, system-ui, -apple-system, Segoe UI, sans-serif">',
        f'<rect width="{W}" height="{H}" fill="{c["surface"]}" rx="8"/>',
        f'<text x="{L}" y="30" font-size="16" font-weight="600" fill="{c["ink"]}">'
        "Tool-surface tokens in every request, by catalogue size</text>",
        f'<text x="{L}" y="48" font-size="12" fill="{c["ink2"]}">'
        "Measured with the count_tokens endpoint, claude-sonnet-5-5. 25 real capabilities plus "
        "near-miss distractors.</text>",
    ]
    step = 25_000
    for v in range(0, int(ymax) + 1, step):
        y = py(v)
        out.append(
            f'<line x1="{L}" x2="{W - R}" y1="{y:.1f}" y2="{y:.1f}" stroke="{c["grid"]}" stroke-width="1"/>'
        )
        out.append(
            f'<text x="{L - 10}" y="{y + 4:.1f}" font-size="11" fill="{c["muted"]}" '
            f'text-anchor="end">{v // 1000}k</text>'
        )
    out.append(
        f'<line x1="{L}" x2="{W - R}" y1="{py(0):.1f}" y2="{py(0):.1f}" stroke="{c["axis"]}" stroke-width="1"/>'
    )
    last = -1e9
    for x in xs:
        if px(x) - last < 30:  # skip a tick label that would collide with the previous one
            continue
        last = px(x)
        out.append(
            f'<text x="{px(x):.1f}" y="{H - B + 18}" font-size="11" fill="{c["muted"]}" '
            f'text-anchor="middle">{x}</text>'
        )
    out.append(
        f'<text x="{(L + W - R) / 2:.1f}" y="{H - 14}" font-size="12" fill="{c["ink2"]}" '
        'text-anchor="middle">capabilities in the catalogue</text>'
    )
    label_y: list[float] = []
    for (key, label), color in zip(SERIES, c["series"], strict=True):
        pts = " ".join(f"{px(r['size']):.1f},{py(r[key]):.1f}" for r in rows)
        out.append(
            f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="2" '
            'stroke-linejoin="round" stroke-linecap="round"/>'
        )
        for r in rows:
            out.append(
                f'<circle cx="{px(r["size"]):.1f}" cy="{py(r[key]):.1f}" r="4" fill="{color}" '
                f'stroke="{c["surface"]}" stroke-width="2"><title>{label}: {r[key]:,.0f} tokens at '
                f"{r['size']} capabilities</title></circle>"
            )
        end = rows[-1][key]
        y = py(end)
        while any(abs(y - other) < 30 for other in label_y):  # flat series share a baseline: stack labels
            y -= 30
        label_y.append(y)
        out.append(f'<circle cx="{W - R + 14}" cy="{y - 4:.1f}" r="4" fill="{color}"/>')
        out.append(
            f'<text x="{W - R + 24}" y="{y:.1f}" font-size="12" fill="{c["ink"]}">{end:,.0f} tokens</text>'
        )
        out.append(
            f'<text x="{W - R + 24}" y="{y + 14:.1f}" font-size="11" fill="{c["ink2"]}">{label}</text>'
        )
    out.append("</svg>")
    return "\n".join(out)


def main(path: str = "bench/results/scaling") -> None:
    d = Path(path)
    rows = json.loads((d / "scaling.json").read_text())
    for theme in THEMES:
        (d / f"surface-tokens-{theme}.svg").write_text(svg(rows, theme))
    print(f"wrote {d}/surface-tokens-light.svg and -dark.svg")


if __name__ == "__main__":
    main(*sys.argv[1:])
