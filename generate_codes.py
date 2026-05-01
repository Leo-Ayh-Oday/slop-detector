"""Generate activation codes for AI Slop Detector.

Usage:
    python generate_codes.py --count 20        # Generate 20 codes
    python generate_codes.py --code SLOP-XXXX-XXXX  # Add a single code
"""

import hashlib
import json
import secrets
import string
import sys
from pathlib import Path

CODES_FILE = Path(__file__).parent / "activation_codes.json"
CODE_ALPHABET = string.ascii_uppercase + string.digits


def generate_code() -> str:
    """Generate a code like SLOP-A3F8-2B1D."""
    part1 = "".join(secrets.choice(CODE_ALPHABET) for _ in range(4))
    part2 = "".join(secrets.choice(CODE_ALPHABET) for _ in range(4))
    return f"SLOP-{part1}-{part2}"


def hash_code(code: str) -> str:
    return hashlib.sha256(code.strip().encode()).hexdigest()


def load_codes() -> dict:
    if CODES_FILE.exists():
        return json.loads(CODES_FILE.read_text(encoding="utf-8"))
    return {"codes": [], "_plain_codes": []}


def save_codes(data: dict):
    CODES_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def main():
    args = sys.argv[1:]

    if not args:
        # Default: generate 10 codes
        count = 10
    elif args[0] == "--count":
        count = int(args[1]) if len(args) > 1 else 10
    elif args[0] == "--code":
        code = args[1] if len(args) > 1 else generate_code()
        data = load_codes()
        if hash_code(code) in data["codes"]:
            print(f"Code {code} already exists (hash collision).")
            return
        data["codes"].append(hash_code(code))
        data["_plain_codes"].append(code)
        save_codes(data)
        print(f"Added code: {code}")
        return
    elif args[0] == "--list":
        data = load_codes()
        print(f"{len(data.get('_plain_codes', []))} codes total:")
        for c in data.get("_plain_codes", []):
            print(f"  {c}")
        return
    else:
        print(__doc__)
        return

    data = load_codes()
    new_codes = []
    for _ in range(count):
        code = generate_code()
        while hash_code(code) in data["codes"]:
            code = generate_code()
        data["codes"].append(hash_code(code))
        new_codes.append(code)

    data.setdefault("_plain_codes", []).extend(new_codes)
    save_codes(data)

    print(f"Generated {count} new activation codes ({len(data['codes'])} total):")
    for c in new_codes:
        print(f"  {c}")
    print(f"\nSaved to {CODES_FILE}")
    print("Keep these codes safe. Give one to each paying customer.")


if __name__ == "__main__":
    main()
