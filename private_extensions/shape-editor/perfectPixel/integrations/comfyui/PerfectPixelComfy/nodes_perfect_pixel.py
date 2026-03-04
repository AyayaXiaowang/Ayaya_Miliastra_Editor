import numpy as np
import torch
import torch.nn.functional as F

# ---- helpers ----

def _torch_image_to_uint8_rgb(img: torch.Tensor) -> np.ndarray:
    """
    ComfyUI IMAGE: float32, [B,H,W,C], range 0..1, C=3
    -> numpy uint8 RGB [H,W,3]
    """
    img = img.detach().cpu()
    img = torch.clamp(img, 0.0, 1.0)
    img = (img * 255.0).round().to(torch.uint8)
    return img.numpy()

def _uint8_rgb_to_torch_image(rgb: np.ndarray) -> torch.Tensor:
    """
    numpy uint8 RGB [H,W,3] -> torch float32 [1,H,W,3] 0..1
    """
    if rgb.dtype != np.uint8:
        rgb = np.clip(np.rint(rgb), 0, 255).astype(np.uint8)
    t = torch.from_numpy(rgb).float() / 255.0
    return t.unsqueeze(0)  # [1,H,W,3]

def _nearest_scale_bhwc(img_bhwc: torch.Tensor, scale: int) -> torch.Tensor:
    """
    img_bhwc: [B,H,W,C] -> scaled [B,H*scale,W*scale,C] using nearest
    """
    if scale == 1:
        return img_bhwc
    b, h, w, c = img_bhwc.shape
    x = img_bhwc.permute(0, 3, 1, 2)  # [B,C,H,W]
    x = F.interpolate(x, scale_factor=scale, mode="nearest")
    return x.permute(0, 2, 3, 1)  # [B,H,W,C]

def _load_backend(backend: str):
    """
    backend:
      - "Auto"
      - "OpenCV Backend"
      - "Lightweight Backend"
    returns: get_perfect_pixel callable
    """
    if backend == "Lightweight Backend":
        from perfect_pixel_noCV2 import get_perfect_pixel
        return get_perfect_pixel

    if backend == "OpenCV Backend":
        # hard-require cv2
        import cv2  # noqa: F401
        from perfect_pixel import get_perfect_pixel
        return get_perfect_pixel

    # Auto: prefer OpenCV if available, else fallback
    try:
        import cv2  # noqa: F401
        from perfect_pixel import get_perfect_pixel
        return get_perfect_pixel
    except Exception:
        from perfect_pixel_noCV2 import get_perfect_pixel
        return get_perfect_pixel


class PerfectPixelNode:
    """
    IMAGE -> IMAGE
    PerfectPixel grid detection + sampling (center/majority) + nearest zoom/export scale.
    """

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "sampling": (["Majority Cluster", "Center Sample"], {"default": "Majority Cluster"}),
                "export_scale": ("INT", {"default": 4, "min": 1, "max": 16, "step": 1}),
                "backend": (["Auto", "OpenCV Backend", "Lightweight Backend"], {"default": "Auto"}),
            },
        }

    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("image",)
    FUNCTION = "run"
    CATEGORY = "image/postprocessing"

    def run(self, image, sampling, export_scale, backend):
        get_perfect_pixel = _load_backend(backend)

        # ComfyUI may pass batches: [B,H,W,C]
        imgs = _torch_image_to_uint8_rgb(image)  # -> numpy [B,H,W,C] uint8
        if imgs.ndim != 4 or imgs.shape[-1] != 3:
            raise ValueError(f"Expected IMAGE as [B,H,W,3], got {imgs.shape}")

        method = "majority" if sampling == "Majority Cluster" else "center"

        outs = []
        out_shapes = []
        for i in range(imgs.shape[0]):
            rgb = imgs[i]  # [H,W,3] uint8

            # perfect_pixel expects RGB
            w, h, out_rgb = get_perfect_pixel(
                rgb,
                sample_method=method,
                debug=False
            )
            # fallback behavior in your code: if failed, it returns original image
            # so out_rgb is always valid.

            out_t = _uint8_rgb_to_torch_image(out_rgb)  # [1,h,w,3]
            outs.append(out_t)
            out_shapes.append(out_t.shape)

        # stack: require same H/W across batch (common case)
        Hs = {t.shape[1] for t in outs}
        Ws = {t.shape[2] for t in outs}
        if len(Hs) != 1 or len(Ws) != 1:
            raise ValueError(
                "PerfectPixel produced different sizes across the batch. "
                "Please process images one-by-one or ensure same input sizing."
            )

        out = torch.cat(outs, dim=0)  # [B,H,W,3]
        out = _nearest_scale_bhwc(out, int(export_scale))
        out = torch.clamp(out, 0.0, 1.0)
        return (out,)
