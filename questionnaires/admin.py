from django.contrib import admin
from .models import Questionnaire, QuestionnaireStep, Question, QuestionOption, Submission, Answer

class QuestionOptionInline(admin.TabularInline):
    model = QuestionOption
    extra = 1

@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ("id", "slug", "label", "field_type", "required", "step", "depends_on", "depends_value")
    inlines = [QuestionOptionInline]

@admin.register(Questionnaire)
class QuestionnaireAdmin(admin.ModelAdmin):
    list_display = ("title", "slug", "is_active")

@admin.register(Submission)
class SubmissionAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "questionnaire", "status", "created_at", "submitted_at")
    list_filter = ("status", "questionnaire")
    search_fields = ("user__username",)

admin.site.register(QuestionnaireStep)
admin.site.register(Answer)