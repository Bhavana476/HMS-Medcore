from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from rest_framework.test import APIClient
from .models import Patient


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class SignupTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client=APIClient()
        self.data=dict(username='newpatient',first_name='New',last_name='Patient',
            email='new@example.test',phone='9876543210',password='Fresh-care-829!')

    def test_signup_creates_linked_patient_and_can_sign_in(self):
        response=self.client.post('/api/signup/',self.data)
        self.assertEqual(response.status_code,201)
        user=get_user_model().objects.get(username=self.data['username'])
        self.assertEqual(user.role,'PATIENT')
        self.assertTrue(user.check_password(self.data['password']))
        profile=Patient.objects.get(user=user)
        self.assertEqual(profile.email,self.data['email'])
        response=self.client.post('/api/login/',dict(username=user.username,password=self.data['password']))
        self.assertEqual(response.status_code,200)
        self.client.credentials(HTTP_AUTHORIZATION='Bearer '+response.data['access'])
        self.assertEqual(self.client.get('/api/me/').data['role'],'PATIENT')

    def test_rejects_staff_role_and_weak_password(self):
        for role in ['ADMIN','DOCTOR']:
            self.assertEqual(self.client.post('/api/signup/',dict(self.data,role=role)).status_code,400)
        self.assertEqual(self.client.post('/api/signup/',dict(self.data,password='password')).status_code,400)
        self.assertFalse(get_user_model().objects.exists())
        self.assertFalse(Patient.objects.exists())

    def test_duplicate_username_does_not_create_another_profile(self):
        self.assertEqual(self.client.post('/api/signup/',self.data).status_code,201)
        self.assertEqual(self.client.post('/api/signup/',self.data).status_code,400)
        self.assertEqual(Patient.objects.count(),1)

    def test_admin_registration_remains_protected(self):
        self.assertEqual(self.client.post('/api/register/',dict(self.data,role='ADMIN')).status_code,401)
