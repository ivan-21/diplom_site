from django.conf import settings
from django.db import models

class Questionnaire(models.Model):
    slug = models.SlugField(unique=True)
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.title

class QuestionnaireStep(models.Model):
    questionnaire = models.ForeignKey(Questionnaire, on_delete=models.CASCADE, related_name="steps")
    order = models.PositiveIntegerField()
    title = models.CharField(max_length=200, blank=True)

    class Meta:
        unique_together = ("questionnaire", "order")
        ordering = ["order"]

    def __str__(self):
        return f"{self.questionnaire.slug} / step {self.order}"

class Question(models.Model):
    TEXT = "text"
    NUMBER = "number"
    SELECT = "select"
    CHECKBOX = "checkbox"
    TYPES = [
        (TEXT, "Text"),
        (NUMBER, "Number"),
        (SELECT, "Select"),
        (CHECKBOX, "Checkbox"),
    ]

    step = models.ForeignKey(QuestionnaireStep, on_delete=models.CASCADE, related_name="questions")
    slug = models.SlugField()
    label = models.CharField(max_length=300)
    help_text = models.CharField(max_length=400, blank=True)
    field_type = models.CharField(max_length=20, choices=TYPES, default=TEXT)
    required = models.BooleanField(default=False)

    class Meta:
        unique_together = ("step", "slug")

    def __str__(self):
        return f"{self.step} :: {self.slug}"
    
    depends_on = models.ForeignKey(
    "self",
    null=True, blank=True,
    on_delete=models.SET_NULL,
    related_name="dependent_questions",
    help_text="Показывать вопрос только если выполнено условие зависимости"
    )
    depends_value = models.CharField(
        max_length=120,
        blank=True,
        help_text="Какое значение должно быть у depends_on (например: sand)"
    )
    

class QuestionOption(models.Model):
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name="options")
    value = models.CharField(max_length=120)
    label = models.CharField(max_length=200)

class Submission(models.Model):
    DRAFT      = "draft"
    SUBMITTED  = "submitted"
    IN_REVIEW  = "in_review"
    PROCESSED  = "processed"
    REJECTED   = "rejected"

    STATUSES = [
        (DRAFT,     "Черновик"),
        (SUBMITTED, "Отправлено"),
        (IN_REVIEW, "На проверке"),
        (PROCESSED, "Обработано"),
        (REJECTED,  "Отклонено"),
    ]

    questionnaire      = models.ForeignKey(Questionnaire, on_delete=models.PROTECT, related_name="submissions")
    user               = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="submissions")
    status             = models.CharField(max_length=20, choices=STATUSES, default=DRAFT)
    created_at         = models.DateTimeField(auto_now_add=True)
    submitted_at       = models.DateTimeField(null=True, blank=True)
    processed_data_json = models.JSONField(default=dict, blank=True)
    issues_json        = models.JSONField(default=dict, blank=True)

class Answer(models.Model):
    submission = models.ForeignKey(Submission, on_delete=models.CASCADE, related_name="answers")
    question = models.ForeignKey(Question, on_delete=models.PROTECT)

    value_text = models.TextField(blank=True, default="")
    value_number = models.DecimalField(max_digits=18, decimal_places=6, null=True, blank=True)
    value_bool = models.BooleanField(null=True, blank=True)

    class Meta:
        unique_together = ("submission", "question")