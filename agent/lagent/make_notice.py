# -*- coding: utf-8 -*-
from docx import Document
from docx.shared import Pt, Cm, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn

doc = Document()

# 页面设置
sec = doc.sections[0]
sec.top_margin = Cm(2.54)
sec.bottom_margin = Cm(2.54)
sec.left_margin = Cm(3.0)
sec.right_margin = Cm(3.0)

# 正文默认字体
style = doc.styles['Normal']
style.font.name = 'Times New Roman'
style.font.size = Pt(12)
style.element.rPr.rFonts.set(qn('w:eastAsia'), '宋体')


def add_para(text, size=12, bold=False, font='宋体', align=None,
             first_indent=0, space_before=0, space_after=0, line_spacing=1.5):
    p = doc.add_paragraph()
    if align is not None:
        p.alignment = align
    pf = p.paragraph_format
    pf.space_before = Pt(space_before)
    pf.space_after = Pt(space_after)
    pf.line_spacing = line_spacing
    if first_indent:
        pf.first_line_indent = Pt(first_indent)
    run = p.add_run(text)
    run.font.name = 'Times New Roman'
    run.font.size = Pt(size)
    run.bold = bold
    run._element.rPr.rFonts.set(qn('w:eastAsia'), font)
    return p


# 标题
add_para('通　　知', size=26, bold=True, font='黑体',
         align=WD_ALIGN_PARAGRAPH.CENTER, space_before=6, space_after=6, line_spacing=1.5)

add_para('关于明天（11月6日 星期五）正常上班不放假的通知',
         size=15, bold=False, font='楷体',
         align=WD_ALIGN_PARAGRAPH.CENTER, space_after=18, line_spacing=1.5)

# 称呼
add_para('物流部各位同事：', size=12, font='宋体', space_after=6)

# 正文
body = [
    '经公司研究决定，明天（2026年11月6日，星期五）不安排放假，公司各部门正常上班，'
    '我部各项工作按正常工作日运转。',
    '请各位同事按平时排班时间准时到岗，提前做好以下准备：一是核对当日收货、发货计划，'
    '与承运商确认车辆和到货时间；二是检查库存与在途单据，保证账实相符、单据齐全；'
    '三是做好仓库、装卸现场的安全检查和设备点检，作业中规范操作、注意人身与货物安全。',
    '如因特殊情况确需请假的同事，请提前向我报备，并按公司请假流程办理，'
    '以便及时调整岗位安排，确保物流作业不受影响。',
    '如后续安排有新的变化，我会第一时间在部门群里通知大家。感谢各位的理解与配合，'
    '请大家合理安排作息，明天以良好状态投入工作。',
]
for t in body:
    add_para(t, size=12, font='宋体', first_indent=24, line_spacing=1.5, space_after=6)

add_para('特此通知。', size=12, font='宋体', first_indent=24, space_after=24)

# 落款
add_para('物流部　小丽', size=12, font='宋体', align=WD_ALIGN_PARAGRAPH.RIGHT, space_after=2)
add_para('2026年11月5日', size=12, font='宋体', align=WD_ALIGN_PARAGRAPH.RIGHT, line_spacing=1.5)

out = 'L:/LY284/agent/lagent/关于明天不放假的 通知.docx'
doc.save(out)
print('saved:', out)
