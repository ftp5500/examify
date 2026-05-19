from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.db import transaction
from .models import UserProfile, School, Student, Exam, Question, AnswerSheet


class SchoolSerializer(serializers.ModelSerializer):
    class Meta:
        model = School
        fields = ['id', 'name', 'education_directorate', 'created_at']
        read_only_fields = ['id', 'created_at']


class StudentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Student
        fields = ['id', 'school', 'name', 'student_id', 'grade', 'section']


class QuestionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Question
        fields = ['id', 'exam', 'number', 'correct_answer']


class ExamSerializer(serializers.ModelSerializer):
    questions = QuestionSerializer(many=True, read_only=True)

    class Meta:
        model = Exam
        fields = [
            'id', 'title', 'subject', 'grade', 'section', 'sections_list',
            'school', 'academic_year', 'semester', 'period',
            'exam_date', 'num_questions', 'num_choices', 'questions',
        ]


class AnswerSheetSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source='student.name', read_only=True)
    student_id_number = serializers.CharField(source='student.student_id', read_only=True)

    class Meta:
        model = AnswerSheet
        fields = [
            'id', 'exam', 'student', 'student_name', 'student_id_number',
            'barcode', 'status', 'score', 'answers',
        ]


class PrincipalRegistrationSerializer(serializers.Serializer):
    full_name = serializers.CharField(max_length=200)
    national_id = serializers.CharField(max_length=20)
    email = serializers.EmailField()
    mobile = serializers.CharField(max_length=20, required=False, allow_blank=True)
    password = serializers.CharField(write_only=True, min_length=8)
    school_name = serializers.CharField(max_length=200)
    education_directorate = serializers.CharField(max_length=200, required=False, allow_blank=True)

    def validate_national_id(self, value):
        value = value.strip()
        if not value.isdigit() or len(value) != 10:
            raise serializers.ValidationError("رقم الهوية يجب أن يكون 10 أرقام")
        if UserProfile.objects.filter(national_id=value).exists():
            raise serializers.ValidationError("رقم الهوية مسجّل مسبقاً")
        if User.objects.filter(username=value).exists():
            raise serializers.ValidationError("رقم الهوية مسجّل مسبقاً")
        return value

    def validate_email(self, value):
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError("البريد الإلكتروني مسجّل مسبقاً")
        return value

    def validate_password(self, value):
        validate_password(value)
        return value

    def validate_mobile(self, value):
        if not value:
            return ''
        value = value.strip().replace(' ', '').replace('-', '')
        if value.startswith('00966'):
            value = '+966' + value[5:]
        elif value.startswith('966'):
            value = '+' + value
        elif value.startswith('05'):
            value = '+966' + value[1:]
        elif value.startswith('5') and len(value) == 9:
            value = '+966' + value
        return value

    @transaction.atomic
    def create(self, validated_data):
        first_name = validated_data['full_name'].split()[0] if validated_data['full_name'] else ''
        user = User.objects.create_user(
            username=validated_data['national_id'],
            email=validated_data['email'],
            password=validated_data['password'],
            first_name=first_name,
        )
        UserProfile.objects.create(
            user=user,
            role='principal',
            full_name=validated_data['full_name'],
            national_id=validated_data['national_id'],
            mobile=validated_data.get('mobile', ''),
            must_change_password=False,
        )
        school = School.objects.create(
            name=validated_data['school_name'],
            principal=user,
            education_directorate=validated_data.get('education_directorate', ''),
        )
        return {'user': user, 'school': school}


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    def validate(self, attrs):
        data = super().validate(attrs)
        user = self.user
        profile = getattr(user, 'profile', None)

        data['user'] = {
            'id': user.id,
            'username': user.username,
            'email': user.email,
            'full_name': profile.full_name if profile else user.get_full_name(),
            'role': profile.role if profile else None,
            'must_change_password': profile.must_change_password if profile else False,
        }

        # إضافة بيانات المدرسة
        school = None
        if profile and profile.role == 'principal':
            school = user.managed_schools.first()
        elif profile and profile.role == 'teacher':
            school = user.teaching_schools.first()

        if school:
            data['school'] = {'id': school.id, 'name': school.name}

        return data