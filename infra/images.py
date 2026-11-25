"""Build the two images and load them into the local kind cluster (spec appendix 10, section 3).

Run from the repo root:

    conda run -n agentic-jev-trader python infra/images.py build

Two images, each tagged with the git commit and loaded with `kind load docker-image`, with no
registry: the Python image (recipe `Dockerfile`, every Python piece) and the web image (recipe
`web/Dockerfile`). Output is plain ASCII: `conda run` on Windows fails on other characters.

Skeleton: `build` names each image's build command and stops as not built yet. Building and
loading arrive with the slice's images ticket (#198).
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Image:
    name: str
    recipe: Path
    context: Path

    def build_command(self, tag: str) -> list[str]:
        """The `docker build` that makes this image, tagged `<name>:<tag>`."""
        return [
            "docker",
            "build",
            "--file",
            str(self.recipe),
            "--tag",
            f"{self.name}:{tag}",
            str(self.context),
        ]


IMAGES = (
    Image("jev-trader", REPO_ROOT / "Dockerfile", REPO_ROOT),
    Image("jev-trader-web", REPO_ROOT / "web" / "Dockerfile", REPO_ROOT / "web"),
)


def build() -> int:
    for image in IMAGES:
        print(" ".join(image.build_command("<git commit>")))
    print("building the images and loading them into kind is not built yet")
    return 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python infra/images.py")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("build", help="build both images and load them into kind")
    parser.parse_args(argv)
    return build()


if __name__ == "__main__":
    sys.exit(main())
