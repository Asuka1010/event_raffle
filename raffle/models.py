from django.db import models
from django.contrib.auth import get_user_model


class Student(models.Model):
    """Represents a student and their attendance history summary.

    Note: The raffle algorithm primarily operates on uploaded CSV data stored in
    session. These models are provided to persist core entities for future
    enhancements (e.g., storing historical runs) and to satisfy the requirement
    to add needed backend models.
    """

    user_id = models.CharField(max_length=64, blank=True, null=True)
    name = models.CharField(max_length=255)
    email = models.EmailField(unique=True)
    student_class = models.CharField(max_length=255, blank=True, null=True)

    num_absences = models.PositiveIntegerField(default=0)
    num_late_arrivals = models.PositiveIntegerField(default=0)
    num_events_attended = models.PositiveIntegerField(default=0)
    last_attended_date = models.DateField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"{self.name} <{self.email}>"


class Event(models.Model):
    """Represents an event for which a raffle can be run."""

    name = models.CharField(max_length=255)
    capacity = models.PositiveIntegerField()
    selection_date = models.DateField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.name


class HistoricalData(models.Model):
    """Stores the latest historical database CSV per user."""

    user = models.OneToOneField(get_user_model(), on_delete=models.CASCADE, related_name="historical_data")
    csv_text = models.TextField()
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"HistoricalData<{self.user_id}>"


class RaffleRun(models.Model):
    """Stores each event run and its datasets for later review."""

    user = models.ForeignKey(get_user_model(), on_delete=models.CASCADE, related_name="raffle_runs")
    name = models.CharField(max_length=255)
    date = models.DateField(blank=True, null=True)
    capacity = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    signup_csv_text = models.TextField(blank=True, default="")
    selected_csv_text = models.TextField(blank=True, default="")
    eligible_csv_text = models.TextField(blank=True, default="")

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"{self.name} ({self.date})"

