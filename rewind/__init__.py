"""Rewind: postmortem debugging for Node.js applications."""
from pathlib import Path

__version__ = "0.1.0"
RECORDER = Path(__file__).resolve().parent.parent / "recorder" / "recorder.js"
