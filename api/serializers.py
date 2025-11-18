# api/serializers.py

from rest_framework import serializers
from django.contrib.auth.models import User
from students.models import UserProfile # Import UserProfile to get role

class UserSerializer(serializers.ModelSerializer):
    """
    Serializer for the User model, including the role from the profile.
    """
    # Read the role from the related UserProfile model
    role = serializers.CharField(source='profile.role', read_only=True)

    class Meta:
        model = User
        # Include fields needed for the dropdown in ManageClasses.tsx
        fields = ["id", "username", "first_name", "last_name", "email", "role"]

# You can also add your RegisterSerializer here if you want to keep
# all api-related serializers in one file.

# class RegisterSerializer(serializers.ModelSerializer):
#     password = serializers.CharField(write_only=True)
#
#     class Meta:
#         model = User
#         fields = ("username", "email", "password")
#
#     def create(self, validated_data):
#         user = User.objects.create_user(
#             username=validated_data["username"],
#             email=validated_data["email"],
#             password=validated_data["password"]
#         )
#         # Note: This basic RegisterSerializer doesn't create the UserProfile.
#         # Your RegisterView handles profile creation separately.
#         return user