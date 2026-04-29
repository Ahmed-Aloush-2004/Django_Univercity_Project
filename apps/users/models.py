from django.contrib.auth.models import AbstractUser
from django.db import models

class User(AbstractUser):
    # We use email as the primary identifier (username)
    email = models.EmailField(unique=True)
    username = models.CharField(max_length=150, unique=True, blank=True, null=False)

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username']

    def __str__(self):
        return self.email