"""
生成 macOS 应用专属高清图标 AppIcon.icns
"""
import os
import subprocess
from PIL import Image, ImageDraw


def draw_master_icon(size=1024) -> Image.Image:
    # 创建带有透明通道的高清画布
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # 绘制带圆角的渐变/纯色现代卡片背景 (macOS Big Sur+ 风格圆角矩形)
    margin = size * 0.1
    card_rect = [margin, margin, size - margin, size - margin]
    radius = size * 0.22

    # macOS 深邃蓝紫渐变底色
    draw.rounded_rectangle(card_rect, radius=radius, fill="#0A84FF")

    # 绘制内部微光晕装饰
    inner_margin = size * 0.13
    inner_rect = [inner_margin, inner_margin, size - inner_margin, size - inner_margin]
    inner_radius = size * 0.18
    draw.rounded_rectangle(inner_rect, radius=inner_radius, outline="#64D2FF", width=int(size * 0.015))

    # 绘制中心鼠标图形 (极简拟物与现代矢量风格)
    cx, cy = size / 2, size / 2
    mw = size * 0.32
    mh = size * 0.48
    mx0 = cx - mw / 2
    my0 = cy - mh / 2
    mx1 = cx + mw / 2
    my1 = cy + mh / 2
    m_radius = mw / 2

    # 鼠标主体 (白色磨砂质感)
    draw.rounded_rectangle([mx0, my0, mx1, my1], radius=m_radius, fill="#FFFFFF")

    # 鼠标按键分割线 (浅灰)
    line_y = my0 + mh * 0.38
    draw.line([mx0, line_y, mx1, line_y], fill="#D1D1D6", width=int(size * 0.01))
    draw.line([cx, my0 + size * 0.02, cx, line_y], fill="#D1D1D6", width=int(size * 0.01))

    # 鼠标滚轮 (高亮橙/蓝色)
    ww = size * 0.04
    wh = size * 0.1
    wx0 = cx - ww / 2
    wy0 = my0 + size * 0.08
    wx1 = cx + ww / 2
    wy1 = wy0 + wh
    draw.rounded_rectangle([wx0, wy0, wx1, wy1], radius=ww / 2, fill="#FF9500")

    # 绘制轨迹光点与光环 (表达运动与循环回放)
    orbit_r = size * 0.03
    draw.ellipse([cx + size * 0.16, cy + size * 0.12, cx + size * 0.16 + orbit_r * 2, cy + size * 0.12 + orbit_r * 2], fill="#30D158")
    draw.ellipse([cx - size * 0.22, cy - size * 0.05, cx - size * 0.22 + orbit_r * 1.5, cy - size * 0.05 + orbit_r * 1.5], fill="#FFD60A")

    return img


def generate_icns():
    master = draw_master_icon(1024)
    iconset_dir = "AppIcon.iconset"
    os.makedirs(iconset_dir, exist_ok=True)

    sizes = [
        ("icon_16x16.png", 16),
        ("icon_16x16@2x.png", 32),
        ("icon_32x32.png", 32),
        ("icon_32x32@2x.png", 64),
        ("icon_128x128.png", 128),
        ("icon_128x128@2x.png", 256),
        ("icon_256x256.png", 256),
        ("icon_256x256@2x.png", 512),
        ("icon_512x512.png", 512),
        ("icon_512x512@2x.png", 1024),
    ]

    for fname, sz in sizes:
        resized = master.resize((sz, sz), Image.Resampling.LANCZOS)
        resized.save(os.path.join(iconset_dir, fname))

    # 调用 macOS 原生 iconutil 转换为 .icns
    subprocess.run(["iconutil", "-c", "icns", iconset_dir, "-o", "AppIcon.icns"], check=True)
    print("AppIcon.icns 生成成功！")


if __name__ == "__main__":
    generate_icns()
