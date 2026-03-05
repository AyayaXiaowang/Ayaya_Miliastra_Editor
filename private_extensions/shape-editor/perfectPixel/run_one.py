import argparse
from pathlib import Path

import numpy as np
from PIL import Image

from src.perfect_pixel import get_perfect_pixel


def _default_output_path(input_path: Path) -> Path:
    return input_path.with_name(f"{input_path.stem}.perfect{input_path.suffix}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="PerfectPixel：自动检测像素网格并输出对齐结果图"
    )
    parser.add_argument("input", help="输入图片路径（png/jpg 等）")
    parser.add_argument(
        "-o",
        "--output",
        default="",
        help="输出图片路径（默认：输入同目录，文件名追加 .perfect）",
    )
    parser.add_argument(
        "--sample-method",
        default="center",
        choices=["center", "median", "majority"],
        help="采样方法（默认：center）",
    )
    parser.add_argument(
        "--refine-intensity",
        type=float,
        default=0.30,
        help="网格线细化强度（默认：0.30，推荐范围 [0, 0.5]）",
    )
    parser.add_argument(
        "--fix-square",
        action="store_true",
        default=True,
        help="当检测到近似正方形时，强制输出正方形（默认开启）",
    )
    parser.add_argument(
        "--no-fix-square",
        action="store_false",
        dest="fix_square",
        help="关闭强制正方形输出",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="开启调试输出（可能弹出图窗/绘图依赖）",
    )
    args = parser.parse_args()

    input_path = Path(args.input).expanduser().resolve()
    if not input_path.is_file():
        raise FileNotFoundError(f"找不到输入图片：{input_path}")

    output_path = (
        Path(args.output).expanduser().resolve()
        if args.output
        else _default_output_path(input_path)
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)

    rgb = np.array(Image.open(input_path).convert("RGB"))

    refined_w, refined_h, out_rgb = get_perfect_pixel(
        rgb,
        sample_method=args.sample_method,
        refine_intensity=args.refine_intensity,
        fix_square=args.fix_square,
        debug=args.debug,
    )

    out_img = Image.fromarray(out_rgb.astype(np.uint8), mode="RGB")
    out_img.save(output_path)

    print("OK")
    print(f"- input : {input_path}")
    print(f"- output: {output_path}")
    print(f"- refined: {refined_w}x{refined_h}")


if __name__ == "__main__":
    main()

