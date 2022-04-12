from django.db import models

from django.conf import settings

from users.models import get_sentinel_user

from tags.models import Tag

############################################################################

class Night(models.Model):
    #   Name
    name = models.CharField(max_length=200)

    #   Rights management
    is_public = models.BooleanField(default=True)

    readonly_users  = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name='readonly_night',
        blank=True,
    )
    readwrite_users = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name='readwrite_night',
        blank=True,
    )
    managers        = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name='managed_night',
        blank=True,
    )

    #   Data reduction status
    PARTLY_REDUCED   = 'PR'
    FULLY_REDUCED    = 'FR'
    REDUCTION_FAILED = 'ER'
    NEW              = 'NE'
    REDUCTION_STATUS_CHOICES = (
        (PARTLY_REDUCED,   'Partly reduced'),
        (FULLY_REDUCED,    'Fully reduced'),
        (REDUCTION_FAILED, 'Reduction error'),
        (NEW,              'New')
    )
    reduction_status = models.CharField(
        max_length=2,
        choices=REDUCTION_STATUS_CHOICES,
        default=NEW,
    )

    #   Field to add notes etc.
    note = models.TextField(default='', blank=True)

    #   Tags
    tags = models.ManyToManyField(Tag, related_name='nights', blank=True)

    #   Bookkeeping
    added_on      = models.DateTimeField(auto_now_add=True)
    last_modified = models.DateTimeField(auto_now=True)
    added_by      = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET(get_sentinel_user),
        null=True,
        related_name='added_night',
    )

    #   Representation of self
    def __str__(self):
        return self.name
