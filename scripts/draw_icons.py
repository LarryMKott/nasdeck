# -*- coding: utf-8 -*-
"""NasDeck 应用图标生成管线（方案 A：深色金属面板 + 黄色描边环 + 硬盘托架 + 状态条）。

python scripts/draw_icons.py 一键落位仓库图标：
  ICON_256.PNG                                商店图标源（256x256；build_fpk.py 由此派生 64px
                                              与 app/ui/images/icon-{64,256}.png）
  frontend/public/favicon.svg                 浏览器标签图标（32 viewBox，4 盘简化形）
  frontend/src/assets/images/logo.svg         侧边栏 logo（与 favicon 同形）
  docs/assets/icons/icon-4k.png               5 盘全细节 4K 母版（4096x4096，宣传/文档用，不进包）
  docs/assets/icons/logo-4k.png               4 盘简化形 4K 母版（与 SVG 同源几何）
  build/icon-preview/*                        三套配色全尺寸预览与尺寸阶梯（gitignore，仅供评审）

配色备选：yellow（正式）/ teal / light —— 预览目录内生成三套便于对比，仓库正式文件取 yellow。
"""
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
PREVIEW = ROOT / "build" / "icon-preview"
DOCS_ICONS = ROOT / "docs" / "assets" / "icons"
OUT_4K = 4096

Y = (255, 211, 41)  # 品牌黄

# 全参数调色板：黄（正式）/ 青 / 浅色银白（5 盘全细节设计用）
PALETTES = {
    "yellow": dict(
        tile_top=(45, 47, 52), tile_bottom=(19, 20, 23),
        edge_hi=(255, 255, 255, 16), edge_lo=(0, 0, 0, 150),
        ring=Y,
        cage=(11, 12, 14), cage_edge=(255, 255, 255, 14),
        tick=(205, 210, 220, 42),
        tab=(58, 62, 68),
        tray_top=(65, 69, 76), tray_bottom=(38, 41, 46), tray_edge=(255, 255, 255, 20),
        vent=(16, 17, 20),
        seg=(42, 45, 51), seg_edge=(0, 0, 0, 90),
        glow=70,
        led=(255, 214, 60),
        bar_top=(255, 218, 70), bar_bottom=(245, 196, 16), bar_edge=(255, 255, 255, 36),
    ),
    "teal": dict(
        tile_top=(45, 47, 52), tile_bottom=(19, 20, 23),
        edge_hi=(255, 255, 255, 16), edge_lo=(0, 0, 0, 150),
        ring=Y,  # 参考稿中描边恒为黄
        cage=(11, 12, 14), cage_edge=(255, 255, 255, 14),
        tick=(205, 210, 220, 42),
        tab=(58, 62, 68),
        tray_top=(65, 69, 76), tray_bottom=(38, 41, 46), tray_edge=(255, 255, 255, 20),
        vent=(16, 17, 20),
        seg=(42, 45, 51), seg_edge=(0, 0, 0, 90),
        glow=70,
        led=(62, 233, 208),
        bar_top=(96, 241, 218), bar_bottom=(28, 203, 178), bar_edge=(255, 255, 255, 36),
    ),
    "light": dict(
        tile_top=(250, 251, 253), tile_bottom=(211, 215, 222),
        edge_hi=(255, 255, 255, 220), edge_lo=(140, 146, 156, 170),
        ring=(246, 196, 10),  # 深一档的琥珀黄，保证浅底对比
        cage=(224, 227, 233), cage_edge=(255, 255, 255, 200),
        tick=(96, 103, 115, 70),
        tab=(182, 187, 196),
        tray_top=(253, 254, 255), tray_bottom=(206, 210, 218), tray_edge=(160, 166, 176, 110),
        vent=(172, 177, 186),
        seg=(196, 201, 210), seg_edge=(255, 255, 255, 160),
        glow=46,
        led=(243, 185, 5),
        bar_top=(255, 208, 40), bar_bottom=(241, 178, 2), bar_edge=(255, 255, 255, 120),
    ),
}

# 小图标（4 盘简化形）调色板：SVG 与 4K PNG 共用同一份色值
SVG_PALETTES = {
    "yellow": dict(tile_top="#2d2f34", tile_bottom="#131417", ring="#ffd329", bay="#484c53",
                   led="#ffd63c", recess="#0c0d0f", seg="#3b3e44",
                   bar_top="#ffda46", bar_bottom="#f5c410"),
    "teal": dict(tile_top="#2d2f34", tile_bottom="#131417", ring="#ffd329", bay="#484c53",
                 led="#3ee9d0", recess="#0c0d0f", seg="#3b3e44",
                 bar_top="#60f1da", bar_bottom="#1ccbb2"),
    "light": dict(tile_top="#fafbfd", tile_bottom="#d3d7de", ring="#f2c40a", bay="#ccd1d9",
                  led="#f3b905", recess="#dee1e7", seg="#c4c9d2",
                  bar_top="#ffd028", bar_bottom="#f1b202"),
}


def rgb(hexs):
    return tuple(int(hexs[i:i + 2], 16) for i in (1, 3, 5))


def make_ctx(s):
    """返回 (画布尺寸 s 下的坐标换算与渐变/圆角工具)。"""

    def u256(v):
        return int(round(v * s / 256))

    def u32(v):
        return int(round(v * s / 32))

    def vgrad(top, bottom):
        img = Image.new("RGB", (1, s))
        for y in range(s):
            t = y / (s - 1)
            img.putpixel((0, y), tuple(int(a + (b - a) * t) for a, b in zip(top, bottom)))
        img = img.resize((s, s))
        # 噪声抖动消除大面积渐变的 8bit 色带
        noise = Image.effect_noise((s, s), 1.1).convert("RGB")
        return ImageChops.add(img, noise, scale=1, offset=-128)

    def rrect_grad(canvas, box, r, top, bottom):
        mask = Image.new("L", (s, s), 0)
        ImageDraw.Draw(mask).rounded_rectangle(box, radius=r, fill=255)
        canvas.paste(vgrad(top, bottom), (0, 0), mask)

    return u256, u32, vgrad, rrect_grad


def draw_full(p, s):
    """5 盘全细节设计（256 单位几何），渲染在 s x s 画布上。"""
    u, _, vgrad, rrect_grad = make_ctx(s)
    canvas = Image.new("RGBA", (s, s), (0, 0, 0, 0))

    # 底板投影（很淡，适配浅色商店背景）
    shadow = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle(
        (u(6), u(10), u(250), u(252)), radius=u(54), fill=(10, 12, 16, 90)
    )
    canvas.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(u(2.6))))

    # 主体圆角方块：金属渐变
    rrect_grad(canvas, (u(4), u(4), u(252), u(252)), u(54), p["tile_top"], p["tile_bottom"])
    draw = ImageDraw.Draw(canvas, "RGBA")
    draw.rounded_rectangle((u(5), u(5), u(251), u(251)), radius=u(53), outline=p["edge_hi"], width=max(1, u(1)))
    draw.rounded_rectangle((u(4), u(4), u(252), u(252)), radius=u(54), outline=p["edge_lo"], width=max(1, u(1)))

    # 品牌描边环
    draw.rounded_rectangle(
        (u(14), u(14), u(242), u(242)), radius=u(46), outline=p["ring"] + (255,), width=max(1, u(3.4))
    )

    # ---- 上：硬盘笼（内凹面板）----
    draw.rounded_rectangle((u(37), u(42), u(219), u(150)), radius=u(12), fill=p["cage"] + (255,))
    draw.rounded_rectangle(
        (u(38.5), u(43.5), u(217.5), u(148.5)), radius=u(10.5), outline=p["cage_edge"], width=max(1, u(1))
    )
    # 笼内两侧导轨刻点
    for ty in (58, 74, 90, 106, 122):
        for tx in (41.2, 214.4):
            draw.rounded_rectangle(
                (u(tx), u(ty), u(tx + 2.6), u(ty + 1.8)), radius=u(0.8), fill=p["tick"]
            )

    # ---- 5 个硬盘托架 ----
    tray_w, gap, x0 = 26.4, 7.8, 47.0
    ty0, ty1 = 50.0, 142.0
    for i in range(5):
        tx = x0 + i * (tray_w + gap)
        # 顶部拉手小凸块
        draw.rounded_rectangle(
            (u(tx + (tray_w - 11) / 2), u(45.6), u(tx + (tray_w + 11) / 2), u(51.2)),
            radius=u(2), fill=p["tab"] + (255,),
        )
        # 托架本体
        rrect_grad(canvas, (u(tx), u(ty0), u(tx + tray_w), u(ty1)), u(6.5), p["tray_top"], p["tray_bottom"])
        td = ImageDraw.Draw(canvas, "RGBA")
        td.rounded_rectangle(
            (u(tx + 1), u(ty0 + 1), u(tx + tray_w - 1), u(ty1 - 1)),
            radius=u(5.5), outline=p["tray_edge"], width=max(1, u(1)),
        )
        cx = tx + tray_w / 2
        if i == 0:
            pass  # 首盘无指示灯（对应参考稿）
        elif i == 4:
            # 末盘：指示灯 + 中部散热栅缝
            draw.rounded_rectangle(
                (u(cx - 4.5), u(56.5), u(cx + 4.5), u(60)), radius=u(1.6), fill=p["led"] + (255,)
            )
            for vy in (98, 106, 114):
                draw.rounded_rectangle(
                    (u(cx - 6.5), u(vy), u(cx + 6.5), u(vy + 2.4)), radius=u(1.1), fill=p["vent"] + (255,)
                )
        else:
            draw.rounded_rectangle(
                (u(cx - 4.5), u(56.5), u(cx + 4.5), u(60)), radius=u(1.6), fill=p["led"] + (255,)
            )
        # 活动指示圆点（第 3 盘）
        if i == 2:
            dot_y = 124
            glow = Image.new("RGBA", (s, s), (0, 0, 0, 0))
            ImageDraw.Draw(glow).ellipse(
                (u(cx - 8), u(dot_y - 8), u(cx + 8), u(dot_y + 8)), fill=p["led"] + (p["glow"],)
            )
            canvas.alpha_composite(glow.filter(ImageFilter.GaussianBlur(u(2.2))))
            draw = ImageDraw.Draw(canvas, "RGBA")
            draw.ellipse(
                (u(cx - 4.2), u(dot_y - 4.2), u(cx + 4.2), u(dot_y + 4.2)), fill=p["led"] + (255,)
            )

    # ---- 下：状态条托盘 ----
    draw.rounded_rectangle((u(37), u(164), u(219), u(210)), radius=u(11), fill=p["cage"] + (255,))
    draw.rounded_rectangle(
        (u(38.5), u(165.5), u(217.5), u(208.5)), radius=u(9.5), outline=p["cage_edge"], width=max(1, u(1))
    )
    by0, by1 = 174.0, 200.0
    # 已用段（品牌色）
    rrect_grad(canvas, (u(46), u(by0), u(110), u(by1)), u(5), p["bar_top"], p["bar_bottom"])
    draw.rounded_rectangle(
        (u(47.5), u(by0 + 1.5), u(108.5), u(by1 - 1.5)), radius=u(4), outline=p["bar_edge"], width=max(1, u(1))
    )
    # 余量暗段
    for bx0, bx1 in ((115, 160), (165, 210)):
        draw.rounded_rectangle((u(bx0), u(by0), u(bx1), u(by1)), radius=u(5), fill=p["seg"] + (255,))
        draw.rounded_rectangle(
            (u(bx0 + 1), u(by0 + 1), u(bx1 - 1), u(by1 - 1)), radius=u(4), outline=p["seg_edge"], width=max(1, u(1))
        )

    return canvas


def draw_small(sp, s):
    """4 盘简化形（32 单位几何，与 SVG 模板同源），渲染在 s x s 画布上。"""
    _, u, vgrad, rrect_grad = make_ctx(s)
    c = {k: rgb(v) for k, v in sp.items()}
    canvas = Image.new("RGBA", (s, s), (0, 0, 0, 0))

    # 底板投影
    shadow = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle(
        (u(0.6), u(0.9), u(31.5), u(31.8)), radius=u(7.4), fill=(10, 12, 16, 80)
    )
    canvas.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(u(0.5))))

    # 圆角方块 + 描边环
    rrect_grad(canvas, (0, 0, u(32) - 1, u(32) - 1), u(7.2), c["tile_top"], c["tile_bottom"])
    draw = ImageDraw.Draw(canvas, "RGBA")
    draw.rounded_rectangle(
        (u(1.9), u(1.9), u(30.1) - 1, u(30.1) - 1), radius=u(5.6),
        outline=c["ring"] + (255,), width=max(1, u(1.8)),
    )

    # 4 个托架
    for bx, bw in ((5.4, 3.8), (11.4, 3.8), (17.4, 3.8), (23.4, 3.2)):
        draw.rounded_rectangle(
            (u(bx), u(7.2), u(bx + bw) - 1, u(20.4) - 1), radius=u(1.7), fill=c["bay"] + (255,)
        )
    # 指示灯（短划 x3 + 活动圆点）
    for lx in (12.2, 18.2, 23.9):
        draw.rounded_rectangle(
            (u(lx), u(9), u(lx + 2.2) - 1, u(10) - 1), radius=u(0.5), fill=c["led"] + (255,)
        )
    dot_cx, dot_cy, dot_r = 13.3, 17.4, 1.15
    glow = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse(
        (u(dot_cx - 2.2), u(dot_cy - 2.2), u(dot_cx + 2.2) - 1, u(dot_cy + 2.2) - 1),
        fill=c["led"] + (90,),
    )
    canvas.alpha_composite(glow.filter(ImageFilter.GaussianBlur(u(0.9))))
    draw = ImageDraw.Draw(canvas, "RGBA")
    draw.ellipse(
        (u(dot_cx - dot_r), u(dot_cy - dot_r), u(dot_cx + dot_r) - 1, u(dot_cy + dot_r) - 1),
        fill=c["led"] + (255,),
    )

    # 状态条
    draw.rounded_rectangle(
        (u(4.8), u(22.4), u(27.2) - 1, u(26.4) - 1), radius=u(1.6), fill=c["recess"] + (255,)
    )
    rrect_grad(canvas, (u(6), u(23.4), u(13) - 1, u(25.4) - 1), u(1), c["bar_top"], c["bar_bottom"])
    draw = ImageDraw.Draw(canvas, "RGBA")
    for bx in (14.3, 20.8):
        draw.rounded_rectangle(
            (u(bx), u(23.4), u(bx + 5.2) - 1, u(25.4) - 1), radius=u(1), fill=c["seg"] + (255,)
        )
    return canvas


SVG_TEMPLATE = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">
  <defs>
    <linearGradient id="t" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="{tile_top}"/><stop offset="1" stop-color="{tile_bottom}"/>
    </linearGradient>
    <linearGradient id="a" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="{bar_top}"/><stop offset="1" stop-color="{bar_bottom}"/>
    </linearGradient>
  </defs>
  <rect width="32" height="32" rx="7.2" fill="url(#t)"/>
  <rect x="1.9" y="1.9" width="28.2" height="28.2" rx="5.6" fill="none" stroke="{ring}" stroke-width="1.8"/>
  <g fill="{bay}">
    <rect x="5.4" y="7.2" width="3.8" height="13.2" rx="1.7"/>
    <rect x="11.4" y="7.2" width="3.8" height="13.2" rx="1.7"/>
    <rect x="17.4" y="7.2" width="3.8" height="13.2" rx="1.7"/>
    <rect x="23.4" y="7.2" width="3.2" height="13.2" rx="1.7"/>
  </g>
  <g fill="{led}">
    <rect x="12.2" y="9" width="2.2" height="1" rx="0.5"/>
    <rect x="18.2" y="9" width="2.2" height="1" rx="0.5"/>
    <rect x="23.9" y="9" width="2.2" height="1" rx="0.5"/>
    <circle cx="13.3" cy="17.4" r="1.15"/>
  </g>
  <rect x="4.8" y="22.4" width="22.4" height="4" rx="1.6" fill="{recess}"/>
  <rect x="6" y="23.4" width="7" height="2" rx="1" fill="url(#a)"/>
  <rect x="14.3" y="23.4" width="5.2" height="2" rx="1" fill="{seg}"/>
  <rect x="20.8" y="23.4" width="5.2" height="2" rx="1" fill="{seg}"/>
</svg>
"""


def main():
    PREVIEW.mkdir(parents=True, exist_ok=True)

    for tag, p in PALETTES.items():
        # 商店图标：2048 超采样 → 256 + 尺寸阶梯（预览）
        icon = draw_full(p, 256 * 8)
        base = icon.resize((256, 256), Image.LANCZOS)
        base.save(PREVIEW / f"icon-256-{tag}.png", optimize=True)
        for size in (128, 64, 48, 32, 16):
            base.resize((size, size), Image.LANCZOS).save(PREVIEW / f"icon-{size}-{tag}.png", optimize=True)
        # 4K 母版（8192 超采样 → 4096）
        draw_full(p, OUT_4K * 2).resize((OUT_4K, OUT_4K), Image.LANCZOS).save(
            PREVIEW / f"icon-4k-{tag}.png", optimize=True
        )
        # 小图标 4K（与 SVG 同源几何）
        draw_small(SVG_PALETTES[tag], OUT_4K * 2).resize((OUT_4K, OUT_4K), Image.LANCZOS).save(
            PREVIEW / f"logo-4k-{tag}.png", optimize=True
        )
        # 小图标 SVG（预览副本）
        body = SVG_TEMPLATE.format(**SVG_PALETTES[tag])
        (PREVIEW / f"logo-{tag}.svg").write_text(body, encoding="utf-8")
        (PREVIEW / f"favicon-{tag}.svg").write_text(body, encoding="utf-8")
        print(f"preview: {tag}")

    # ---- 正式落位（方案 A yellow）----
    (ROOT / "ICON_256.PNG").write_bytes((PREVIEW / "icon-256-yellow.png").read_bytes())
    svg = (PREVIEW / "logo-yellow.svg").read_text(encoding="utf-8")
    (ROOT / "frontend" / "public" / "favicon.svg").write_text(svg, encoding="utf-8")
    (ROOT / "frontend" / "src" / "assets" / "images" / "logo.svg").write_text(svg, encoding="utf-8")

    DOCS_ICONS.mkdir(parents=True, exist_ok=True)
    (DOCS_ICONS / "icon-4k.png").write_bytes((PREVIEW / "icon-4k-yellow.png").read_bytes())
    (DOCS_ICONS / "logo-4k.png").write_bytes((PREVIEW / "logo-4k-yellow.png").read_bytes())
    print("已落位：ICON_256.PNG / favicon.svg / logo.svg / docs/assets/icons/*4k.png")


if __name__ == "__main__":
    main()
