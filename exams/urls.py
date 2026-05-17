from rest_framework.routers import DefaultRouter
from django.urls import path
from .views import (
    ExamViewSet, StudentViewSet, AnswerSheetViewSet,import_staff,
    QuestionViewSet, SchoolViewSet,
    generate_sheets, grade_sheet, export_results, import_students
)

router = DefaultRouter()
router.register('exams', ExamViewSet, basename='exam')
router.register('students', StudentViewSet, basename='student')
router.register('sheets', AnswerSheetViewSet, basename='sheet')
router.register('questions', QuestionViewSet, basename='question')
router.register('schools', SchoolViewSet, basename='school')

urlpatterns = [
    path('students/import/', import_students),
    path('exams/<int:exam_id>/generate/', generate_sheets),
    path('exams/<int:exam_id>/grade/', grade_sheet),
    path('exams/<int:exam_id>/export/', export_results),
                  path('staff/import/', import_staff),

              ] + router.urls