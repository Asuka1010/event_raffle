from django.urls import path
from . import views


app_name = "raffle"


urlpatterns = [
    path("register/", views.register_view, name="register"),
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("settings/", views.settings_view, name="settings"),
    path("events/", views.events_list_view, name="events"),
    path("events/<int:run_id>/", views.event_detail_view, name="event_detail"),
    path("historical/edit/", views.edit_historical_view, name="edit_historical"),
    path("", views.upload_view, name="upload"),
    path("config/", views.config_view, name="config"),
    path("database/", views.database_view, name="database"),
    path("selection/", views.selection_view, name="selection"),
    path("results/", views.results_view, name="results"),
    path("download/selected/", views.download_selected_csv, name="download_selected"),
    path("download/ranking/", views.download_ranking_csv, name="download_ranking"),
    path("download/database/", views.download_updated_database_csv, name="download_database"),
]


