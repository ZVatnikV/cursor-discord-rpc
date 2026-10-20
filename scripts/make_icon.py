"""Generate a simple teal app icon (.ico + png)."""

from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"
ASSETS.mkdir(exist_ok=True)


def make(size: int) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    m = size // 16
    d.rounded_rectangle(
        (m, m, size - m, size - m),
        radius=size // 4,
        fill=(61, 214, 198, 255),
    )
    # window
    pad = size // 4
    d.rounded_rectangle(
        (pad, pad - m, size - pad, size - pad - m),
        radius=size // 12,
        outline=(7, 16, 24, 255),
        width=max(2, size // 18),
    )
    # dock line
    y = size - pad
    d.line((pad + m * 2, y, size - pad - m * 2, y), fill=(7, 16, 24, 255), width=max(2, size // 20))
    return img


def main() -> None:
    sizes = [16, 32, 48, 64, 128, 256]
    images = [make(s) for s in sizes]
    ico_path = ASSETS / "icon.ico"
    images[-1].save(ico_path, format="ICO", sizes=[(s, s) for s in sizes])
    make(512).save(ASSETS / "icon.png")
    print(f"Wrote {ico_path}")


if __name__ == "__main__":
    main()
