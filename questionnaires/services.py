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
        add("TH", +50, "Для высокодебитных скважин с малой глубины без газированной жидкости. — TH рекомендовано")
        log.append("Для высокодебитных скважин с малой глубины без газированной жидкости. — TH +50")
    if gas == 'high':
        add("TH", -1000, "Высокий газовый фактор — TH не рекомендован")
    elif gas == 'medium':
        add("TH", -30, "Среднее содержание газа — TH нежелателен")
    
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

def get_cylinder_recommendation(answers_dict, flow_rec=None):
    """
    Расчёт длины цилиндра и удлинителей по формуле приложения В справочника:
        В + У = Н + П + К
    где:
        В — длина цилиндра (футы)
        У — суммарная длина удлинителей (футы)
        Н — ход плунжера (футы)
        П — длина плунжера (футы) — рассчитывается здесь по глубине
        К — конструктивный коэффициент (зависит от типа насоса)
    """

    K_TABLE = {
        "20-106 RHAM": 1.211,
        "20-106 RHBM": 1.178,
        "20-125 RHAM": 1.214,
        "20-125 RHBM": 1.178,
        "25-150 RHAM": 1.266,
        "25-150 RHBM": 1.289,
        "25-175 RHAM": 1.352,
        "25-175 RHBM": 1.375,
        "20-125 THM":  1.614,
        "20-175 THM":  1.877,
        "25-225 THM":  2.080,
        "30-275 THM":  2.293,
    }

    STD_CYL_RH = [8, 10, 12, 14, 16, 18, 20, 22, 24, 26, 28, 30]
    STD_CYL_TH = [6, 7, 8, 9, 10, 11, 12, 14, 16, 18, 20, 22, 24, 26, 28, 30]

    # Стандартные пары удлинителей (суммарная длина → (удл1, удл2))
    EXT_PAIRS = {
        2.0: (1.0, 1.0),
        3.0: (1.5, 1.5),
        4.0: (2.0, 2.0),
        5.0: (2.0, 3.0),
    }

    depth_raw     = answers_dict.get("glubina_pogruzhenia", "")
    pump_type_key = answers_dict.get("pump_type_full", "")

    if flow_rec and flow_rec.get("has_data") and not flow_rec.get("overflow"):
        stroke_mm = flow_rec["opt_stroke"]
    else:
        stroke_raw = answers_dict.get("plunger_length", "")
        try:
            stroke_mm = float(str(stroke_raw).replace(",", ".")) if stroke_raw else None
        except:
            stroke_mm = None

    try:
        depth = float(str(depth_raw).replace(",", ".")) if depth_raw else None
    except:
        depth = None

    if depth is None and stroke_mm is None:
        return {"has_data": False}

    # ── Длина плунжера П по глубине ──
    if depth is not None:
        if depth <= 1500:
            P = 4
            plunger_mm   = 1295
            plunger_note = "Глубина до 1500 м — 4 фута"
        elif depth <= 2000:
            P = 5
            plunger_mm   = 1600
            plunger_note = "Глубина до 2000 м — 5 футов"
        else:
            P = 6
            plunger_mm   = 1829
            plunger_note = "Глубина свыше 2000 м — 6 футов"
    else:
        P = 4
        plunger_mm   = 1295
        plunger_note = "Глубина не указана — принято 4 фута по умолчанию"

    # ── Ход плунжера Н ──
    if stroke_mm is not None:
        N = stroke_mm / 304.8
    elif depth is not None:
        stroke_mm = 3000
        N = stroke_mm / 304.8
    else:
        return {"has_data": False}

    K        = K_TABLE.get(pump_type_key)
    is_TH    = pump_type_key.endswith("THM") if pump_type_key else False
    std_cyl  = STD_CYL_TH if is_TH else STD_CYL_RH

    if K is not None:
        required = N + P + K  # минимальное В+У

        results = []
        for U, (u1, u2) in EXT_PAIRS.items():
            V_needed = required - U
            V = next((c for c in std_cyl if c >= V_needed), None)
            if V is None:
                continue
            actual_BU        = V + U
            actual_stroke_mm = round(stroke_mm + (actual_BU - required) * 304.8)

            results.append({
                "U":           U,
                "u1":          u1,
                "u2":          u2,
                "V":           V,
                "BU":          actual_BU,
                "stroke_mm":   actual_stroke_mm,
                "designation": f"{pump_type_key} {int(V)}-{int(P)}-{u1}-{u2}",
            })

        return {
            "has_data":    True,
            "pump_type":   pump_type_key,
            "K":           K,
            "P":           P,
            "plunger_mm":  plunger_mm,
            "plunger_note": plunger_note,
            "N_ft":        round(N, 3),
            "stroke_mm":   round(stroke_mm),
            "required_BU": round(required, 3),
            "results":     results[:3],
            "note":        None,
        }

    else:
        # Тип насоса не выбран — даём диапазон
        K_min, K_max = 1.178, 2.293
        req_min = N + P + K_min
        req_max = N + P + K_max

        return {
            "has_data":     True,
            "pump_type":    None,
            "K":            None,
            "P":            P,
            "plunger_mm":   plunger_mm,
            "plunger_note": plunger_note,
            "N_ft":         round(N, 3),
            "stroke_mm":    round(stroke_mm),
            "required_BU":  None,
            "req_range":    (round(req_min, 1), round(req_max, 1)),
            "results":      [],
            "note":         f"Укажите тип насоса для точного расчёта. "
                            f"Ориентировочная В+У: {round(req_min, 1)}–{round(req_max, 1)} фута.",
        }


def get_fit_recommendation(answers_dict):
    """
    Подбор группы посадки плунжера (Fit-1..Fit-5) по таблицам 6 и 13 справочника.

    Таблица 6 — группы посадок:
        Fit-1: номинал 0,025 мм  диапазон 0,025–0,088
        Fit-2: номинал 0,050 мм  диапазон 0,050–0,113
        Fit-3: номинал 0,075 мм  диапазон 0,075–0,138
        Fit-4: номинал 0,100 мм  диапазон 0,100–0,163
        Fit-5: номинал 0,125 мм  диапазон 0,125–0,188

    Таблица 13 (Шеллер-Блекманн) — рекомендации по диаметру:
        106 (27,0 мм):  Fit-2, Fit-3  → оптимальная Fit-2
        125 (31,8 мм):  Fit-2, Fit-3  → оптимальная Fit-2
        150 (38,1 мм):  Fit-2, Fit-3  → оптимальная Fit-2
        175 (44,5 мм):  Fit-2, Fit-3  → оптимальная Fit-2
        225 (57,2 мм):  Fit-2, Fit-3, Fit-4  → оптимальная Fit-2
        275 (69,9 мм):  Fit-3, Fit-4, Fit-5  → оптимальная Fit-3

    Корректировки по условиям:
        - Высоковязкая нефть → увеличить зазор на 1 группу
        - Высокое содержание песка → уменьшить зазор на 1 группу (меньше утечек)
        - Высокий газовый фактор → минимальный зазор (уменьшить мёртвый объём)
    """

    FIT_TABLE = {
        1: {"nominal": 0.025, "range_min": 0.025, "range_max": 0.088},
        2: {"nominal": 0.050, "range_min": 0.050, "range_max": 0.113},
        3: {"nominal": 0.075, "range_min": 0.075, "range_max": 0.138},
        4: {"nominal": 0.100, "range_min": 0.100, "range_max": 0.163},
        5: {"nominal": 0.125, "range_min": 0.125, "range_max": 0.188},
    }

    # Рекомендации по диаметру: [допустимые], оптимальная
    DIAMETER_FIT = {
        "106": {"allowed": [2, 3],    "optimal": 2, "diam_mm": 27.0},
        "125": {"allowed": [2, 3],    "optimal": 2, "diam_mm": 31.8},
        "150": {"allowed": [2, 3],    "optimal": 2, "diam_mm": 38.1},
        "175": {"allowed": [2, 3],    "optimal": 2, "diam_mm": 44.5},
        "225": {"allowed": [2, 3, 4], "optimal": 2, "diam_mm": 57.2},
        "275": {"allowed": [3, 4, 5], "optimal": 3, "diam_mm": 69.9},
    }

    # Получаем данные из ответов
    # inner_diameter — условный размер насоса (106/125/150/175/225/275)
    inner_diameter = answers_dict.get("inner_diameter", "")
    sand    = answers_dict.get("sand_content", "none")
    gas     = answers_dict.get("gas_factor", "low")
    viscosity_raw = answers_dict.get("viscosity", "")   # вязкость в сП если есть

    try:
        viscosity = float(str(viscosity_raw).replace(",", ".")) if viscosity_raw else None
    except:
        viscosity = None

    # Нормируем inner_diameter (берём только числовую часть "106", "125" и т.д.)
    size_key = str(inner_diameter).strip().split("-")[-1] if inner_diameter else ""

    diam_info = DIAMETER_FIT.get(size_key)
    if not diam_info:
        return {"has_data": False}

    base_fit = diam_info["optimal"]
    allowed  = diam_info["allowed"]
    reasons  = []
    adjustments = 0

    # ── Корректировки ────────────────────────────────────────────────────────

    # Высоковязкая нефть (> 25 сП — предел по справочнику, или явно высокая)
    high_viscosity = viscosity is not None and viscosity > 15
    if high_viscosity:
        adjustments += 1
        reasons.append({
            "text": f"Высокая вязкость ({viscosity:.0f} сП) — увеличен зазор для обеспечения смазки",
            "direction": "up"
        })

    # Высокое содержание песка — минимизируем зазор чтобы частицы не проникали
    if sand == 'high':
        adjustments -= 1
        reasons.append({
            "text": "Высокое содержание песка — уменьшен зазор для снижения абразивного износа",
            "direction": "down"
        })
    elif sand == 'medium':
        reasons.append({
            "text": "Среднее содержание песка — зазор в пределах нормы",
            "direction": "neutral"
        })

    # Высокий газовый фактор — минимальный зазор (уменьшаем мёртвый объём)
    if gas == 'high':
        adjustments -= 1
        reasons.append({
            "text": "Высокий газовый фактор — минимальный зазор для уменьшения мёртвого объёма",
            "direction": "down"
        })
    elif gas == 'medium':
        reasons.append({
            "text": "Среднее содержание газа — рекомендуется минимальный зазор из допустимых",
            "direction": "neutral"
        })

    # Итоговая группа посадки с ограничением по допустимым
    recommended_fit = base_fit + adjustments
    recommended_fit = max(min(allowed), min(max(allowed), recommended_fit))

    fit_data = FIT_TABLE[recommended_fit]
    optimal_data = FIT_TABLE[base_fit]

    # Все допустимые группы с данными
    allowed_fits = []
    for f in allowed:
        fd = FIT_TABLE[f]
        allowed_fits.append({
            "fit":       f,
            "label":     f"Fit-{f}",
            "nominal":   fd["nominal"],
            "range_min": fd["range_min"],
            "range_max": fd["range_max"],
            "is_optimal":     f == base_fit,
            "is_recommended": f == recommended_fit,
        })

    return {
        "has_data":        True,
        "size_key":        size_key,
        "diam_mm":         diam_info["diam_mm"],
        "base_fit":        base_fit,
        "recommended_fit": recommended_fit,
        "nominal_mm":      fit_data["nominal"],
        "range_min":       fit_data["range_min"],
        "range_max":       fit_data["range_max"],
        "allowed_fits":    allowed_fits,
        "reasons":         reasons,

    }

def get_flow_recommendation(answers_dict):
    """
    Подбор оптимальных параметров насоса по требуемой подаче.
    Вход: только V_otkach_zhidkosti (м³/сут).
    
    Алгоритм (справочник 2.2):
    1. Перебираем все комбинации (ход × N × диаметр)
    2. Для каждой подходящей комбинации считаем "стоимость" —
       штрафуем за большой диаметр и высокое N сильнее, чем за длинный ход
    3. Возвращаем оптимальную комбинацию + все подходящие размеры насосов
    """
    import math

    # Таблица 10: условный размер → диаметр плунжера
    PUMP_SIZES = [
        {"size": "106", "d_inch": 1.0625, "d_mm": 27.0,  "nkt": ["60.3"]},
        {"size": "125", "d_inch": 1.25,   "d_mm": 31.8,  "nkt": ["60.3"]},
        {"size": "150", "d_inch": 1.5,    "d_mm": 38.1,  "nkt": ["73.0"]},
        {"size": "175", "d_inch": 1.75,   "d_mm": 44.5,  "nkt": ["73.0"]},
        {"size": "225", "d_inch": 2.25,   "d_mm": 57.2,  "nkt": ["73.0", "88.9"]},
        {"size": "275", "d_inch": 2.75,   "d_mm": 69.9,  "nkt": ["88.9"]},
    ]

    # Допустимые ходы плунжера (мм) — стандартный ряд
    STD_STROKES = [1800, 2500, 3000, 3500]
    # Допустимые числа качаний (ход/мин)
    STD_SPM     = [10, 12, 14]
    # Ходы для таблицы 10 (отображение)
    TABLE_STROKES = [1800, 2500, 3000, 3500]

    # Размеры насосов по типам для таблицы 9
    NKT_BY_SIZE = {
        "106": "60.3", "125": "60.3",
        "150": "73.0", "175": "73.0",
        "225": "88.9", "275": "88.9",
    }
    RH_SIZES = ["106", "125", "150", "175", "225"]  # вставные
    TH_SIZES = ["125", "175", "225", "275"]          # трубные

    volume_raw = answers_dict.get("V_otkach_zhidkosti", "")
    try:
        V = float(str(volume_raw).replace(",", ".")) if volume_raw else None
    except:
        V = None

    if V is None or V <= 0:
        return {"has_data": False}

    def calc_flow(d_inch, stroke_mm, spm):
        return 72.9 * 0.0001 * (d_inch ** 2) * (stroke_mm / 10.0) * spm

    # ── Перебор: ход → N → диаметр (приоритет как в справочнике) ──────
    # Штрафная функция: предпочитаем большой ход, средний N, малый диаметр
    # score = индекс_хода*0 + индекс_N*10 + индекс_диаметра*100
    # (меньше = лучше)
    best = None
    best_score = 999999
    candidates = []  # все подходящие комбинации

    for i_s, stroke in enumerate(STD_STROKES):
        for i_n, spm in enumerate(STD_SPM):
            for i_d, ps in enumerate(PUMP_SIZES):
                flow = calc_flow(ps["d_inch"], stroke, spm)
                if flow >= V:
                    score = i_s * 1 + i_n * 10 + i_d * 100
                    combo = {
                        "stroke_mm":  stroke,
                        "spm":        spm,
                        "pump":       ps,
                        "flow":       round(flow, 1),
                        "score":      score,
                        "excess_pct": round((flow / V - 1) * 100, 1),
                    }
                    candidates.append(combo)
                    if score < best_score:
                        best_score = score
                        best = combo

    if best is None:
        return {
            "has_data":   True,
            "V_required": V,
            "overflow":   True,
            "max_flow":   round(calc_flow(PUMP_SIZES[-1]["d_inch"], max(STD_STROKES), max(STD_SPM)), 1),
        }

    # ── Пояснение почему именно эта комбинация ────────────────────────
    steps = []

    # Шаг 1: хватает ли хода при минимальном диаметре и N=10?
    base_pump = PUMP_SIZES[0]
    base_spm  = 10
    step1_stroke = None
    for stroke in STD_STROKES:
        if calc_flow(base_pump["d_inch"], stroke, base_spm) >= V:
            step1_stroke = stroke
            break

    if step1_stroke:
        steps.append({
            "num": 1, "label": "Ход плунжера",
            "result": f"{step1_stroke} мм достаточно при N=10 и размере 106",
            "achieved": True, "is_decisive": True,
        })
        steps.append({"num": 2, "label": "Число качаний", "result": "Не требуется", "achieved": False, "is_decisive": False})
        steps.append({"num": 3, "label": "Диаметр насоса", "result": "Не требуется", "achieved": False, "is_decisive": False})
    else:
        steps.append({
            "num": 1, "label": "Ход плунжера",
            "result": f"Недостаточно даже при ходе {max(STD_STROKES)} мм и размере 106",
            "achieved": False, "is_decisive": False,
        })
        # Шаг 2: хватает ли N при максимальном ходе и минимальном диаметре?
        max_stroke = max(STD_STROKES)
        step2_spm = None
        for spm in STD_SPM:
            if calc_flow(base_pump["d_inch"], max_stroke, spm) >= V:
                step2_spm = spm
                break

        if step2_spm:
            steps.append({
                "num": 2, "label": "Число качаний",
                "result": f"N={step2_spm} ход/мин при ходе {max_stroke} мм и размере 106",
                "achieved": True, "is_decisive": True,
            })
            steps.append({"num": 3, "label": "Диаметр насоса", "result": "Не требуется", "achieved": False, "is_decisive": False})
        else:
            steps.append({
                "num": 2, "label": "Число качаний",
                "result": f"Недостаточно даже при N={max(STD_SPM)} и ходе {max_stroke} мм",
                "achieved": False, "is_decisive": False,
            })
            steps.append({
                "num": 3, "label": "Диаметр насоса",
                "result": f"Требуется размер {best['pump']['size']} ({best['pump']['d_mm']} мм)",
                "achieved": True, "is_decisive": True,
            })

    # ── Подходящие размеры насосов (все что обеспечивают подачу V) ────
    # при оптимальных ходе и N из best
    opt_stroke = best["stroke_mm"]
    opt_spm    = best["spm"]

    suitable_sizes = []
    for ps in PUMP_SIZES:
        flow = calc_flow(ps["d_inch"], opt_stroke, opt_spm)
        if flow >= V:
            suitable_sizes.append({
                "size":       ps["size"],
                "d_mm":       ps["d_mm"],
                "d_inch":     ps["d_inch"],
                "flow":       round(flow, 1),
                "excess_pct": round((flow / V - 1) * 100, 1),
                "nkt":        NKT_BY_SIZE.get(ps["size"], ""),
                "rh_ok":      ps["size"] in RH_SIZES,
                "th_ok":      ps["size"] in TH_SIZES,
                "is_optimal": ps["size"] == best["pump"]["size"],
            })

    # ── Таблица 10 при оптимальном N ─────────────────────────────────
    table_rows = []
    for ps in PUMP_SIZES:
        flows = [round(calc_flow(ps["d_inch"], s, opt_spm), 1) for s in TABLE_STROKES]
        table_rows.append({
            "size":           ps["size"],
            "d_mm":           ps["d_mm"],
            "flows":          flows,
            "is_suitable":    ps["size"] in [s["size"] for s in suitable_sizes],
            "is_optimal":     ps["size"] == best["pump"]["size"],
        })

    return {
        "has_data":       True,
        "overflow":       False,
        "V_required":     V,
        # оптимальная комбинация
        "best":           best,
        "opt_stroke":     opt_stroke,
        "opt_spm":        opt_spm,
        # пояснение
        "steps":          steps,
        # подходящие размеры
        "suitable_sizes": suitable_sizes,
        # таблица
        "table_rows":     table_rows,
        "table_strokes":  TABLE_STROKES,
        "opt_spm_label":  opt_spm,
        # формула
        "formula": (
            f"V = 72,9 × 0,0001 × {best['pump']['d_inch']}² × "
            f"{round(opt_stroke/10.0, 1)} × {opt_spm} = {best['flow']} м³/сут"
        ),
    }