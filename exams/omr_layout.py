"""
الملف المشترك بين pdf_generator.py و omr_engine.py
يضمن أن الـ PDF والـ OMR يستخدمان نفس الإحداثيات بالضبط
"""
import math

# ── أبعاد A4 ──
W_PDF = 595.0
H_PDF = 842.0

# ── ثوابت التصميم ──
MARGIN    = 30.0
MARK_SIZE = 14.0   # حجم العلامة المرجعية

# ── الخيارات العربية (من اليمين للشمال) ──
AR_CHOICES   = ['أ', 'ب', 'ج', 'د', 'هـ']
IDX_TO_LATIN = ['A', 'B', 'C', 'D', 'E']

# ── منطقة شبكة الإجابات ──
GRID_TOP_Y    = H_PDF - 255.0   # = 587 (أسفل التعليمات بمسافة كافية)
GRID_BOTTOM_Y = MARGIN + MARK_SIZE + 20.0
GRID_RIGHT_X  = W_PDF - MARGIN - MARK_SIZE - 10.0   # = 541
GRID_LEFT_X   = MARGIN + MARK_SIZE + 10.0            # = 54
GRID_WIDTH    = GRID_RIGHT_X - GRID_LEFT_X           # = 487
COL_GAP       = 22.0   # مسافة بين العمودين


def get_grid_params(num_q, num_choices):
    """حساب أبعاد شبكة الإجابات"""
    grid_h    = GRID_TOP_Y - GRID_BOTTOM_Y
    num_cols  = 2 if num_q <= 70 else 3
    q_per_col = math.ceil(num_q / num_cols)
    row_h     = min(28.0, grid_h / q_per_col)
    row_h     = max(13.0, row_h)
    bubble_r  = min(8.5, row_h * 0.33)
    bubble_r  = max(5.0, bubble_r)
    bubble_sp = bubble_r * 2 + 5.0
    q_num_w   = 22.0
    col_w     = (GRID_WIDTH - COL_GAP * (num_cols - 1)) / num_cols

    return {
        'num_cols':  num_cols,
        'q_per_col': q_per_col,
        'row_h':     row_h,
        'bubble_r':  bubble_r,
        'bubble_sp': bubble_sp,
        'q_num_w':   q_num_w,
        'col_w':     col_w,
        'col_gap':   COL_GAP,
    }


def get_bubble_positions_pdf(num_q, num_choices):
    """
    إحداثيات مراكز الدوائر بنظام ReportLab (أسفل يسار = 0,0)
    Returns: { (q_num, choice_idx): (cx, cy) }
    choice_idx: 0=أ (يمين)، 1=ب، ...
    """
    p = get_grid_params(num_q, num_choices)
    positions = {}

    for i in range(num_q):
        col   = i // p['q_per_col']
        row   = i % p['q_per_col']
        q_num = i + 1

        cy        = GRID_TOP_Y - row * p['row_h']
        col_right = GRID_RIGHT_X - col * (p['col_w'] + COL_GAP)
        start_x   = col_right - p['q_num_w'] - p['bubble_r']

        for j in range(num_choices):
            cx = start_x - j * p['bubble_sp']
            positions[(q_num, j)] = (cx, cy)

    return positions


def get_bubble_positions_normalized(num_q, num_choices):
    """
    نفس الإحداثيات لكن مُطبَّعة (0-1) بنظام الشاشة (أعلى يسار = 0,0)
    تُستخدم في omr_engine.py
    """
    pdf_pos = get_bubble_positions_pdf(num_q, num_choices)
    return {
        key: (cx / W_PDF, 1.0 - cy / H_PDF)
        for key, (cx, cy) in pdf_pos.items()
    }