"""
exams/question_extractor.py
يدعم PDF نصي وPDF ممسوح (صور) عبر Claude Vision
"""
import json
import re
import base64
import threading
import anthropic
from django.conf import settings


# ══════════════════════════════════════════════════
#  استخراج النص من PDF (نصي)
# ══════════════════════════════════════════════════

def extract_text_pdf(pdf_path):
    """يحاول استخراج نص من PDF نصي"""
    try:
        import pdfplumber
        text = ""
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                t = page.extract_text()
                if t:
                    text += t + "\n\n"
        return text.strip()
    except Exception:
        return ""


# ══════════════════════════════════════════════════
#  تحويل صفحات PDF لصور
# ══════════════════════════════════════════════════

def pdf_pages_to_images(pdf_path, dpi=150):
    """يحوّل صفحات PDF لصور base64"""
    try:
        from pdf2image import convert_from_path
        pages = convert_from_path(pdf_path, dpi=dpi)
        images = []
        for page in pages:
            import io
            buf = io.BytesIO()
            page.save(buf, format='JPEG', quality=85)
            buf.seek(0)
            images.append(base64.b64encode(buf.read()).decode('utf-8'))
        return images
    except Exception as e:
        raise Exception(f"فشل تحويل PDF لصور: {e} — تأكد من تثبيت poppler")


# ══════════════════════════════════════════════════
#  استخراج أسئلة من نص
# ══════════════════════════════════════════════════

def extract_from_text_chunk(client, chunk, subject, grade):
    prompt = f"""أنت مساعد تعليمي. المادة: {subject} | الصف: {grade}

من النص التالي اصنع أكبر عدد ممكن من أسئلة اختيار من متعدد بالعربية.
كل سؤال: نص واضح + 4 خيارات + إجابة صحيحة واحدة.

النص:
{chunk}

أرجع JSON فقط بلا أي نص إضافي:
[{{"question":"...","a":"...","b":"...","c":"...","d":"...","correct":"A","difficulty":"medium","topic":"..."}}]

correct = A أو B أو C أو D فقط."""

    r = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}]
    )
    raw = re.sub(r'```json\s*|```\s*', '', r.content[0].text).strip()
    data = json.loads(raw)
    return data if isinstance(data, list) else []


# ══════════════════════════════════════════════════
#  استخراج أسئلة من صورة (Claude Vision)
# ══════════════════════════════════════════════════

def extract_from_image(client, image_b64, subject, grade, page_num):
    prompt = f"""أنت مساعد تعليمي متخصص في المناهج السعودية.
المادة: {subject} | الصف: {grade} | الصفحة: {page_num}

اقرأ هذه الصفحة من الكتاب المدرسي واصنع منها أكبر عدد ممكن من أسئلة اختيار من متعدد.
الأسئلة يجب أن:
- تكون مبنية على محتوى الصفحة فقط
- تكون باللغة العربية الفصحى
- تحتوي 4 خيارات متنوعة
- تكون مناسبة للمرحلة الدراسية

أرجع JSON فقط بلا أي نص إضافي:
[{{"question":"...","a":"...","b":"...","c":"...","d":"...","correct":"A","difficulty":"medium","topic":"..."}}]

correct = A أو B أو C أو D فقط.
إذا الصفحة لا تحتوي محتوى تعليمي مناسب للأسئلة أرجع: []"""

    r = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=4096,
        messages=[{
            "role": "user",
            "content": [
                {
                    "type":  "image",
                    "source": {
                        "type":       "base64",
                        "media_type": "image/jpeg",
                        "data":       image_b64,
                    }
                },
                {"type": "text", "text": prompt}
            ]
        }]
    )
    raw = re.sub(r'```json\s*|```\s*', '', r.content[0].text).strip()
    try:
        data = json.loads(raw)
        return data if isinstance(data, list) else []
    except Exception:
        return []


# ══════════════════════════════════════════════════
#  حفظ سؤال في قاعدة البيانات
# ══════════════════════════════════════════════════

def save_question(curriculum, q):
    from .models import BankQuestion
    q_text = q.get('question', '').strip()
    a      = q.get('a', '').strip()
    b      = q.get('b', '').strip()
    c      = q.get('c', '').strip()
    d      = q.get('d', '').strip()
    ans    = q.get('correct', 'A').strip().upper()

    if not q_text or not a or not b or not c:
        return False
    if ans not in ('A', 'B', 'C', 'D'):
        return False

    BankQuestion.objects.create(
        curriculum     = curriculum,
        subject        = curriculum.subject,
        grade          = curriculum.grade,
        question_text  = q_text,
        choice_a       = a,
        choice_b       = b,
        choice_c       = c,
        choice_d       = d,
        correct_answer = ans,
        difficulty     = q.get('difficulty', 'medium'),
        topic          = q.get('topic', ''),
    )
    return True


# ══════════════════════════════════════════════════
#  المهمة الرئيسية
# ══════════════════════════════════════════════════

def extract_questions_task(curriculum_id):
    from .models import Curriculum

    curriculum = None
    try:
        curriculum = Curriculum.objects.get(id=curriculum_id)
        curriculum.status          = 'processing'
        curriculum.questions_count = 0
        curriculum.error_message   = ''
        curriculum.save()

        pdf_path = curriculum.pdf_file.path
        client   = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        target   = 1000
        total    = 0

        # ── المحاولة 1: PDF نصي ──
        print("[Extractor] محاولة استخراج نص...")
        text = extract_text_pdf(pdf_path)

        if text and len(text) > 500:
            print(f"[Extractor] PDF نصي ✅ — {len(text)} حرف")

            # تقسيم لـ chunks
            words  = text.split()
            chunks = []
            chunk_size = 4000
            cur, size = [], 0
            for w in words:
                cur.append(w)
                size += len(w) + 1
                if size >= chunk_size:
                    chunks.append(' '.join(cur))
                    cur, size = [], 0
            if cur:
                chunks.append(' '.join(cur))

            for idx, chunk in enumerate(chunks):
                if total >= target:
                    break
                try:
                    questions = extract_from_text_chunk(client, chunk, curriculum.subject, curriculum.grade)
                    for q in questions:
                        if total >= target:
                            break
                        if save_question(curriculum, q):
                            total += 1
                    curriculum.questions_count = total
                    curriculum.save(update_fields=['questions_count'])
                    print(f"[Extractor] chunk {idx+1}/{len(chunks)} — {total} سؤال")
                except Exception as e:
                    print(f"[Extractor] chunk {idx} error: {e}")
                    continue

        else:
            # ── المحاولة 2: PDF ممسوح — Claude Vision ──
            print("[Extractor] PDF ممسوح — تحويل لصور...")
            images = pdf_pages_to_images(pdf_path, dpi=150)
            print(f"[Extractor] {len(images)} صفحة — بدء Vision...")

            for idx, img_b64 in enumerate(images):
                if total >= target:
                    break
                try:
                    questions = extract_from_image(
                        client, img_b64, curriculum.subject, curriculum.grade, idx + 1
                    )
                    for q in questions:
                        if total >= target:
                            break
                        if save_question(curriculum, q):
                            total += 1
                    curriculum.questions_count = total
                    curriculum.save(update_fields=['questions_count'])
                    print(f"[Extractor] صفحة {idx+1}/{len(images)} — {total} سؤال")
                except Exception as e:
                    print(f"[Extractor] صفحة {idx+1} error: {e}")
                    continue

        curriculum.status          = 'done'
        curriculum.questions_count = total
        curriculum.save()
        print(f"[Extractor] ✅ اكتمل: {total} سؤال")

    except Exception as e:
        print(f"[Extractor] ❌ خطأ: {e}")
        if curriculum:
            curriculum.status        = 'error'
            curriculum.error_message = str(e)
            curriculum.save()


def start_extraction(curriculum_id):
    t = threading.Thread(target=extract_questions_task, args=(curriculum_id,))
    t.daemon = True
    t.start()