from django.db import models
from django.contrib.auth.models import User

import uuid


class School(models.Model):
    name = models.CharField(max_length=200)
    teacher = models.ForeignKey(User, on_delete=models.CASCADE)

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