import copy
import hashlib
import json
import os

from utils.json_generator import IntactJSONGenerator
from utils import json_generator_pure
from utils import company_config
from utils.company_validators import get_required_top_level_fields
from utils.company_postprocess import pipeline as company_postprocess_pipeline


def _make_generator(company: str, fields_config=None):
    """Build generator instance without calling external API setup."""
    generator = IntactJSONGenerator.__new__(IntactJSONGenerator)
    generator.company = company
    generator.fields_config = fields_config or {"fields": {}}
    generator.use_company_schema_validation = False
    return generator


def _load_json_config(filename: str) -> dict:
    root = os.path.join(os.path.dirname(__file__), "..", "config", filename)
    with open(root, encoding="utf-8") as f:
        return json.load(f)


def test_import_intact_json_generator():
    assert IntactJSONGenerator is not None


def test_validate_and_clean_json_for_intact_dates_and_membership_cleanup():
    fields_config = {
        "fields": {
            "applicant_information": {
                "fields": {
                    "date_of_birth": {"mode": "date"},
                }
            },
            "term": {
                "fields": {
                    "policy_effective_date": {"mode": "date"},
                }
            },
            "driver": {
                "fields": {
                    "g_class_date_licensed": {"mode": "date", "description": "G Class - Date Licensed in DD-MM-YYYY format"},
                    "request_date_time": {"mode": "date", "description": "MVR's Request Date/Time in DD-MM-YYYY format"},
                    "insurance_history_report_request_date": {
                        "mode": "date",
                        "description": "Insurance History Report Request Date in DD-MM-YYYY format",
                    },
                    "insured_without_interruption_since": {"mode": "date", "description": "Insured Without Interruption Since in YYYY-MM-DD format"},
                    "lapse_start": {"mode": "date", "description": "Lapse start date in YYYY-MM-DD format"},
                    "lapse_end": {"mode": "date", "description": "Lapse end date in YYYY-MM-DD format"},
                    "expiry_date": {"mode": "date", "description": "Expiry date in DD-MM-YYYY format"},
                }
            },
            "claim": {
                "fields": {
                    "date_of_loss": {"mode": "date", "description": "Date of loss in DD-MM-YYYY format"},
                }
            },
        }
    }
    generator = _make_generator("Intact_Auto", fields_config=fields_config)
    data = {
        "application_info": {
            "caa_membership": "No",
            "caa_membership_number": "",
        },
        "applicant_information": {
            "date_of_birth": "12/05/1970",
        },
        "term": {
            "policy_effective_date": "19-03-2026",
        },
        "driver": [
            {
                "licence_class": "G",
                "g_class_date_licensed": "2016-12-10",
                "request_date_time": "2026-03-14",
                "insurance_history_report_request_date": "2026-03-14",
                "insured_without_interruption_since": "2017-06-24",
                "expiry_date": "2026-06-24",
                "lapse_in_insurance": "No",
                "lapse_in_insurance_description": "Non-Payment",
                "lapse_start": "2024-10-18",
                "lapse_end": "2026-04-09",
            },
        ],
        "claim": {
            "has_claim": "No",
            "date_of_loss": ["2023-01-19", "2020-03-10"],
        },
        "interest": {
            "has_loan": "No",
            "type_of_interest": "Lienholder",
            "company_name": "Some Bank",
        },
    }

    cleaned = generator._validate_and_clean_json(copy.deepcopy(data), documents={})

    assert cleaned["applicant_information"]["date_of_birth"] == "1970-12-05"
    assert cleaned["term"]["policy_effective_date"] == "2026-03-19"
    assert cleaned["driver"][0]["g_class_date_licensed"] == "10-12-2016"
    assert cleaned["driver"][0]["MVR_request_date_time"] == "14-03-2026"
    assert "request_date_time" not in cleaned["driver"][0]
    assert cleaned["driver"][0]["insurance_history_report_request_date"] == "14-03-2026"
    assert cleaned["driver"][0]["insured_without_interruption_since"] == "2017-06-24"
    assert cleaned["driver"][0]["expiry_date"] == "24-06-2026"
    assert "lapse_in_insurance_description" not in cleaned["driver"][0]
    assert "lapse_start" not in cleaned["driver"][0]
    assert "lapse_end" not in cleaned["driver"][0]
    assert cleaned["claim"] == {"has_claim": "No"}
    assert cleaned["interest"] == {"has_loan": "No"}
    assert cleaned["application_info"] == {}


def test_validate_and_clean_json_for_intact_fills_broker_and_insured_since_defaults():
    fields_config = {
        "fields": {
            "term": {
                "fields": {
                    "policy_effective_date": {"mode": "date", "description": "Policy effective date in YYYY-MM-DD format"},
                }
            },
            "driver": {
                "fields": {
                    "insured_without_interruption_since": {
                        "mode": "date",
                        "description": "Insured Without Interruption Since in YYYY-MM-DD format",
                    },
                }
            },
            "insureds": {
                "fields": {
                    "insured_with_broker_since": {
                        "mode": "date",
                        "description": "Insured With Broker Since in YYYY-MM-DD format",
                    },
                }
            },
        }
    }
    generator = _make_generator("Intact_Auto", fields_config=fields_config)
    data = {
        "broker_information": {
            "broker_number": None,
            "edi_client_code": None,
        },
        "term": {
            "policy_effective_date": "19-03-2026",
        },
        "driver": [
            {
                "insurance_history_report_status": "Not Found",
                "insured_without_interruption_since": None,
            }
        ],
        "insureds": {
            "insured_with_broker_since": "",
        },
    }
    documents = {
        "Application": "Some header text... Broker Code :X40501 ... footer",
    }

    cleaned = generator._validate_and_clean_json(copy.deepcopy(data), documents=documents)

    assert cleaned["broker_information"]["broker_number"] == "40501"
    assert cleaned["driver"][0]["insured_without_interruption_since"] == "2026-03-19"
    assert cleaned["insureds"]["insured_with_broker_since"] == "2026-03-19"


def test_validate_and_clean_json_for_intact_sets_consent_date_to_earlier_mvr_vs_autoplus():
    fields_config = {
        "fields": {
            "driver": {
                "fields": {
                    "Consent_Date": {
                        "mode": "date",
                        "description": "Consent date in YYYY-MM-DD format",
                    },
                }
            }
        }
    }
    generator = _make_generator("Intact_Auto", fields_config=fields_config)
    data = {
        "driver": [
            {"licence_class": "G"},
            {"licence_class": "G2"},
        ]
    }
    documents = {
        "MVR_1": "*** MOTOR VEHICLE RECORD - 2026/04/08 ***",
        "Autoplus_1": "Report Date: 2026-04-10",
    }

    cleaned = generator._validate_and_clean_json(copy.deepcopy(data), documents=documents)

    assert cleaned["driver"][0]["Consent_Date"] == "2026-04-08"
    assert cleaned["driver"][1]["Consent_Date"] == "2026-04-08"


def test_validate_and_clean_json_for_intact_keeps_lapse_start_end_when_lapse_yes():
    fields_config = {
        "fields": {
            "driver": {
                "fields": {
                    "lapse_start": {"mode": "date", "description": "Lapse start date in YYYY-MM-DD format"},
                    "lapse_end": {"mode": "date", "description": "Lapse end date in YYYY-MM-DD format"},
                }
            }
        }
    }
    generator = _make_generator("Intact_Auto", fields_config=fields_config)
    data = {
        "driver": [
            {
                "lapse_in_insurance": "Yes",
                "lapse_in_insurance_description": "No Automobile",
                "lapse_start": "10/18/2024",
                "lapse_end": "04/09/2026",
            }
        ],
    }

    cleaned = generator._validate_and_clean_json(copy.deepcopy(data), documents={})

    assert cleaned["driver"][0]["lapse_start"] == "2024-10-18"
    assert cleaned["driver"][0]["lapse_end"] == "2026-04-09"
    assert cleaned["driver"][0]["lapse_in_insurance_description"] == "No Automobile"


def test_validate_and_clean_json_for_caa_normalizes_birth_dates():
    generator = _make_generator("CAA_Auto")
    data = {
        "applicant_information": {"date_of_birth": "1970-05-12"},
        "drivers_information": {
            "driver_1": {"date_of_birth": "1988-02-01"},
        },
        "vehicles_information": {},
        "application_info": {},
        "address": {},
    }

    cleaned = generator._validate_and_clean_json(copy.deepcopy(data), documents={})

    assert cleaned["applicant_information"]["date_of_birth"] == "05/12/1970"
    assert cleaned["drivers_information"]["driver_1"]["date_of_birth"] == "02/01/1988"


def test_validate_and_clean_json_for_caa_normalizes_effective_and_claim_dates():
    generator = _make_generator("CAA_Auto", fields_config=_load_json_config("caa_auto_fields_config.json"))
    data = {
        "applicant_information": {},
        "drivers_information": {
            "JOHN DOE": {
                "claims": [
                    {"date": "2019-06-15", "policy": "P1"},
                ],
            },
        },
        "vehicles_information": {},
        "application_info": {"effective_date": "03/01/2026"},
        "address": {},
    }

    cleaned = generator._validate_and_clean_json(copy.deepcopy(data), documents={})

    assert cleaned["application_info"]["effective_date"] == "2026-03-01"
    assert cleaned["drivers_information"]["JOHN DOE"]["claims"][0]["date"] == "06/15/2019"


def test_validate_and_clean_json_for_caa_defaults_km_at_purchase_to_zero():
    generator = _make_generator("CAA_Auto")
    data = {
        "applicant_information": {},
        "drivers_information": {},
        "application_info": {},
        "address": {},
        "vehicles_information": {
            "vehicle_1": {
                "km_at_purchase": None,
            },
            "vehicle_2": {},
        },
    }

    cleaned = generator._validate_and_clean_json(copy.deepcopy(data), documents={})

    assert cleaned["vehicles_information"]["vehicle_1"]["km_at_purchase"] == 0
    assert cleaned["vehicles_information"]["vehicle_2"]["km_at_purchase"] == 0


def test_apply_caa_vehicle_purchase_sanity_clears_km_when_duplicate_of_list_price():
    generator = _make_generator("CAA_Auto")
    data = {
        "vehicles_information": {
            "vehicle_1": {
                "km_at_purchase": "68984",
                "list_price_new": "68984",
            },
        },
    }
    _, fixes = generator._apply_caa_vehicle_purchase_sanity(data)
    assert fixes == 1
    v = data["vehicles_information"]["vehicle_1"]
    assert v["km_at_purchase"] is None
    assert v["list_price_new"] == "68984"


def test_validate_and_clean_json_for_caa_duplicate_km_list_price_becomes_zero_after_normalization():
    generator = _make_generator("CAA_Auto")
    data = {
        "applicant_information": {},
        "drivers_information": {},
        "application_info": {},
        "address": {},
        "vehicles_information": {
            "vehicle_1": {
                "purchase_condition": "New",
                "km_at_purchase": "68984",
                "list_price_new": "68984",
            },
        },
    }
    cleaned = generator._validate_and_clean_json(copy.deepcopy(data), documents={})
    v = cleaned["vehicles_information"]["vehicle_1"]
    assert v["list_price_new"] == "68984"
    assert v["km_at_purchase"] == 0


def test_validate_and_clean_json_for_property_keeps_structure_without_error():
    generator = _make_generator("CAA_property")
    data = {
        "applicant_information": {},
        "address": {},
        "application_info": {},
        "drivers_information": {},
        "vehicles_information": {},
        "coverages_information": [],
    }

    cleaned = generator._validate_and_clean_json(copy.deepcopy(data), documents={})

    assert isinstance(cleaned, dict)
    assert isinstance(cleaned["coverages_information"], list)


def test_delegate_helpers_match_pure_module():
    # parse_response_json
    wrapped_json = 'prefix {"a": 1, "b": "x"} suffix'
    assert IntactJSONGenerator._parse_response_json(wrapped_json) == json_generator_pure.parse_response_json(wrapped_json)

    # date helpers
    assert IntactJSONGenerator._format_to_mmddyyyy("1970-05-12") == json_generator_pure.format_to_mmddyyyy("1970-05-12")
    assert IntactJSONGenerator._format_to_yyyymmdd("19-03-2026") == json_generator_pure.format_to_yyyymmdd("19-03-2026")
    assert IntactJSONGenerator._format_to_yyyymmdd("2017-06") == json_generator_pure.format_to_yyyymmdd("2017-06")

    # scalar helpers
    assert IntactJSONGenerator._is_missing("  ") == json_generator_pure.is_missing("  ")
    assert IntactJSONGenerator._extract_digits_as_int("A-123") == json_generator_pure.extract_digits_as_int("A-123")
    assert IntactJSONGenerator._is_non_price_text("Private Driveway") == json_generator_pure.is_non_price_text("Private Driveway")


def test_company_postprocess_pipeline_order():
    class DummyGenerator:
        def __init__(self):
            self.company = "CAA_property"
            self.calls = []

        def _should_apply_caa_dob_normalization(self, _data):
            return True

        def _is_intact_company(self):
            return True

        def _normalize_dates_by_fields_config(self, data):
            self.calls.append("caa_cfg_dates")
            return data, 0

        def _normalize_caa_birth_dates(self, data):
            self.calls.append("caa_dob")
            data["a"] = 1
            return data, 1

        def _apply_caa_vehicle_purchase_sanity(self, data):
            self.calls.append("caa_purchase")
            return data, 0

        def _fix_vehicle_table_column_misalignment(self, data):
            self.calls.append("caa_vehicle")
            return data, 0

        def _apply_caa_output_normalization(self, data, _documents):
            self.calls.append("caa_output")
            data["b"] = 2
            return data

        def _normalize_intact_dates(self, data):
            self.calls.append("intact_dates")
            data["c"] = 3
            return data, 1

        def _remove_non_intact_membership_fields(self, data):
            self.calls.append("intact_membership")
            return data

        def _normalize_property_names(self, data):
            self.calls.append("property_names")
            return data

        def _normalize_property_structure(self, data):
            self.calls.append("property_structure")
            return data

        def _normalize_intact_structure(self, data):
            self.calls.append("intact_structure")
            return data

    dummy = DummyGenerator()
    out = company_postprocess_pipeline.run(dummy, {"start": True}, documents={})
    assert out["start"] is True
    assert out["a"] == 1
    assert out["b"] == 2
    assert out["c"] == 3
    assert dummy.calls == [
        "caa_cfg_dates",
        "caa_dob",
        "caa_purchase",
        "caa_vehicle",
        "caa_output",
        "intact_dates",
        "intact_membership",
        "intact_structure",
        "property_names",
        "property_structure",
    ]


def test_build_prompt_hash_is_stable_for_fixture():
    generator = _make_generator("Intact_Auto")
    prompt = generator._build_prompt({"quote": "abc", "application": "xyz"})
    digest = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    assert digest == "096f974cde5bd6e51a8975c91cb4e05d4fbb946049f4aaa9eec30853946108ba"


def test_company_routing_resolution():
    routing = {
        "company_suffix_patterns": ["_auto", "_property"],
        "legacy_aliases": {
            "caa": "caa_auto_fields_config.json",
            "intact": "intact_auto_fields_config.json",
        },
        "default_template": "{company_lower}_fields_config.json",
    }
    assert company_config.resolve_fields_config_name("CAA_Auto", routing) == "caa_auto_fields_config.json"
    assert company_config.resolve_fields_config_name("CAA_property", routing) == "caa_property_fields_config.json"
    assert company_config.resolve_fields_config_name("CAA", routing) == "caa_auto_fields_config.json"
    assert company_config.resolve_fields_config_name("Intact", routing) == "intact_auto_fields_config.json"
    assert company_config.resolve_fields_config_name("Aviva", routing) == "aviva_fields_config.json"


def test_company_schema_validation_toggle_keeps_legacy_by_default():
    generator = _make_generator(
        "Intact_Auto",
        fields_config={"fields": {"applicant_information": {"fields": {}}}},
    )
    cleaned = generator._validate_and_clean_json({}, documents={})
    assert "drivers_information" in cleaned
    assert "vehicles_information" in cleaned


def test_company_schema_validation_uses_fields_config_when_enabled():
    generator = _make_generator(
        "Intact_Auto",
        fields_config={
            "fields": {
                "applicant_information": {"fields": {}},
                "address": {"fields": {}},
                "term": {"fields": {}},
            }
        },
    )
    generator.use_company_schema_validation = True
    cleaned = generator._validate_and_clean_json({}, documents={})
    assert "applicant_information" in cleaned
    assert "address" in cleaned
    assert "term" in cleaned
    assert "drivers_information" not in cleaned


def test_intact_auto_promotes_additional_driver_identity_blocks():
    generator = _make_generator("Intact_Auto", fields_config={"fields": {}})
    data = {
        "application_info": {},
        "applicant_information": {
            "last_name": "GU",
            "first_name": "MIN",
        },
        "address": {
            "postal_code": "L6C2C5",
            "full_address": "168 TRAIL RIDGE LANE, MARKHAM, ON",
        },
        "driver": [
            {"licence_class": "G"},
            {
                "licence_class": "G",
                "last_name": "DOE",
                "first_name": "JANE",
                "gender": "Female",
                "date_of_birth": "1990-01-15",
                "marital_status": "Single",
                "postal_code": "M5V1A1",
                "full_address": "1 Example St, Toronto, ON",
            },
        ],
        "drivers_information": {},
        "vehicles_information": {},
    }
    cleaned = generator._validate_and_clean_json(copy.deepcopy(data), documents={})

    assert "last_name" not in cleaned["driver"][1]
    assert cleaned["driver_2_information"]["last_name"] == "DOE"
    assert cleaned["driver_2_information"]["first_name"] == "JANE"
    assert cleaned["driver_2_address"]["postal_code"] == "M5V1A1"
    assert cleaned["driver_2_address"]["full_address"] == "1 Example St, Toronto, ON"


def test_intact_auto_additional_driver_address_falls_back_to_root():
    generator = _make_generator("Intact_Auto", fields_config={"fields": {}})
    data = {
        "application_info": {},
        "applicant_information": {},
        "address": {
            "postal_code": "L6C2C5",
            "full_address": "168 TRAIL RIDGE LANE, MARKHAM, ON",
        },
        "driver": [
            {"licence_class": "G"},
            {
                "licence_class": "G",
                "last_name": "DOE",
                "first_name": "JANE",
                "gender": "Female",
                "date_of_birth": "1990-01-15",
                "marital_status": "Single",
            },
        ],
        "drivers_information": {},
        "vehicles_information": {},
    }
    cleaned = generator._validate_and_clean_json(copy.deepcopy(data), documents={})

    assert cleaned["driver_2_address"]["postal_code"] == "L6C2C5"
    assert cleaned["driver_2_address"]["full_address"] == "168 TRAIL RIDGE LANE, MARKHAM, ON"


def test_intact_auto_normalizes_single_risk_object_to_array():
    generator = _make_generator("Intact_Auto", fields_config={"fields": {}})
    data = {
        "risk": {
            "risk_type": "PPV",
            "serial_number": "2FMPK3J91MBA27618",
            "model": "2021 FORD EDGE SEL 4DR 2WD",
        }
    }

    cleaned = generator._validate_and_clean_json(copy.deepcopy(data), documents={})

    assert isinstance(cleaned["risk"], list)
    assert len(cleaned["risk"]) == 1
    assert cleaned["risk"][0]["serial_number"] == "2FMPK3J91MBA27618"


def test_intact_auto_claim_total_amount_paid_removes_trailing_zero_decimals():
    generator = _make_generator("Intact_Auto", fields_config={"fields": {}})
    data = {
        "claim": {
            "has_claim": "Yes",
            "total_amount_paid": ["3203.00", "1250.50", "0.00"],
        }
    }

    cleaned = generator._validate_and_clean_json(copy.deepcopy(data), documents={})

    assert cleaned["claim"]["total_amount_paid"] == ["3203", "1250", "0"]


def test_intact_auto_multi_risk_assignment_moves_common_fields_into_each_vehicle():
    generator = _make_generator("Intact_Auto", fields_config={"fields": {}})
    data = {
        "risk": [
            {"risk_type": "PPV", "serial_number": "VIN1"},
            {"risk_type": "PPV", "serial_number": "VIN2"},
        ],
        "assignment": {
            "vehicle_1": {
                "driver_1": {
                    "name": "A B",
                    "percentage_of_use": 100,
                }
            },
            "vehicle_2": {
                "driver_1": {
                    "name": "A B",
                    "percentage_of_use": 100,
                }
            },
            "type_of_use": "Pleasure",
            "km_toward_work": None,
            "annual_km": 10000,
            "annual_business_km": 0,
            "automobile_rented_or_leased_to_others": "No",
            "automobile_used_to_carry_passengers_for_compensation_or_hire": "No",
            "automobile_carry_explosives_or_radioactive_materials": "No",
        },
    }

    cleaned = generator._validate_and_clean_json(copy.deepcopy(data), documents={})

    assignment = cleaned["assignment"]
    assert "type_of_use" not in assignment
    assert "annual_km" not in assignment
    assert assignment["vehicle_1"]["type_of_use"] == "Pleasure"
    assert assignment["vehicle_1"]["annual_km"] == 10000
    assert assignment["vehicle_2"]["type_of_use"] == "Pleasure"
    assert assignment["vehicle_2"]["annual_km"] == 10000


def test_intact_auto_multi_risk_assignment_copies_vehicle1_fields_to_other_vehicles():
    generator = _make_generator("Intact_Auto", fields_config={"fields": {}})
    data = {
        "risk": [
            {"risk_type": "PPV", "serial_number": "VIN1"},
            {"risk_type": "PPV", "serial_number": "VIN2"},
        ],
        "assignment": {
            "vehicle_1": {
                "driver_1": {"name": "A B", "percentage_of_use": 100},
                "type_of_use": "Pleasure",
                "km_toward_work": None,
                "annual_km": 12000,
                "annual_business_km": 0,
                "automobile_rented_or_leased_to_others": "No",
                "automobile_used_to_carry_passengers_for_compensation_or_hire": "No",
                "automobile_carry_explosives_or_radioactive_materials": "No",
            },
            "vehicle_2": {
                "driver_1": {"name": "C D", "percentage_of_use": 100},
            },
        },
    }

    cleaned = generator._validate_and_clean_json(copy.deepcopy(data), documents={})
    v2 = cleaned["assignment"]["vehicle_2"]
    assert v2["type_of_use"] == "Pleasure"
    assert v2["annual_km"] == 12000
    assert v2["annual_business_km"] == 0
    assert v2["automobile_rented_or_leased_to_others"] == "No"
    assert v2["automobile_used_to_carry_passengers_for_compensation_or_hire"] == "No"
    assert v2["automobile_carry_explosives_or_radioactive_materials"] == "No"


def test_intact_auto_multi_risk_assignment_uses_per_vehicle_quote_blocks():
    generator = _make_generator("Intact_Auto", fields_config={"fields": {}})
    data = {
        "risk": [
            {"risk_type": "PPV", "serial_number": "VIN1"},
            {"risk_type": "PPV", "serial_number": "VIN2"},
        ],
        "assignment": {
            "vehicle_1": {
                "driver_1": {"name": "Maxiongyi Peng", "percentage_of_use": 100},
            },
            "vehicle_2": {
                "driver_1": {"name": "Maxiongyi Peng", "percentage_of_use": 100},
            },
            # Simulate model mistakenly outputting one shared set.
            "type_of_use": "Pleasure",
            "km_toward_work": 15,
            "annual_km": 15000,
            "annual_business_km": 0,
            "automobile_rented_or_leased_to_others": "No",
            "automobile_used_to_carry_passengers_for_compensation_or_hire": "No",
            "automobile_carry_explosives_or_radioactive_materials": "No",
        },
    }
    documents = {
        "Quote": """
Vehicle 1 of 2 | Private Passenger - 2021 MERCEDES-BENZ C43 4MATIC 4DR
Pleasure                         8000                    0
Primary Use                      Annual km               Business km              Daily km

Vehicle 2 of 2 | Private Passenger - 2013 MAZDA MX5 MIATA GS CONVERTIBLE
Pleasure                         15000                   15
Primary Use                      Annual km               Business km              Daily km
""",
    }

    cleaned = generator._validate_and_clean_json(copy.deepcopy(data), documents=documents)
    assignment = cleaned["assignment"]
    assert assignment["vehicle_1"]["type_of_use"] == "Pleasure"
    assert assignment["vehicle_1"]["annual_km"] == 8000
    assert assignment["vehicle_1"]["annual_business_km"] == 0
    assert assignment["vehicle_1"]["km_toward_work"] == 0
    assert assignment["vehicle_2"]["type_of_use"] == "Pleasure"
    assert assignment["vehicle_2"]["annual_km"] == 15000
    assert assignment["vehicle_2"]["annual_business_km"] == 0
    assert assignment["vehicle_2"]["km_toward_work"] == 15


def test_build_prompt_includes_strict_json_output_rules():
    generator = _make_generator("Intact_Auto")
    prompt = generator._build_prompt({"quote": "abc"})

    assert "Output ONLY a single valid JSON object." in prompt
    assert "For sections configured as arrays (for example `risk` in Intact Auto), ALWAYS output an array `[]`." in prompt


def test_build_prompt_caa_excludes_intact_auto_json_rules():
    generator = _make_generator("CAA_Auto", fields_config=_load_json_config("caa_auto_fields_config.json"))
    prompt = generator._build_prompt({"quote": "abc"})

    assert "## Intact Auto — JSON output (mandatory)" not in prompt
    assert "Output ONLY a single valid JSON object." not in prompt


def test_caa_vehicle_table_keeps_single_digit_daily_km_when_not_cylinders():
    """Regression: Pleasure + empty business_km + daily 8 must not be cleared as 'misalignment'."""
    generator = _make_generator("CAA_Auto", fields_config={"fields": {}})
    data = {
        "vehicles_information": {
            "vehicle_1": {
                "daily_km": "8",
                "business_km": "",
                "cylinders": "4",
            }
        }
    }
    dup = copy.deepcopy(data)
    _, fixes = generator._fix_vehicle_table_column_misalignment(dup)
    assert fixes == 0
    assert dup["vehicles_information"]["vehicle_1"]["daily_km"] == "8"


def test_caa_vehicle_table_clears_daily_km_when_same_as_cylinders():
    generator = _make_generator("CAA_Auto", fields_config={"fields": {}})
    data = {
        "vehicles_information": {
            "vehicle_1": {
                "daily_km": "4",
                "cylinders": "4",
            }
        }
    }
    dup = copy.deepcopy(data)
    _, fixes = generator._fix_vehicle_table_column_misalignment(dup)
    assert fixes == 1
    assert dup["vehicles_information"]["vehicle_1"]["daily_km"] is None


def test_caa_coapplicant_name_order_swaps_when_labeled_document_evidence_conflicts():
    generator = _make_generator("CAA_Auto", fields_config={"fields": {}})
    data = {
        "applicant_information": {},
        "drivers_information": {},
        "application_info": {},
        "address": {},
        "vehicles_information": {},
        "coapplicant_information": {
            "first_name": "RAJVINDER",
            "last_name": "KAUR",
        },
    }
    documents = {
        "Application": "Co-Applicant First Name: KAUR   Last Name: RAJVINDER",
    }

    cleaned = generator._validate_and_clean_json(copy.deepcopy(data), documents=documents)

    assert cleaned["coapplicant_information"]["first_name"] == "KAUR"
    assert cleaned["coapplicant_information"]["last_name"] == "RAJVINDER"


def test_caa_coapplicant_name_order_keeps_current_when_labels_match_current_mapping():
    generator = _make_generator("CAA_Auto", fields_config={"fields": {}})
    data = {
        "applicant_information": {},
        "drivers_information": {},
        "application_info": {},
        "address": {},
        "vehicles_information": {},
        "coapplicant_information": {
            "first_name": "RAJVINDER",
            "last_name": "KAUR",
        },
    }
    documents = {
        "Application": "Co-Applicant First Name: RAJVINDER   Last Name: KAUR",
    }

    cleaned = generator._validate_and_clean_json(copy.deepcopy(data), documents=documents)

    assert cleaned["coapplicant_information"]["first_name"] == "RAJVINDER"
    assert cleaned["coapplicant_information"]["last_name"] == "KAUR"


def test_caa_coapplicant_name_order_swaps_by_fullname_frequency_when_no_labels():
    generator = _make_generator("CAA_Auto", fields_config={"fields": {}})
    data = {
        "applicant_information": {},
        "drivers_information": {
            "RAJVINDER KAUR": {
                "first_name": "RAJVINDER",
                "last_name": "KAUR",
            },
        },
        "driver_list": ["RAJVINDER KAUR"],
        "application_info": {},
        "address": {},
        "vehicles_information": {
            "V1": {"drivers": ["RAJVINDER KAUR (Occ)"]},
        },
        "coapplicant_information": {
            "first_name": "RAJVINDER",
            "last_name": "KAUR",
        },
    }
    documents = {
        "Quote": "Insured: KAUR RAJVINDER; Driver: KAUR RAJVINDER; Additional: KAUR RAJVINDER",
    }

    cleaned = generator._validate_and_clean_json(copy.deepcopy(data), documents=documents)

    assert cleaned["coapplicant_information"]["first_name"] == "KAUR"
    assert cleaned["coapplicant_information"]["last_name"] == "RAJVINDER"
    assert cleaned["driver_list"] == ["KAUR RAJVINDER"]
    assert "KAUR RAJVINDER" in cleaned["drivers_information"]
    assert cleaned["vehicles_information"]["V1"]["drivers"] == ["KAUR RAJVINDER (Occ)"]


def test_get_required_top_level_fields_from_config():
    fallback = ["applicant_information", "drivers_information"]
    fields_config = {"fields": {"a": {}, "b": {}}}
    assert get_required_top_level_fields("Intact_Auto", fields_config, fallback) == ["a", "b"]


def test_get_required_top_level_fields_fallback_when_missing_fields():
    fallback = ["applicant_information", "drivers_information"]
    assert get_required_top_level_fields("Intact_Auto", {}, fallback) == fallback
