"""Rewind: causal time-travel debugging for Node.js."""
from pathlib import Path

__version__ = "0.1.0"
RECORDER = Path(__file__).resolve().parent.parent / "recorder" / "recorder.js"
