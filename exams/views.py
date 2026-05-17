import io
import uuid
from .models import Exam, Student, AnswerSheet, Question, School
from .serializers import ExamSerializer, StudentSerializer, AnswerSheetSerializer, QuestionSerializer , SchoolSerializer
from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.http import FileResponse
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from .pdf_generator import generate_answer_sheet
from .models import Exam, Student, AnswerSheet
from .omr_engine import process_answer_sheet, calculate_score
import tempfile, os
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

class ExamViewSet(viewsets.ModelViewSet):
    serializer_class = ExamSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Exam.objects.filter(teacher=self.request.user)

    def perform_create(self, serializer):
        serializer.save(teacher=self.request.user)

class StudentViewSet(viewsets.ModelViewSet):
    queryset = Student.objects.all()
    serializer_class = StudentSerializer
    permission_classes = [IsAuthenticated]

class AnswerSheetViewSet(viewsets.ModelViewSet):
    queryset = AnswerSheet.objects.all()
    serializer_class = AnswerSheetSerializer
    permission_classes = [IsAuthenticated]

class SchoolViewSet(viewsets.ModelViewSet):
    serializer_class = SchoolSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return School.objects.filter(teacher=self.request.user)

    def perform_create(self, serializer):
        serializer.save(teacher=self.request.user)

class QuestionViewSet(viewsets.ModelViewSet):
        queryset = Question.objects.all()
        serializer_class = QuestionSerializer
        permission_classes = [IsAuthenticated]



@api_view(['POST'])
@permission_classes([IsAuthenticated])
def generate_sheets(request, exam_id):
    exam = Exam.objects.get(id=exam_id)
    student_ids = request.data.get('student_ids', [])
    students = Student.objects.filter(id__in=student_ids)

    if not students.exists():
        return Response({'error': 'no students selected'}, status=400)


    from PyPDF2 import PdfWriter, PdfReader
    import io

    writer = PdfWriter()

    for student in students:
        sheet, created = AnswerSheet.objects.get_or_create(
            exam=exam,
            student=student,
            defaults={'barcode': str(uuid.uuid4())[:12]}
        )

        buffer = generate_answer_sheet(exam, student, sheet.barcode)
        reader = PdfReader(buffer)
        writer.add_page(reader.pages[0])

    output = io.BytesIO()
    writer.write(output)
    output.seek(0)

    from django.http import HttpResponse
    response = HttpResponse(output.read(), content_type='application/pdf')
    response['Content-Disposition'] = 'inline; filename="sheets.pdf"'
    return response



@api_view(['POST'])
@permission_classes([IsAuthenticated])
def grade_sheet(request, exam_id):
    exam = Exam.objects.get(id=exam_id)
    uploaded_file = request.FILES.get('image')

    if not uploaded_file:
        return Response({'error': 'no file'}, status=400)

    import tempfile, os
    file_ext = os.path.splitext(uploaded_file.name)[1].lower()

    with tempfile.NamedTemporaryFile(delete=False, suffix=file_ext) as tmp:
        for chunk in uploaded_file.chunks():
            tmp.write(chunk)
        tmp_path = tmp.name

    try:
        # إذا كان PDF حوّله لصورة
        if file_ext == '.pdf':
            from pdf2image import convert_from_path
            pages = convert_from_path(tmp_path, dpi=300)
            img_tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.jpg')
            pages[0].save(img_tmp.name, 'JPEG')
            process_path = img_tmp.name
        else:
            process_path = tmp_path

        barcode, answers, confidence = process_answer_sheet(
            process_path, exam.num_questions, exam.num_choices
        )

        if not barcode:
            barcode = request.data.get('barcode')

        if not barcode:
            return Response({'error': 'لم يتم قراءة الباركود'}, status=400)

        sheet = AnswerSheet.objects.get(barcode=barcode, exam=exam)
        correct = {str(q.number): q.correct_answer for q in exam.questions.all()}
        score = calculate_score(answers, correct)
        print(f"ANSWERS: {answers}")
        print(f"SCORE: {score}")

        sheet.answers = answers
        sheet.score = score
        sheet.status = 'graded'
        sheet.save()

        return Response({
            'student': sheet.student.name,
            'score': score,
            'answers': answers,
            'confidence': confidence,
        })
    finally:
        os.unlink(tmp_path)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def export_results(request, exam_id):
    exam = Exam.objects.get(id=exam_id)
    sheets = AnswerSheet.objects.filter(exam=exam, status='graded').select_related('student')

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "النتائج"
    ws.sheet_view.rightToLeft = True

    # العنوان
    ws.merge_cells('A1:F1')
    ws['A1'] = f"نتائج {exam.title} - {exam.subject}"
    ws['A1'].font = Font(bold=True, size=14)
    ws['A1'].alignment = Alignment(horizontal='center')

    # الرأس
    headers = ['م', 'اسم الطالب', 'الرقم', 'الصف', 'الدرجة', 'التقدير']
    for col, h in enumerate(headers, 1):
        cell = ws.cell(row=2, column=col, value=h)
        cell.font = Font(bold=True, color='FFFFFF')
        cell.fill = PatternFill(fill_type='solid', fgColor='2563EB')
        cell.alignment = Alignment(horizontal='center')

    # البيانات
    for row_num, sheet in enumerate(sheets, 1):
        score = sheet.score or 0
        grade = 'ممتاز' if score >= 90 else 'جيد جداً' if score >= 80 else 'جيد' if score >= 70 else 'مقبول' if score >= 60 else 'ضعيف'
        row = [row_num, sheet.student.name, sheet.student.student_id, sheet.student.grade, score, grade]
        for col, val in enumerate(row, 1):
            cell = ws.cell(row=row_num + 2, column=col, value=val)
            cell.alignment = Alignment(horizontal='center')
            if col == 5:
                cell.font = Font(bold=True, color='16A34A' if score >= 60 else 'DC2626')

    # عرض الأعمدة
    ws.column_dimensions['A'].width = 5
    ws.column_dimensions['B'].width = 25
    ws.column_dimensions['C'].width = 12
    ws.column_dimensions['D'].width = 10
    ws.column_dimensions['E'].width = 10
    ws.column_dimensions['F'].width = 12

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)

    from django.http import HttpResponse
    response = HttpResponse(buffer.read(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = f'attachment; filename="results_{exam_id}.xlsx"'
    return response

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def import_students(request):
    import openpyxl
    from .models import School

    excel_file = request.FILES.get('file')
    if not excel_file:
        return Response({'error': 'الملف مطلوب'}, status=400)

    try:
        wb = openpyxl.load_workbook(excel_file, data_only=True)
    except Exception as e:
        return Response({'error': f'ملف غير صالح: {str(e)}'}, status=400)

    total_created = 0
    total_updated = 0
    all_errors = []

    def get_val(rows, row_idx, col_idx):
        try:
            v = rows[row_idx][col_idx]
            return str(v).strip() if v else ''
        except:
            return ''

    # ── معالجة كل sheet ──
    for sheet_name in wb.sheetnames:
        ws = wb[sheet_name]
        rows = list(ws.iter_rows(values_only=True))

        if len(rows) < 27:
            continue

        # استخراج بيانات الرأس
        academic_year = get_val(rows, 1, 5)
        grade         = get_val(rows, 6, 3)
        section       = get_val(rows, 14, 2)
        school_name   = get_val(rows, 15, 37)

        if not school_name:
            continue

        school, _ = School.objects.get_or_create(
            name=school_name,
            teacher=request.user
        )

        # استخراج بيانات الطلاب
        student_rows = rows[26:]
        i = 0
        while i < len(student_rows):
            row = student_rows[i]
            seq = row[45] if len(row) > 45 else None
            if seq is None or str(seq).strip() == '':
                i += 1
                continue
            try:
                name       = str(row[40]).strip() if len(row) > 40 and row[40] else ''
                student_id = str(row[33]).strip() if len(row) > 33 and row[33] else ''

                if not name or not student_id:
                    i += 2
                    continue

                student, was_created = Student.objects.update_or_create(
                    student_id=student_id,
                    defaults={
                        'name': name,
                        'grade': grade,
                        'section': section,
                        'school': school,
                    }
                )
                if was_created:
                    total_created += 1
                else:
                    total_updated += 1
            except Exception as e:
                all_errors.append(f"{sheet_name}: {str(e)}")
            i += 2

    return Response({
        'created': total_created,
        'updated': total_updated,
        'sheets': len(wb.sheetnames),
        'errors': all_errors[:5],
    })

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def import_staff(request):
    import openpyxl
    from .models import School, Staff

    excel_file = request.FILES.get('file')
    if not excel_file:
        return Response({'error': 'الملف مطلوب'}, status=400)

    try:
        wb = openpyxl.load_workbook(excel_file, data_only=True)
    except Exception as e:
        return Response({'error': f'ملف غير صالح: {str(e)}'}, status=400)

    total_created = 0
    total_updated = 0
    errors = []

    for sheet_name in wb.sheetnames:
        ws = wb[sheet_name]
        rows = list(ws.iter_rows(values_only=True))

        if len(rows) < 16:
            continue

        # اسم المدرسة من الصف 9
        try:
            school_name = str(rows[8][20]).strip() if rows[8][20] else ''
        except:
            school_name = ''

        school = None
        if school_name:
            school, _ = School.objects.get_or_create(
                name=school_name,
                teacher=request.user
            )

        # بيانات الكادر من الصف 16
        for row in rows[15:]:
            try:
                name     = str(row[21]).strip() if len(row) > 21 and row[21] else ''
                staff_id = str(row[23]).strip() if len(row) > 23 and row[23] else ''
                mobile   = str(row[5]).strip()  if len(row) > 5  and row[5]  else ''
                email    = str(row[8]).strip()   if len(row) > 8  and row[8]  else ''

                if not name or not staff_id or staff_id == 'رقم الهوية':
                    continue

                staff, was_created = Staff.objects.update_or_create(
                    staff_id=staff_id,
                    defaults={
                        'name': name,
                        'mobile': mobile,
                        'email': email,
                        'school': school,
                        'role': 'teacher',
                    }
                )
                if was_created:
                    total_created += 1
                else:
                    total_updated += 1
            except Exception as e:
                errors.append(str(e))

    return Response({
        'created': total_created,
        'updated': total_updated,
        'errors': errors[:5],
    })
