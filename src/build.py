from pathlib import Path

from manuscript.build import build

if __name__ == "__main__":
    build(Path(__file__).resolve().parents[1] / "docs")
