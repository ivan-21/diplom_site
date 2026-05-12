from django.urls import path
from . import views

urlpatterns = [
    path("", views.questionnaire_list, name="questionnaire_list"),
    path("<slug:slug>/start/", views.start_questionnaire, name="start_questionnaire"),
    path("<slug:slug>/step/<int:step_order>/", views.fill_step, name="fill_step"),
    path("<slug:slug>/submit/", views.submit_questionnaire, name="submit_questionnaire"),

    path("manager/submissions/", views.manager_list, name="manager_list"),
    path("manager/submissions/<int:submission_id>/", views.manager_detail, name="manager_detail"),
    path("manager/submissions/<int:submission_id>/set-status/", views.manager_set_status, name="manager_set_status"),
    path("handbook/", views.handbook, name="handbook"),
    path("manager/submissions/<int:submission_id>/select-pump/", views.manager_select_pump, name="manager_select_pump"),
    path("manager/submissions/<int:submission_id>/update-flow-params/", views.manager_update_flow_params, name="manager_update_flow_params"),
    path("manager/schema/", views.schema_view, name="schema"),
]