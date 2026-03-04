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

admin.site.register(QuestionnaireStep)
admin.site.register(Submission)
admin.site.register(Answer)