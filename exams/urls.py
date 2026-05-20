from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (
    SchoolViewSet, StudentViewSet, ExamViewSet,
    QuestionViewSet, AnswerSheetViewSet,
    RegisterPrincipalView,
    generate_sheets, grade_sheet, export_results,
    import_students, import_teachers, list_teachers,
    resend_teacher_credentials, change_password,
    student_filters, student_details, update_sheet_answers, debug_grade
)

router = DefaultRouter()
router.register(r'schools', SchoolViewSet, basename='school')
router.register(r'students', StudentViewSet, basename='student')
router.register(r'exams', ExamViewSet, basename='exam')
router.register(r'questions', QuestionViewSet, basename='question')
router.register(r'sheets', AnswerSheetViewSet, basename='sheet')

urlpatterns = [
    path('register/principal/', RegisterPrincipalView.as_view(), name='register-principal'),
    path('change-password/', change_password, name='change-password'),
    path('students/filters/', student_filters, name='student-filters'),
    path('students/import/', import_students, name='import-students'),
    path('students/<int:student_id>/details/', student_details, name='student-details'),
    path('teachers/', list_teachers, name='list-teachers'),
    path('teachers/import/', import_teachers, name='import-teachers'),
    path('teachers/<int:teacher_id>/resend-credentials/', resend_teacher_credentials,
         name='resend-teacher-credentials'),
    path('exams/<int:exam_id>/generate/', generate_sheets, name='generate-sheets'),
    path('exams/<int:exam_id>/grade/', grade_sheet, name='grade-sheet'),
    path('exams/<int:exam_id>/export/', export_results, name='export-results'),
    path('', include(router.urls)),
    path('sheets/<int:sheet_id>/update-answers/', update_sheet_answers, name='update-sheet-answers'),
    path('exams/<int:exam_id>/debug-grade/', debug_grade, name='debug-grade'),

]
