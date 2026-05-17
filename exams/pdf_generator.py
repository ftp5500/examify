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

FONT_PATH = os.path.join(os.path.dirname(__file__), 'Amiri-Regular.ttf')
pdfmetrics.registerFont(TTFont('Amiri', FONT_PATH))


def ar(text):
    if text is None or text == '':
        return ''
    reshaped = arabic_reshaper.reshape(str(text))
    return get_display(reshaped)


W, H = A4


def generate_answer_sheet(exam, student, barcode_value):
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)

    # الإطار الخارجي
    c.setLineWidth(1.5)
    c.rect(30, 30, W - 60, H - 60)

    # ── الترويسة العلوية ──
    # اسم المدرسة
    school_name = exam.school.name if exam.school else ''
    c.setFont("Amiri", 13)
    c.drawCentredString(W / 2, H - 60, ar(school_name))

    # عنوان الاختبار
    c.setFont("Amiri", 16)
    c.drawCentredString(W / 2, H - 82, ar(exam.title))

    # السنة الدراسية والتاريخ
    c.setFont("Amiri", 10)
    year_text = f"العام الدراسي: {exam.academic_year}" if exam.academic_year else ''
    date_text = f"التاريخ: {exam.exam_date}" if exam.exam_date else ''
    if year_text:
        c.drawString(45, H - 105, ar(year_text))
    if date_text:
        c.drawRightString(W - 45, H - 105, ar(date_text))

    # خط فاصل
    c.setLineWidth(0.5)
    c.line(45, H - 115, W - 45, H - 115)

    # ── QR Code ──
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=4,
        border=2,
    )
    qr.add_data(barcode_value)
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color="black", back_color="white")
    qr_buffer = io.BytesIO()
    qr_img.save(qr_buffer, format='PNG')
    qr_buffer.seek(0)
    c.drawImage(ImageReader(qr_buffer), 45, H - 220, width=85, height=85)

    # ── بيانات الطالب ──
    c.setFont("Amiri", 12)
    info_x = W - 50
    y = H - 135

    c.drawRightString(info_x, y, ar(f"الطالب: {student.name}"))
    y -= 18
    c.drawRightString(info_x, y, ar(f"الرقم: {student.student_id}"))
    y -= 18

    grade_text = exam.grade or student.grade
    if grade_text:
        c.drawRightString(info_x, y, ar(f"الصف: {grade_text}"))
        y -= 18

    section = exam.section or student.section
    if section:
        c.drawRightString(info_x, y, ar(f"الفصل: {section}"))
        y -= 18

    c.drawRightString(info_x, y, ar(f"المادة: {exam.subject}"))

    # رمز الورقة الصغير
    c.setFont("Helvetica", 8)
    c.drawString(45, H - 232, f"Sheet: {barcode_value}")

    # ── التعليمات ──
    c.setLineWidth(0.5)
    c.line(45, H - 245, W - 45, H - 245)
    c.setFont("Amiri", 10)
    c.drawCentredString(W / 2, H - 262, ar("ظلّل الدائرة بالكامل باستخدام قلم غامق"))

    # ── شبكة الإجابات ──
    choices = ['A', 'B', 'C', 'D', 'E'][:exam.num_choices]
    num_q = exam.num_questions

    questions_per_col = -(-num_q // 2)
    col_width = (W - 80) / 2
    start_y = H - 290
    row_h = 24
    bubble_r = 7

    for i in range(num_q):
        col = i // questions_per_col
        row = i % questions_per_col

        x = 45 + col * col_width
        y_pos = start_y - row * row_h

        c.setFont("Helvetica-Bold", 9)
        c.drawString(x, y_pos - 4, f"{i + 1}.")

        for j, choice in enumerate(choices):
            cx = x + 30 + j * 26
            cy = y_pos
            c.setLineWidth(0.8)
            c.circle(cx, cy, bubble_r, stroke=1, fill=0)
            c.setFont("Helvetica", 8)
            c.drawCentredString(cx, cy - 3, choice)

    c.save()
    buffer.seek(0)
    return buffer