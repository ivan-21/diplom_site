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

def get_pump_recommendation(answers_dict):
    # Получаем данные из ответов клиента
    depth_raw  = answers_dict.get("glubina_pogruzhenia", "")
    volume_raw = answers_dict.get("V_otkach_zhidkosti", "")
    skvazhina  = answers_dict.get("type_skvazhina", "")
    gas        = answers_dict.get("gas_factor", "")
    sand       = answers_dict.get("sand_content", "")
    corr_h2s      = answers_dict.get("corr_h2s", "none")
    corr_co2      = answers_dict.get("corr_co2", "none")
    corr_saltwater = answers_dict.get("corr_saltwater", "none")
    corr_oxygen   = answers_dict.get("corr_oxygen", "none")
    level      = answers_dict.get("oil_level", "")

    try:
        depth = float(str(depth_raw).replace(",", ".")) if depth_raw else None
    except:
        depth = None
    try:
        volume = float(str(volume_raw).replace(",", ".")) if volume_raw else None
    except:
        volume = None
        
    # Таблица 9 — размеры насосов по диаметру НКТ
    NKT_SIZES = {
        "60.3": {
            "RH": ["20-106", "20-125"],
            "TH": ["20-125", "20-175"],
        },
        "73.0": {
            "RH": ["25-150", "25-175"],
            "TH": ["25-225"],
        },
        "88.9": {
            "RH": ["30-225"],
            "TH": ["30-275"],
        },
    }


    # Типы насосов
    PUMPS = {
        "TH":   {"name": "Трубный насос (ТН)",                    "desc": "Цилиндр входит в состав колонны НКТ"},
        "RHA": {"name": "Вставной RHA — верхнее крепление",       "desc": "Механическое или манжетное крепление сверху"},
        "RHB": {"name": "Вставной RHB — нижнее крепление",        "desc": "Механическое или манжетное крепление снизу"},
        "RHT": {"name": "Вставной RHT — подвижный цилиндр",       "desc": "Нижнее механическое крепление"},
    }

    scores = {"TH": 50, "RHA": 50, "RHB": 50, "RHT": 50} # начальные очки у каждого насоса
    reasons = {k: []  for k in PUMPS}
    log     = []

    def add(code, delta, text):
        scores[code] += delta
        reasons[code].append({"text": text, "good": delta >= 0, "bad": delta < 0})

    # ── дебит ── если объем больше 100 пока считаем что дебит высокий
    
    if volume is not None and volume > 100:
        debit = 'high'
    else:
        debit = 'low'

    # ── RHA рекомендации ──

    if sand == 'high' or sand == 'medium':
        add("RHA", +10, "Высокое и среднее содержание песка — RHA (верхнее крепление) рекомендовано")
        log.append("Песок высокий или средний — RHA +10")
    if gas == 'medium' and depth <= 1500:
        add("RHA", +10, "Среднее содержание газа, глубина до 1500 м — RHA (верхнее крепление) рекомендовано")
        log.append("Среднее содержание газа, глубина до 1500 м — RHA +10")
    if corr_h2s != 'none' and depth <= 1500:
        add("RHA", +10, "H₂S, глубина до 1500 м — RHA (верхнее крепление) рекомендовано")
        log.append("H₂S, глубина до 1500 м — RHA +10")
    if corr_co2 != 'none' and depth <= 2000:
        add("RHA", +10, "CO₂, глубина до 2000 м — RHA (верхнее крепление) рекомендовано")
        log.append("CO₂, глубина до 2000 м — RHA +10")
    if depth > 2100:
        add("RHA", -1000, "⚠ Глубже 2100 м — RHA (верхнее крепление) не рекомендуется")
        log.append("⚠ Глубже 2100 м — RHA -1000")

    # ── RHB рекомендации ──

    if debit == 'high' and depth <= 900:
        add("RHB", +10, "Высокий дебит, глубина до 900 м — RHB (нижнее крепление) рекомендовано")
        log.append("Высокий дебит, глубина до 900 м — RHB +10")
    if level == 'low' and depth >=900 and depth <= 2000:
        add("RHB", +10, "Низкий уровень нефти, глубина 900–2000 м — RHB (нижнее крепление) рекомендовано")
        log.append("Низкий уровень нефти, глубина 900–2000 м — RHB +10")
    if corr_saltwater != 'none' and depth <= 1500:
        add("RHB", +10, "Соленая вода, глубина до 1500 м — RHB (нижнее крепление) рекомендовано")
        log.append("Соленая вода, глубина до 1500 м — RHB +10")
    if gas == 'medium' and depth <= 1500:
        add("RHB", +10, "Среднее содержание газа, до 1500 м — RHB (нижнее крепление) рекомендовано")
        log.append("Среднее содержание газа, до 1500 м — RHB +10")
    if skvazhina == 'curved':
        add("RHB", +10, "Искривлённые скважины — RHB (нижнее крепление) рекомендовано")
        log.append("Искривлённые скважины — RHB +10")
    
    # ── RHT рекомендации ── Только механическое крепление. Для неглубоких скважин с высоким уровнем нефти и повышенным содержанием песка.
    
    if depth <= 900 and level == 'high' and sand == 'high':
        add("RHT", +70, "Для неглубоких скважин с высоким уровнем нефти и повышенным содержанием песка. — RHT (нижнее крепление) рекомендовано")
        log.append("Для неглубоких скважин с высоким уровнем нефти и повышенным содержанием песка. — RHT +70")

    # ── TH рекомендации ── Оптимальны для высокодебитных скважин малой глубины !!без газов(low)
    
    if depth <= 900 and debit == 'high':
        add("TH", +100, "Для высокодебитных скважин с малой глубины без газированной жидкости. — TH рекомендовано")
        log.append("Для высокодебитных скважин с малой глубины без газированной жидкости. — TH +100")
    if gas != 'low':
        add("TH", -1000, "Не применять для газированных жидкостей. — TH не рекомендовано")
        log.append("Не применять для газированных жидкостей. — TH -1000")
    
    # ── Манжетное крепление для RHA и RHB──

    manjetnoe = False
    manjetnoe_reasons = []

    if gas in ('medium', 'high'):
        manjetnoe = True
        manjetnoe_reasons.append("Средний или высокий газовый фактор")

    if skvazhina == 'curved':
        manjetnoe = True
        manjetnoe_reasons.append("Искривлённая скважина")

    if (corr_h2s != 'none' or corr_co2 != 'none' or 
        corr_saltwater != 'none' or corr_oxygen == 'yes'):
        manjetnoe = True
        manjetnoe_reasons.append("Повышенная коррозионная активность среды")

    # Не ниже 0
    for k in scores:
        if scores[k] < 0:
            scores[k] = 0

    # Сортировка по баллам
    sorted_pumps = sorted(PUMPS.keys(), key=lambda k: scores[k], reverse=True)
    max_score = scores[sorted_pumps[0]] if sorted_pumps else 1

    results = []
    for code in sorted_pumps:
        sc = scores[code]
        pct = round(sc / max_score * 100) if max_score > 0 else 0
        if pct >= 90:
            verdict = "recommended"
        elif pct >= 60:
            verdict = "acceptable"
        else:
            verdict = "not_recommended"

        results.append({
            "code":    code,
            "name":    PUMPS[code]["name"],
            "desc":    PUMPS[code]["desc"],
            "score":   sc,
            "pct":     pct,
            "verdict": verdict,
            "reasons": reasons[code],
        })

    return {
        "pumps":   results,
        "best":    results[0] if results else None,
        "log":     log,
        "has_data": depth is not None or volume is not None,        
        "manjetnoe":         manjetnoe,         
        "manjetnoe_reasons": manjetnoe_reasons,  
    }

def get_plunger_recommendation(answers_dict):
    depth_raw    = answers_dict.get("glubina_pogruzhenia", "")
    nkt_diameter = answers_dict.get("nkt_diameter", "")

    try:
        depth = float(str(depth_raw).replace(",", ".")) if depth_raw else None
    except:
        depth = None

    if depth is None:
        return {"has_data": False}

    # Длина плунжера по глубине (правило из справочника: 1 фут на 380-400м)
    if depth <= 1500:
        plunger_feet = 4
        plunger_mm   = 1295
        plunger_note = "Глубина до 1500 м"
    elif depth <= 2000:
        plunger_feet = 5
        plunger_mm   = 1600
        plunger_note = "Глубина до 2000 м"
    else:
        plunger_feet = 6
        plunger_mm   = 1829
        plunger_note = "Глубина свыше 2000 м"

    # Таблица 9 — допустимые размеры насосов по диаметру НКТ
    NKT_SIZES = {
        "60.3": {"RH": ["20-106", "20-125"], "TH": ["20-125", "20-175"]},
        "73.0": {"RH": ["25-150", "25-175"], "TH": ["25-225"]},
        "88.9": {"RH": ["30-225"],           "TH": ["30-275"]},
    }
    nkt_sizes = NKT_SIZES.get(nkt_diameter, None)

    return {
        "has_data":     True,
        "depth":        depth,
        "plunger_feet": plunger_feet,
        "plunger_mm":   plunger_mm,
        "plunger_note": plunger_note,
        "nkt_diameter": nkt_diameter,
        "nkt_sizes":    nkt_sizes,
    }

def get_material_recommendation(answers_dict):
    corr_h2s       = answers_dict.get("corr_h2s", "none")
    corr_co2       = answers_dict.get("corr_co2", "none")
    corr_saltwater = answers_dict.get("corr_saltwater", "none")
    corr_oxygen    = answers_dict.get("corr_oxygen", "none")
    sand           = answers_dict.get("sand_content", "none")

    abrasive = sand in ('medium', 'high')

    # Определяем среду (может быть несколько)
    environments = []

    # Некоррозионная среда
    if corr_h2s == 'none' and corr_co2 == 'none' and corr_saltwater == 'none' and corr_oxygen == 'none':
        if abrasive:
            environments.append("non_corr_abrasive")
        else:
            environments.append("non_corr")

    # H2S + CO2 комбо
    if corr_h2s != 'none' and corr_co2 != 'none':
        both_high = (corr_h2s == 'high' and corr_co2 == 'high') or \
                    (corr_h2s == 'high' and corr_co2 == 'medium') or \
                    (corr_h2s == 'medium' and corr_co2 == 'high')
        if both_high:
            environments.append("h2s_co2_high_abrasive" if abrasive else "h2s_co2_high")
        else:
            environments.append("h2s_co2_mod_abrasive" if abrasive else "h2s_co2_mod")

    # H2S отдельно
    elif corr_h2s != 'none':
        if corr_h2s == 'high':
            environments.append("h2s_high_abrasive" if abrasive else "h2s_high")
        else:
            environments.append("h2s_mod_abrasive" if abrasive else "h2s_mod")

    # CO2 отдельно
    elif corr_co2 != 'none':
        if corr_co2 == 'high':
            environments.append("co2_high_abrasive" if abrasive else "co2_high")
        else:
            environments.append("co2_mod_abrasive" if abrasive else "co2_mod")

    # Солевой раствор
    if corr_saltwater != 'none':
        if corr_saltwater == 'high':
            environments.append("saltwater_high_abrasive" if abrasive else "saltwater_high")
        else:
            environments.append("saltwater_mod_abrasive" if abrasive else "saltwater_mod")

    # Кислород
    if corr_oxygen == 'yes':
        environments.append("oxygen")

    # Таблица 14
    TABLE_14 = {
        "non_corr":              {"cyl_cr":"A","cyl_hn":"A","plu_cr":"A","plu_t":"A","val_ss":"A","val_st":"A","label":"Некоррозионная"},
        "non_corr_abrasive":     {"cyl_cr":"A","cyl_hn":"A","plu_cr":"A","plu_t":"A","val_ss":"A","val_st":"A","label":"Некоррозионная + абразивная"},
        "h2s_high":              {"cyl_cr":"X","cyl_hn":"C","plu_cr":"X","plu_t":"C","val_ss":"B","val_st":"A","label":"Сильно активная H₂S"},
        "h2s_high_abrasive":     {"cyl_cr":"X","cyl_hn":"C","plu_cr":"X","plu_t":"C","val_ss":"C","val_st":"B","label":"Сильно активная H₂S + абразивная"},
        "h2s_mod":               {"cyl_cr":"C","cyl_hn":"C","plu_cr":"X","plu_t":"A","val_ss":"A","val_st":"A","label":"Умеренная H₂S"},
        "h2s_mod_abrasive":      {"cyl_cr":"X","cyl_hn":"C","plu_cr":"X","plu_t":"A","val_ss":"B","val_st":"A","label":"Умеренная H₂S + абразивная"},
        "co2_high":              {"cyl_cr":"C","cyl_hn":"X","plu_cr":"X","plu_t":"C","val_ss":"A","val_st":"A","label":"Сильно активная CO₂"},
        "co2_high_abrasive":     {"cyl_cr":"C","cyl_hn":"X","plu_cr":"X","plu_t":"C","val_ss":"B","val_st":"B","label":"Сильно активная CO₂ + абразивная"},
        "co2_mod":               {"cyl_cr":"B","cyl_hn":"X","plu_cr":"B","plu_t":"A","val_ss":"A","val_st":"A","label":"Умеренная CO₂"},
        "co2_mod_abrasive":      {"cyl_cr":"B","cyl_hn":"X","plu_cr":"B","plu_t":"A","val_ss":"A","val_st":"A","label":"Умеренная CO₂ + абразивная"},
        "h2s_co2_high":          {"cyl_cr":"X","cyl_hn":"X","plu_cr":"X","plu_t":"X","val_ss":"B","val_st":"A","label":"Сильно активная H₂S + CO₂"},
        "h2s_co2_high_abrasive": {"cyl_cr":"X","cyl_hn":"X","plu_cr":"X","plu_t":"X","val_ss":"C","val_st":"B","label":"Сильно активная H₂S + CO₂ + абразивная"},
        "h2s_co2_mod":           {"cyl_cr":"X","cyl_hn":"X","plu_cr":"X","plu_t":"B","val_ss":"A","val_st":"A","label":"Умеренная H₂S + CO₂"},
        "h2s_co2_mod_abrasive":  {"cyl_cr":"X","cyl_hn":"X","plu_cr":"X","plu_t":"B","val_ss":"B","val_st":"A","label":"Умеренная H₂S + CO₂ + абразивная"},
        "saltwater_high":        {"cyl_cr":"C","cyl_hn":"B","plu_cr":"X","plu_t":"B","val_ss":"A","val_st":"A","label":"Сильно активный солевой раствор"},
        "saltwater_high_abrasive":{"cyl_cr":"C","cyl_hn":"B","plu_cr":"C","plu_t":"B","val_ss":"B","val_st":"A","label":"Сильно активный солевой раствор + абразивная"},
        "saltwater_mod":         {"cyl_cr":"B","cyl_hn":"A","plu_cr":"C","plu_t":"A","val_ss":"-","val_st":"-","label":"Умеренный солевой раствор"},
        "saltwater_mod_abrasive":{"cyl_cr":"B","cyl_hn":"A","plu_cr":"C","plu_t":"A","val_ss":"-","val_st":"-","label":"Умеренный солевой раствор + абразивная"},
        "oxygen":                {"cyl_cr":"X","cyl_hn":"B","plu_cr":"C","plu_t":"B","val_ss":"A","val_st":"A","label":"Кислородосодержащая среда"},
    }

    GRADE_LABEL = {
        "A": {"text": "Стоек",            "color": "#166534", "bg": "#f0fdf4", "border": "#bbf7d0", "priority": 5},
        "B": {"text": "Слабая коррозия",  "color": "#92400e", "bg": "#fffbeb", "border": "#fde68a", "priority": 4},
        "C": {"text": "Сильная коррозия", "color": "#be123c", "bg": "#fff1f2", "border": "#fecdd3", "priority": 3},
        "X": {"text": "Неприменим",       "color": "#6b7280", "bg": "#f3f4f6", "border": "#e5e7eb", "priority": 1},
        "-": {"text": "Нет данных",       "color": "#6b7280", "bg": "#f3f4f6", "border": "#e5e7eb", "priority": 0},
    }

    if not environments:
        return {"has_data": False}

    rows = []
    for env_key in environments:
        row = TABLE_14.get(env_key)
        if not row:
            continue

        def grade(code):
            g = GRADE_LABEL.get(code, GRADE_LABEL["-"])
            return {"code": code, "text": g["text"], "color": g["color"], 
                    "bg": g["bg"], "border": g["border"], "priority": g["priority"]}

        cyl_options = [
            {"material": "CR (Угл. сталь + хром)", "slug": "cyl_cr", **grade(row["cyl_cr"])},
            {"material": "HN (Лег. сталь + азотир.)", "slug": "cyl_hn", **grade(row["cyl_hn"])},
        ]
        plu_options = [
            {"material": "CR (Угл. сталь + хром)", "slug": "plu_cr", **grade(row["plu_cr"])},
            {"material": "T (Лег. сталь + напыл.)", "slug": "plu_t", **grade(row["plu_t"])},
        ]
        val_options = [
            {"material": "Нержав. сталь SS", "slug": "val_ss", **grade(row["val_ss"])},
            {"material": "Кобальтовый сплав ST", "slug": "val_st", **grade(row["val_st"])},
        ]

        # Возвращает ВСЕ варианты с максимальным приоритетом (лучшие для ЭТОЙ среды)
        def best_multiple(options):
            if not options:
                return []
            max_priority = max(o["priority"] for o in options)
            return [o for o in options if o["priority"] == max_priority]

        rows.append({
            "label":         row["label"],
            "cyl_best":      best_multiple(cyl_options),
            "cyl_all":       cyl_options,
            "plu_best":      best_multiple(plu_options),
            "plu_all":       plu_options,
            "val_best":      best_multiple(val_options),
            "val_all":       val_options,
        })
    
    # ✅ ИСПРАВЛЕННАЯ ФУНКЦИЯ: собирает НАИХУДШИЕ варианты из всех сред
    # Потому что если одна среда требует X, а другая A — нужно выбрать X (самый строгий)
    def collect_worst_across_environments(rows, component_key):
        """
        Собирает наихудшие (самые низкие приоритеты) материалы из всех сред.
        Для итоговой рекомендации выбираем самый строгий вариант.
        """
        all_materials = {}
        
        for row in rows:
            for item in row[component_key]:  # item — это лучший вариант для ЭТОЙ среды
                material_name = item["material"]
                if material_name not in all_materials:
                    all_materials[material_name] = item
                else:
                    # Если у этого материала в другой среде приоритет ниже — обновляем
                    if item["priority"] < all_materials[material_name]["priority"]:
                        all_materials[material_name] = item
        
        if not all_materials:
            return []
        
        # Находим НАИМЕНЬШИЙ приоритет среди всех материалов (самый плохой)
        min_priority = min(item["priority"] for item in all_materials.values())
        
        # Возвращаем все материалы с этим минимальным приоритетом
        return [item for item in all_materials.values() if item["priority"] == min_priority]

    if rows:
        summary = {
            "cyl": collect_worst_across_environments(rows, "cyl_best"),
            "plu": collect_worst_across_environments(rows, "plu_best"),
            "val": collect_worst_across_environments(rows, "val_best"),
        }
    else:
        summary = None

    return {
        "has_data": True,
        "rows":     rows,
        "summary":  summary,
    }