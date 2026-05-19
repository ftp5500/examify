import io
from django.db.models import Q
import uuid
import tempfile
import os
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment

from django.http import HttpResponse
from rest_framework import viewsets, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework_simplejwt.tokens import RefreshToken

from .models import Exam, Student, AnswerSheet, Question, School, UserProfile
from .serializers import (
    ExamSerializer, StudentSerializer, AnswerSheetSerializer,
    QuestionSerializer, SchoolSerializer,
    PrincipalRegistrationSerializer, CustomTokenObtainPairSerializer,
)
from .pdf_generator import generate_answer_sheet
from .omr_engine import process_answer_sheet, calculate_score


# ============== Helpers ==============

def get_user_schools(user):
    """يرجع المدارس التي للمستخدم صلاحية عليها"""
    profile = getattr(user, 'profile', None)
    if profile and profile.role == 'principal':
        return user.managed_schools.all()
    return user.teaching_schools.all()


# ============== Auth ==============

class CustomTokenObtainPairView(TokenObtainPairView):
    """تسجيل دخول يرجّع بيانات المستخدم مع التوكن"""
    serializer_class = CustomTokenObtainPairSerializer


class RegisterPrincipalView(APIView):
    """تسجيل مدير مدرسة جديد"""
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = PrincipalRegistrationSerializer(data=request.data)
        if serializer.is_valid():
            result = serializer.save()
            user = result['user']
            school = result['school']
            refresh = RefreshToken.for_user(user)
            return Response({
                'message': 'تم التسجيل بنجاح',
                'user': {
                    'id': user.id,
                    'username': user.username,
                    'full_name': user.profile.full_name,
                    'role': 'principal',
                },
                'school': {
                    'id': school.id,
                    'name': school.name,
                },
                'access': str(refresh.access_token),
                'refresh': str(refresh),
            }, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# ============== ViewSets ==============

class ExamViewSet(viewsets.ModelViewSet):
    serializer_class = ExamSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        profile = getattr(user, 'profile', None)
        if profile and profile.role == 'principal':
            schools = user.managed_schools.all()
            return Exam.objects.filter(school__in=schools)
        return Exam.objects.filter(teacher=user)

    def perform_create(self, serializer):
        serializer.save(teacher=self.request.user)


class StudentViewSet(viewsets.ModelViewSet):
    serializer_class = StudentSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        schools = get_user_schools(self.request.user)
        queryset = Student.objects.filter(school__in=schools)

        grade = self.request.query_params.get('grade')
        section = self.request.query_params.get('section')
        search = self.request.query_params.get('search')

        if grade:
            queryset = queryset.filter(grade=grade)
        if section:
            queryset = queryset.filter(section=section)
        if search:
            queryset = queryset.filter(
                Q(name__icontains=search) | Q(student_id__icontains=search)
            )

        return queryset.order_by('grade', 'section', 'name')


class AnswerSheetViewSet(viewsets.ModelViewSet):
    serializer_class = AnswerSheetSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        profile = getattr(user, 'profile', None)
        if profile and profile.role == 'principal':
            schools = user.managed_schools.all()
            return AnswerSheet.objects.filter(exam__school__in=schools)
        return AnswerSheet.objects.filter(exam__teacher=user)


class SchoolViewSet(viewsets.ModelViewSet):
    serializer_class = SchoolSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return get_user_schools(self.request.user)

    def perform_create(self, serializer):
        serializer.save(principal=self.request.user)


class QuestionViewSet(viewsets.ModelViewSet):
    queryset = Question.objects.all()
    serializer_class = QuestionSerializer
    permission_classes = [IsAuthenticated]


# ============== توليد أوراق PDF ==============

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def generate_sheets(request, exam_id):
    exam = Exam.objects.get(id=exam_id)
    student_ids = request.data.get('student_ids', [])
    students = Student.objects.filter(id__in=student_ids)

    if not students.exists():
        return Response({'error': 'no students selected'}, status=400)

    from PyPDF2 import PdfWriter, PdfReader

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

    response = HttpResponse(output.read(), content_type='application/pdf')
    response['Content-Disposition'] = 'inline; filename="sheets.pdf"'
    return response


# ============== تصحيح الورقة ==============

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def grade_sheet(request, exam_id):
    exam = Exam.objects.get(id=exam_id)
    uploaded_file = request.FILES.get('image')

    if not uploaded_file:
        return Response({'error': 'no file'}, status=400)

    file_ext = os.path.splitext(uploaded_file.name)[1].lower()

    with tempfile.NamedTemporaryFile(delete=False, suffix=file_ext) as tmp:
        for chunk in uploaded_file.chunks():
            tmp.write(chunk)
        tmp_path = tmp.name

    try:
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


# ============== تصدير النتائج Excel ==============

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def export_results(request, exam_id):
    exam = Exam.objects.get(id=exam_id)
    sheets = AnswerSheet.objects.filter(exam=exam, status='graded').select_related('student')

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "النتائج"
    ws.sheet_view.rightToLeft = True

    ws.merge_cells('A1:F1')
    ws['A1'] = f"نتائج {exam.title} - {exam.subject}"
    ws['A1'].font = Font(bold=True, size=14)
    ws['A1'].alignment = Alignment(horizontal='center')

    headers = ['م', 'اسم الطالب', 'الرقم', 'الصف', 'الدرجة', 'التقدير']
    for col, h in enumerate(headers, 1):
        cell = ws.cell(row=2, column=col, value=h)
        cell.font = Font(bold=True, color='FFFFFF')
        cell.fill = PatternFill(fill_type='solid', fgColor='2563EB')
        cell.alignment = Alignment(horizontal='center')

    for row_num, sheet in enumerate(sheets, 1):
        score = sheet.score or 0
        if score >= 90:
            grade = 'ممتاز'
        elif score >= 80:
            grade = 'جيد جداً'
        elif score >= 70:
            grade = 'جيد'
        elif score >= 60:
            grade = 'مقبول'
        else:
            grade = 'ضعيف'
        row = [row_num, sheet.student.name, sheet.student.student_id, sheet.student.grade, score, grade]
        for col, val in enumerate(row, 1):
            cell = ws.cell(row=row_num + 2, column=col, value=val)
            cell.alignment = Alignment(horizontal='center')
            if col == 5:
                cell.font = Font(bold=True, color='16A34A' if score >= 60 else 'DC2626')

    ws.column_dimensions['A'].width = 5
    ws.column_dimensions['B'].width = 25
    ws.column_dimensions['C'].width = 12
    ws.column_dimensions['D'].width = 10
    ws.column_dimensions['E'].width = 10
    ws.column_dimensions['F'].width = 12

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)

    response = HttpResponse(
        buffer.read(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = f'attachment; filename="results_{exam_id}.xlsx"'
    return response


# ============== استيراد الطلاب من نور ==============

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def import_students(request):
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

    for sheet_name in wb.sheetnames:
        ws = wb[sheet_name]
        rows = list(ws.iter_rows(values_only=True))

        if len(rows) < 27:
            continue

        academic_year = get_val(rows, 1, 5)
        grade         = get_val(rows, 6, 3)
        section       = get_val(rows, 14, 2)
        school_name   = get_val(rows, 15, 37)

        if not school_name:
            continue

        # نستخدم المدرسة المحددة من المدير بدل اسم الملف
        school_id = request.data.get('school_id')
        if school_id:
            try:
                school = School.objects.get(id=school_id, principal=request.user)
            except School.DoesNotExist:
                return Response({'error': 'المدرسة غير موجودة'}, status=404)
        else:
            # fallback: أول مدرسة للمدير
            school = request.user.managed_schools.first()
            if not school:
                return Response({'error': 'لا توجد مدرسة مرتبطة بحسابك'}, status=400)

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

# ============== استيراد المعلمين ==============

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def import_teachers(request):
    """استيراد المعلمين من ملف Excel الرسمي"""
    from django.contrib.auth.models import User
    from django.core.mail import send_mail
    from django.conf import settings
    from .models import generate_random_password

    # تحقق أن المستخدم مدير
    profile = getattr(request.user, 'profile', None)
    if not profile or profile.role != 'principal':
        return Response({'error': 'فقط مدير المدرسة يقدر يستورد معلمين'}, status=403)

    excel_file = request.FILES.get('file')
    school_id = request.data.get('school_id')

    if not excel_file:
        return Response({'error': 'الملف مطلوب'}, status=400)
    if not school_id:
        return Response({'error': 'يجب اختيار المدرسة'}, status=400)

    # تحقق أن المدرسة تخص هذا المدير
    try:
        school = School.objects.get(id=school_id, principal=request.user)
    except School.DoesNotExist:
        return Response({'error': 'المدرسة غير موجودة أو ليست لك صلاحية عليها'}, status=404)

    try:
        wb = openpyxl.load_workbook(excel_file, data_only=True)
    except Exception as e:
        return Response({'error': f'ملف غير صالح: {str(e)}'}, status=400)

    ws = wb.active

    created = []     # معلمين جدد
    linked = []      # موجودين مسبقاً وتم ربطهم
    errors = []
    email_failures = []

    def normalize_mobile(mobile):
        if not mobile:
            return ''
        m = str(mobile).strip().replace(' ', '').replace('-', '')
        if m.startswith('00966'):
            return '+966' + m[5:]
        if m.startswith('966'):
            return '+' + m
        if m.startswith('05'):
            return '+966' + m[1:]
        if m.startswith('5') and len(m) == 9:
            return '+966' + m
        return m

    # نقرأ من الصف 16 فما فوق
    for row_idx in range(16, ws.max_row + 1):
        name = ws.cell(row=row_idx, column=22).value         # V
        national_id = ws.cell(row=row_idx, column=24).value  # X
        mobile = ws.cell(row=row_idx, column=6).value        # F
        email = ws.cell(row=row_idx, column=9).value         # I

        # تخطي الصفوف الفارغة
        if not name or not national_id:
            continue

        name = str(name).strip()
        national_id = str(national_id).strip()
        mobile = normalize_mobile(mobile)
        email = str(email).strip() if email else ''

        # تحقق أن رقم الهوية صحيح
        if not national_id.isdigit() or len(national_id) != 10:
            errors.append(f"رقم هوية غير صالح: {name} ({national_id})")
            continue

        try:
            # هل المعلم موجود مسبقاً؟
            existing_profile = UserProfile.objects.filter(national_id=national_id).first()

            if existing_profile:
                # موجود → فقط نربطه بهذه المدرسة
                if existing_profile.user not in school.teachers.all():
                    school.teachers.add(existing_profile.user)
                    linked.append({'name': name, 'national_id': national_id})
            else:
                # جديد → ننشئ حساب
                password = generate_random_password()

                user = User.objects.create_user(
                    username=national_id,
                    email=email or '',
                    password=password,
                    first_name=name.split()[0] if name else '',
                )

                UserProfile.objects.create(
                    user=user,
                    role='teacher',
                    full_name=name,
                    national_id=national_id,
                    mobile=mobile,
                    must_change_password=True,
                )

                school.teachers.add(user)

                # إرسال الإيميل بكلمة السر
                if email:
                    try:
                        send_mail(
                            subject=f'تم تسجيلك في نظام Examify - {school.name}',
                            message=(
                                f'مرحباً أ. {name}،\n\n'
                                f'تم تسجيلك كمعلم في {school.name}.\n\n'
                                f'بيانات الدخول:\n'
                                f'اسم المستخدم: {national_id}\n'
                                f'كلمة المرور المؤقتة: {password}\n\n'
                                f'⚠️ سيُطلب منك تغيير كلمة المرور عند أول تسجيل دخول.\n\n'
                                f'رابط النظام: http://localhost:3000\n\n'
                                f'مع تحيات إدارة {school.name}'
                            ),
                            from_email=settings.DEFAULT_FROM_EMAIL,
                            recipient_list=[email],
                            fail_silently=False,
                        )
                    except Exception as e:
                        email_failures.append({'name': name, 'email': email, 'error': str(e)})

                created.append({
                    'name': name,
                    'national_id': national_id,
                    'email': email,
                    'temp_password': password if not email else None,  # نرجعها فقط لو ما عنده إيميل
                })

        except Exception as e:
            errors.append(f"{name}: {str(e)}")

    return Response({
        'created_count': len(created),
        'linked_count': len(linked),
        'errors_count': len(errors),
        'email_failures_count': len(email_failures),
        'created': created,
        'linked': linked,
        'errors': errors[:10],
        'email_failures': email_failures[:10],
    })

# ============== قائمة المعلمين ==============

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def list_teachers(request):
    """قائمة معلمي مدارس المدير"""
    from django.contrib.auth.models import User

    profile = getattr(request.user, 'profile', None)
    if not profile or profile.role != 'principal':
        return Response({'error': 'فقط المدير يقدر يشوف المعلمين'}, status=403)

    schools = request.user.managed_schools.all()
    teachers = User.objects.filter(teaching_schools__in=schools).distinct()

    data = []
    for t in teachers:
        p = getattr(t, 'profile', None)
        data.append({
            'id': t.id,
            'username': t.username,
            'email': t.email,
            'full_name': p.full_name if p else '',
            'national_id': p.national_id if p else '',
            'mobile': p.mobile if p else '',
            'must_change_password': p.must_change_password if p else False,
        })
    return Response(data)

# ============== إعادة إرسال بيانات دخول معلم ==============

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def resend_teacher_credentials(request, teacher_id):
    """إرسال أو إعادة إرسال بيانات الدخول لمعلم"""
    from django.contrib.auth.models import User
    from django.core.mail import send_mail
    from django.conf import settings
    from .models import generate_random_password

    profile = getattr(request.user, 'profile', None)
    if not profile or profile.role != 'principal':
        return Response({'error': 'فقط المدير يقدر يرسل بيانات الدخول'}, status=403)

    try:
        teacher = User.objects.get(id=teacher_id)
    except User.DoesNotExist:
        return Response({'error': 'المعلم غير موجود'}, status=404)

    # تحقق أن المعلم في مدرسة هذا المدير
    schools = request.user.managed_schools.all()
    if not teacher.teaching_schools.filter(id__in=schools).exists():
        return Response({'error': 'هذا المعلم ليس في مدرستك'}, status=403)

    teacher_profile = getattr(teacher, 'profile', None)
    if not teacher_profile:
        return Response({'error': 'بيانات المعلم غير كاملة'}, status=400)

    if not teacher.email:
        return Response({'error': 'المعلم ليس لديه بريد إلكتروني مسجل'}, status=400)

    # توليد كلمة سر جديدة
    new_password = generate_random_password()
    teacher.set_password(new_password)
    teacher.save()

    teacher_profile.must_change_password = True
    teacher_profile.save()

    # إرسال الإيميل
    school = schools.first()
    try:
        send_mail(
            subject=f'بيانات الدخول إلى نظام Examify - {school.name}',
            message=(
                f'مرحباً أ. {teacher_profile.full_name}،\n\n'
                f'تم إعادة تعيين كلمة المرور الخاصة بك في نظام Examify.\n\n'
                f'بيانات الدخول:\n'
                f'اسم المستخدم: {teacher.username}\n'
                f'كلمة المرور الجديدة: {new_password}\n\n'
                f'⚠️ سيُطلب منك تغيير كلمة المرور عند تسجيل الدخول.\n\n'
                f'رابط النظام: http://localhost:3000\n\n'
                f'مع تحيات إدارة {school.name}'
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[teacher.email],
            fail_silently=False,
        )
        return Response({
            'success': True,
            'message': f'تم إرسال بيانات الدخول إلى {teacher.email}',
            'temp_password': new_password,
        })
    except Exception as e:
        return Response({
            'error': f'فشل إرسال البريد الإلكتروني: {str(e)}',
            'temp_password': new_password,
        }, status=500)


# ============== تغيير كلمة السر ==============

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def change_password(request):
    """تغيير كلمة السر — إجباري لأول دخول"""
    old_password = request.data.get('old_password')
    new_password = request.data.get('new_password')

    if not old_password or not new_password:
        return Response({'error': 'كلمة المرور القديمة والجديدة مطلوبتان'}, status=400)

    if not request.user.check_password(old_password):
        return Response({'error': 'كلمة المرور القديمة غير صحيحة'}, status=400)

    if len(new_password) < 8:
        return Response({'error': 'كلمة المرور الجديدة يجب أن تكون 8 أحرف على الأقل'}, status=400)

    if old_password == new_password:
        return Response({'error': 'كلمة المرور الجديدة يجب أن تختلف عن القديمة'}, status=400)

    request.user.set_password(new_password)
    request.user.save()

    # إيقاف إجبار تغيير كلمة السر
    profile = getattr(request.user, 'profile', None)
    if profile:
        profile.must_change_password = False
        profile.save()

    return Response({'message': 'تم تغيير كلمة المرور بنجاح'})
# ============== فلاتر الطلاب ==============

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def student_filters(request):
    """يرجع الصفوف والفصول المتاحة"""
    schools = get_user_schools(request.user)
    queryset = Student.objects.filter(school__in=schools)
    grades = list(queryset.values_list('grade', flat=True).distinct().order_by('grade'))
    return Response({'grades': [g for g in grades if g]})


# ============== تفاصيل طالب ==============

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def student_details(request, student_id):
    """تفاصيل طالب مع سجل اختباراته كاملاً"""
    schools = get_user_schools(request.user)

    try:
        student = Student.objects.get(id=student_id, school__in=schools)
    except Student.DoesNotExist:
        return Response({'error': 'الطالب غير موجود'}, status=404)

    sheets = AnswerSheet.objects.filter(
        student=student
    ).select_related('exam').order_by('-id')

    history = []
    for sheet in sheets:
        history.append({
            'sheet_id': sheet.id,
            'exam_id': sheet.exam.id,
            'exam_title': sheet.exam.title,
            'exam_subject': sheet.exam.subject,
            'exam_date': str(sheet.exam.exam_date) if sheet.exam.exam_date else None,
            'status': sheet.status,
            'score': sheet.score,
        })

    graded = [s for s in history if s['status'] == 'graded' and s['score'] is not None]
    avg_score = sum(s['score'] for s in graded) / len(graded) if graded else None

    return Response({
        'id': student.id,
        'name': student.name,
        'student_id': student.student_id,
        'grade': student.grade,
        'section': student.section,
        'school': student.school.name if student.school else '',
        'stats': {
            'total': len(history),
            'graded': len(graded),
            'pending': len([s for s in history if s['status'] == 'pending']),
            'avg_score': round(avg_score, 1) if avg_score is not None else None,
        },
        'history': history,
    })