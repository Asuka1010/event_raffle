from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import get_user_model


class UploadForm(forms.Form):
    historical_csv = forms.FileField(allow_empty_file=False, required=False, label="Historical Database CSV")


class ConfigForm(forms.Form):
    event_name = forms.CharField(max_length=255, required=True, label="Event Name")
    event_capacity = forms.IntegerField(min_value=1, required=True, label="Event Capacity")
    event_date = forms.DateField(required=True, label="Event Date", widget=forms.DateInput(attrs={"type": "date"}))
    signup_csv = forms.FileField(allow_empty_file=False, required=True, label="Sign-up CSV")
    event_cutoff = forms.DateTimeField(required=False, label="Registration Cutoff (optional)", widget=forms.DateTimeInput(attrs={"type": "datetime-local"}))


class RegistrationForm(UserCreationForm):
    email = forms.EmailField(required=True)
    first_name = forms.CharField(max_length=150, required=True, label="First name")
    last_name = forms.CharField(max_length=150, required=False, label="Last name")

    class Meta(UserCreationForm.Meta):
        model = get_user_model()
        fields = ("username", "email", "first_name", "last_name")


class UserSettingsForm(forms.ModelForm):
    class Meta:
        model = get_user_model()
        fields = ("first_name", "last_name")


