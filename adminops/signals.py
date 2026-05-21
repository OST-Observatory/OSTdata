"""
Audit log hooks for M2M tag changes on Object and ObservationRun.
"""
from django.db.models.signals import m2m_changed
from django.dispatch import receiver

from adminops.audit_events import get_audit_user, log_audit_event
from obs_run.models import ObservationRun
from objects.models import Object


def _log_tag_m2m(instance, action: str, pk_set, *, model_type: str, entity_path: str):
    if action not in ('post_add', 'post_remove', 'post_clear'):
        return
    user = get_audit_user()
    if user is None:
        return

    if action == 'post_clear':
        verb = 'cleared'
        label = getattr(instance, 'name', None) or f'#{instance.pk}'
        changes = [{'field': 'tags', 'old': '(all)', 'new': None}]
    elif action == 'post_add':
        verb = 'added'
        label = getattr(instance, 'name', None) or f'#{instance.pk}'
        changes = [{'field': 'tags', 'old': None, 'new': sorted(pk_set)}]
    else:
        verb = 'removed'
        label = getattr(instance, 'name', None) or f'#{instance.pk}'
        changes = [{'field': 'tags', 'old': sorted(pk_set), 'new': None}]

    log_audit_event(
        model_type='tag_assignment',
        action='updated',
        entity_label=f'{label} ({verb} tags)',
        entity_path=entity_path,
        change_reason=f'api:{model_type}_tags_{verb}',
        user=user,
        instance_id=instance.pk,
        changes=changes,
        summary=f'Tags {verb} on {model_type}',
    )


@receiver(m2m_changed, sender=Object.tags.through)
def audit_object_tags_changed(sender, instance, action, pk_set, **kwargs):
    if not isinstance(instance, Object):
        return
    _log_tag_m2m(instance, action, pk_set, model_type='object', entity_path=f'/objects/{instance.pk}')


@receiver(m2m_changed, sender=ObservationRun.tags.through)
def audit_run_tags_changed(sender, instance, action, pk_set, **kwargs):
    if not isinstance(instance, ObservationRun):
        return
    _log_tag_m2m(
        instance,
        action,
        pk_set,
        model_type='observation_run',
        entity_path=f'/observation-runs/{instance.pk}',
    )
