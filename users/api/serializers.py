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
            'is_supervisor',
            'is_superuser',
            'is_staff',
            'note',
        ]
        read_only_fields = ['id', 'is_active', 'is_superuser', 'is_staff']


class UserAdminSerializer(serializers.ModelSerializer):
    """
    Admin serializer: allows managing activation and roles.
    """
    source = serializers.SerializerMethodField()
    last_login = serializers.DateTimeField(read_only=True)

    def get_source(self, obj: User) -> str:
        try:
            # Heuristic: LDAP-provisioned users typically have an unusable password
            return 'LDAP' if not obj.has_usable_password() else 'local'
        except Exception:
            return 'local'

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
            'is_supervisor',
            'is_superuser',
            'is_staff',
            'note',
            'source',
            'last_login',
        ]
        read_only_fields = ['id', 'username', 'is_superuser']