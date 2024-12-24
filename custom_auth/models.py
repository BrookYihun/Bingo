from django.db import models
from django.contrib.auth.base_user import BaseUserManager
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.utils.timezone import now
from datetime import timedelta

# Custom manager for handling user creation and authentication via phone number
class CustomUserManager(BaseUserManager):
    def create_user(self, phone_number, password=None, **extra_fields):
        if not phone_number:
            raise ValueError('The Phone Number field must be set')
        user = self.model(phone_number=phone_number, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, phone_number, password=None, **extra_fields):

        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)

        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True.')

        return self.create_user(phone_number, password, **extra_fields)

# User model
class AbstractUser(AbstractBaseUser,PermissionsMixin):
    phone_number = models.CharField(max_length=15, unique=True)
    name = models.CharField(max_length=100)
    date_joined = models.DateTimeField(auto_now_add=True)
    is_verified = models.BooleanField(default=False)
    
    is_staff = models.BooleanField(default=False)  # Added for admin access
    is_active = models.BooleanField(default=True)  # Added for active users
    
    USERNAME_FIELD = 'phone_number'  # Use phone number for authentication
    REQUIRED_FIELDS = ['name']

    objects = CustomUserManager()

    def verify_otp(self):
        self.is_verified = True
        self.save()

    def __str__(self):
        return self.phone_number
    

class OTP(models.Model):
    phone_number = models.CharField(max_length=15)
    otp = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now_add=True)

    def is_expired(self):
        return now() > self.created_at + timedelta(seconds=300)  # 5 minutes expiry


# User model with specific fields
class User(AbstractUser):
    wallet = models.DecimalField(max_digits=10, decimal_places=2,default=0)

    def __str__(self):
        return self.name

# Cashier model with its own specific fields
class Cashier(AbstractUser):
    location = models.CharField(max_length=15, unique=True)

    def __str__(self):
        return f"Cashier: {self.name}"

