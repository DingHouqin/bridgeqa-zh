"""Usage: python -m bridgeqa.cli validate PATH | evaluate GOLD PREDICTIONS."""

import argparse
import json
import sys
from .io import read_jsonl
from .validation import validate_samples
from .evaluation import evaluate


def main():
    parser = argparse.ArgumentParser(description="BridgeQA ZH local reference tools")
    commands = parser.add_subparsers(dest="command", required=True)
    validate = commands.add_parser("validate", help="check core sample/pair structure")
    validate.add_argument("samples")
    score = commands.add_parser("evaluate", help="score canonical answers and paired fixtures")
    score.add_argument("samples")
    score.add_argument("predictions")
    args = parser.parse_args()
    try:
        samples = read_jsonl(args.samples)
        result = validate_samples(samples) if args.command == "validate" else evaluate(samples, read_jsonl(args.predictions))
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
