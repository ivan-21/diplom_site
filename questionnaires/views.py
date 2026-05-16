import json

from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django import forms
from django.db import transaction
from django.views.decorators.http import require_POST
from .models import Questionnaire, QuestionnaireStep, Question, Submission, Answer


# ══════════════════════════════════════════════════════════════════════════════
# СПРАВОЧНИК МОДИФИКАЦИЙ НАСОСОВ (Приложение Б)
# ══════════════════════════════════════════════════════════════════════════════

ALL_MODIFICATIONS = {
    # ── RH вставные, НКТ 60,3 мм (размеры 106 и 125) ─────────────────────
    "RH_60": {
        "nkt": "60.3",
        "label": "НКТ 60,3 мм (2 3/8\")",
        "sizes": {
            "20-106": [
                {"full": "20-106 RHAM",         "label": "RHAM",         "desc": "Верхнее мех. (API)"},
                {"full": "20-106 RHAM (ОСТ)",   "label": "RHAM (ОСТ)",  "desc": "Верхнее мех. (ОСТ)"},
                {"full": "20-106 RHBM",         "label": "RHBM",         "desc": "Нижнее мех."},
                {"full": "20-106 RHAC",         "label": "RHAC",         "desc": "Верхнее манж."},
                {"full": "20-106 RHBC",         "label": "RHBC",         "desc": "Нижнее манж."},
                {"full": "25-106 RHAM-T",       "label": "RHAM-T",       "desc": "Верхнее мех., увел. узел"},
                {"full": "25/20-106 RHM-T",     "label": "RHM-T",        "desc": "Узел перенесён вниз"},
                {"full": "25-106 RHAM (Конус)", "label": "RHAM (Конус)", "desc": "Спец. крепл. «Конус в конус»"},
                {"full": "25-106 RHAC",         "label": "RHAC",         "desc": "Верхнее манж., увел. узел"},
                {"full": "25-106 RHBC",         "label": "RHBC",         "desc": "Нижнее манж., увел. узел"},
            ],
            "20-125": [
                {"full": "20-125 RHAM",         "label": "RHAM",         "desc": "Верхнее мех. (API)"},
                {"full": "20-125 RHAM (ОСТ)",   "label": "RHAM (ОСТ)",  "desc": "Верхнее мех. (ОСТ)"},
                {"full": "20-125 RHBM",         "label": "RHBM",         "desc": "Нижнее мех."},
                {"full": "20-125 RHBC",         "label": "RHBC",         "desc": "Нижнее манж."},
                {"full": "25-125 RHAM-T",       "label": "RHAM-T",       "desc": "Верхнее мех., увел. узел"},
                {"full": "25/20-125 RHM-T",     "label": "RHM-T",        "desc": "Узел перенесён вниз"},
                {"full": "25-125 RHAM (Конус)", "label": "RHAM (Конус)", "desc": "Спец. крепл. «Конус в конус»"},
                {"full": "25-125 RHAC",         "label": "RHAC",         "desc": "Верхнее манж., увел. узел"},
                {"full": "25-125 RHBC",         "label": "RHBC",         "desc": "Нижнее манж., увел. узел"},
                {"full": "25-125 RHBM",         "label": "RHBM",         "desc": "Нижнее мех., увел. узел"},
            ],
        },
    },

    # ── RH вставные, НКТ 73,0 мм (размеры 150 и 175) ─────────────────────
    "RH_73": {
        "nkt": "73.0",
        "label": "НКТ 73,0 мм (2 7/8\")",
        "sizes": {
            "25-150": [
                {"full": "25-150 RHAM",         "label": "RHAM",         "desc": "Верхнее мех. (API)"},
                {"full": "25-150 RHAM (ОСТ)",   "label": "RHAM (ОСТ)",  "desc": "Верхнее мех. (ОСТ)"},
                {"full": "25-150 RHAM (Конус)", "label": "RHAM (Конус)", "desc": "Спец. крепл. «Конус в конус»"},
                {"full": "25-150 RHBM",         "label": "RHBM",         "desc": "Нижнее мех."},
                {"full": "25-150 RHAC",         "label": "RHAC",         "desc": "Верхнее манж."},
                {"full": "25-150 RHBC",         "label": "RHBC",         "desc": "Нижнее манж."},
                {"full": "25/20-150 RHM-T",     "label": "RHM-T",        "desc": "Узел перенесён вниз"},
                {"full": "20-150 RHBC",         "label": "RHBC (20)",     "desc": "НКТ 60,3 мм, без удлинителей"},
            ],
            "25-175": [
                {"full": "25-175 RHAM",         "label": "RHAM",         "desc": "Верхнее мех. (API)"},
                {"full": "25-175 RHAM (ОСТ)",   "label": "RHAM (ОСТ)",  "desc": "Верхнее мех. (ОСТ)"},
                {"full": "25-175 RHAM (Конус)", "label": "RHAM (Конус)", "desc": "Спец. крепл. «Конус в конус»"},
                {"full": "25-175 RHBM",         "label": "RHBM",         "desc": "Нижнее мех."},
                {"full": "25-175 RHAC",         "label": "RHAC",         "desc": "Верхнее манж."},
                {"full": "25-175 RHBC",         "label": "RHBC",         "desc": "Нижнее манж."},
                {"full": "25/20-175 RHM-T",     "label": "RHM-T",        "desc": "Узел перенесён вниз"},
                {"full": "25-175 RHTM",         "label": "RHTM",         "desc": "Нижн. мех. (ОСТ), подв. цил."},
            ],
        },
    },

    # ── RH вставные, НКТ 88,9 мм (размер 225) ────────────────────────────
    "RH_89": {
        "nkt": "88.9",
        "label": "НКТ 88,9 мм (3 1/2\")",
        "sizes": {
            "30-225": [
                {"full": "30-225 RHBM",      "label": "RHBM",        "desc": "Нижнее мех."},
                {"full": "30-225/150 RHBM",  "label": "RHBM (2-ст)", "desc": "Двухступенчатый"},
            ],
        },
    },

    # ── TH трубные, НКТ 48,3 мм (размер 125) ─────────────────────────────
    "TH_48": {
        "nkt": "48.3",
        "label": "НКТ 48,3 мм (1 7/8\")",
        "sizes": {
            "15-125": [
                {"full": "15-125 THM", "label": "THM", "desc": "Базовый трубный"},
            ],
        },
    },

    # ── TH трубные, НКТ 60,3 мм (размеры 125 и 175) ──────────────────────
    "TH_60": {
        "nkt": "60.3",
        "label": "НКТ 60,3 мм (2 3/8\")",
        "sizes": {
            "20-125": [
                {"full": "20-125 THM",      "label": "THM",          "desc": "Базовый трубный"},
                {"full": "25-125 THM",      "label": "THM (увел.)",  "desc": "Увеличенная верхняя муфта"},
                {"full": "25-125 THM-T",    "label": "THM-T",        "desc": "Неизвл. всасыв. клапан"},
                {"full": "25-125 THM-C",    "label": "THM-C",        "desc": "Клапан увел. размера + сбивной винт"},
                {"full": "25-125 THM-СЛ",   "label": "THM-СЛ",       "desc": "Клапан увел. + сбивной (СЛ)"},
                {"full": "25-106 THM-C",    "label": "THM-C (106)",  "desc": "Размер 106, клапан увел."},
                {"full": "25-106 THM-СЛ",   "label": "THM-СЛ (106)", "desc": "Размер 106, клапан + сбивной"},
            ],
            "20-175": [
                {"full": "20-175 THM",      "label": "THM",           "desc": "Базовый трубный"},
                {"full": "20-175 THM-A",    "label": "THM-A",         "desc": "Модификация A"},
                {"full": "25-175 THM",      "label": "THM (увел.)",   "desc": "Увеличенная верхняя муфта"},
                {"full": "25-175 THM-A",    "label": "THM-A (увел.)", "desc": "Модификация A, увел. муфта"},
                {"full": "25-175 THM-T",    "label": "THM-T",         "desc": "Неизвл. всасыв. клапан"},
                {"full": "25-175 THM-TA",   "label": "THM-TA",        "desc": "Неизвл. клапан, модиф. A"},
                {"full": "25-175 THM-C",    "label": "THM-C",         "desc": "Клапан увел. + сбивной"},
                {"full": "25-175 THM-CA",   "label": "THM-CA",        "desc": "Клапан увел. + сбивной A"},
                {"full": "25-175 THM-СП",   "label": "THM-СП",        "desc": "Сбивной плунжер"},
                {"full": "25-175 THM-СПА",  "label": "THM-СПА",       "desc": "Сбивной плунжер A"},
                {"full": "25-175 THM-СЛ",   "label": "THM-СЛ",        "desc": "Сбивной левый"},
                {"full": "25-175 THM-СЛА",  "label": "THM-СЛА",       "desc": "Сбивной левый A"},
                {"full": "25-175 THC",      "label": "THC",           "desc": "Тонкостенный цилиндр"},
                {"full": "25-175 THC-A",    "label": "THC-A",         "desc": "Тонкостенный, модиф. A"},
                {"full": "25-150 THM-C",    "label": "THM-C (150)",   "desc": "Размер 150, клапан увел."},
                {"full": "25-150 THM-СЛ",   "label": "THM-СЛ (150)",  "desc": "Размер 150, клапан + сбивной"},
            ],
        },
    },

    # ── TH трубные, НКТ 73,0 мм (размер 225) ─────────────────────────────
    "TH_73": {
        "nkt": "73.0",
        "label": "НКТ 73,0 мм (2 7/8\")",
        "sizes": {
            "25-225": [
                {"full": "25-225 THM",     "label": "THM",     "desc": "Базовый трубный"},
                {"full": "25-225 THM-T",   "label": "THM-T",   "desc": "Неизвл. всасыв. клапан"},
                {"full": "25-225 THM-C",   "label": "THM-C",   "desc": "Клапан увел. + сбивной"},
                {"full": "25-225 THM-СЛ",  "label": "THM-СЛ",  "desc": "Клапан увел. + сбивной (СЛ)"},
                {"full": "25-225 THM-CA",  "label": "THM-CA",  "desc": "Неувел. клапан + сбивной"},
            ],
        },
    },

    # ── TH трубные, НКТ 88,9 мм (размер 275) ─────────────────────────────
    "TH_89": {
        "nkt": "88.9",
        "label": "НКТ 88,9 мм (3 1/2\")",
        "sizes": {
            "30-275": [
                {"full": "30-275 THM",     "label": "THM",    "desc": "Базовый трубный"},
                {"full": "30-275 THM-T",   "label": "THM-T",  "desc": "Неизвл. всасыв. клапан"},
                {"full": "30-275 THM-C",   "label": "THM-C",  "desc": "Клапан увел. + сбивной"},
                {"full": "30-275 THM-СЛ",  "label": "THM-СЛ", "desc": "Клапан увел. + сбивной (СЛ)"},
            ],
        },
    },
}


# ══════════════════════════════════════════════════════════════════════════════
# ФОРМЫ И ОПРОСНИКИ
# ══════════════════════════════════════════════════════════════════════════════

def build_step_form(step: QuestionnaireStep, draft_answers: dict):
    fields = {}

    for q in step.questions.prefetch_related("options").all():
        initial = draft_answers.get(q.slug)
        common = {
            "label": q.label,
            "required": q.required,
            "help_text": q.help_text,
            "initial": initial,
        }

        if q.field_type == Question.TEXT:
            fields[q.slug] = forms.CharField(**common)
        elif q.field_type == Question.NUMBER:
            fields[q.slug] = forms.DecimalField(**common)
        elif q.field_type == Question.CHECKBOX:
            fields[q.slug] = forms.BooleanField(
                required=False, label=q.label,
                help_text=q.help_text, initial=bool(initial),
            )
        elif q.field_type == Question.SELECT:
            choices = [(opt.value, opt.label) for opt in q.options.all()]
            fields[q.slug] = forms.ChoiceField(
                choices=[("", "— выберите —")] + choices, **common
            )

        fields[q.slug].depends_on = q.depends_on.slug if getattr(q, "depends_on", None) else ""
        fields[q.slug].depends_value = q.depends_value if getattr(q, "depends_value", "") else ""

    DynamicForm = type("DynamicForm", (forms.Form,), fields)
    return DynamicForm


# ══════════════════════════════════════════════════════════════════════════════
# VIEWS — КЛИЕНТСКАЯ ЧАСТЬ
# ══════════════════════════════════════════════════════════════════════════════

@login_required
def questionnaire_list(request):
    items = Questionnaire.objects.filter(is_active=True).order_by("title")
    return render(request, "questionnaires/list.html", {"items": items})


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
def fill_step(request, slug, step_order):
    q = get_object_or_404(Questionnaire, slug=slug, is_active=True)
    step = get_object_or_404(QuestionnaireStep, questionnaire=q, order=step_order)

    draft = _get_draft(request, slug) or {"answers": {}}
    draft_answers = draft.get("answers", {})

    FormClass = build_step_form(step, draft_answers)
    form = FormClass(request.POST or None)

    if request.method == "POST" and form.is_valid():
        for k, v in form.cleaned_data.items():
            draft_answers[k] = "" if v is None else str(v)

        draft["answers"] = draft_answers
        _set_draft(request, slug, draft)

        next_step = q.steps.filter(order__gt=step.order).order_by("order").first()
        if next_step:
            return redirect("fill_step", slug=slug, step_order=next_step.order)

        return redirect("submit_questionnaire", slug=slug)

    return render(request, "questionnaires/fill_step.html", {
        "questionnaire": q,
        "step": step,
        "form": form,
        "draft_answers": draft_answers,
    })


@login_required
def submit_questionnaire(request, slug):
    q = get_object_or_404(Questionnaire, slug=slug, is_active=True)
    draft = _get_draft(request, slug) or {}
    draft_answers = draft.get("answers") or {}

    if request.method == "POST":
        with transaction.atomic():
            submission = Submission.objects.create(
                questionnaire=q,
                user=request.user,
                status=Submission.SUBMITTED,
                submitted_at=timezone.now(),
            )

            questions = Question.objects.filter(
                step__questionnaire=q
            ).select_related("step")
            q_by_slug = {qq.slug: qq for qq in questions}

            for slug_key, raw_value in draft_answers.items():
                qq = q_by_slug.get(slug_key)
                if not qq or raw_value in ("", None):
                    continue

                ans = Answer(submission=submission, question=qq)

                if qq.field_type == Question.NUMBER:
                    try:
                        ans.value_number = raw_value if raw_value != "" else None
                    except Exception:
                        ans.value_number = None
                elif qq.field_type == Question.CHECKBOX:
                    ans.value_bool = raw_value in ("True", "true", "1")
                else:
                    ans.value_text = raw_value

                ans.save()

        _clear_draft(request, slug)
        return render(request, "questionnaires/thanks.html", {"submission": submission})

    return render(request, "questionnaires/submit.html", {
        "questionnaire": q,
        "draft_answers": draft_answers,
    })


# ══════════════════════════════════════════════════════════════════════════════
# VIEWS — МЕНЕДЖЕРСКАЯ ЧАСТЬ
# ══════════════════════════════════════════════════════════════════════════════

from django.contrib.admin.views.decorators import staff_member_required


@staff_member_required
def manager_list(request):
    items = Submission.objects.exclude(status=Submission.DRAFT).order_by("-created_at")
    return render(request, "manager/list.html", {
        "items":           items,
        "count_total":     items.count(),
        "count_submitted": items.filter(status=Submission.SUBMITTED).count(),
        "count_in_review": items.filter(status=Submission.IN_REVIEW).count(),
        "count_processed": items.filter(status=Submission.PROCESSED).count(),
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

    # Собираем ответы клиента в словарь
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

    recommendation = get_pump_recommendation(answers_dict)
    material_rec   = get_material_recommendation(answers_dict)

    # Читаем выбор менеджера из processed_data_json
    manager_data       = sub.processed_data_json or {}
    selected_pump      = manager_data.get("selected_pump_code", "")
    selected_size      = manager_data.get("selected_pump_size", "")
    selected_nkt       = manager_data.get("selected_nkt", "")
    selected_pump_full = manager_data.get("selected_pump_full", "")

    # Число качаний и коэффициент подачи, заданные менеджером вручную
    try:
        custom_spm = float(manager_data["custom_spm"]) if manager_data.get("custom_spm") not in (None, "") else None
    except (ValueError, TypeError):
        custom_spm = None

    try:
        custom_eta = float(manager_data["custom_eta"]) if manager_data.get("custom_eta") not in (None, "") else None
    except (ValueError, TypeError):
        custom_eta = None

    # Расчёт подачи с учётом параметров менеджера
    flow_rec = get_flow_recommendation(answers_dict, custom_spm=custom_spm, custom_eta=custom_eta)

    # Подставляем выбранный насос для расчётов цилиндра и зазора
    calc_dict = dict(answers_dict)
    if selected_pump_full:
        calc_dict["pump_type_full"] = selected_pump_full
    if selected_size:
        calc_dict["inner_diameter"] = (
            selected_size.split("-")[-1] if "-" in selected_size else selected_size
        )

    cylinder_rec = get_cylinder_recommendation(calc_dict, flow_rec=flow_rec)
    fit_rec      = get_fit_recommendation(calc_dict)

    # Фильтрация модификаций по НКТ клиента (если указан)
    NKT_MAP = {
        "60.3": "60.3", "60,3": "60.3", "2 3/8": "60.3", "2-3/8": "60.3",
        "73.0": "73.0", "73,0": "73.0", "73":    "73.0", "2 7/8": "73.0",
        "88.9": "88.9", "88,9": "88.9", "88":    "88.9", "3 1/2": "88.9",
    }
    nkt_raw        = answers_dict.get("nkt_diameter", "")
    nkt_normalized = NKT_MAP.get(str(nkt_raw).strip(), "")

    # Фильтруем ALL_MODIFICATIONS по НКТ клиента если он указан
    if nkt_normalized:
        filtered_modifications = {
            k: v for k, v in ALL_MODIFICATIONS.items()
            if v["nkt"] == nkt_normalized
        }
    else:
        filtered_modifications = ALL_MODIFICATIONS

    return render(request, "manager/detail.html", {
        "sub":                    sub,
        "answers":                answers,
        "recommendation":         recommendation,
        "material_rec":           material_rec,
        "cylinder_rec":           cylinder_rec,
        "fit_rec":                fit_rec,
        "selected_pump":          selected_pump,
        "selected_size":          selected_size,
        "selected_nkt":           selected_nkt,
        "selected_pump_full":     selected_pump_full,
        "nkt_normalized":         nkt_normalized,
        "flow_rec":               flow_rec,
        "custom_spm":             custom_spm,
        "custom_eta":             custom_eta,
        "all_modifications":      filtered_modifications,
        "all_modifications_json": json.dumps(filtered_modifications, ensure_ascii=False),
    })


@staff_member_required
@require_POST
def manager_select_pump(request, submission_id):
    sub            = get_object_or_404(Submission, id=submission_id)
    pump_type_full = request.POST.get("pump_type_full", "").strip()

    NKT_BY_PREFIX = {
        "15": "48.3",
        "20": "60.3",
        "25": "73.0",
        "30": "88.9",
    }

    size = nkt = ""
    if pump_type_full:
        parts  = pump_type_full.split(" ")
        size   = parts[0] if parts else ""
        prefix = size.split("-")[0] if "-" in size else size[:2]
        nkt    = NKT_BY_PREFIX.get(prefix, "")

    # pump_code — для обратной совместимости с шаблоном
    code_part = pump_type_full.split(" ")[1] if len(pump_type_full.split(" ")) > 1 else ""
    if code_part.startswith("TH"):
        pump_code = "TH"
    elif "RHAM" in code_part or "RHAC" in code_part or "RHAM-T" in code_part:
        pump_code = "RHA"
    elif "RHBM" in code_part or "RHBC" in code_part:
        pump_code = "RHB"
    elif "RHTM" in code_part or "RHM-T" in code_part:
        pump_code = "RHT"
    else:
        pump_code = code_part[:3] if code_part else ""

    data = sub.processed_data_json or {}
    data["selected_pump_full"] = pump_type_full
    data["selected_pump_size"] = size
    data["selected_nkt"]       = nkt
    data["selected_pump_code"] = pump_code
    sub.processed_data_json    = data
    sub.save()

    return redirect("manager_detail", submission_id=submission_id)


@staff_member_required
@require_POST
def manager_update_flow_params(request, submission_id):
    """Сохраняет число качаний и коэффициент подачи, заданные менеджером."""
    sub  = get_object_or_404(Submission, id=submission_id)
    data = sub.processed_data_json or {}

    spm_raw = request.POST.get("custom_spm", "").strip()
    eta_raw = request.POST.get("custom_eta", "").strip()

    if spm_raw == "":
        data.pop("custom_spm", None)
    else:
        try:
            spm_val = float(spm_raw)
            if 1 <= spm_val <= 30:
                data["custom_spm"] = spm_val
        except ValueError:
            pass

    if eta_raw == "":
        data.pop("custom_eta", None)
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


# ══════════════════════════════════════════════════════════════════════════════
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ══════════════════════════════════════════════════════════════════════════════

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