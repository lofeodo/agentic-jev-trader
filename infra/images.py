"""Build the two images and load them into the local kind cluster (spec appendix 10, section 3).

Run from the repo root, with Docker running and the kind cluster created:

    conda run -n agentic-jev-trader python infra/images.py build

Two images, each tagged with the git commit (`git rev-parse --short HEAD`, the same commit a
sim records) and loaded with `kind load docker-image`, with no registry: the Python image
(recipe `Dockerfile`, every Python piece) and the web image (recipe `web/Dockerfile`).
`--no-load` only builds, as CI does; `--cluster` names another kind cluster than `jev-trader`.
`tag` prints the tag, for Terraform's `image_tag`. It needs only Python's standard library.
Output is plain ASCII: `conda run` on Windows fails on other characters.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
# The kind cluster's name; Terraform's Kubernetes part reaches it as context kind-jev-trader.
CLUSTER = "jev-trader"


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
            "--build-arg",
            f"CODE_VERSION={tag}",
            str(self.context),
        ]

    def load_command(self, tag: str, cluster: str) -> list[str]:
        """The `kind load docker-image` that copies this image into the cluster's node."""
        return ["kind", "load", "docker-image", f"{self.name}:{tag}", "--name", cluster]


IMAGES = (
    Image("jev-trader", REPO_ROOT / "Dockerfile", REPO_ROOT),
    Image("jev-trader-web", REPO_ROOT / "web" / "Dockerfile", REPO_ROOT / "web"),
)


def git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=REPO_ROOT, capture_output=True, text=True, check=True
    ).stdout.strip()


def commit_tag() -> str:
    """The same short commit `jev_trader.sim.runner.code_version` records for a sim."""
    return git("rev-parse", "--short", "HEAD")


def run(command: list[str], env: dict[str, str] | None = None) -> bool:
    """Run a command, asking it nothing, and pass on what it prints as plain ASCII: the web
    build and Terraform print other characters, on which `conda run` on Windows fails. `env`
    replaces the environment it runs in."""
    print("> " + " ".join(command), flush=True)
    with subprocess.Popen(
        command,
        cwd=REPO_ROOT,
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    ) as process:
        for line in process.stdout:
            print(line.rstrip().encode("ascii", "replace").decode("ascii"), flush=True)
    return process.returncode == 0


def build(load: bool, cluster: str) -> int:
    tools = ["docker", "kind"] if load else ["docker"]
    missing = [tool for tool in tools if shutil.which(tool) is None]
    if missing:
        print("not found on this computer: " + ", ".join(missing))
        return 2
    if git("status", "--porcelain"):
        # The tag names a commit; a sim run from the image records it as the code it ran.
        print("the checkout has uncommitted changes: commit them first, then build")
        return 2
    tag = commit_tag()
    for image in IMAGES:
        if not run(image.build_command(tag)):
            print(f"building {image.name} failed")
            return 1
    if load:
        for image in IMAGES:
            if not run(image.load_command(tag, cluster)):
                print(f"loading {image.name} into the kind cluster {cluster} failed")
                return 1
    where = f"loaded into the kind cluster {cluster}" if load else "not loaded"
    print(f"built {', '.join(f'{image.name}:{tag}' for image in IMAGES)}; {where}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python infra/images.py")
    commands = parser.add_subparsers(dest="command", required=True)
    building = commands.add_parser(
        "build", help="build both images and load them into kind"
    )
    building.add_argument(
        "--no-load", action="store_true", help="only build; load nothing into kind"
    )
    building.add_argument("--cluster", default=CLUSTER, help="the kind cluster's name")
    commands.add_parser("tag", help="print the git commit the images are tagged with")
    args = parser.parse_args(argv)
    if args.command == "tag":
        print(commit_tag())
        return 0
    return build(load=not args.no_load, cluster=args.cluster)


if __name__ == "__main__":
    sys.exit(main())
