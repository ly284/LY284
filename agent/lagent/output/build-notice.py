# -*- coding: utf-8 -*-
"""生成 PPT 内容 batch JSON（供 officecli batch --input 使用）"""
import json

FONT = "微软雅黑"
ACCENT = "00C2A8"
CARD = "1B344A"
WHITE = "FFFFFF"
MUTED = "9FB3C8"
DIM = "6B7C8F"

cmds = []


def shape(slide, text, x, y, w, h, size, color=WHITE, bold=False,
          fill=None, align="left", valign="top", geometry="rect", spacing=None):
    props = {
        "text": text,
        "geometry": geometry,
        "x": f"{x}cm", "y": f"{y}cm",
        "width": f"{w}cm", "height": f"{h}cm",
        "font.ea": FONT, "font.latin": FONT,
        "size": f"{size}pt", "color": color, "bold": str(bold).lower(),
        "align": align, "valign": valign,
        "fill": fill if fill else "none",
        "line": "none",
    }
    if spacing:
        props["lineSpacing"] = f"{spacing}%"
    cmds.append({"command": "add", "parent": f"/slide[{slide}]",
                 "type": "shape", "props": props})


def card(slide, x, y, w, h, title, body):
    """一张带左侧强调条的卡片"""
    shape(slide, "", x, y, w, h, 12, fill=CARD, geometry="roundRect")
    shape(slide, "", x, y + 0.6, 0.14, h - 1.2, 12, fill=ACCENT)
    shape(slide, title, x + 0.75, y + 0.85, w - 1.2, 1.2, 18, color=WHITE, bold=True)
    shape(slide, body, x + 0.75, y + 2.3, w - 1.2, h - 3.2, 13, color=MUTED, spacing=135)


# ============ Slide 1 封面 ============
shape(1, "明天不放假", 3.2, 6.0, 24, 2.4, 44, color=WHITE, bold=True)
shape(1, "11月3日（周二）正常上班 · 排班照常执行", 3.2, 8.9, 26, 1.4, 20, color=MUTED)
shape(1, "", 3.2, 11.0, 6, 0.06, 10, fill=ACCENT)
shape(1, "发布：物流部 小王        日期：2026年11月2日", 3.2, 12.2, 26, 1.0, 12, color=DIM)

# ============ Slide 2 为什么 ============
shape(2, "", 2.2, 2.2, 0.2, 4.2, 12, fill=ACCENT)
shape(2, "为什么明天不放假", 3.0, 2.0, 28, 1.6, 30, color=WHITE, bold=True)
shape(2, "一句话：订单不等人，客户的承诺时间不会因为假期往后挪。", 3.0, 4.0, 28, 1.2, 14, color=MUTED)

cw, gap = 9.42, 0.6
card(2, 2.2, 7.0, cw, 8.0, "订单峰值", "双十一预售订单持续涌入库房，明天的发运量预计是平时的 1.8 倍。")
card(2, 2.2 + cw + gap, 7.0, cw, 8.0, "排班已锁定", "干线车次、外包装卸、第三方仓的交接时间都已确认，临时调整会连带影响下游。")
card(2, 2.2 + 2 * (cw + gap), 7.0, cw, 8.0, "承诺时效", "客户下单时锁定的是 48 小时送达，明天停摆一天，后天就要加倍追赶。")

# ============ Slide 3 作息安排 ============
shape(3, "", 2.2, 2.2, 0.2, 4.2, 12, fill=ACCENT)
shape(3, "明天的作息与安排", 3.0, 2.0, 28, 1.6, 30, color=WHITE, bold=True)
shape(3, "11月3日 · 仓库与干线作业时间表", 3.0, 4.0, 28, 1.2, 14, color=MUTED)

rows = [
    ("07:30", "早班集合点名", "库前广场，各班组长带队，不得代签。"),
    ("08:00 — 12:00", "拣货 · 打包", "A 区优先，预售单先行；缺货位即时上报调度。"),
    ("12:00 — 13:00", "午餐轮换", "分两批用餐，确保打包线不断线。"),
    ("13:30 — 18:00", "装车发运", "对接干线司机，装卸组提前 15 分钟到位。"),
    ("18:30", "当日复盘", "10 分钟站会，通报发运缺口与次日重点。"),
]
y = 6.2
for time_s, title_s, desc in rows:
    shape(3, time_s, 2.2, y, 6.0, 1.2, 15, color=ACCENT, bold=True)
    shape(3, title_s, 8.4, y, 6.0, 1.2, 15, color=WHITE, bold=True)
    shape(3, desc, 14.6, y, 17.0, 1.2, 13, color=MUTED)
    y += 1.85

# ============ Slide 4 提醒 & 联系人 ============
shape(4, "", 2.2, 2.2, 0.2, 4.2, 12, fill=ACCENT)
shape(4, "请注意这三件事", 3.0, 2.0, 28, 1.6, 30, color=WHITE, bold=True)
shape(4, "避免明天出现不必要的麻烦", 3.0, 4.0, 28, 1.2, 14, color=MUTED)

cw4 = 9.42
card(4, 2.2, 6.6, cw4, 6.6, "考勤不变", "正常刷卡上下班，迟到与旷工按日常考勤规则处理。")
card(4, 2.2 + cw4 + gap, 6.6, cw4, 6.6, "加班与补贴", "当日加班照计，餐补与夜班补贴按公司标准发放，不用单独申请。")
card(4, 2.2 + 2 * (cw4 + gap), 6.6, cw4, 6.6, "请假流程", "确有特殊情况，提前报班组长并在 OA 提交请假单，不接口头请假。")

shape(4, "有疑问随时找我：物流部 小王 · 分机 8021 · 微信同号", 2.2, 14.0, 30, 1.2, 13, color=DIM)
shape(4, "谢谢配合，明天见。", 2.2, 15.3, 30, 1.2, 15, color=ACCENT, bold=True)

print(json.dumps(cmds, ensure_ascii=False, indent=1))
