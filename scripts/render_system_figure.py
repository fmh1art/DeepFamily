from __future__ import annotations

import hashlib
import json
from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
from matplotlib.axes import Axes
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Rectangle

PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = PROJECT_ROOT / "paper/figures"

INK = "#20242A"
MUTED = "#5B6470"
LIGHT = "#F3F5F7"
LINE = "#A7AFB8"
BLUE = "#0072B2"
GREEN = "#009E73"
ORANGE = "#E69F00"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def box(
    axis: Axes,
    x: float,
    y: float,
    width: float,
    height: float,
    title: str,
    subtitle: str,
    *,
    edge: str = LINE,
    face: str = "white",
    linewidth: float = 0.9,
) -> None:
    patch = FancyBboxPatch(
        (x, y),
        width,
        height,
        boxstyle="round,pad=0.025,rounding_size=0.045",
        facecolor=face,
        edgecolor=edge,
        linewidth=linewidth,
    )
    axis.add_patch(patch)
    axis.text(
        x + width / 2,
        y + height * 0.62,
        title,
        ha="center",
        va="center",
        color=INK,
        fontsize=6.8,
        fontweight="bold",
    )
    axis.text(
        x + width / 2,
        y + height * 0.28,
        subtitle,
        ha="center",
        va="center",
        color=MUTED,
        fontsize=6.0,
    )


def arrow(
    axis: Axes,
    start: tuple[float, float],
    end: tuple[float, float],
    *,
    color: str = BLUE,
    style: str = "-",
    connection: str = "arc3",
    width: float = 1.1,
) -> None:
    axis.add_patch(
        FancyArrowPatch(
            start,
            end,
            arrowstyle="-|>",
            mutation_scale=8,
            linewidth=width,
            linestyle=style,
            color=color,
            connectionstyle=connection,
            shrinkA=1,
            shrinkB=1,
        )
    )


def render() -> None:
    mpl.rcParams.update(
        {
            "font.family": "sans-serif",
            "font.sans-serif": ["DejaVu Sans", "Arial", "Helvetica"],
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
        }
    )
    figure, axis = plt.subplots(figsize=(7.15, 2.72))
    figure.patch.set_facecolor("white")
    axis.set_xlim(0, 12.2)
    axis.set_ylim(0, 4.6)
    axis.axis("off")

    axis.text(0.05, 4.38, "a", fontsize=9, fontweight="bold", color=INK)
    axis.text(
        0.32, 4.38, "Question-only boundary", fontsize=8.2, fontweight="bold", color=INK
    )
    axis.text(4.03, 4.38, "b", fontsize=9, fontweight="bold", color=INK)
    axis.text(
        4.30,
        4.38,
        "Execution-grounded closed loop",
        fontsize=8.2,
        fontweight="bold",
        color=INK,
    )

    axis.add_patch(
        Rectangle(
            (0.05, 0.28),
            3.52,
            3.76,
            facecolor="#FAFBFC",
            edgecolor=LINE,
            linewidth=0.8,
        )
    )
    box(
        axis,
        0.36,
        2.73,
        2.88,
        0.82,
        "Analytical question",
        "no file · table · schema",
        edge=BLUE,
        face="#EAF3F8",
    )
    arrow(axis, (1.80, 2.70), (1.80, 2.27))
    box(
        axis,
        0.36,
        1.43,
        2.88,
        0.82,
        "Authorized environment",
        "repositories · policies · budget",
    )
    arrow(axis, (1.50, 1.40), (1.03, 0.98), color=GREEN)
    arrow(axis, (2.10, 1.40), (2.57, 0.98), color=ORANGE)
    box(
        axis,
        0.36,
        0.48,
        1.34,
        0.48,
        "Report",
        "claim lineage",
        edge=GREEN,
        face="#EAF6F2",
    )
    box(
        axis,
        1.90,
        0.48,
        1.34,
        0.48,
        "Data gap",
        "attempts + needs",
        edge=ORANGE,
        face="#FFF5E5",
    )
    axis.text(
        1.80,
        3.82,
        "Only per-task input",
        ha="center",
        color=BLUE,
        fontsize=6.0,
        fontweight="bold",
    )

    xs = [4.08, 5.61, 7.14, 8.67, 10.20]
    widths = [1.32, 1.32, 1.32, 1.32, 1.66]
    labels = [
        ("Contract", "needs · joins"),
        ("Discover", "rank · profile"),
        ("Prepare", "clean · join"),
        ("Analyze", "execute"),
        ("Validate", "coverage · proof"),
    ]
    colors = [BLUE, BLUE, GREEN, GREEN, ORANGE]
    faces = ["#EAF3F8", "#EAF3F8", "#EAF6F2", "#EAF6F2", "#FFF5E5"]
    for x, width, (title, subtitle), edge, face in zip(
        xs, widths, labels, colors, faces, strict=True
    ):
        box(axis, x, 2.55, width, 0.82, title, subtitle, edge=edge, face=face)
    for left_x, left_width, right_x in zip(xs, widths, xs[1:], strict=False):
        arrow(axis, (left_x + left_width, 2.96), (right_x, 2.96))

    box(
        axis,
        10.35,
        1.17,
        1.75,
        0.64,
        "Accept report",
        "obligations met",
        edge=GREEN,
        face="#EAF6F2",
    )
    arrow(axis, (10.94, 2.53), (11.14, 1.84), color=GREEN)
    axis.text(11.34, 2.13, "pass", fontsize=6.0, color=GREEN, fontweight="bold")

    box(
        axis,
        7.04,
        0.95,
        2.17,
        0.70,
        "Repair goal",
        "violation + upstream stage",
        edge=ORANGE,
        face="#FFF5E5",
    )
    arrow(axis, (10.57, 2.53), (9.12, 1.67), color=ORANGE, style="--")
    axis.text(9.76, 2.08, "fail", fontsize=6.0, color=ORANGE, fontweight="bold")
    arrow(
        axis,
        (7.03, 1.26),
        (6.32, 2.51),
        color=ORANGE,
        style="--",
        connection="arc3,rad=-0.35",
        width=1.35,
    )
    axis.text(
        5.38,
        1.70,
        "reopen Discovery",
        color=ORANGE,
        fontsize=6.1,
        fontweight="bold",
    )

    axis.plot([4.20, 11.86], [0.48, 0.48], color=LINE, linewidth=0.8)
    lineage_items = [
        (4.25, "source decision"),
        (6.15, "table state"),
        (7.78, "analysis artifact"),
        (9.72, "report claim"),
    ]
    for x, label in lineage_items:
        axis.plot(x, 0.48, marker="o", markersize=3.8, color=INK)
        axis.text(x, 0.21, label, ha="center", va="center", color=MUTED, fontsize=6.0)
    axis.text(
        11.88,
        0.48,
        "lineage",
        ha="right",
        va="bottom",
        color=MUTED,
        fontsize=6.0,
        fontweight="bold",
    )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    pdf_path = OUTPUT_DIR / "system-overview.pdf"
    png_path = OUTPUT_DIR / "system-overview.png"
    figure.savefig(pdf_path, bbox_inches="tight", pad_inches=0.02)
    figure.savefig(
        png_path,
        dpi=300,
        bbox_inches="tight",
        pad_inches=0.02,
    )
    plt.close(figure)
    source_path = Path(__file__).resolve()
    manifest = {
        "schema_version": "askdu-system-figure-v1",
        "source_script": source_path.relative_to(PROJECT_ROOT).as_posix(),
        "source_sha256": sha256_file(source_path),
        "outputs": {
            pdf_path.relative_to(PROJECT_ROOT).as_posix(): {
                "sha256": sha256_file(pdf_path),
                "bytes": pdf_path.stat().st_size,
                "format": "vector-pdf",
            },
            png_path.relative_to(PROJECT_ROOT).as_posix(): {
                "sha256": sha256_file(png_path),
                "bytes": png_path.stat().st_size,
                "format": "png-300-dpi",
            },
        },
    }
    (OUTPUT_DIR / "system-overview.capture.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    render()
