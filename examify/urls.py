from django.contrib import admin
from django.urls import path, include
from rest_framework_simplejwt.views import TokenRefreshView

from exams import views
from exams.views import CustomTokenObtainPairView

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include('exams.urls')),
    path('api/token/', CustomTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('api/exams/<int:exam_id>/clear/', views.clear_exam_sheets),
    path('api/admin/curricula/', views.curricula_list),
    path('api/admin/curricula/<int:curriculum_id>/', views.curriculum_detail),
    path('api/admin/curricula/<int:curriculum_id>/extract/', views.extract_questions_view),
    path('api/admin/curricula/<int:curriculum_id>/questions/', views.curriculum_questions),
    path('api/admin/questions/<int:question_id>/', views.question_admin_detail),
    path('api/bank/questions/', views.bank_questions),

]
