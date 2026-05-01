"""Generate simple PNG icons for the AI Slop Detector extension.
Uses only Python stdlib (struct + zlib) — no external dependencies.
"""

import struct
import zlib
from pathlib import Path


def create_png(width: int, height: int, pixels: list[tuple[int, int, int, int]]) -> bytes:
    """Create a valid PNG from raw RGBA pixel data (row-major, top-to-bottom)."""
    # PNG signature
    sig = b'\x89PNG\r\n\x1a\n'

    # IHDR chunk
    ihdr_data = struct.pack('>IIBBBBB', width, height, 8, 6, 0, 0, 0)  # 8-bit RGBA
    ihdr_crc = zlib.crc32(b'IHDR' + ihdr_data)
    ihdr = struct.pack('>I', 13) + b'IHDR' + ihdr_data + struct.pack('>I', ihdr_crc)

    # IDAT chunk: filter byte 0 per row, then RGBA pixels
    raw = b''
    for y in range(height):
        raw += b'\x00'  # filter: none
        for x in range(width):
            r, g, b, a = pixels[y * width + x]
            raw += struct.pack('BBBB', r, g, b, a)

    compressed = zlib.compress(raw)
    idat_crc = zlib.crc32(b'IDAT' + compressed)
    idat = struct.pack('>I', len(compressed)) + b'IDAT' + compressed + struct.pack('>I', idat_crc)

    # IEND chunk
    iend_crc = zlib.crc32(b'IEND')
    iend = struct.pack('>I', 0) + b'IEND' + struct.pack('>I', iend_crc)

    return sig + ihdr + idat + iend


def draw_shield_icon(size: int) -> list[tuple[int, int, int, int]]:
    """Draw a stylized shield/S icon on a dark background."""
    bg = (13, 13, 13, 255)       # --bg
    accent = (99, 102, 241, 255)  # --accent (indigo-500)
    accent_light = (129, 140, 248, 255)  # lighter accent

    pixels = [bg] * (size * size)

    margin = max(2, size // 8)
    inner = size - 2 * margin

    # Draw a rounded square with "S" letter
    for y in range(size):
        for x in range(size):
            # Center the shape
            cx = (x - size / 2) / (size / 2)
            cy = (y - size / 2) / (size / 2)

            # Shield shape: rounded rectangle with pointed bottom
            rx = abs(cx)
            ry_top = cy + 0.7  # top half
            ry_bottom = -(cy - 0.3)  # bottom half tapering

            # Simple rounded rect
            corner_radius = 0.3
            in_rect = abs(cx) < 0.75 and abs(cy) < 0.7

            # Rounded corners
            if in_rect:
                # Bottom point (shield shape)
                if cy > 0.5:
                    # Taper to a point at bottom
                    taper = (cy - 0.5) / 0.3
                    edge = 0.75 * (1.0 - taper)
                    if abs(cx) < edge:
                        pixels[y * size + x] = accent
                    elif abs(cx) < edge + 0.1:
                        # Anti-alias edge
                        alpha = max(0, min(255, int(255 * (1 - (abs(cx) - edge) / 0.1))))
                        pixels[y * size + x] = (accent[0], accent[1], accent[2], alpha)
                else:
                    # Top rounded corners
                    corner = False
                    if abs(cx) > 0.75 - corner_radius and cy < -0.7 + corner_radius:
                        dx = abs(cx) - (0.75 - corner_radius)
                        dy = -(cy + 0.7 - corner_radius)
                        if dx * dx + dy * dy > corner_radius * corner_radius:
                            corner = True
                    if not corner:
                        pixels[y * size + x] = accent

    # Draw a simplified "S" or dot pattern for small icons
    if size <= 16:
        # For 16x16: just a filled diamond/lozenge shape
        for y in range(size):
            for x in range(size):
                cx = abs(x - size / 2 + 0.5)
                cy = abs(y - size / 2 + 0.5)
                if cx + cy < size * 0.32:
                    pixels[y * size + x] = (255, 255, 255, 255)
        return pixels

    # For 48+ sizes: draw an "S" letter
    s_thickness = max(2, size // 12)
    s_left = size // 2 - size // 6
    s_right = size // 2 + size // 6
    s_top = margin + size // 5
    s_bottom = size - margin - size // 5
    s_mid = (s_top + s_bottom) // 2

    for y in range(s_top, s_bottom + 1):
        for x in range(s_left, s_right + 1):
            in_top_bar = y < s_top + s_thickness * 2
            in_bottom_bar = y > s_bottom - s_thickness * 2
            in_mid_bar = abs(y - s_mid) < s_thickness
            in_left = x < s_left + s_thickness * 2
            in_right = x > s_right - s_thickness * 2

            if in_top_bar:
                pixels[y * size + x] = (13, 13, 13, 255)  # cut-out
            elif in_mid_bar:
                pixels[y * size + x] = (13, 13, 13, 255)
            elif in_bottom_bar:
                pixels[y * size + x] = (13, 13, 13, 255)
            elif in_left and y < s_mid:
                pixels[y * size + x] = (13, 13, 13, 255)
            elif in_right and y > s_mid:
                pixels[y * size + x] = (13, 13, 13, 255)

    return pixels


def main():
    icons_dir = Path(__file__).parent / "extension" / "icons"
    icons_dir.mkdir(parents=True, exist_ok=True)

    for size in (16, 48, 128):
        pixels = draw_shield_icon(size)
        png_data = create_png(size, size, pixels)
        out_path = icons_dir / f"icon-{size}.png"
        out_path.write_bytes(png_data)
        print(f"Generated {out_path} ({len(png_data)} bytes)")


if __name__ == "__main__":
    main()
