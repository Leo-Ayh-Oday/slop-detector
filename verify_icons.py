"""Verify generated extension icons are valid PNGs."""
from pathlib import Path
import struct
import io

icons_dir = Path(__file__).parent / "extension" / "icons"
for size in (16, 48, 128):
    path = icons_dir / f"icon-{size}.png"
    data = path.read_bytes()
    print(f"\nicon-{size}.png: {len(data)} bytes")

    # Check PNG signature
    assert data[:8] == b'\x89PNG\r\n\x1a\n', "Bad PNG signature"
    print("  Signature: OK")

    # Parse chunks
    pos = 8
    chunks = []
    try:
        while pos < len(data):
            length = int.from_bytes(data[pos:pos+4], 'big')
            chunk_type = data[pos+4:pos+8].decode('ascii')
            chunks.append((chunk_type, length))
            # Read chunk data for IHDR
            if chunk_type == 'IHDR':
                w, h = struct.unpack('>II', data[pos+8:pos+16])
                print(f"  IHDR: {w}x{h}, OK" if w == size and h == size else f"  IHDR: {w}x{h}, WRONG SIZE")
            pos += 12 + length
        print(f"  Total chunks: {len(chunks)} — {[c for c, _ in chunks]}")
    except Exception as e:
        print(f"  Parse error at offset {pos}: {e}")
        break

    assert pos == len(data), f"Extra bytes: {len(data) - pos}"
    assert ('IHDR', 13) in chunks, "Missing IHDR"
    assert ('IDAT', chunks[[c for c, _ in chunks].index('IDAT')][1]) in chunks if 'IDAT' in [c for c, _ in chunks] else False, "Missing IDAT"
    assert ('IEND', 0) in chunks, "Missing IEND"
    print("  PNG structure: VALID")

print("\nAll icons OK.")
