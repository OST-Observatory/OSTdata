from django.db import models

############################################################################

class Tag(models.Model):
    """
    A tag that can be added to an object to facilitate grouping

    Multiple objects can have the same tag and multiple tags can be added to
    one object
    """
    #   Identifier
    name = models.CharField(max_length=75)

    #   Description
    description = models.TextField(default='')

    # Color as hex color value
    color = models.CharField(max_length=7, default='#8B0000')

    #   Bookkeeping
    added_on = models.DateTimeField(auto_now_add=True)
    last_modified = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']

    #   Representation of self
    def __str__(self):
        return "{}:{}".format(self.name, self.description)
