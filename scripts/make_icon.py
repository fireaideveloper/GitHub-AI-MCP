"""Original code-drawn application icon, reproducible with Python's standard library."""
import math
import struct
import zlib
from pathlib import Path


def png(size):
    rows = []
    def segment(x, y, ax, ay, bx, by, radius):
        dx, dy = bx-ax, by-ay
        t = max(0, min(1, ((x-ax)*dx+(y-ay)*dy)/(dx*dx+dy*dy)))
        return math.hypot(x-ax-t*dx, y-ay-t*dy) <= radius
    for iy in range(size):
        row = bytearray(b"\0")
        for ix in range(size):
            x, y = (ix+.5)*256/size, (iy+.5)*256/size
            dx, dy = max(52-x, 0, x-204), max(52-y, 0, y-204)
            inside = dx*dx+dy*dy <= 44*44 and 8 <= x <= 248 and 8 <= y <= 248
            color = (22, 52, 80, 255) if inside else (0, 0, 0, 0)
            if inside:
                if segment(x,y,68,64,68,192,7) or segment(x,y,68,108,148,92,7) or segment(x,y,148,92,164,60,7):
                    color = (112,191,255,255)
                if any(math.hypot(x-a,y-b)<=17 for a,b in [(68,64),(68,192),(164,60)]):
                    color = (255,255,255,255)
                d = math.hypot(x-162,y-162)
                if d <= 42:
                    color = (255,255,255,255) if d >= 30 else (22,52,80,255)
                if segment(x,y,189,189,218,218,8):
                    color = (112,191,255,255)
            row.extend(color)
        rows.append(bytes(row))
    def chunk(kind, data):
        return struct.pack(">I",len(data))+kind+data+struct.pack(">I",zlib.crc32(kind+data)&0xffffffff)
    return b"\x89PNG\r\n\x1a\n"+chunk(b"IHDR",struct.pack(">IIBBBBB",size,size,8,6,0,0,0))+chunk(b"IDAT",zlib.compress(b"".join(rows),9))+chunk(b"IEND",b"")


def generate(destination: Path):
    destination.mkdir(parents=True, exist_ok=True)
    sizes = [16,32,48,64,128,256]
    images = [png(n) for n in sizes]
    offset = 6+16*len(sizes)
    headers = []
    for size, data in zip(sizes, images):
        headers.append(struct.pack("<BBBBHHII",size%256,size%256,0,0,1,32,len(data),offset))
        offset += len(data)
    (destination/"github-ai-mcp.ico").write_bytes(struct.pack("<HHH",0,1,len(sizes))+b"".join(headers)+b"".join(images))
    (destination/"github-ai-mcp.png").write_bytes(images[-1])


if __name__ == "__main__":
    generate(Path(__file__).resolve().parents[1]/"assets")
