from django.urls import path
from . import views

urlpatterns = [
    path('emissions/monthly/', views.monthly_emissions),
    path('incidents/summary/', views.incident_summary),
    path('data-quality/', views.data_quality),
]