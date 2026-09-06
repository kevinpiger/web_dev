"""Normalized ROI coordinate validation, per freeze §8 / §27.

0 <= x < 1
0 <= y < 1
0 < width <= 1
0 < height <= 1
x + width <= 1
y + height <= 1
"""


def is_valid_roi(x: float, y: float, width: float, height: float) -> bool:
    return (
        0 <= x < 1
        and 0 <= y < 1
        and 0 < width <= 1
        and 0 < height <= 1
        and x + width <= 1
        and y + height <= 1
    )


def full_image_roi() -> dict[str, float]:
    return {"x": 0.0, "y": 0.0, "width": 1.0, "height": 1.0}
