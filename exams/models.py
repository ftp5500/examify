import uuid
import secrets
import string
from django.db import models
from django.contrib.auth.models import User


class UserProfile(models.Model):
    """ملف تعريفي لكل مستخدم — يحدد دوره (مدير/معلم)"""

    ROLE_CHOICES = [
        ('principal', 'مدير مدرسة'),
        ('teacher', 'معلم'),
    ]

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='profile'
    )
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='teacher')
    full_name = models.CharField(max_length=200, blank=True)
    national_id = models.CharField(max_length=20, unique=True)
    mobile = models.CharField(max_length=20, blank=True)
    must_change_password = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.full_name or self.user.username} ({self.get_role_display()})"


def generate_random_password(length=10):
    """توليد كلمة مرور عشوائية للمعلمين الجدد"""
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))


class School(models.Model):
    name = models.CharField(max_length=200)

    # المدير: مالك المدرسة (واحد فقط)
    principal = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='managed_schools'
    )

    # المعلمون: عدة معلمين، ومعلم يمكن يكون في عدة مدارس
    teachers = models.ManyToManyField(
        User,
        related_name='teaching_schools',
        blank=True
    )

    # معلومات إضافية للتقارير
    education_directorate = models.CharField(max_length=200, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class Student(models.Model):
    school = models.ForeignKey(School, on_delete=models.CASCADE, null=True, blank=True)
    name = models.CharField(max_length=100)
    student_id = models.CharField(max_length=20)
    grade = models.CharField(max_length=20)  # الصف (مثل: السادس)
    section = models.CharField(max_length=20, blank=True)  # الفصل (مثل: أ، ب، 1، 2)

    class Meta:
        unique_together = ('school', 'student_id')

    def __str__(self):
        return f"{self.name} - {self.student_id}"


class Exam(models.Model):
    teacher = models.ForeignKey(User, on_delete=models.CASCADE)
    school = models.ForeignKey(School, on_delete=models.CASCADE, null=True, blank=True)
    title = models.CharField(max_length=200)
    subject = models.CharField(max_length=100)
    grade = models.CharField(max_length=20, blank=True)
    section = models.CharField(max_length=20, blank=True)
    academic_year = models.CharField(max_length=20, blank=True, default='1447/1448')
    exam_date = models.DateField(null=True, blank=True)
    num_questions = models.IntegerField(default=20)
    num_choices = models.IntegerField(default=4)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title


class Question(models.Model):
    exam = models.ForeignKey(Exam, related_name='questions', on_delete=models.CASCADE)
    number = models.IntegerField()
    correct_answer = models.CharField(max_length=1)

    class Meta:
        ordering = ['number']


class AnswerSheet(models.Model):
    STATUS_CHOICES = [
        ('pending', 'لم تُصحح'),
        ('graded', 'مصححة'),
        ('error', 'خطأ'),
    ]
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE)
    student = models.ForeignKey(Student, on_delete=models.CASCADE)
    barcode = models.CharField(max_length=50, unique=True, default=uuid.uuid4)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    score = models.FloatField(null=True, blank=True)
    answers = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

class Staff(models.Model):
    ROLE_CHOICES = [
        ('teacher', 'معلم'),
        ('admin', 'إداري'),
        ('principal', 'مدير'),
    ]
    school = models.ForeignKey(School, on_delete=models.CASCADE, null=True, blank=True)
    name = models.CharField(max_length=100)
    staff_id = models.CharField(max_length=20, unique=True)
    mobile = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='teacher')

    def __str__(self):
        return f"{self.name} - {self.get_role_display()}"