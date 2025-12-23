"""
Generate idle/running/error tray icon variants from the base icon.ico.

Copyright (C) 2023-2025 by tinbox.wu
"""

from __future__ import annotations

import os
import sys

from pathlib import Path
from typing import List

from PIL import Image, ImageOps

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else BASE_DIR

ICON_DIR = Path(APP_DIR) / "icon"
BASE_ICON = ICON_DIR / "icon.ico"
IDLE_ICON = ICON_DIR / "icon-idle.ico"
RUNNING_ICON = ICON_DIR / "icon-running.ico"
ERROR_ICON = ICON_DIR / "icon-error.ico"

IDLE_COLORS = {"black": "#4b5563", "white": "#f1f5f9"}
RUNNING_COLORS = {"black": "#065f46", "white": "#34d399"}
ERROR_COLORS = {"black": "#7f1d1d", "white": "#f87171"}


def ensure_icon_exists() -> Path:
    icon_path = BASE_ICON
    if not icon_path.exists():
        print(f"找不到原始图标: {icon_path.resolve()}")
        raise FileNotFoundError(f"找不到原始图标: {icon_path.resolve()}")
    return icon_path


def transform_frame(frame: Image.Image, colors: dict[str, str]) -> Image.Image:
    rgba = frame.convert("RGBA")
    alpha = rgba.getchannel("A")
    gray = ImageOps.grayscale(rgba)
    colored = ImageOps.colorize(gray, **colors).convert("RGBA")
    colored.putalpha(alpha)
    return colored


def collect_frames(icon_path: Path, colors: dict[str, str]) -> List[Image.Image]:
    frames: List[Image.Image] = []
    with Image.open(icon_path) as source:
        frame_count = getattr(source, "n_frames", 1)
        for idx in range(frame_count):
            source.seek(idx)
            frames.append(transform_frame(source.copy(), colors))
    return frames


def save_icon(frames: List[Image.Image], target_path: Path) -> None:
    if not frames:
        raise ValueError("没有可写入的帧数据。")
    sizes = [img.size for img in frames]
    frames[0].save(target_path, format="ICO", sizes=sizes)


def main() -> None:
    icon_path = ensure_icon_exists()
    idle_frames = collect_frames(icon_path, IDLE_COLORS)
    running_frames = collect_frames(icon_path, RUNNING_COLORS)
    error_frames = collect_frames(icon_path, ERROR_COLORS)
    save_icon(idle_frames, IDLE_ICON)
    save_icon(running_frames, RUNNING_ICON)
    save_icon(error_frames, ERROR_ICON)
    print("已生成", IDLE_ICON, RUNNING_ICON, ERROR_ICON)


if __name__ == "__main__":
    main()
