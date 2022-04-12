
from django import forms

from tags.models import Tag

class UploadNightForm(forms.Form):
    #   Target name
    main_id = forms.CharField(max_length=20, required=True)

    #   Download from Simbad/Vizier?
    is_public = forms.BooleanField(initial=True, required=False)

    #   Tags
    tags = forms.ModelMultipleChoiceField(
        label='Tags',
        queryset=Tag.objects.all(),
        widget=forms.CheckboxSelectMultiple,
        required=False,
        )
