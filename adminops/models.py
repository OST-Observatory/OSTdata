from django.conf import settings
from django.db import models


class AuditLogEntry(models.Model):
    """
    Explicit audit events for actions not covered by django-simple-history
    (ACL, banner, jobs, solar images, M2M tag changes, …).
    """

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    model_type = models.CharField(max_length=32, db_index=True)
    model_label = models.CharField(max_length=64)
    action = models.CharField(max_length=16)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='audit_log_entries',
    )
    instance_id = models.BigIntegerField(null=True, blank=True)
    entity_label = models.CharField(max_length=255)
    entity_path = models.CharField(max_length=255, blank=True, default='')
    change_reason = models.CharField(max_length=100, blank=True, default='')
    is_batch = models.BooleanField(default=False)
    batch_count = models.PositiveIntegerField(default=1)
    changes = models.JSONField(default=list, blank=True)
    summary = models.TextField(blank=True, default='')

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['-created_at', 'model_type']),
        ]

    def __str__(self):
        return f'{self.model_type} {self.action} @ {self.created_at}'
