"""Docker image availability and build helpers."""

from __future__ import annotations

import asyncio
import logging
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)

_DEFAULT_IMAGE = "openharness-sandbox:latest"

_DOCKERFILE_CONTENT = """\
FROM python:3.11-slim
RUN apt-get update && apt-get install -y --no-install-recommends \\
    ripgrep bash git && \\
    rm -rf /var/lib/apt/lists/*
RUN useradd -m -s /bin/bash ohuser
USER ohuser
"""


def get_dockerfile_content() -> str:
    """Return the default Dockerfile content for the sandbox image."""
    return _DOCKERFILE_CONTENT


async def _image_exists(image: str) -> bool:
    """Check whether a Docker image exists locally."""
    docker = shutil.which("docker") or "docker"
    process = await asyncio.create_subprocess_exec(
        docker,
        "image",
        "inspect",
        image,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    await process.communicate()
    return process.returncode == 0


async def build_default_image(image: str = _DEFAULT_IMAGE) -> bool:
    """Build the default sandbox image from the bundled Dockerfile.

    Returns ``True`` on success, ``False`` on failure.
    """
    docker = shutil.which("docker") or "docker"
    dockerfile_path = Path(__file__).parent / "Dockerfile"

    if dockerfile_path.exists():
        cmd = [docker, "build", "-t", image, "-f", str(dockerfile_path), str(dockerfile_path.parent)]
    else:
        # Fallback: pipe Dockerfile content via stdin
        cmd = [docker, "build", "-t", image, "-"]

    logger.info("Building Docker sandbox image %r ...", image)

    if dockerfile_path.exists():
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    else:
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await process.communicate(input=_DOCKERFILE_CONTENT.encode("utf-8"))
        if process.returncode == 0:
            logger.info("Docker sandbox image %r built successfully", image)
            return True
        logger.warning("Failed to build Docker sandbox image %r", image)
        return False

    _, stderr_bytes = await process.communicate()
    if process.returncode == 0:
        logger.info("Docker sandbox image %r built successfully", image)
        return True

    logger.warning(
        "Failed to build Docker sandbox image %r: %s",
        image,
        stderr_bytes.decode("utf-8", errors="replace").strip(),
    )
    return False


async def ensure_image_available(image: str, auto_build: bool) -> bool:
    """Ensure the sandbox image exists, optionally building it.

    Returns ``True`` if the image is available.
    """
    if await _image_exists(image):
        return True
    if not auto_build:
        logger.warning("Docker image %r not found and auto_build_image is disabled", image)
        return False
    return await build_default_image(image)
