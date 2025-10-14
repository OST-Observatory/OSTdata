from rest_framework import serializers
from users.models import User


class UserSerializer(serializers.ModelSerializer):
    """
    Serializer for User model
    """
    class Meta:
        model = User
        fields = [
            'id',
            'username',
            'email',
            'first_name',
            'last_name',
            'is_active',
            'is_student',
            'is_superuser',
            'is_staff',
            'note',
        ]
        read_only_fields = ['id', 'is_active', 'is_superuser', 'is_staff'] 