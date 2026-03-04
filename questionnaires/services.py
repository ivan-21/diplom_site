from .models import Question

def submission_to_dict(submission):
    """
    Собираем ответы в словарь {slug: value}.
    """
    result = {}
    answers = submission.answers.select_related("question").all()
    for a in answers:
        q = a.question
        if q.field_type == Question.NUMBER:
            result[q.slug] = float(a.value_number) if a.value_number is not None else None
        elif q.field_type == Question.CHECKBOX:
            result[q.slug] = bool(a.value_bool)
        else:
            result[q.slug] = a.value_text
    return result


def process_submission(submission):
    """
    Простая обработка:
    - выжимка ключевых данных
    - предупреждения
    """
    data = submission_to_dict(submission)

    issues = []
    summary = {}

    # пример выжимки
    for key in ["customer", "well", "diameter_mm", "pump_type"]:
        if key in data and data[key] not in ("", None):
            summary[key] = data[key]

    # пример логики предупреждений
    diameter = data.get("diameter_mm")
    if diameter is not None:
        if diameter < 30:
            issues.append("Слишком малый диаметр — проверьте корректность.")
        if diameter > 120:
            issues.append("Слишком большой диаметр — проверьте корректность.")

    # пример: если песок указан и высокий
    sand = data.get("sand_g_l")
    if sand is not None:
        try:
            if float(sand) > 0.1:
                issues.append("Высокое содержание песка — рекомендуется пескобрей/износостойкое покрытие.")
        except:
            pass

    # статус
    submission.processed_data_json = summary
    submission.issues_json = {"issues": issues}

    if issues:
        submission.status = "needs_info"
    else:
        submission.status = "processed"

    submission.save()