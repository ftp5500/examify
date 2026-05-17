from django.contrib import admin
from .models import Exam, Question, Student, AnswerSheet, School , Staff


@admin.register(School)
class SchoolAdmin(admin.ModelAdmin):
    list_display = ['name', 'teacher']


class QuestionInline(admin.TabularInline):
    model = Question
    extra = 5


@admin.register(Exam)
class ExamAdmin(admin.ModelAdmin):
    inlines = [QuestionInline]
    list_display = ['title', 'subject', 'grade', 'section', 'teacher', 'created_at']


@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display = ['name', 'student_id', 'grade', 'section', 'school']
    list_filter = ['school', 'grade']


@admin.register(AnswerSheet)
class AnswerSheetAdmin(admin.ModelAdmin):
    list_display = ['student', 'exam', 'status', 'score', 'barcode']
    list_filter = ['exam', 'status']

from .models import Exam, Question, Student, AnswerSheet, School, Staff

@admin.register(Staff)
class StaffAdmin(admin.ModelAdmin):
    list_display = ['name', 'staff_id', 'mobile', 'email', 'role', 'school']
    list_filter = ['role', 'school']