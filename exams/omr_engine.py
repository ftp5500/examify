import cv2
import numpy as np

IDX_TO_LATIN = ['A', 'B', 'C', 'D', 'E']


# ══════════════════════════════════════════════════
#  قراءة الباركود
# ══════════════════════════════════════════════════

def read_barcode(gray):
    try:
        from pyzbar.pyzbar import decode
        for d in decode(gray):
            return d.data.decode('utf-8')
    except Exception:
        pass
    return None


# ══════════════════════════════════════════════════
#  تصحيح الصورة
# ══════════════════════════════════════════════════

def _order_pts(pts):
    pts  = pts.reshape(4, 2).astype(np.float32)
    s, d = pts.sum(axis=1), np.diff(pts, axis=1)
    return np.array([
        pts[np.argmin(s)],
        pts[np.argmin(d)],
        pts[np.argmax(d)],
        pts[np.argmax(s)],
    ], dtype=np.float32)


def correct_image(gray):
    """
    يصحح الانحراف والتشوه.
    يجرب كشف حدود الورقة أولاً، ثم resize بسيط.
    """
    h, w  = gray.shape
    STD_W = int(595 * 2)   # 1190
    STD_H = int(842 * 2)   # 1684

    # ── محاولة 1: كشف الإطار الخارجي للورقة ──
    try:
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        edges   = cv2.Canny(blurred, 30, 100)
        kernel  = np.ones((5, 5), np.uint8)
        edges   = cv2.dilate(edges, kernel)

        contours, _ = cv2.findContours(
            edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )
        candidates = []
        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area < 0.25 * h * w:
                continue
            approx = cv2.approxPolyDP(
                cnt, 0.02 * cv2.arcLength(cnt, True), True
            )
            if len(approx) == 4:
                candidates.append((area, approx))

        if candidates:
            _, best = max(candidates, key=lambda x: x[0])
            pts = _order_pts(best)
            dst = np.float32([
                [0, 0], [STD_W, 0], [0, STD_H], [STD_W, STD_H]
            ])
            M = cv2.getPerspectiveTransform(pts, dst)
            return cv2.warpPerspective(gray, M, (STD_W, STD_H))
    except Exception:
        pass

    # ── محاولة 2: resize مع تصحيح النسبة ──
    ar_a4 = 595.0 / 842.0
    ar    = w / h
    if ar > ar_a4:
        nw    = int(h * ar_a4)
        x_off = (w - nw) // 2
        gray  = gray[:, x_off: x_off + nw]
    else:
        nh    = int(w / ar_a4)
        y_off = (h - nh) // 2
        gray  = gray[y_off: y_off + nh, :]

    return cv2.resize(gray, (STD_W, STD_H))


# ══════════════════════════════════════════════════
#  كشف الدوائر (HoughCircles)
# ══════════════════════════════════════════════════

def detect_bubbles(warped, num_choices):
    """
    يكشف دوائر الإجابات بـ HoughCircles.
    يستبعد منطقة الترويسة (أعلى 25%) ومنطقة QR.
    """
    h, w  = warped.shape
    scale = w / 595.0
    blur  = cv2.GaussianBlur(warped, (5, 5), 0)

    circles = cv2.HoughCircles(
        blur,
        cv2.HOUGH_GRADIENT,
        dp        = 1,
        minDist   = int(12 * scale),
        param1    = 50,
        param2    = 16,
        minRadius = int(5  * scale),
        maxRadius = int(12 * scale),
    )

    if circles is None:
        return None

    circles = np.round(circles[0]).astype(int)

    # ── استبعاد منطقة الترويسة والتعليمات (أعلى 25%) ──
    grid_start_y = int(h * 0.25)
    circles = [c for c in circles if c[1] > grid_start_y]

    # ── استبعاد منطقة QR ──
    qr_x = int(w * 0.22)
    qr_y = int(h * 0.24)
    circles = [c for c in circles
               if not (c[0] < qr_x and c[1] < qr_y)]

    return circles if circles else None


# ══════════════════════════════════════════════════
#  ترتيب الدوائر وقياس التظليل
# ══════════════════════════════════════════════════

def grade_by_circles(warped, circles, num_questions, num_choices):
    """
    يفصل العمودين أولاً ثم يجمع صفوف كل عمود على حدة.
    الخيارات من اليمين للشمال: أ=يمين، د=يسار
    """
    h, w  = warped.shape
    avg_r = int(np.median([c[2] for c in circles]))
    mid_x = w / 2

    # ── فصل العمودين بناءً على x ──
    right_circles = [c for c in circles if c[0] > mid_x]
    left_circles  = [c for c in circles if c[0] <= mid_x]

    def cluster(bubble_list):
        if not bubble_list:
            return []
        sorted_y = sorted(bubble_list, key=lambda c: c[1])
        gap      = avg_r * 1.8   # فاصل آمن بين الصفوف
        rows     = []
        current  = [sorted_y[0]]
        for c in sorted_y[1:]:
            if abs(c[1] - np.mean([r[1] for r in current])) < gap:
                current.append(c)
            else:
                rows.append(current)
                current = [c]
        rows.append(current)
        return rows

    # ── clustering لكل عمود على حدة ──
    right_rows = cluster(right_circles)
    left_rows  = cluster(left_circles)

    # ── تصفية الصفوف الصالحة ──
    def valid(rows):
        return sorted(
            [r for r in rows if abs(len(r) - num_choices) <= 1],
            key=lambda r: np.mean([c[1] for c in r])
        )

    right_valid = valid(right_rows)
    left_valid  = valid(left_rows)

    q_per_col = (num_questions + 1) // 2
    all_rows  = right_valid[:q_per_col] + left_valid[:q_per_col]
    all_rows  = all_rows[:num_questions]

    if not all_rows:
        return {}

    # ── قياس التظليل وتحديد الإجابات ──
    answers = {}
    for idx, row in enumerate(all_rows):
        q_num = idx + 1

        # من اليمين للشمال: أ في اليمين
        row_sorted = sorted(row[:num_choices], key=lambda c: -c[0])

        if len(row_sorted) < num_choices:
            answers[str(q_num)] = None
            continue

        readings = []
        for cx, cy, r in row_sorted:
            roi_r = int(r * 1.2)
            roi   = warped[
                max(0, cy - roi_r): min(h, cy + roi_r),
                max(0, cx - roi_r): min(w, cx + roi_r),
            ]
            readings.append(float(np.mean(roi)) if roi.size > 0 else 255.0)

        min_val = min(readings)
        spread  = max(readings) - min_val

        # threshold: spread > 25 و min < 175 (معايرة من بيانات فعلية)
        if spread > 25 and min_val < 175:
            answers[str(q_num)] = IDX_TO_LATIN[readings.index(min_val)]
        else:
            answers[str(q_num)] = None

    return answers


# ══════════════════════════════════════════════════
#  المعالجة الرئيسية
# ══════════════════════════════════════════════════

def process_answer_sheet(image_path, num_questions, num_choices):
    """
    يقرأ ورقة الإجابة ويرجع الإجابات.

    Returns:
        barcode   (str | None)
        answers   {'1': 'A', '2': 'B', ...}  — None إذا لم يُجب
        confidence (float 0-1)
    """
    img = cv2.imread(image_path)
    if img is None:
        return None, {}, 0.0

    # تصحيح الاتجاه
    if img.shape[1] > img.shape[0]:
        img = cv2.rotate(img, cv2.ROTATE_90_CLOCKWISE)

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # ── 1. قراءة QR قبل الـ warp ──
    barcode = read_barcode(gray)

    # ── 2. تصحيح الصورة ──
    warped = correct_image(gray)

    # ── 3. تحسين التباين ──
    clahe  = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    warped = clahe.apply(cv2.GaussianBlur(warped, (3, 3), 0))

    # ── 4. كشف الدوائر ──
    circles = detect_bubbles(warped, num_choices)

    if circles is None or len(circles) < num_questions * num_choices * 0.6:
        return barcode, {str(i): None for i in range(1, num_questions + 1)}, 0.0

    # ── 5. تحديد الإجابات ──
    answers    = grade_by_circles(warped, circles, num_questions, num_choices)
    answered   = sum(1 for v in answers.values() if v is not None)
    confidence = round(answered / max(num_questions, 1), 2)

    return barcode, answers, confidence


# ══════════════════════════════════════════════════
#  حساب الدرجة
# ══════════════════════════════════════════════════

def calculate_score(student_answers, correct_answers, total_weight=100):
    """
    student_answers: {'1': 'A', '2': None, ...}
    correct_answers: {'1': 'A', '2': 'C', ...}
    """
    if not correct_answers:
        return 0.0

    correct = sum(
        1 for q, ans in correct_answers.items()
        if student_answers.get(str(q)) == ans
    )

    return round((correct / len(correct_answers)) * total_weight, 1)