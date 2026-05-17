from rest_framework import serializers
from .models import Exam, Question, Student, AnswerSheet
from .models import School
class QuestionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Question
        fields = ['id', 'number', 'correct_answer']

class ExamSerializer(serializers.ModelSerializer):
    questions = QuestionSerializer(many=True, read_only=True)

    class Meta:
        model = Exam
        fields = ['id', 'title', 'subject', 'num_questions', 'num_choices', 'questions', 'created_at']

class StudentSerializer(serializers.ModelSerializer):
    school_name = serializers.CharField(source='school.name', read_only=True)

    class Meta:
        model = Student
        fields = ['id', 'name', 'student_id', 'grade', 'section', 'school', 'school_name']

class AnswerSheetSerializer(serializers.ModelSerializer):
    class Meta:
        model = AnswerSheet
        fields = ['id', 'exam', 'student', 'barcode', 'status', 'score', 'answers']



class SchoolSerializer(serializers.ModelSerializer):
        class Meta:
            model = School
            fields = ['id', 'name']

