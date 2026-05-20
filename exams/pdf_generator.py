import qrcode
import io
import os
import arabic_reshaper
from bidi.algorithm import get_display
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.colors import black

from .omr_layout import (
    W_PDF, H_PDF, MARGIN, MARK_SIZE, AR_CHOICES,
    GRID_TOP_Y, GRID_BOTTOM_Y, GRID_RIGHT_X,
    get_grid_params, get_bubble_positions_pdf,
)

FONT_PATH = os.path.join(os.path.dirname(__file__), 'Amiri-Regular.ttf')
pdfmetrics.registerFont(TTFont('Amiri', FONT_PATH))

W, H = A4


def ar(text):
    if not text:
        return ''
    return get_display(arabic_reshaper.reshape(str(text)))


def _draw_marks(c):
    """العلامات المرجعية السوداء في الزوايا الأربعة"""
    c.setFillColor(black)
    for (x, y) in [
        (MARGIN,                   H - MARGIN - MARK_SIZE),
        (W - MARGIN - MARK_SIZE,   H - MARGIN - MARK_SIZE),
        (MARGIN,                   MARGIN),
        (W - MARGIN - MARK_SIZE,   MARGIN),
    ]:
        c.rect(x, y, MARK_SIZE, MARK_SIZE, stroke=0, fill=1)


def generate_answer_sheet(exam, student, barcode_value):
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)

    num_q       = exam.num_questions
    num_choices = exam.num_choices
    ar_choices  = AR_CHOICES[:num_choices]
    p           = get_grid_params(num_q, num_choices)
    positions   = get_bubble_positions_pdf(num_q, num_choices)

    # ══ 1. العلامات المرجعية ══
    _draw_marks(c)

    # ══ 2. الإطار الخارجي ══
    c.setStrokeColor(black)
    c.setLineWidth(1.5)
    c.rect(MARGIN, MARGIN, W - 2 * MARGIN, H - 2 * MARGIN)

    # ══ 3. الترويسة ══
    hdr_top = H - MARGIN - MARK_SIZE - 8

    school_name = exam.school.name if exam.school else ''
    c.setFont("Amiri", 12)
    c.drawCentredString(W / 2, hdr_top - 2, ar(school_name))

    c.setFont("Amiri", 15)
    c.drawCentredString(W / 2, hdr_top - 22, ar(exam.title))

    c.setLineWidth(0.5)
    c.line(MARGIN + MARK_SIZE + 5, hdr_top - 35, W - MARGIN - MARK_SIZE - 5, hdr_top - 35)

    # ══ 4. QR Code (يسار) ══
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=4, border=2,
    )
    qr.add_data(barcode_value)
    qr.make(fit=True)
    qr_buf = io.BytesIO()
    qr.make_image(fill_color="black", back_color="white").save(qr_buf, format='PNG')
    qr_buf.seek(0)

    qr_x, qr_y, qr_sz = MARGIN + MARK_SIZE + 5, hdr_top - 125, 80
    c.drawImage(ImageReader(qr_buf), qr_x, qr_y, width=qr_sz, height=qr_sz)

    c.setFont("Helvetica", 7)
    c.drawCentredString(qr_x + qr_sz / 2, qr_y - 10, barcode_value[:20])

    # ══ 5. بيانات الطالب (يمين) ══
    c.setFont("Amiri", 11)
    dx = W - MARGIN - MARK_SIZE - 8
    dy = hdr_top - 47

    grade   = exam.grade   or getattr(student, 'grade',   '')
    section = exam.section or getattr(student, 'section', '')
    if hasattr(exam, 'sections_list') and exam.sections_list:
        section = '، '.join(exam.sections_list)

    sem_map = {'first': 'الأول', 'second': 'الثاني'}
    per_map = {
        'first':  'الفترة الأولى',
        'second': 'الفترة الثانية',
        'final':  'نهاية الفصل',
    }

    info_parts = list(filter(None, [
        exam.academic_year or '',
        f"الفصل {sem_map[exam.semester]}" if getattr(exam, 'semester', '') else '',
        per_map.get(getattr(exam, 'period', ''), ''),
    ]))

    rows = [
        f"الطالب: {student.name}",
        f"رقم الطالب: {student.student_id}",
        f"المادة: {exam.subject}",
    ]
    if grade:
        rows.append(f"الصف: {grade}   الفصل: {section}")
    if info_parts:
        rows.append(' | '.join(info_parts))

    for txt in rows:
        c.drawRightString(dx, dy, ar(txt))
        dy -= 19

    # ══ 6. فاصل + تعليمات ══
    sep = GRID_TOP_Y + 50   # دائماً 50pt فوق بداية الشبكة
    c.setLineWidth(1)
    c.line(MARGIN + MARK_SIZE + 5, sep, W - MARGIN - MARK_SIZE - 5, sep)
    c.setFont("Amiri", 10)
    c.drawCentredString(W / 2, sep - 14, ar("ظلِّل الدائرة المناسبة كاملاً باستخدام قلم رصاص غامق"))
    c.setLineWidth(0.5)
    c.line(MARGIN + MARK_SIZE + 5, sep - 26, W - MARGIN - MARK_SIZE - 5, sep - 26)

    # ══ 7. شبكة الإجابات ══
    for i in range(num_q):
        q_num     = i + 1
        col       = i // p['q_per_col']
        row       = i % p['q_per_col']
        base_y    = GRID_TOP_Y - row * p['row_h']
        col_right = GRID_RIGHT_X - col * (p['col_w'] + p['col_gap'])

        # رقم السؤال
        c.setFont("Amiri", 9)
        c.drawRightString(col_right, base_y - 3, ar(str(q_num)))

        # الدوائر من اليمين للشمال
        for j in range(num_choices):
            cx, cy = positions[(q_num, j)]
            c.setLineWidth(0.9)
            c.setStrokeColor(black)
            c.circle(cx, cy, p['bubble_r'], stroke=1, fill=0)

            fs = max(6, p['bubble_r'] * 0.85)
            c.setFont("Amiri", fs)
            c.drawCentredString(cx, cy - fs * 0.38, ar(ar_choices[j]))

        # خط فاصل خفيف بين الصفوف
        if row < p['q_per_col'] - 1:
            line_y = base_y - p['row_h'] * 0.55
            end_x  = positions[(q_num, num_choices - 1)][0] - p['bubble_r'] - 3
            c.setLineWidth(0.2)
            c.setStrokeColorRGB(0.85, 0.85, 0.85)
            c.line(end_x, line_y, col_right + 4, line_y)
            c.setStrokeColor(black)

    # ── فاصل عمودي بين الأعمدة ──
    if p['num_cols'] >= 2:
        mid_x = GRID_RIGHT_X - p['col_w'] - p['col_gap'] / 2
        c.setLineWidth(0.4)
        c.setStrokeColorRGB(0.7, 0.7, 0.7)
        c.line(mid_x, GRID_TOP_Y + 5, mid_x, GRID_BOTTOM_Y)
        c.setStrokeColor(black)

    c.save()
    buffer.seek(0)
    return buffer