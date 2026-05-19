from django.test import TestCase
from .services import (
    get_pump_recommendation,
    get_material_recommendation,
    get_cylinder_recommendation,
    get_fit_recommendation,
    get_flow_recommendation,
)


# ══════════════════════════════════════════════════════════════════════════════
# ВСПОМОГАТЕЛЬНЫЕ ДАННЫЕ
# ══════════════════════════════════════════════════════════════════════════════

def base_answers(**overrides):
    """Базовый набор ответов клиента. Переопределяйте нужные поля через kwargs."""
    defaults = {
        "glubina_pogruzhenia":  "1200",
        "V_otkach_zhidkosti":   "30",
        "type_skvazhina":       "straight",
        "gas_factor":           "low",
        "sand_content":         "none",
        "corr_h2s":             "none",
        "corr_co2":             "none",
        "corr_saltwater":       "none",
        "corr_oxygen":          "none",
        "oil_level":            "low",
        "viscosity":            "",
        "inner_diameter":       "125",
        "plunger_length":       "",
        "nkt_diameter":         "73.0",
    }
    defaults.update(overrides)
    return defaults


# ══════════════════════════════════════════════════════════════════════════════
# ТЕСТЫ: get_pump_recommendation
# ══════════════════════════════════════════════════════════════════════════════

class PumpRecommendationTests(TestCase):

    def test_has_data_when_depth_given(self):
        """Если глубина указана — has_data=True."""
        result = get_pump_recommendation(base_answers())
        self.assertTrue(result["has_data"])

    def test_has_data_false_when_no_depth_no_volume(self):
        """Если ни глубина ни объём не указаны — has_data=False."""
        result = get_pump_recommendation(base_answers(
            glubina_pogruzhenia="",
            V_otkach_zhidkosti="",
        ))
        self.assertFalse(result["has_data"])

    def test_returns_four_pumps(self):
        """Всегда возвращает четыре типа насосов."""
        result = get_pump_recommendation(base_answers())
        codes = [p["code"] for p in result["pumps"]]
        self.assertIn("TH",  codes)
        self.assertIn("RHA", codes)
        self.assertIn("RHB", codes)
        self.assertIn("RHT", codes)

    def test_high_sand_favors_rha(self):
        """Высокое содержание песка — RHA должен получить бонус."""
        result = get_pump_recommendation(base_answers(sand_content="high"))
        rha = next(p for p in result["pumps"] if p["code"] == "RHA")
        self.assertGreater(rha["score"], 50)
        rha_reasons = [r["text"] for r in rha["reasons"]]
        self.assertTrue(any("песка" in r.lower() for r in rha_reasons))

    def test_high_gas_penalizes_th(self):
        """Высокий газовый фактор — TH должен получить штраф (score=0)."""
        result = get_pump_recommendation(base_answers(gas_factor="high"))
        th = next(p for p in result["pumps"] if p["code"] == "TH")
        self.assertEqual(th["score"], 0)

    def test_th_recommended_for_shallow_high_flow(self):
        """Малая глубина + высокий дебит — TH рекомендован."""
        result = get_pump_recommendation(base_answers(
            glubina_pogruzhenia="500",
            V_otkach_zhidkosti="150",
            gas_factor="low",
        ))
        th = next(p for p in result["pumps"] if p["code"] == "TH")
        self.assertEqual(th["verdict"], "recommended")

    def test_rha_not_recommended_deep_well(self):
        """Глубина свыше 2100 м — RHA получает штраф -1000 и не рекомендован."""
        result = get_pump_recommendation(base_answers(glubina_pogruzhenia="2500"))
        rha = next(p for p in result["pumps"] if p["code"] == "RHA")
        self.assertEqual(rha["verdict"], "not_recommended")

    def test_manjetnoe_triggered_by_gas(self):
        """Средний газовый фактор — рекомендуется манжетное крепление."""
        result = get_pump_recommendation(base_answers(gas_factor="medium"))
        self.assertTrue(result["manjetnoe"])

    def test_manjetnoe_triggered_by_h2s(self):
        """H2S коррозия — рекомендуется манжетное крепление."""
        result = get_pump_recommendation(base_answers(corr_h2s="high"))
        self.assertTrue(result["manjetnoe"])

    def test_no_manjetnoe_clean_conditions(self):
        """Чистые условия — манжетное крепление не нужно."""
        result = get_pump_recommendation(base_answers())
        self.assertFalse(result["manjetnoe"])

    def test_best_is_first_in_sorted_list(self):
        """best — всегда насос с наибольшим score."""
        result = get_pump_recommendation(base_answers())
        best_score = result["best"]["score"]
        for pump in result["pumps"]:
            self.assertLessEqual(pump["score"], best_score)

    def test_scores_not_negative(self):
        """Баллы никогда не отрицательные."""
        result = get_pump_recommendation(base_answers(
            gas_factor="high",
            glubina_pogruzhenia="2500",
        ))
        for pump in result["pumps"]:
            self.assertGreaterEqual(pump["score"], 0)


# ══════════════════════════════════════════════════════════════════════════════
# ТЕСТЫ: get_material_recommendation
# ══════════════════════════════════════════════════════════════════════════════

class MaterialRecommendationTests(TestCase):

    def test_no_corrosion_has_data(self):
        """Некоррозионная среда — has_data=True."""
        result = get_material_recommendation(base_answers())
        self.assertTrue(result["has_data"])

    def test_no_corrosion_returns_rows(self):
        """Некоррозионная среда — возвращает хотя бы одну строку."""
        result = get_material_recommendation(base_answers())
        self.assertGreater(len(result["rows"]), 0)

    def test_strong_h2s_recommends_tc3(self):
        """Сильная H2S — клапаны ST рекомендованы (A-рейтинг)."""
        result = get_material_recommendation(base_answers(corr_h2s="high"))
        val_summary = result["summary"]["val"]
        materials = [m["material"] for m in val_summary]
        self.assertIn("Кобальтовый сплав ST", materials)

    def test_strong_h2s_excludes_ss_cylinder(self):
        """Сильная H2S — цилиндр CR получает X-рейтинг (неприменим)."""
        result = get_material_recommendation(base_answers(corr_h2s="high"))
        # summary должен показывать наихудший материал
        cyl_summary = result["summary"]["cyl"]
        # CR при сильной H2S имеет X — значит в summary его не будет с высоким приоритетом
        for mat in cyl_summary:
            self.assertNotEqual(mat["code"], "A")  # лучшего нет, только C или X

    def test_oxygen_environment_detected(self):
        """Кислородосодержащая среда обрабатывается."""
        result = get_material_recommendation(base_answers(corr_oxygen="yes"))
        self.assertTrue(result["has_data"])
        labels = [r["label"] for r in result["rows"]]
        self.assertTrue(any("кислород" in l.lower() for l in labels))

    def test_summary_exists_when_has_data(self):
        """Если has_data=True — summary всегда присутствует."""
        result = get_material_recommendation(base_answers(corr_h2s="medium"))
        self.assertIsNotNone(result["summary"])
        self.assertIn("cyl", result["summary"])
        self.assertIn("plu", result["summary"])
        self.assertIn("val", result["summary"])

    def test_combined_h2s_co2_strict(self):
        """H2S + CO2 одновременно — самые строгие требования к материалам."""
        result_combined = get_material_recommendation(base_answers(
            corr_h2s="high", corr_co2="high"
        ))
        result_h2s_only = get_material_recommendation(base_answers(corr_h2s="high"))
        # При комбинации приоритет summary не выше чем при одиночной среде
        combined_priority = result_combined["summary"]["val"][0]["priority"]
        h2s_priority = result_h2s_only["summary"]["val"][0]["priority"]
        self.assertLessEqual(combined_priority, h2s_priority)


# ══════════════════════════════════════════════════════════════════════════════
# ТЕСТЫ: get_cylinder_recommendation
# ══════════════════════════════════════════════════════════════════════════════

class CylinderRecommendationTests(TestCase):

    def test_has_data_with_depth(self):
        """Глубина указана — has_data=True."""
        result = get_cylinder_recommendation(base_answers())
        self.assertTrue(result["has_data"])

    def test_has_data_false_no_depth_no_stroke(self):
        """Нет ни глубины ни хода — has_data=False."""
        result = get_cylinder_recommendation(base_answers(
            glubina_pogruzhenia="",
            plunger_length="",
        ))
        self.assertFalse(result["has_data"])

    def test_plunger_4ft_for_shallow(self):
        """Глубина до 1500 м — плунжер 4 фута."""
        result = get_cylinder_recommendation(base_answers(glubina_pogruzhenia="1200"))
        self.assertEqual(result["P"], 4)

    def test_plunger_5ft_for_medium_depth(self):
        """Глубина 1500–2000 м — плунжер 5 футов."""
        result = get_cylinder_recommendation(base_answers(glubina_pogruzhenia="1800"))
        self.assertEqual(result["P"], 5)

    def test_plunger_6ft_for_deep(self):
        """Глубина свыше 2000 м — плунжер 6 футов."""
        result = get_cylinder_recommendation(base_answers(glubina_pogruzhenia="2200"))
        self.assertEqual(result["P"], 6)

    def test_plunger_note_contains_depth_info(self):
        """Сообщение о плунжере содержит информацию о глубине, не 'не указана'."""
        result = get_cylinder_recommendation(base_answers(glubina_pogruzhenia="1200"))
        self.assertNotIn("не указана", result["plunger_note"])
        self.assertIn("1500", result["plunger_note"])

    def test_plunger_note_default_when_no_depth(self):
        """Глубина не указана — сообщение об умолчании."""
        result = get_cylinder_recommendation(base_answers(
            glubina_pogruzhenia="",
            plunger_length="3000",
        ))
        self.assertIn("не указана", result["plunger_note"])

    def test_results_when_pump_selected(self):
        """Если тип насоса выбран — возвращает варианты цилиндров."""
        answers = base_answers(pump_type_full="25-175 RHBM")
        result = get_cylinder_recommendation(answers)
        self.assertTrue(result["has_data"])
        self.assertGreater(len(result["results"]), 0)

    def test_results_max_three(self):
        """Вариантов цилиндра не более трёх."""
        answers = base_answers(pump_type_full="25-175 RHBM")
        result = get_cylinder_recommendation(answers)
        self.assertLessEqual(len(result["results"]), 3)

    def test_cylinder_covers_stroke(self):
        """Подобранный цилиндр обеспечивает ход не меньше требуемого."""
        answers = base_answers(pump_type_full="25-175 RHBM", plunger_length="3000")
        result = get_cylinder_recommendation(answers)
        for r in result["results"]:
            self.assertGreaterEqual(r["stroke_mm"], 3000)

    def test_no_pump_returns_range(self):
        """Без выбранного насоса возвращает диапазон req_range."""
        result = get_cylinder_recommendation(base_answers())
        self.assertIsNone(result["K"])
        self.assertIn("req_range", result)

    def test_flow_rec_stroke_takes_priority(self):
        """Ход из flow_rec имеет приоритет над plunger_length в ответах."""
        flow_rec = {
            "has_data": True,
            "overflow": False,
            "opt_stroke": 2500,
        }
        answers = base_answers(plunger_length="3500", pump_type_full="25-175 RHBM")
        result = get_cylinder_recommendation(answers, flow_rec=flow_rec)
        self.assertEqual(result["stroke_mm"], 2500)


# ══════════════════════════════════════════════════════════════════════════════
# ТЕСТЫ: get_fit_recommendation
# ══════════════════════════════════════════════════════════════════════════════

class FitRecommendationTests(TestCase):

    def test_has_data_with_diameter(self):
        """Диаметр указан — has_data=True."""
        result = get_fit_recommendation(base_answers(inner_diameter="125"))
        self.assertTrue(result["has_data"])

    def test_has_data_false_no_diameter(self):
        """Диаметр не указан — has_data=False."""
        result = get_fit_recommendation(base_answers(inner_diameter=""))
        self.assertFalse(result["has_data"])

    def test_base_fit_for_125(self):
        """Для размера 125 базовая посадка — Fit-2."""
        result = get_fit_recommendation(base_answers(inner_diameter="125"))
        self.assertEqual(result["base_fit"], 2)

    def test_base_fit_for_275(self):
        """Для размера 275 базовая посадка — Fit-3."""
        result = get_fit_recommendation(base_answers(inner_diameter="275"))
        self.assertEqual(result["base_fit"], 3)

    def test_high_viscosity_increases_fit(self):
        """Высокая вязкость — зазор увеличивается на одну группу."""
        result_normal = get_fit_recommendation(base_answers(
            inner_diameter="125", viscosity=""
        ))
        result_viscous = get_fit_recommendation(base_answers(
            inner_diameter="125", viscosity="20"
        ))
        self.assertGreater(
            result_viscous["recommended_fit"],
            result_normal["recommended_fit"]
        )

    def test_high_sand_decreases_fit(self):
        """Высокое содержание песка — зазор уменьшается."""
        result_no_sand = get_fit_recommendation(base_answers(
            inner_diameter="225", sand_content="none"
        ))
        result_sand = get_fit_recommendation(base_answers(
            inner_diameter="225", sand_content="high"
        ))
        self.assertLessEqual(
            result_sand["recommended_fit"],
            result_no_sand["recommended_fit"]
        )

    def test_high_gas_decreases_fit(self):
        """Высокий газовый фактор — зазор уменьшается."""
        result_no_gas = get_fit_recommendation(base_answers(
            inner_diameter="225", gas_factor="low"
        ))
        result_gas = get_fit_recommendation(base_answers(
            inner_diameter="225", gas_factor="high"
        ))
        self.assertLessEqual(
            result_gas["recommended_fit"],
            result_no_gas["recommended_fit"]
        )

    def test_fit_within_allowed_range(self):
        """Рекомендованная посадка всегда в пределах допустимого диапазона."""
        for size in ["106", "125", "150", "175", "225", "275"]:
            for sand in ["none", "medium", "high"]:
                for gas in ["low", "medium", "high"]:
                    result = get_fit_recommendation(base_answers(
                        inner_diameter=size, sand_content=sand, gas_factor=gas
                    ))
                    allowed = [f["fit"] for f in result["allowed_fits"]]
                    self.assertIn(result["recommended_fit"], allowed,
                        msg=f"size={size}, sand={sand}, gas={gas}")

    def test_allowed_fits_not_empty(self):
        """Список допустимых групп посадки не пустой."""
        result = get_fit_recommendation(base_answers())
        self.assertGreater(len(result["allowed_fits"]), 0)

    def test_size_extracted_from_full_designation(self):
        """Размер корректно извлекается из полного обозначения типа '25-175'."""
        result = get_fit_recommendation(base_answers(inner_diameter="25-175"))
        self.assertTrue(result["has_data"])
        self.assertEqual(result["size_key"], "175")


# ══════════════════════════════════════════════════════════════════════════════
# ТЕСТЫ: get_flow_recommendation
# ══════════════════════════════════════════════════════════════════════════════

class FlowRecommendationTests(TestCase):

    def test_has_data_with_volume(self):
        """Объём откачки указан — has_data=True."""
        result = get_flow_recommendation(base_answers(V_otkach_zhidkosti="30"))
        self.assertTrue(result["has_data"])

    def test_has_data_false_no_volume(self):
        """Объём не указан — has_data=False."""
        result = get_flow_recommendation(base_answers(V_otkach_zhidkosti=""))
        self.assertFalse(result["has_data"])

    def test_flow_meets_required(self):
        """Подобранная подача не меньше требуемой."""
        result = get_flow_recommendation(base_answers(V_otkach_zhidkosti="30"))
        self.assertGreaterEqual(result["best"]["flow"], 30)

    def test_priority_stroke_before_spm(self):
        """Приоритет: сначала ход, потом число качаний."""
        result = get_flow_recommendation(base_answers(V_otkach_zhidkosti="15"))
        self.assertFalse(result["overflow"])
        # При малой подаче должен подобраться минимальный ход с N=10
        self.assertEqual(result["opt_spm"], 10)

    def test_priority_spm_before_diameter(self):
        """Если ход 3500 недостаточен при N=10 — увеличивается N, не диаметр."""
        # Подача которая требует N>10 но не требует большого диаметра
        result = get_flow_recommendation(base_answers(V_otkach_zhidkosti="25"))
        self.assertFalse(result["overflow"])
        # Диаметр должен остаться минимальным (106) если N справляется
        if result["opt_spm"] <= 14:
            self.assertEqual(result["best"]["pump"]["size"], "106")

    def test_overflow_for_huge_volume(self):
        """Очень большой объём — overflow=True."""
        result = get_flow_recommendation(base_answers(V_otkach_zhidkosti="99999"))
        self.assertTrue(result["overflow"])

    def test_custom_spm_respected(self):
        """Число качаний заданное вручную используется в расчёте."""
        result = get_flow_recommendation(
            base_answers(V_otkach_zhidkosti="30"),
            custom_spm=12
        )
        self.assertEqual(result["opt_spm"], 12)

    def test_custom_eta_reduces_flow(self):
        """Коэффициент подачи η < 1 увеличивает требуемый диаметр или ход."""
        result_ideal = get_flow_recommendation(
            base_answers(V_otkach_zhidkosti="30"),
            custom_eta=1.0
        )
        result_eta = get_flow_recommendation(
            base_answers(V_otkach_zhidkosti="30"),
            custom_eta=0.7
        )
        # При η=0.7 нужен больший насос — score должен быть выше
        self.assertGreaterEqual(
            result_eta["best"]["score"],
            result_ideal["best"]["score"]
        )

    def test_eta_clamped_to_valid_range(self):
        """Коэффициент подачи зажимается в диапазон (0, 1]."""
        result = get_flow_recommendation(
            base_answers(V_otkach_zhidkosti="30"),
            custom_eta=1.5  # выше максимума
        )
        self.assertEqual(result["eta"], 1.0)

    def test_suitable_sizes_all_cover_required(self):
        """Все подходящие размеры обеспечивают требуемую подачу."""
        result = get_flow_recommendation(base_answers(V_otkach_zhidkosti="30"))
        for s in result["suitable_sizes"]:
            self.assertGreaterEqual(s["flow"], 30)

    def test_optimal_size_is_smallest_sufficient(self):
        """Оптимальный размер — наименьший из достаточных."""
        result = get_flow_recommendation(base_answers(V_otkach_zhidkosti="20"))
        optimal = next(s for s in result["suitable_sizes"] if s["is_optimal"])
        # Все остальные подходящие размеры должны быть >= оптимального
        sizes_order = ["106", "125", "150", "175", "225", "275"]
        opt_idx = sizes_order.index(optimal["size"])
        for s in result["suitable_sizes"]:
            self.assertGreaterEqual(sizes_order.index(s["size"]), opt_idx)

    def test_formula_string_present(self):
        """Строка с формулой присутствует в результате."""
        result = get_flow_recommendation(base_answers(V_otkach_zhidkosti="30"))
        self.assertIn("formula", result)
        self.assertIn("72,9", result["formula"])

    def test_steps_has_three_items(self):
        """Блок шагов всегда содержит три пункта."""
        result = get_flow_recommendation(base_answers(V_otkach_zhidkosti="30"))
        self.assertEqual(len(result["steps"]), 3)

    def test_exactly_one_decisive_step(self):
        """Ровно один шаг помечен как решающий (is_decisive=True)."""
        result = get_flow_recommendation(base_answers(V_otkach_zhidkosti="30"))
        decisive = [s for s in result["steps"] if s["is_decisive"]]
        self.assertEqual(len(decisive), 1)