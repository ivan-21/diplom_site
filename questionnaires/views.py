from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django import forms
from django.db import transaction

from .models import Questionnaire, QuestionnaireStep, Question, Submission, Answer


def build_step_form(step: QuestionnaireStep, draft_answers: dict):
    fields = {}

    for q in step.questions.prefetch_related("options").all():
        initial = draft_answers.get(q.slug)

        common = {"label": q.label, "required": q.required, "help_text": q.help_text, "initial": initial}

        if q.field_type == Question.TEXT:
            fields[q.slug] = forms.CharField(**common)
        elif q.field_type == Question.NUMBER:
            fields[q.slug] = forms.DecimalField(**common)
        elif q.field_type == Question.CHECKBOX:
            fields[q.slug] = forms.BooleanField(required=False, label=q.label, help_text=q.help_text, initial=bool(initial))
        elif q.field_type == Question.SELECT:
            choices = [(opt.value, opt.label) for opt in q.options.all()]
            fields[q.slug] = forms.ChoiceField(choices=[("", "— выберите —")] + choices, **common)

        # если у тебя есть ветвление:
        fields[q.slug].depends_on = q.depends_on.slug if getattr(q, "depends_on", None) else ""
        fields[q.slug].depends_value = q.depends_value if getattr(q, "depends_value", "") else ""

    DynamicForm = type("DynamicForm", (forms.Form,), fields)
    return DynamicForm


@login_required
def questionnaire_list(request):
    items = Questionnaire.objects.filter(is_active=True).order_by("title")
    return render(request, "questionnaires/list.html", {"items": items})


@login_required
def start_questionnaire(request, slug):
    q = get_object_or_404(Questionnaire, slug=slug, is_active=True)
    submission = Submission.objects.create(questionnaire=q, user=request.user)

    first_step = q.steps.order_by("order").first()
    if not first_step:
        return render(request, "questionnaires/error.html", {"message": "У опросника нет шагов."})

    return redirect("fill_step", submission_id=submission.id, step_order=first_step.order)


@login_required
def fill_step(request, slug, step_order):
    q = get_object_or_404(Questionnaire, slug=slug, is_active=True)
    step = get_object_or_404(QuestionnaireStep, questionnaire=q, order=step_order)

    draft = _get_draft(request, slug) or {"answers": {}}
    draft_answers = draft.get("answers", {})

    FormClass = build_step_form(step, draft_answers)
    form = FormClass(request.POST or None)

    if request.method == "POST" and form.is_valid():
        for k, v in form.cleaned_data.items():
            if v is None:
                draft_answers[k] = ""
            else:
                draft_answers[k] = str(v)  

        draft["answers"] = draft_answers
        _set_draft(request, slug, draft)

        next_step = q.steps.filter(order__gt=step.order).order_by("order").first()
        if next_step:
            return redirect("fill_step", slug=slug, step_order=next_step.order)

        return redirect("submit_questionnaire", slug=slug)

    return render(request, "questionnaires/fill_step.html", {"questionnaire": q, "step": step, "form": form, "draft_answers": draft_answers})


@login_required
def start_questionnaire(request, slug):
    q = get_object_or_404(Questionnaire, slug=slug, is_active=True)

    if not _get_draft(request, slug):
        _set_draft(request, slug, {"answers": {}})

    first_step = q.steps.order_by("order").first()
    if not first_step:
        return render(request, "questionnaires/error.html", {"message": "У опросника нет шагов."})

    return redirect("fill_step", slug=slug, step_order=first_step.order)

@login_required
def submit_questionnaire(request, slug):
    q = get_object_or_404(Questionnaire, slug=slug, is_active=True)
    draft = _get_draft(request, slug) or {}
    draft_answers = (draft.get("answers") or {})

    if request.method == "POST":
        with transaction.atomic():
            submission = Submission.objects.create(
                questionnaire=q,
                user=request.user,
                status=Submission.SUBMITTED,
                submitted_at=timezone.now(),
            )

            questions = Question.objects.filter(step__questionnaire=q).select_related("step")
            q_by_slug = {qq.slug: qq for qq in questions}

            for slug_key, raw_value in draft_answers.items():
                qq = q_by_slug.get(slug_key)
                if not qq:
                    continue

                if raw_value == "" or raw_value is None:
                    continue

                ans = Answer(submission=submission, question=qq)

                if qq.field_type == Question.NUMBER:
                    try:
                        ans.value_number = raw_value if raw_value != "" else None
                    except:
                        ans.value_number = None
                elif qq.field_type == Question.CHECKBOX:
                    ans.value_bool = (raw_value == "True" or raw_value == "true" or raw_value == "1")
                else:
                    ans.value_text = raw_value

                ans.save()

                ans.save()

        _clear_draft(request, slug)

        return render(request, "questionnaires/thanks.html", {"submission": submission})

    return render(request, "questionnaires/submit.html", {"questionnaire": q, "draft_answers": draft_answers})

from django.contrib.admin.views.decorators import staff_member_required

@staff_member_required
def manager_list(request):
    items = Submission.objects.exclude(status=Submission.DRAFT).order_by("-created_at")
    count_total     = items.count()
    count_submitted = items.filter(status=Submission.SUBMITTED).count()
    count_in_review = items.filter(status=Submission.IN_REVIEW).count()
    count_processed = items.filter(status=Submission.PROCESSED).count()
    return render(request, "manager/list.html", {
        "items": items,
        "count_total": count_total,
        "count_submitted": count_submitted,
        "count_in_review": count_in_review,
        "count_processed": count_processed,
    })

@staff_member_required
def manager_set_status(request, submission_id):
    if request.method == "POST":
        sub = get_object_or_404(Submission, id=submission_id)
        new_status = request.POST.get("status")
        allowed = [Submission.IN_REVIEW, Submission.PROCESSED, Submission.REJECTED]
        if new_status in allowed:
            sub.status = new_status
            sub.save()
    return redirect("manager_detail", submission_id=submission_id)

@staff_member_required
def manager_detail(request, submission_id):
    sub = get_object_or_404(Submission, id=submission_id)
    answers = sub.answers.select_related("question").prefetch_related("question__options").all()
    return render(request, "manager/detail.html", {"sub": sub, "answers": answers})

def _draft_key(slug: str) -> str:
    return f"draft_q_{slug}"

def _get_draft(request, slug: str) -> dict:
    return request.session.get(_draft_key(slug), {})

def _set_draft(request, slug: str, data: dict) -> None:
    request.session[_draft_key(slug)] = data
    request.session.modified = True

def _clear_draft(request, slug: str) -> None:
    request.session.pop(_draft_key(slug), None)
    request.session.modified = True