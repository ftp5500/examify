# نظام الاختبارات الآلي (Examify)

## تشغيل المشروع

### Backend (Django)
```bash
cd examify
python -m venv .venv
source .venv/bin/activate       # Mac/Linux
# أو: .venv\Scripts\activate   # Windows
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

### Frontend (Next.js)
```bash
cd examify-frontend
npm install
npm run dev
```

### الروابط
- Frontend: http://localhost:3000
- Backend API: http://localhost:8000
- Django Admin: http://localhost:8000/admin