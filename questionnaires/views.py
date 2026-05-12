from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django import forms
from django.db import transaction
from django.views.decorators.http import require_POST
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

        fields[q.slug].depends_on = q.depends_on.slug if getattr(q, "depends_on", None) else ""
        fields[q.slug].depends_value = q.depends_value if getattr(q, "depends_value", "") else ""

    DynamicForm = type("DynamicForm", (forms.Form,), fields)
    return DynamicForm


@login_required
def questionnaire_list(request):
    items = Questionnaire.objects.filter(is_active=True).order_by("title")
    return render(request, "questionnaires/list.html", {"items": items})


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

    answers_dict = {}
    for a in answers:
        if a.value_number is not None:
            answers_dict[a.question.slug] = str(a.value_number)
        elif a.value_bool is not None:
            answers_dict[a.question.slug] = a.value_bool
        else:
            answers_dict[a.question.slug] = a.value_text

    from .services import (
        get_pump_recommendation,
        get_material_recommendation,
        get_cylinder_recommendation,
        get_fit_recommendation,
        get_flow_recommendation,
    )

    recommendation  = get_pump_recommendation(answers_dict)
    material_rec    = get_material_recommendation(answers_dict)

    # ── Читаем параметры менеджера из processed_data_json ──
    manager_data       = sub.processed_data_json or {}
    selected_pump      = manager_data.get("selected_pump_code", "")
    selected_size      = manager_data.get("selected_pump_size", "")
    selected_nkt       = manager_data.get("selected_nkt", "")
    selected_pump_full = manager_data.get("selected_pump_full", "")

    # Число качаний и коэффициент подачи, заданные менеджером
    custom_spm_raw = manager_data.get("custom_spm", None)
    custom_eta_raw = manager_data.get("custom_eta", None)

    try:
        custom_spm = float(custom_spm_raw) if custom_spm_raw not in (None, "") else None
    except (ValueError, TypeError):
        custom_spm = None

    try:
        custom_eta = float(custom_eta_raw) if custom_eta_raw not in (None, "") else None
    except (ValueError, TypeError):
        custom_eta = None

    # Пересчитываем flow_rec с пользовательскими параметрами
    flow_rec = get_flow_recommendation(answers_dict, custom_spm=custom_spm, custom_eta=custom_eta)

    # Подставляем выбранный насос для расчётов цилиндра и зазора
    calc_dict = dict(answers_dict)
    if selected_pump_full:
        calc_dict["pump_type_full"] = selected_pump_full
    if selected_size:
        calc_dict["inner_diameter"] = selected_size.split("-")[-1] if "-" in selected_size else selected_size

    cylinder_rec = get_cylinder_recommendation(calc_dict, flow_rec=flow_rec)
    fit_rec      = get_fit_recommendation(calc_dict)

    ALL_SIZES = {
        "RH": [
            {"size": "20-106", "nkt": "60.3"},
            {"size": "20-125", "nkt": "60.3"},
            {"size": "25-150", "nkt": "73.0"},
            {"size": "25-175", "nkt": "73.0"},
            {"size": "30-225", "nkt": "88.9"},
        ],
        "TH": [
            {"size": "20-125", "nkt": "60.3"},
            {"size": "20-175", "nkt": "60.3"},
            {"size": "25-225", "nkt": "73.0"},
            {"size": "30-275", "nkt": "88.9"},
        ],
    }

    nkt_raw = answers_dict.get("nkt_diameter", "")
    NKT_MAP = {
        "60.3": "60.3", "60,3": "60.3", "2 3/8": "60.3", "2-3/8": "60.3",
        "73.0": "73.0", "73,0": "73.0", "73":    "73.0", "2 7/8": "73.0",
        "88.9": "88.9", "88,9": "88.9", "88":    "88.9", "3 1/2": "88.9",
    }
    nkt_normalized = NKT_MAP.get(str(nkt_raw).strip(), "")

    if nkt_normalized:
        rh_sizes = [s for s in ALL_SIZES["RH"] if s["nkt"] == nkt_normalized]
        th_sizes = [s for s in ALL_SIZES["TH"] if s["nkt"] == nkt_normalized]
    else:
        rh_sizes = ALL_SIZES["RH"]
        th_sizes = ALL_SIZES["TH"]

    return render(request, "manager/detail.html", {
        "sub":             sub,
        "answers":         answers,
        "recommendation":  recommendation,
        "material_rec":    material_rec,
        "cylinder_rec":    cylinder_rec,
        "fit_rec":         fit_rec,
        "selected_pump":   selected_pump,
        "selected_size":   selected_size,
        "selected_nkt":    selected_nkt,
        "selected_pump_full": selected_pump_full,
        "rh_sizes":        rh_sizes,
        "th_sizes":        th_sizes,
        "nkt_normalized":  nkt_normalized,
        "flow_rec":        flow_rec,
        # параметры менеджера для отображения в форме
        "custom_spm":      custom_spm,
        "custom_eta":      custom_eta,
    })


@staff_member_required
@require_POST
def manager_select_pump(request, submission_id):
    sub        = get_object_or_404(Submission, id=submission_id)
    pump_code  = request.POST.get("pump_code", "")
    size       = request.POST.get("pump_size", "")
    nkt        = request.POST.get("nkt_diameter", "")

    if pump_code in ("RHA", "RHB", "RHT"):
        pump_type_full = f"{size} {pump_code}M"
    elif pump_code == "TH":
        pump_type_full = f"{size} THM"
    else:
        pump_type_full = ""

    data = sub.processed_data_json or {}
    data["selected_pump_code"] = pump_code
    data["selected_pump_size"] = size
    data["selected_nkt"]       = nkt
    data["selected_pump_full"] = pump_type_full
    sub.processed_data_json    = data
    sub.save()

    return redirect("manager_detail", submission_id=submission_id)


@staff_member_required
@require_POST
def manager_update_flow_params(request, submission_id):
    """Сохраняет число качаний и коэффициент подачи, заданные менеджером."""
    sub = get_object_or_404(Submission, id=submission_id)

    spm_raw = request.POST.get("custom_spm", "").strip()
    eta_raw = request.POST.get("custom_eta", "").strip()

    data = sub.processed_data_json or {}

    # Число качаний
    if spm_raw == "":
        data.pop("custom_spm", None)          # сброс → автоподбор
    else:
        try:
            spm_val = float(spm_raw)
            if 1 <= spm_val <= 30:
                data["custom_spm"] = spm_val
        except ValueError:
            pass

    # Коэффициент подачи
    if eta_raw == "":
        data.pop("custom_eta", None)           # сброс → η = 1.0
    else:
        try:
            eta_val = float(eta_raw.replace(",", "."))
            if 0.01 <= eta_val <= 1.0:
                data["custom_eta"] = eta_val
        except ValueError:
            pass

    sub.processed_data_json = data
    sub.save()

    return redirect("manager_detail", submission_id=submission_id)


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

def handbook(request):
    return render(request, "questionnaires/handbook.html")

@staff_member_required
def schema_view(request):
    return render(request, "manager/schema.html")