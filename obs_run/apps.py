from django.apps import AppConfig
from django.db.models.signals import post_delete, m2m_changed


class RunConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'obs_run'

    def ready(self):
        """Register signal handlers when the app is ready."""
        from .models import DataFile
        from objects.models import Object
        
        # Signal handler for DataFile deletion
        def handle_datafile_deleted(sender, instance, **kwargs):
            """Update photometry/spectroscopy flags when a DataFile is deleted."""
            try:
                # Import here to avoid circular import and django.setup() issues
                from utilities import update_observation_run_photometry_spectroscopy, update_object_photometry_spectroscopy
                
                # Store observation_run and associated objects before deletion
                observation_run = instance.observation_run
                # Get associated objects - in post_delete, M2M relations should still be accessible
                # but we'll use a safe approach by getting the PKs first
                associated_object_pks = list(instance.object_set.values_list('pk', flat=True))
                
                # Update observation run if it exists
                if observation_run:
                    update_observation_run_photometry_spectroscopy(observation_run)
                
                # Update all associated objects by their PKs
                for obj_pk in associated_object_pks:
                    try:
                        obj = Object.objects.get(pk=obj_pk)
                        update_object_photometry_spectroscopy(obj)
                    except Object.DoesNotExist:
                        # Object might have been deleted, skip
                        pass
            except Exception as e:
                import logging
                logger = logging.getLogger(__name__)
                logger.warning(f'Error updating photometry/spectroscopy after DataFile deletion: {e}', exc_info=True)
        
        # Signal handler for M2M changes (when DataFile is added/removed from Object)
        def handle_object_datafiles_changed(sender, instance, action, pk_set, **kwargs):
            """Update photometry/spectroscopy flags when DataFiles are added/removed from an Object."""
            # Only handle post_add and post_remove actions
            if action not in ('post_add', 'post_remove', 'post_clear'):
                return
            
            try:
                # Import here to avoid circular import and django.setup() issues
                from utilities import update_observation_run_photometry_spectroscopy, update_object_photometry_spectroscopy
                
                update_object_photometry_spectroscopy(instance)
                
                # Also update observation runs for the affected DataFiles
                if pk_set:
                    from .models import DataFile
                    for df_pk in pk_set:
                        try:
                            df = DataFile.objects.get(pk=df_pk)
                            if df.observation_run:
                                update_observation_run_photometry_spectroscopy(df.observation_run)
                        except DataFile.DoesNotExist:
                            pass
            except Exception as e:
                import logging
                logger = logging.getLogger(__name__)
                logger.warning(f'Error updating photometry/spectroscopy after Object-DataFile M2M change: {e}', exc_info=True)
        
        # Register signals
        post_delete.connect(handle_datafile_deleted, sender=DataFile)
        m2m_changed.connect(handle_object_datafiles_changed, sender=Object.datafiles.through)
