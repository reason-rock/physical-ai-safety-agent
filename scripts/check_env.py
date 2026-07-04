from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from gaitlab.config import GaitLabConfig
from gaitlab.tools.node_registry import list_nodes


def main() -> None:
    config = GaitLabConfig.load()
    print(json.dumps(config.safe_summary(), indent=2))
    print(json.dumps(list_nodes(), indent=2))


if __name__ == "__main__":
    main()
