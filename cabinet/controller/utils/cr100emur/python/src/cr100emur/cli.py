from __future__ import annotations

import argparse
import json
import sys

from .sdk import CR100Error, DEFAULT_BAUD, Reader, find_device


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Read card UIDs with the CR-100EMUR Python SDK."
    )
    parser.add_argument("-d", "--device")
    parser.add_argument("-b", "--baud", type=int, default=DEFAULT_BAUD)
    parser.add_argument(
        "-n", "--count", type=int, default=0, help="0 reads continuously"
    )
    parser.add_argument(
        "-t",
        "--timeout",
        type=float,
        default=None,
        help="per-card timeout in seconds",
    )
    parser.add_argument(
        "-f",
        "--format",
        choices=("hex", "decimal", "json", "bytes"),
        default="hex",
    )
    parser.add_argument(
        "-l", "--list", action="store_true", help="print the detected device"
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.count < 0:
        _parser().error("--count cannot be negative")

    try:
        if args.list:
            print(find_device())
            return 0

        read_count = 0
        with Reader(args.device, args.baud) as reader:
            while args.count == 0 or read_count < args.count:
                card = reader.read(args.timeout)
                if card is None:
                    print("timed out waiting for a card", file=sys.stderr)
                    return 3
                if args.format == "hex":
                    print(card.hex)
                elif args.format == "decimal":
                    print(card.value)
                elif args.format == "bytes":
                    print(":".join(f"{byte:02X}" for byte in card.uid))
                else:
                    print(
                        json.dumps(
                            {
                                "uid": card.hex,
                                "value": card.value,
                                "bytes": list(card.uid),
                            },
                            separators=(",", ":"),
                        )
                    )
                read_count += 1
    except KeyboardInterrupt:
        return 130
    except (CR100Error, OSError, ValueError) as error:
        print(f"cr100-python: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

