from django.contrib import admin
from .models import UserProfile, School, Student, Exam, Question, AnswerSheet


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'full_name', 'role', 'national_id', 'mobile', 'must_change_password')
    list_filter = ('role', 'must_change_password')
    search_fields = ('full_name', 'national_id', 'user__username', 'user__email')


@admin.register(School)
class SchoolAdmin(admin.ModelAdmin):
    list_display = ('name', 'principal', 'education_directorate', 'created_at')
    search_fields = ('name', 'principal__username')
    list_filter = ('created_at',)
    filter_horizontal = ('teachers',)


@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display = ('name', 'student_id', 'school', 'grade', 'section')
    list_filter = ('school', 'grade', 'section')
    search_fields = ('name', 'student_id')


@admin.register(Exam)
class ExamAdmin(admin.ModelAdmin):
    list_display = ('title', 'teacher', 'subject', 'school', 'num_questions', 'exam_date')
    list_filter = ('school', 'subject', 'grade')
    search_fields = ('title',)


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ('exam', 'number', 'correct_answer')
    list_filter = ('exam',)


@admin.register(AnswerSheet)
class AnswerSheetAdmin(admin.ModelAdmin):
    list_display = ('exam', 'student', 'barcode', 'status', 'score')
    list_filter = ('exam', 'status')
    search_fields = ('barcode',)