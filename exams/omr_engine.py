import cv2
import numpy as np
from pyzbar.pyzbar import decode
from itertools import combinations


def process_answer_sheet(image_path, num_questions, num_choices):
    img = cv2.imread(image_path)
    if img is None:
        return None, {}, 0
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    gray = deskew(gray)
    barcode = read_barcode(gray)
    answers, confidence = detect_answers_hough(gray, num_questions, num_choices)
    return barcode, answers, confidence


def deskew(gray):
    coords = np.column_stack(np.where(gray < 200))
    if len(coords) < 100:
        return gray
    angle = cv2.minAreaRect(coords)[-1]
    if angle < -45:
        angle = 90 + angle
    if abs(angle) < 0.5:
        return gray
    h, w = gray.shape
    M = cv2.getRotationMatrix2D((w // 2, h // 2), -angle, 1.0)
    return cv2.warpAffine(gray, M, (w, h), flags=cv2.INTER_CUBIC,
                          borderMode=cv2.BORDER_REPLICATE)


def read_barcode(gray):
    barcodes = decode(gray)
    if barcodes:
        return barcodes[0].data.decode('utf-8')
    return None


def pick_best_bubbles(half, num_choices, expected_gap=None, anchor_x=None):
    if len(half) == num_choices:
        return half
    best = None
    best_score = float('inf')
    for combo in combinations(half, num_choices):
        xs = sorted([c[0] for c in combo])
        gaps = [xs[i+1] - xs[i] for i in range(len(xs)-1)]
        avg_gap = sum(gaps) / len(gaps)
        variance = sum((g - avg_gap) ** 2 for g in gaps)
        if expected_gap:
            variance += (avg_gap - expected_gap) ** 2 * 0.5
        if anchor_x is not None:
            variance += (xs[0] - anchor_x) ** 2 * 0.3
        if variance < best_score:
            best_score = variance
            best = sorted(combo, key=lambda c: c[0])
    return best


def detect_answers_hough(gray, num_questions, num_choices):
    h, w = gray.shape
    blurred = cv2.GaussianBlur(gray, (7, 7), 0)
    scale = w / 595.0
    expected_r = int(7 * scale)
    expected_gap = int(26 * scale)
    mid_x = w // 2
    grid_top = int(h * 0.27)
    grid_bottom = int(h * 0.88)

    circles_raw = cv2.HoughCircles(
        blurred, cv2.HOUGH_GRADIENT, dp=1,
        minDist=int(15 * scale),
        param1=30, param2=12,
        minRadius=expected_r - 15,
        maxRadius=expected_r + 20
    )

    if circles_raw is None:
        return {}, 0

    all_circles = [(int(x), int(y), int(r))
                   for x, y, r in np.round(circles_raw[0]).astype("int")
                   if grid_top < y < grid_bottom]

    # تجميع في صفوف
    bubbles = sorted(all_circles, key=lambda b: (round(b[1] / 60) * 60, b[0]))
    rows = []
    current_row = []
    last_y = -999

    for b in bubbles:
        if abs(b[1] - last_y) < 50:
            current_row.append(b)
        else:
            if current_row:
                rows.append(sorted(current_row, key=lambda c: c[0]))
            current_row = [b]
            last_y = b[1]
    if current_row:
        rows.append(sorted(current_row, key=lambda c: c[0]))

    # حساب المرجعيات
    actual_gap = expected_gap
    anchor_left = None
    anchor_right = None

    for row in rows:
        lh = [c for c in row if c[0] < mid_x]
        rh = [c for c in row if c[0] >= mid_x]
        if len(lh) == num_choices and anchor_left is None:
            xs = sorted([c[0] for c in lh])
            gaps = [xs[i+1]-xs[i] for i in range(len(xs)-1)]
            actual_gap = sum(gaps) / len(gaps)
            anchor_left = xs[0]
        if len(rh) == num_choices and anchor_right is None:
            anchor_right = sorted([c[0] for c in rh])[0]

    questions_per_col = -(-num_questions // 2)

    # تقسيم لعمودين
    left = []
    right = []

    for row in rows:
        lh = sorted([c for c in row if c[0] < mid_x], key=lambda c: c[0])
        rh = sorted([c for c in row if c[0] >= mid_x], key=lambda c: c[0])

        if len(lh) >= num_choices:
            best = pick_best_bubbles(lh, num_choices, actual_gap, anchor_left)
            if best:
                left.append(best)

        if len(rh) >= num_choices:
            best = pick_best_bubbles(rh, num_choices, actual_gap, anchor_right)
            if best:
                right.append(best)

    left.sort(key=lambda r: r[0][1])
    right.sort(key=lambda r: r[0][1])

    # استرداد الصف المفقود بالموضع المتوقع
    for col_rows, anchor_x in [(left, anchor_left), (right, anchor_right)]:
        if len(col_rows) < questions_per_col and len(col_rows) >= 2 and anchor_x:
            ys = [r[0][1] for r in col_rows]
            spacings = [ys[i+1]-ys[i] for i in range(len(ys)-1)]
            avg_spacing = sum(spacings) / len(spacings)

            # إيجاد الموضع المفقود
            missing_y = None
            missing_idx = len(col_rows)  # افتراضياً في النهاية

            for i in range(len(ys)-1):
                if spacings[i] > avg_spacing * 1.6:
                    missing_y = int(ys[i] + avg_spacing)
                    missing_idx = i + 1
                    break

            if missing_y is None:
                missing_y = int(ys[-1] + avg_spacing)

            # ابحث في الدوائر الأصلية عن دوائر قريبة من الموضع المتوقع
            nearby = [c for c in all_circles
                      if abs(c[1] - missing_y) < 60
                      and (c[0] < mid_x if anchor_x < mid_x else c[0] >= mid_x)]

            if len(nearby) >= num_choices:
                best = pick_best_bubbles(
                    sorted(nearby, key=lambda c: c[0]),
                    num_choices, actual_gap, anchor_x
                )
                if best:
                    col_rows.insert(missing_idx, best)
            elif anchor_x:
                # أنشئ الصف من الإحداثيات المتوقعة
                r_default = int(7 * scale)
                inferred = [(int(anchor_x + j * actual_gap), missing_y, r_default)
                            for j in range(num_choices)]
                col_rows.insert(missing_idx, inferred)

    all_rows = [None] * num_questions
    for i, row in enumerate(left[:questions_per_col]):
        all_rows[i] = row
    for i, row in enumerate(right[:questions_per_col]):
        all_rows[questions_per_col + i] = row

    choices = ['A', 'B', 'C', 'D', 'E'][:num_choices]
    answers = {}
    total_conf = 0

    for q_idx, bubble_row in enumerate(all_rows):
        if bubble_row is None:
            answers[str(q_idx + 1)] = None
            continue

        darknesses = []
        for (cx, cy, r) in bubble_row:
            inner = max(3, int(r * 0.55))
            x1 = max(0, cx - inner)
            x2 = cx
            y1 = max(0, cy - inner)
            y2 = cy
            cell = gray[y1:y2, x1:x2]
            val = float(np.mean(cell)) if cell.size > 0 else 255.0
            darknesses.append(val)

        while len(darknesses) < num_choices:
            darknesses.append(255.0)

        min_val = min(darknesses)
        min_idx = darknesses.index(min_val)
        sorted_d = sorted(darknesses)
        contrast = sorted_d[1] - sorted_d[0] if len(sorted_d) > 1 else 0

        if contrast > 12 and min_val < 210:
            answers[str(q_idx + 1)] = choices[min_idx]
            total_conf += contrast
        else:
            answers[str(q_idx + 1)] = None

    confidence = min(100.0, total_conf / max(num_questions, 1))
    return answers, round(confidence, 1)


def calculate_score(student_answers, correct_answers, total_weight=100):
    if not correct_answers:
        return 0
    correct = sum(1 for q, a in correct_answers.items()
                  if student_answers.get(q) == a)
    return round((correct / len(correct_answers)) * total_weight, 1)