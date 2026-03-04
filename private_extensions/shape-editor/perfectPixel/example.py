import cv2
import matplotlib.pyplot as plt
from src.perfect_pixel import get_perfect_pixel

path = "images/girl.jpg"
# path = "images/avatar.png"
# path = "images/robot.jpeg"
# path = "images/shanxi.jpg"
# path = "images/skull.png"
# path = "images/rika.png"
# path = "images/car.png"

bgr = cv2.imread(path, cv2.IMREAD_COLOR)

if bgr is None:
    raise FileNotFoundError(f"Cannot read image: {path}")
rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)

w, h, out = get_perfect_pixel(rgb, sample_method="center", refine_intensity=0.3, debug=True)

if w is None or h is None:
    print("Failed to generate pixel-perfect image.")
    exit(1)

# display
plt.figure(figsize=(10, 4))
plt.subplot(1, 2, 1)
plt.title("Input")
plt.imshow(rgb)
plt.axis("off")

plt.subplot(1, 2, 2)
plt.title(f"Pixel-perfect ({w}×{h})")
plt.imshow(out)
plt.axis("off")

plt.show()

# save output
out_bgr = cv2.cvtColor(out, cv2.COLOR_RGB2BGR)
cv2.imwrite("output.png", out_bgr)

# save 8x scaled output
out_8x = cv2.resize(out_bgr, (w * 8, h * 8), interpolation=cv2.INTER_NEAREST)
cv2.imwrite("output_8x.png", out_8x)