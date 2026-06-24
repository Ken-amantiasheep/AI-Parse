import copy
import hashlib
import json
import os

from utils.json_generator import IntactJSONGenerator
from utils import json_generator_pure
from utils import company_config
from utils.company_validators import get_required_top_level_fields
from utils.company_postprocess import pipeline as company_postprocess_pipeline
from datetime import date

from utils.company_postprocess.intact_auto import (
    _build_mvr_name_index,
    _compute_years_with_previous_insurer,
    _extract_lienholders_by_auto_no,
    _normalize_intact_applicant_information,
    _parse_mvr_name,
    _parse_vertical_usage_block,
)


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
        "risk": [
            {
                "interest": {
                    "has_loan": "No",
                    "type_of_interest": "Lienholder",
                    "company_name": "Some Bank",
                }
            }
        ],
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
    assert "non_payment_company" not in cleaned["driver"][0]
    assert cleaned["claim"] == {"has_claim": "No"}
    assert cleaned["risk"][0]["interest"] == {"has_loan": "No"}
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


def test_intact_insured_with_broker_since_uses_quote_brokerage_insured_date():
    generator = _make_generator("Intact_Auto", fields_config={"fields": {}})
    data = {
        "application_info": {},
        "term": {"policy_effective_date": "2026-04-22"},
        "insureds": {},
        "driver": [{"licence_class": "G"}],
        "drivers_information": {},
        "vehicles_information": {},
    }
    documents = {
        "Quote": "Brokerage Insured  03/15/2020\nTotal Premium 1200",
    }
    cleaned = generator._validate_and_clean_json(copy.deepcopy(data), documents=documents)
    assert cleaned["insureds"]["insured_with_broker_since"] == "2020-03-15"


def test_intact_insured_with_broker_since_falls_back_to_effective_when_brokerage_insured_empty():
    generator = _make_generator("Intact_Auto", fields_config={"fields": {}})
    data = {
        "application_info": {},
        "term": {"policy_effective_date": "2026-04-22"},
        "insureds": {"insured_with_broker_since": "2019-01-01"},
        "driver": [{"licence_class": "G"}],
        "drivers_information": {},
        "vehicles_information": {},
    }
    documents = {
        "Quote": "Brokerage Insured\nPolicy Effective 2026-04-22",
    }
    cleaned = generator._validate_and_clean_json(copy.deepcopy(data), documents=documents)
    assert cleaned["insureds"]["insured_with_broker_since"] == "2026-04-22"


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


def test_validate_and_clean_json_for_intact_consent_date_matches_per_driver_mvr():
    """When multiple MVR documents are provided, each driver should use the upper-right
    header date from THEIR OWN MVR (matched by driver name), not the global earliest."""
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
        "applicant_information": {
            "first_name": "NAVDEEP",
            "last_name": "SINGH",
        },
        "driver": [
            {"licence_class": "G2"},
            {
                "first_name": "HARPREET",
                "last_name": "KAUR",
                "licence_class": "G2",
            },
        ],
    }
    documents = {
        "MVR_1": (
            "*** MOTOR VEHICLE RECORD - 2026/04/07 ***\n"
            "Name: SINGH, NAVDEEP\n"
            "Licence: N09080000891124\n"
        ),
        "MVR_2": (
            "*** MOTOR VEHICLE RECORD - 2026/04/22 ***\n"
            "Name: KAUR, HARPREET\n"
            "Licence: H06550000915417\n"
        ),
        "Autoplus_1": "Report Date: 2026-04-25",
    }

    cleaned = generator._validate_and_clean_json(copy.deepcopy(data), documents=documents)

    assert cleaned["driver"][0]["Consent_Date"] == "2026-04-07"
    assert cleaned["driver"][1]["Consent_Date"] == "2026-04-22"


def test_validate_and_clean_json_for_intact_consent_date_picks_earlier_autoplus_per_driver():
    """Per-driver MVR header date, but if AutoPlus Report Date is earlier, it wins."""
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
        "applicant_information": {
            "first_name": "NAVDEEP",
            "last_name": "SINGH",
        },
        "driver": [
            {"licence_class": "G2"},
            {
                "first_name": "HARPREET",
                "last_name": "KAUR",
                "licence_class": "G2",
            },
        ],
    }
    documents = {
        "MVR_1": (
            "*** MOTOR VEHICLE RECORD - 2026/04/07 ***\n"
            "Name: SINGH, NAVDEEP\n"
        ),
        "MVR_2": (
            "*** MOTOR VEHICLE RECORD - 2026/04/22 ***\n"
            "Name: KAUR, HARPREET\n"
        ),
        "Autoplus_1": "Report Date: 2026-04-05",
    }

    cleaned = generator._validate_and_clean_json(copy.deepcopy(data), documents=documents)

    # AutoPlus (2026-04-05) is earlier than both MVR header dates, so both drivers fall back to AutoPlus.
    assert cleaned["driver"][0]["Consent_Date"] == "2026-04-05"
    assert cleaned["driver"][1]["Consent_Date"] == "2026-04-05"


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


def test_validate_and_clean_json_for_intact_property_keeps_structure_without_error():
    generator = _make_generator("Intact_property")
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

        def _is_intact_auto_company(self):
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


def test_company_postprocess_pipeline_intact_property_does_not_use_caa_property_structure():
    class DummyGenerator:
        def __init__(self):
            self.company = "Intact_property"
            self.calls = []

        def _should_apply_caa_dob_normalization(self, _data):
            return False

        def _is_intact_auto_company(self):
            return False

        def _normalize_property_names(self, data):
            self.calls.append("property_names")
            return data

        def _normalize_property_structure(self, data):
            self.calls.append("property_structure")
            return data

        def _normalize_caa_property_structure(self, data):
            self.calls.append("caa_property_structure")
            return data

    dummy = DummyGenerator()
    out = company_postprocess_pipeline.run(dummy, {"start": True}, documents={})
    assert out["start"] is True
    assert dummy.calls == [
        "property_names",
        "property_structure",
    ]


def test_build_prompt_hash_is_stable_for_fixture():
    generator = _make_generator("Intact_Auto")
    prompt = generator._build_prompt({"quote": "abc", "application": "xyz"})
    digest = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    assert digest == "2ac55a1594ce6509fd00584794dba8878eabd01259939db98c0655217061ad4a"


def test_company_routing_resolution():
    routing = {
        "company_suffix_patterns": ["_auto", "_property"],
        "legacy_aliases": {
            "caa": "caa_auto_fields_config.json",
            "intact": "intact_auto_fields_config.json",
            "intact_property": "intact_property_fields_config.json",
        },
        "default_template": "{company_lower}_fields_config.json",
    }
    assert company_config.resolve_fields_config_name("CAA_Auto", routing) == "caa_auto_fields_config.json"
    assert company_config.resolve_fields_config_name("CAA_property", routing) == "caa_property_fields_config.json"
    assert company_config.resolve_fields_config_name("Intact_property", routing) == "intact_property_fields_config.json"
    assert company_config.resolve_fields_config_name("CAA", routing) == "caa_auto_fields_config.json"
    assert company_config.resolve_fields_config_name("Intact", routing) == "intact_auto_fields_config.json"
    assert company_config.resolve_fields_config_name("Aviva", routing) == "aviva_fields_config.json"


def test_intact_property_tenant_risk_template_is_independent():
    import json
    from pathlib import Path

    cfg = json.loads(
        Path("config/intact_property_fields_config.json").read_text(encoding="utf-8")
    )
    tenant_cfg = json.loads(
        Path("config/intact_property/risk_tenant_fields.json").read_text(encoding="utf-8")
    )
    condo_cfg = json.loads(
        Path("config/intact_property/risk_condominium_fields.json").read_text(encoding="utf-8")
    )

    fbrt = cfg["fields"]["risk"]["fields_by_risk_type"]
    assert "Tenant" in fbrt
    assert fbrt["Tenant"]["description"] == "Independent template for Tenant only."
    assert tenant_cfg["description"] == fbrt["Tenant"]["description"]
    assert tenant_cfg["fields"].keys() == fbrt["Tenant"]["fields"].keys()

    # Copied from condo for now, but stored in separate files for independent edits.
    assert tenant_cfg["fields"].keys() == condo_cfg["fields"].keys()
    assert "Tenant" in tenant_cfg["fields"]["fire_hydrant_within_300m"]["extraction_logic"]
    assert "Condominium" not in tenant_cfg["fields"]["fire_hydrant_within_300m"]["extraction_logic"]

    generator = _make_generator(
        "Intact_property",
        fields_config=_load_json_config("intact_property_fields_config.json"),
    )
    prompt = generator._build_prompt({})
    assert "Template for risk_type = Tenant:" in prompt
    assert "Default to 'Yes' for Tenant unless explicit contrary evidence" in prompt


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
                "term": {"fields": {}},
            }
        },
    )
    generator.use_company_schema_validation = True
    cleaned = generator._validate_and_clean_json({}, documents={})
    assert "applicant_information" in cleaned
    assert "address" not in cleaned
    assert "term" in cleaned
    assert "drivers_information" not in cleaned


def test_parse_mvr_name_three_formats():
    assert _parse_mvr_name("SINGH, NAVDEEP") == ("SINGH", "NAVDEEP")
    assert _parse_mvr_name("WANG, AI, LEE") == ("WANG", "AI")
    assert _parse_mvr_name("MADONNA") == ("MADONNA", "MADONNA")
    assert _parse_mvr_name("MADONNA,") == ("MADONNA", "MADONNA")
    assert _parse_mvr_name("SMITH, ") == ("SMITH", "SMITH")
    assert _parse_mvr_name("VAN DER BERG, JOHN ANNE") == ("VAN DER BERG", "JOHN ANNE")
    assert _parse_mvr_name("HE, XINYI") == ("HE", "XINYI")
    assert _parse_mvr_name("HE, XINYI Birth Date : 21/11/1992") == ("HE", "XINYI")
    assert _parse_mvr_name("21/11/1992") is None


def test_build_mvr_name_index_ontario_driving_record():
    ontario_mvr = """
ONTARIO Driving Record
Licence Number : H2001-78909-21121
Name : HE, XINYI
Gender : M
Birth Date : 21/11/1992
"""
    index = _build_mvr_name_index({"MVR": ontario_mvr})
    assert len(index) == 1
    assert index[0][1:4] == ("HE", "XINYI", "H20017890921121")


def test_build_mvr_name_index_value_above_name_label():
    stacked = """
Licence Number : H2001-78909-21121
HE, XINYI
Name
Birth Date
21/11/1992
"""
    index = _build_mvr_name_index({"MVR": stacked})
    assert len(index) == 1
    assert index[0][1:3] == ("HE", "XINYI")


def test_intact_auto_ontario_mvr_name_not_birth_date():
    generator = _make_generator("Intact_Auto", fields_config={"fields": {}})
    data = {
        "application_info": {},
        "applicant_information": {
            "last_name": "Wrong",
            "first_name": "21/11/1992",
        },
        "driver": [
            {
                "licence_class": "G2",
                "licence_number": "H20017890921121",
            }
        ],
        "drivers_information": {},
        "vehicles_information": {},
    }
    documents = {
        "MVR": """
ONTARIO Driving Record
Licence Number : H2001-78909-21121
Name : HE, XINYI
Birth Date : 21/11/1992
""",
    }
    cleaned = generator._validate_and_clean_json(copy.deepcopy(data), documents=documents)
    assert cleaned["applicant_information"]["last_name"] == "HE"
    assert cleaned["applicant_information"]["first_name"] == "XINYI"


def test_extract_lienholders_by_auto_no_from_application_table():
    application = """
Auto No. Lienholder Name & Postal Address
1 TD Auto Finance PO Box 4086, Station A, , Toronto, ON, M5W 5K3
2
3
"""
    rows = _extract_lienholders_by_auto_no(application)
    assert 1 in rows
    assert rows[1]["company_name"] == "TD Auto Finance"
    assert "PO Box 4086" in rows[1]["address"]
    assert rows[1]["postal_code"] == "M5W5K3"
    assert 2 not in rows


def test_extract_lienholders_split_auto_no_and_body_lines():
    application = """
Auto No.
Lienholder Name & Postal Address
1
TD Auto Finance PO Box 4086, Station A, , Toronto, ON, M5W 5K3
2
3
"""
    rows = _extract_lienholders_by_auto_no(application)
    assert rows[1]["company_name"] == "TD Auto Finance"
    assert rows[1]["postal_code"] == "M5W5K3"


def test_extract_lienholders_rejects_applicant_name_as_company():
    application = """
Auto Lienholder Name & Postal Address
No.
1. TARIQ, HUMAIL T06043500861205 1986 12 5 M M
1. TD Auto Finance - PO Box 4086, Station A, , Toronto, ON, M5W5K3
2.
3.
"""
    rows = _extract_lienholders_by_auto_no(application)
    assert rows[1]["company_name"] == "TD Auto Finance"
    assert "PO Box 4086" in rows[1]["address"]
    assert rows[1]["postal_code"] == "M5W5K3"


def test_extract_lienholders_oaf_pp_dotted_row_from_real_pdf_extract():
    """Reproduces AUTOA_PP.PDF text layout seen in HUMAIL TARIQ beacon output."""
    application = """
Yes No
3. km Yes No Yes No Yes No
Auto Lienholder Name & Postal Address
No.
1. TD Auto Finance - PO Box 4086, Station A, , Toronto, ON, M5W5K3
2.
3.
Is the applicant both the Registered
"""
    rows = _extract_lienholders_by_auto_no(application)
    assert rows[1]["company_name"] == "TD Auto Finance"
    assert "PO Box 4086" in rows[1]["address"]
    assert rows[1]["postal_code"] == "M5W5K3"
    assert 8 not in rows


def test_extract_lienholders_without_section_header():
    application = """
Some other application text
1
TD Auto Finance
PO Box 4086, Station A, Toronto, ON, M5W 5K3
"""
    rows = _extract_lienholders_by_auto_no(application)
    assert rows[1]["company_name"] == "TD Auto Finance"
    assert rows[1]["postal_code"] == "M5W5K3"


def test_intact_auto_fills_interest_from_application_lienholder_row():
    generator = _make_generator("Intact_Auto", fields_config={"fields": {}})
    data = {
        "risk": [
            {
                "serial_number": "2T36CRAV9TW040979",
                "interest": {"has_loan": "No"},
            }
        ],
    }
    documents = {
        "Application_Form": """
Auto No. Lienholder Name & Postal Address
1 TD Auto Finance PO Box 4086, Station A, , Toronto, ON, M5W 5K3
""",
    }
    cleaned = generator._validate_and_clean_json(copy.deepcopy(data), documents=documents)
    interest = cleaned["risk"][0]["interest"]
    assert interest["has_loan"] == "Yes"
    assert interest["type_of_interest"] == "Lienholder"
    assert interest["company_name"] == "TD Auto Finance"
    assert "PO Box 4086" in interest["address"]
    assert interest["postal_code"] == "M5W5K3"


def test_intact_auto_interest_postprocess_preserves_llm_address():
    generator = _make_generator("Intact_Auto", fields_config={"fields": {}})
    data = {
        "risk": [
            {
                "interest": {
                    "has_loan": "No",
                    "company_name": "TARIQ, HUMAIL T06043500861205",
                    "address": "100 King St W, Toronto, ON",
                    "postal_code": "M5X1A1",
                },
            }
        ],
    }
    documents = {
        "Application_Form": """
Auto Lienholder Name & Postal Address
No.
1. TD Auto Finance - PO Box 4086, Station A, , Toronto, ON, M5W 5K3
""",
    }
    cleaned = generator._validate_and_clean_json(copy.deepcopy(data), documents=documents)
    interest = cleaned["risk"][0]["interest"]
    assert interest["has_loan"] == "Yes"
    assert interest["company_name"] == "TD Auto Finance"
    assert interest["address"] == "100 King St W, Toronto, ON"
    assert interest["postal_code"] == "M5X1A1"


def test_intact_auto_mvr_request_date_uses_top_right_black_timestamp():
    """CGI abstract: use upper-right black pull time, not duplicate-request banner date."""
    generator = _make_generator("Intact_Auto", fields_config={"fields": {}})
    data = {
        "application_info": {},
        "applicant_information": {"last_name": "DALE", "first_name": "MARY"},
        "driver": [
            {
                "licence_class": "G2",
                "licence_number": "D02630156866220",
                "MVR_request_date_time": "2026-06-10",
            }
        ],
        "drivers_information": {},
        "vehicles_information": {},
    }
    documents = {
        "MVR_1": """
MVR Abstracts
Duplicate request. Abstract found. The request was submitted on 10/06/2026
Monday, June 22, 2026 03:30 PM
Province ON
Licence D0263-01568-66220
Name DALE, AJEH, MARY
Request Date / Release Date 10/06/2026
ONTARIO Driving Record
Requested On 10/06/2026
Print Date 10/06/2026
Reply Date 10/06/2026
""",
    }
    cleaned = generator._validate_and_clean_json(copy.deepcopy(data), documents=documents)
    assert cleaned["driver"][0]["MVR_request_date_time"] == "22-06-2026"


def test_intact_auto_applicant_name_from_mvr_overwrites_application():
    generator = _make_generator("Intact_Auto", fields_config={"fields": {}})
    data = {
        "application_info": {},
        "applicant_information": {
            "last_name": "Wrong",
            "first_name": "Name",
        },
        "driver": [{"licence_class": "G", "licence_number": "N09080000891124"}],
        "drivers_information": {},
        "vehicles_information": {},
    }
    documents = {
        "MVR_1": (
            "*** MOTOR VEHICLE RECORD - 2026/04/07 ***\n"
            "Name: SINGH, NAVDEEP\n"
            "Licence: N09080000891124\n"
        ),
    }
    cleaned = generator._validate_and_clean_json(copy.deepcopy(data), documents=documents)
    assert cleaned["applicant_information"]["last_name"] == "SINGH"
    assert cleaned["applicant_information"]["first_name"] == "NAVDEEP"


def test_intact_auto_applicant_name_from_mvr_single_name_copies_first():
    generator = _make_generator("Intact_Auto", fields_config={"fields": {}})
    data = {
        "application_info": {},
        "applicant_information": {"last_name": "X", "first_name": "Y"},
        "driver": [{"licence_class": "G"}],
        "drivers_information": {},
        "vehicles_information": {},
    }
    documents = {
        "MVR_1": (
            "*** MOTOR VEHICLE RECORD - 2026/04/07 ***\n"
            "Name: MADONNA,\n"
        ),
    }
    cleaned = generator._validate_and_clean_json(copy.deepcopy(data), documents=documents)
    assert cleaned["applicant_information"]["last_name"] == "MADONNA"
    assert cleaned["applicant_information"]["first_name"] == "MADONNA"


def test_intact_auto_additional_driver_name_from_mvr_by_licence():
    generator = _make_generator("Intact_Auto", fields_config={"fields": {}})
    data = {
        "application_info": {},
        "applicant_information": {
            "last_name": "SINGH",
            "first_name": "NAVDEEP",
        },
        "driver": [
            {"licence_class": "G", "licence_number": "N09080000891124"},
            {
                "licence_class": "G2",
                "licence_number": "H06550000915417",
                "last_name": "WRONG",
                "first_name": "NAME",
            },
        ],
        "drivers_information": {},
        "vehicles_information": {},
    }
    documents = {
        "MVR_1": (
            "*** MOTOR VEHICLE RECORD - 2026/04/07 ***\n"
            "Name: SINGH, NAVDEEP\n"
            "Licence: N09080000891124\n"
        ),
        "MVR_2": (
            "*** MOTOR VEHICLE RECORD - 2026/04/22 ***\n"
            "Name: KAUR, HARPREET, ANN\n"
            "Licence: H06550000915417\n"
        ),
    }
    cleaned = generator._validate_and_clean_json(copy.deepcopy(data), documents=documents)
    assert cleaned["driver_2_information"]["last_name"] == "KAUR"
    assert cleaned["driver_2_information"]["first_name"] == "HARPREET"


def test_intact_auto_normalizes_applicant_phone_to_digits_only():
    generator = _make_generator("Intact_Auto", fields_config={"fields": {}})
    data = {
        "application_info": {},
        "applicant_information": {
            "last_name": "Valdez",
            "phone": "(416) 555-0100",
        },
        "driver": [{"licence_class": "G"}],
        "drivers_information": {},
        "vehicles_information": {},
    }
    cleaned = generator._validate_and_clean_json(copy.deepcopy(data), documents={})
    assert cleaned["applicant_information"]["phone"] == "4165550100"


def test_intact_auto_merges_legacy_root_address_into_applicant_information():
    generator = _make_generator("Intact_Auto", fields_config={"fields": {}})
    data = {
        "application_info": {},
        "applicant_information": {
            "last_name": "Valdez",
            "first_name": "Julius Rafael",
        },
        "address": {
            "postal_code": "M4C5L6",
            "full_address": "511-5 Massey Sq, East York, ON",
            "phone": "416-555-0100",
            "email": "julius@example.com",
        },
        "driver": [{"licence_class": "G"}],
        "drivers_information": {},
        "vehicles_information": {},
    }
    cleaned = generator._validate_and_clean_json(copy.deepcopy(data), documents={})

    assert "address" not in cleaned
    app = cleaned["applicant_information"]
    assert app["postal_code"] == "M4C5L6"
    assert app["unit_number"] == "511"
    assert app["full_address"] == "511-5 Massey Sq, East York, ON"
    assert app["phone"] == "4165550100"
    assert app["email"] == "julius@example.com"


def test_intact_auto_promotes_additional_driver_identity_blocks():
    generator = _make_generator("Intact_Auto", fields_config={"fields": {}})
    data = {
        "application_info": {},
        "applicant_information": {
            "last_name": "GU",
            "first_name": "MIN",
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


def test_intact_auto_additional_driver_address_falls_back_to_applicant():
    generator = _make_generator("Intact_Auto", fields_config={"fields": {}})
    data = {
        "application_info": {},
        "applicant_information": {
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


def test_intact_auto_additional_coverages_merges_legacy_arrays_and_keeps_zero_values():
    generator = _make_generator("Intact_Auto", fields_config={"fields": {}})
    data = {
        "coverages": {
            "additional_coverages": ["Uninsured Automobile: 200000"],
            "section_optional_coverages": [
                "OPCF 20 - Coverage for Transportation Replacement: 50000",
                "Roadside Assistance: 0",
            ],
            "accident_benefits_standard_benefits": [
                "Increased AB - Income Replacement: 0",
                "Increased AB - Death & Funeral",
            ],
        }
    }

    cleaned = generator._validate_and_clean_json(copy.deepcopy(data), documents={})
    coverages = cleaned["coverages"]

    assert "section_optional_coverages" not in coverages
    assert "accident_benefits_standard_benefits" not in coverages
    assert coverages["additional_coverages"] == [
        "Uninsured Automobile: 200000",
        "OPCF 20 - Coverage for Transportation Replacement: 50000",
        "Roadside Assistance: 0",
        "Increased AB - Income Replacement: 0",
        "Increased AB - Death & Funeral",
    ]


def test_intact_auto_additional_coverages_keeps_zero_limit_entries():
    generator = _make_generator("Intact_Auto", fields_config={"fields": {}})
    data = {
        "coverages": {
            "additional_coverages": [
                "Bodily Injury / Prop. Damage: 1000000",
                "Direct Compensation",
                "Direct Compensation: 0",
                "Property Damage: 0",
                "All Perils: 1000",
                "Discount - Winter Tire included",
            ]
        }
    }

    cleaned = generator._validate_and_clean_json(copy.deepcopy(data), documents={})

    assert cleaned["coverages"]["additional_coverages"] == [
        "Bodily Injury / Prop. Damage: 1000000",
        "Direct Compensation",
        "Direct Compensation: 0",
        "Property Damage: 0",
        "All Perils: 1000",
        "Discount - Winter Tire included",
    ]


def test_intact_auto_additional_coverages_backfills_quote_row_values():
    generator = _make_generator("Intact_Auto", fields_config={"fields": {}})
    data = {
        "coverages": {
            "additional_coverages": [
                "#39 Responsible Driver Guarantee",
                "Minor Conviction Protection",
                "#23a Lienholder Protection",
                "#35 Emergency Service",
            ]
        }
    }
    documents = {
        "Quote": """
Operator                              PRIN.     TOTALS
#39 Responsible Driver Guarantee       115        115
Minor Conviction Protection             40         40
#23a Lienholder Protection             Inc.        0
#35 Emergency Service
"""
    }

    cleaned = generator._validate_and_clean_json(copy.deepcopy(data), documents=documents)

    assert cleaned["coverages"]["additional_coverages"] == [
        "#39 Responsible Driver Guarantee: 115",
        "Minor Conviction Protection: 40",
        "#23a Lienholder Protection: 0",
        "#35 Emergency Service",
    ]


def test_intact_auto_additional_coverages_prefers_limit_column_over_premium():
    generator = _make_generator("Intact_Auto", fields_config={"fields": {}})
    data = {
        "coverages": {
            "additional_coverages": [
                "Bodily Injury / Prop. Damage: 2000000",
                "Property Damage: 2000000",
                "Direct Compensation: 0",
                "Accident Benefits: 778",
                "All Perils: 1588",
                "#20 Loss Of Use: 95",
                "#23a Lienholder Protection: 0",
                "#27 Liab to Unowned Veh.: 55",
                "#44 Family Protection: 29",
                "Minor Conviction Protection: 0",
            ]
        }
    }
    documents = {
        "Quote": """
Operator                              PRIN.     TOTALS
Bodily Injury / Prop. Damage          2 M       910        910
Property Damage                       2 M                  0
Direct Compensation                   0         1,042      1,042
Accident Benefits                               778        778
All Perils                            1,000     1,588      1,588
Uninsured Automobile                                      0
#20 Loss Of Use                       5,000     95         95
#23a Lienholder Protection            Inc.      0
#27 Liab to Unowned Veh.              75K       55         55
#44 Family Protection                 2 M       29         29
#39 Responsible Driver Guarantee                         0
Minor Conviction Protection                              0
"""
    }

    cleaned = generator._validate_and_clean_json(copy.deepcopy(data), documents=documents)

    assert cleaned["coverages"]["additional_coverages"] == [
        "Bodily Injury / Prop. Damage: 2000000",
        "Property Damage: 2000000",
        "Direct Compensation: 0",
        "Accident Benefits: 778",
        "All Perils: 1000",
        "#20 Loss Of Use: 5000",
        "#23a Lienholder Protection: 0",
        "#27 Liab to Unowned Veh.: 75K",
        "#44 Family Protection: 2000000",
        "Minor Conviction Protection: 0",
    ]


def test_intact_auto_winter_tires_from_quote_discount_single_vehicle():
    generator = _make_generator("Intact_Auto", fields_config={"fields": {}})
    data = {
        "risk": [
            {
                "winter_tires": "No",
            }
        ],
        "coverages": {"additional_coverages": []},
    }
    documents = {
        "Quote": """
1 of 1 | 2025 HONDA CR-V TOURING HEV 4DR AWD
DIS
Discount - Hybrid and Electric Vehicle included
Discount - Winter Tire included
"""
    }

    cleaned = generator._validate_and_clean_json(copy.deepcopy(data), documents=documents)

    assert cleaned["risk"][0]["winter_tires"] == "Yes"


def test_intact_auto_winter_tires_no_when_quote_discount_absent():
    generator = _make_generator("Intact_Auto", fields_config={"fields": {}})
    data = {
        "risk": [
            {
                "winter_tires": "Yes",
            }
        ],
        "coverages": {"additional_coverages": []},
    }
    documents = {
        "Quote": """
1 of 1 | 2025 HONDA CR-V TOURING HEV 4DR AWD
DIS
Discount - Hybrid and Electric Vehicle included
Discount - Graduated License Holder included
"""
    }

    cleaned = generator._validate_and_clean_json(copy.deepcopy(data), documents=documents)

    assert cleaned["risk"][0]["winter_tires"] == "No"


def test_intact_auto_winter_tires_discount_overrides_purchase_table_no():
    """Discount - Winter Tire included always wins => Yes."""
    generator = _make_generator("Intact_Auto", fields_config={"fields": {}})
    data = {
        "risk": [{"winter_tires": "No"}],
        "coverages": {"additional_coverages": []},
    }
    documents = {
        "Quote": """
Vehicle 1 of 1 | 2021 TOYOTA RAV4
Used 06/13/2026 29662 No Private Driveway
Purchase Purchase Date km at Purchase List Price New Purchase Price Winter Tires Parking at Night
DIS
Discount - Winter Tire included
"""
    }

    cleaned = generator._validate_and_clean_json(copy.deepcopy(data), documents=documents)

    assert cleaned["risk"][0]["winter_tires"] == "Yes"


def test_intact_auto_winter_tires_from_quote_purchase_table_column():
    """Purchase-table Winter Tires column overrides absent DIS discount."""
    generator = _make_generator("Intact_Auto", fields_config={"fields": {}})
    data = {
        "risk": [{"winter_tires": "No"}],
        "coverages": {"additional_coverages": []},
    }
    documents = {
        "Quote": """
Vehicle 1 of 1 | Private Passenger - 2021 TOYOTA RAV4 LE 4DR 2WD
Used 06/13/2026 29662 Yes Private Driveway
Purchase Purchase Date km at Purchase List Price New Purchase Price Winter Tires Parking at Night
Condition
Drivers
"""
    }

    cleaned = generator._validate_and_clean_json(copy.deepcopy(data), documents=documents)

    assert cleaned["risk"][0]["winter_tires"] == "Yes"


def test_intact_auto_winter_tires_from_quote_discount_per_vehicle():
    generator = _make_generator("Intact_Auto", fields_config={"fields": {}})
    data = {
        "risk": [
            {"winter_tires": "No"},
            {"winter_tires": "Yes"},
        ],
        "coverages": {"additional_coverages": []},
    }
    documents = {
        "Quote": """
1 of 2 | 2025 HONDA CR-V TOURING HEV 4DR AWD
DIS
Discount - Winter Tire included

2 of 2 | 2022 TOYOTA COROLLA
DIS
Discount - Hybrid and Electric Vehicle included
"""
    }

    cleaned = generator._validate_and_clean_json(copy.deepcopy(data), documents=documents)

    assert cleaned["risk"][0]["winter_tires"] == "Yes"
    assert cleaned["risk"][1]["winter_tires"] == "No"


def test_compute_years_with_previous_insurer_floors_partial_years():
    assert _compute_years_with_previous_insurer(date(2024, 1, 2), date(2025, 1, 2)) == 0
    assert _compute_years_with_previous_insurer(date(2024, 1, 2), date(2025, 1, 3)) == 1
    assert _compute_years_with_previous_insurer(date(2020, 1, 1), date(2023, 1, 1)) == 2
    assert _compute_years_with_previous_insurer(date(2020, 1, 1), date(2023, 1, 2)) == 3


def test_intact_auto_number_of_years_with_previous_insurer_postprocess_floor():
    generator = _make_generator("Intact_Auto", fields_config={"fields": {}})
    data = {
        "driver": [
            {
                "previous_insurer": "Intact Insurance",
                "insured_without_interruption_since": "2024-01-02",
                "expiry_date": "2025-01-02",
                "number_of_years_with_previous_insurer": 1,
            },
            {
                "previous_insurer": "Intact Insurance",
                "insured_without_interruption_since": "2024-01-02",
                "expiry_date": "2025-01-03",
                "number_of_years_with_previous_insurer": 0,
            },
        ],
    }

    cleaned = generator._validate_and_clean_json(copy.deepcopy(data), documents={})

    assert cleaned["driver"][0]["number_of_years_with_previous_insurer"] == 0
    assert cleaned["driver"][1]["number_of_years_with_previous_insurer"] == 1


def test_intact_auto_non_payment_company_kept_for_non_payment_lapse():
    generator = _make_generator("Intact_Auto", fields_config={"fields": {}})
    data = {
        "driver": [
            {
                "lapse_in_insurance": "Yes",
                "lapse_in_insurance_description": ["Non-Payment"],
                "lapse_start": ["2024-01-24"],
                "lapse_end": ["2026-06-10"],
                "non_payment_company": "Intact Insurance",
            }
        ],
    }

    cleaned = generator._validate_and_clean_json(copy.deepcopy(data), documents={})

    assert cleaned["driver"][0]["non_payment_company"] == "Intact Insurance"


def test_intact_auto_non_payment_company_removed_without_non_payment_lapse():
    generator = _make_generator("Intact_Auto", fields_config={"fields": {}})
    data = {
        "driver": [
            {
                "lapse_in_insurance": "Yes",
                "lapse_in_insurance_description": ["No Automobile"],
                "lapse_start": ["2024-01-24"],
                "lapse_end": ["2026-06-10"],
                "non_payment_company": "Intact Insurance",
            }
        ],
    }

    cleaned = generator._validate_and_clean_json(copy.deepcopy(data), documents={})

    assert "non_payment_company" not in cleaned["driver"][0]


def test_intact_applicant_syncs_unit_number_to_second_applicant():
    data = {
        "applicant_information": {
            "unit_number": "24",
            "full_address": "1845 Main St, Val Caron, ON",
        },
        "second_applicant_information": {
            "full_address": "1845 Main St, Val Caron, ON",
        },
    }

    _normalize_intact_applicant_information(data)

    assert data["second_applicant_information"]["unit_number"] == "24"


def test_parse_vertical_usage_block_reads_daily_km_above_label():
    quote = """
Pleasure
Primary Use
10000
Annual km
Business km
6
Daily km
"""
    parsed = _parse_vertical_usage_block(quote)
    assert parsed["type_of_use"] == "Pleasure"
    assert parsed["annual_km"] == 10000
    assert parsed["annual_business_km"] == 0
    assert parsed["km_toward_work"] == 6


def test_intact_auto_single_vehicle_assignment_daily_km_from_vertical_quote():
    generator = _make_generator("Intact_Auto", fields_config={"fields": {}})
    data = {
        "risk": [{"risk_type": "PPV", "serial_number": "VIN1"}],
        "assignment": {
            "vehicle_1": {"driver_1": {"name": "Test User", "percentage_of_use": 100}},
            "type_of_use": "Pleasure",
            "km_toward_work": 0,
            "annual_km": 10000,
            "annual_business_km": 0,
            "automobile_rented_or_leased_to_others": "No",
            "automobile_used_to_carry_passengers_for_compensation_or_hire": "No",
            "automobile_carry_explosives_or_radioactive_materials": "No",
        },
    }
    documents = {
        "Quote": """
Vehicle 1 of 1 | Private Passenger - 2020 TOYOTA CAMRY
Pleasure
Primary Use
10000
Annual km
Business km
6
Daily km
""",
    }

    cleaned = generator._validate_and_clean_json(copy.deepcopy(data), documents=documents)
    assignment = cleaned["assignment"]
    assert assignment["km_toward_work"] == 6
    assert assignment["annual_km"] == 10000
    assert assignment["type_of_use"] == "Pleasure"


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


def test_intact_auto_premium_on_quote_is_last_root_section():
    cfg = _load_json_config("intact_auto_fields_config.json")
    keys = list(cfg["fields"].keys())
    assert keys[-1] == "premium_on_quote"
    poq = cfg["fields"]["premium_on_quote"]
    assert poq.get("scalar_at_root") is True
    assert "fields" not in poq


def test_intact_normalize_flattens_premium_on_quote_total_wrapper():
    data = {"application_info": {}, "premium_on_quote": {"total": "1,234.00"}}
    IntactJSONGenerator._normalize_intact_structure(data)
    assert data["premium_on_quote"] == "1,234.00"


def test_intact_auto_applicant_information_includes_contact_and_address_fields():
    cfg = _load_json_config("intact_auto_fields_config.json")
    assert "address" not in cfg["fields"]
    app_fields = cfg["fields"]["applicant_information"]["fields"]
    for key in ("postal_code", "full_address", "phone", "email"):
        assert key in app_fields
    assert "second_applicant_information" in cfg["fields"]
    assert cfg["fields"]["second_applicant_information"]["required"] is False
    second_fields = cfg["fields"]["second_applicant_information"]["fields"]
    assert set(second_fields.keys()) == set(app_fields.keys())
    assert "second_coverage" in cfg["fields"]
    assert cfg["fields"]["second_coverage"]["required"] is False
    cov_fields = cfg["fields"]["coverages"]["fields"]
    assert set(cfg["fields"]["second_coverage"]["fields"].keys()) == set(cov_fields.keys())


def test_intact_auto_removes_second_coverage_for_single_vehicle():
    generator = _make_generator("Intact_Auto", fields_config={"fields": {}})
    data = {
        "application_info": {},
        "risk": [{"risk_type": "PPV", "serial_number": "VIN1"}],
        "coverages": {"additional_coverages": ["Bodily Injury / Prop. Damage: 1000000"]},
        "second_coverage": {"additional_coverages": ["All Perils: 1000"]},
        "driver": [{"licence_class": "G"}],
        "drivers_information": {},
        "vehicles_information": {},
    }
    documents = {
        "Quote": """
1 of 1 | 2012 DODGE RAM GRAND CARAVAN
Breakdown
Bodily Injury / Prop. Damage          1 M       518        518
"""
    }
    cleaned = generator._validate_and_clean_json(copy.deepcopy(data), documents=documents)
    assert "second_coverage" not in cleaned
    assert cleaned["coverages"]["additional_coverages"] == ["Bodily Injury / Prop. Damage: 1000000"]


def test_intact_auto_dual_vehicle_coverages_use_per_vehicle_quote_blocks():
    generator = _make_generator("Intact_Auto", fields_config={"fields": {}})
    data = {
        "application_info": {},
        "risk": [
            {"risk_type": "PPV", "serial_number": "VIN1"},
            {"risk_type": "PPV", "serial_number": "VIN2"},
        ],
        "coverages": {
            "additional_coverages": [
                "Bodily Injury / Prop. Damage",
                "Minor Conviction Protection",
                "Discount - Winter Tire included",
            ]
        },
        "second_coverage": {
            "additional_coverages": [
                "All Perils",
                "#20 Loss Of Use",
                "#27 Liab to Unowned Veh.",
                "Discount - Hybrid and Electric Vehicle included",
            ]
        },
        "driver": [{"licence_class": "G"}],
        "drivers_information": {},
        "vehicles_information": {},
    }
    documents = {
        "Quote": """
1 of 2 | 2012 DODGE/RAM GRAND CARAVAN SE
DIS
Discount - Winter Tire included
Breakdown
Bodily Injury / Prop. Damage          1 M       518        518
Minor Conviction Protection                     40         40

2 of 2 | 2026 TOYOTA SIENNA XSE HEV AWD
DIS
Discount - Hybrid and Electric Vehicle included
Breakdown
All Perils                            1,000     632        632
#20 Loss Of Use                       1,500     55         55
#27 Liab to Unowned Veh.              75K       55         55
"""
    }
    cleaned = generator._validate_and_clean_json(copy.deepcopy(data), documents=documents)
    assert cleaned["coverages"]["additional_coverages"] == [
        "Bodily Injury / Prop. Damage: 1000000",
        "Minor Conviction Protection: 40",
        "Discount - Winter Tire included",
    ]
    assert cleaned["second_coverage"]["additional_coverages"] == [
        "All Perils: 1000",
        "#20 Loss Of Use: 1500",
        "#27 Liab to Unowned Veh.: 75K",
        "Discount - Hybrid and Electric Vehicle included",
    ]


def test_intact_auto_dual_applicant_splits_names_from_application():
    generator = _make_generator("Intact_Auto", fields_config={"fields": {}})
    data = {
        "application_info": {},
        "applicant_information": {
            "last_name": "COMBINED",
            "first_name": "WRONG",
            "postal_code": "N2E2J2",
            "full_address": "120 Devonglen Dr, Kitchener, ON",
            "phone": "(902) 979-1349",
        },
        "second_applicant_information": {},
        "driver": [{"licence_class": "G", "licence_number": "D11111111111111"}],
        "drivers_information": {},
        "vehicles_information": {},
    }
    documents = {
        "Application_Form": """
1 Applicant's Name & Primary Address
Name and Address
Dang, Thanh Tam & Nguyen, Thi My Trinh (DATH11)
120 Devonglen Dr
Kitchener
Postal Code N2E 2J2
Phone No. Home (902) 979-1349
""",
        "MVR_1": (
            "*** MOTOR VEHICLE RECORD - 2026/04/07 ***\n"
            "Name: DANG, THANH TAM\n"
            "Licence: D11111111111111\n"
        ),
        "MVR_2": (
            "*** MOTOR VEHICLE RECORD - 2026/04/07 ***\n"
            "Name: NGUYEN, THI MY TRINH\n"
            "Licence: N22222222222222\n"
        ),
    }
    cleaned = generator._validate_and_clean_json(copy.deepcopy(data), documents=documents)
    app = cleaned["applicant_information"]
    second = cleaned["second_applicant_information"]
    assert app["last_name"] == "DANG"
    assert app["first_name"] == "THANH TAM"
    assert second["last_name"] == "NGUYEN"
    assert second["first_name"] == "THI MY TRINH"
    assert second["postal_code"] == "N2E2J2"
    assert second["full_address"] == "120 Devonglen Dr, Kitchener, ON"
    assert second["phone"] == "9029791349"


def test_intact_auto_removes_second_applicant_when_single_name():
    generator = _make_generator("Intact_Auto", fields_config={"fields": {}})
    data = {
        "application_info": {},
        "applicant_information": {"last_name": "SINGH", "first_name": "NAVDEEP"},
        "second_applicant_information": {"last_name": "SHOULD", "first_name": "DROP"},
        "driver": [{"licence_class": "G"}],
        "drivers_information": {},
        "vehicles_information": {},
    }
    documents = {
        "Application_Form": """
1 Applicant's Name & Primary Address
Name and Address
SINGH, NAVDEEP
""",
    }
    cleaned = generator._validate_and_clean_json(copy.deepcopy(data), documents=documents)
    assert "second_applicant_information" not in cleaned


def test_intact_auto_removes_second_applicant_when_two_mvrs_but_single_applicant():
    """Extra drivers/MVRs must not create second_applicant_information."""
    generator = _make_generator("Intact_Auto", fields_config={"fields": {}})
    data = {
        "application_info": {},
        "applicant_information": {"last_name": "YOUSIF", "first_name": "AKRAM"},
        "second_applicant_information": {
            "last_name": "OTHER",
            "first_name": "DRIVER",
            "gender": "Male",
        },
        "driver": [
            {"licence_class": "G", "licence_number": "A11111111111111"},
            {
                "licence_class": "G",
                "licence_number": "B22222222222222",
                "last_name": "OTHER",
                "first_name": "DRIVER",
            },
        ],
        "drivers_information": {},
        "vehicles_information": {},
    }
    documents = {
        "Application_Form": """
1. APPLICANT'S FULL NAME AND POSTAL ADDRESS
NAME
AKRAM YOUSIF
ADDRESS
123 MAIN ST
""",
        "MVR_1": (
            "*** MOTOR VEHICLE RECORD - 2026/04/07 ***\n"
            "Name: YOUSIF, AKRAM\n"
            "Licence: A11111111111111\n"
        ),
        "MVR_2": (
            "*** MOTOR VEHICLE RECORD - 2026/04/07 ***\n"
            "Name: OTHER, DRIVER\n"
            "Licence: B22222222222222\n"
        ),
    }
    cleaned = generator._validate_and_clean_json(copy.deepcopy(data), documents=documents)
    assert "second_applicant_information" not in cleaned
    assert cleaned["applicant_information"]["last_name"] == "YOUSIF"
    assert cleaned["applicant_information"]["first_name"] == "AKRAM"
    assert len(cleaned["driver"]) == 2


def test_intact_auto_section_header_with_ampersand_does_not_trigger_dual_applicant():
    generator = _make_generator("Intact_Auto", fields_config={"fields": {}})
    data = {
        "application_info": {},
        "applicant_information": {"last_name": "SINGH", "first_name": "NAVDEEP"},
        "second_applicant_information": {"last_name": "GHOST", "first_name": "APPLICANT"},
        "driver": [{"licence_class": "G"}],
        "drivers_information": {},
        "vehicles_information": {},
    }
    documents = {
        "Application_Form": """
1 Applicant's Name & Primary Address
Name and Address
SINGH, NAVDEEP
""",
    }
    cleaned = generator._validate_and_clean_json(copy.deepcopy(data), documents=documents)
    assert "second_applicant_information" not in cleaned


def test_intact_auto_section1_name_field_extraction_dale_single_applicant():
    from utils.company_postprocess.intact_auto import (
        _extract_section1_name_field_text,
        _parse_dual_names_from_section1_name_field,
    )

    section1 = """
1. Applicant's Name & Primary Address
Name and Address
Dale, Ajeh Mary (DAAJ01)
24-1845 Main St
Val Caron, ON
Postal Code P3N 1B6
"""
    name_field = _extract_section1_name_field_text(section1)
    assert name_field == "Dale, Ajeh Mary (DAAJ01)"
    assert _parse_dual_names_from_section1_name_field(name_field) is None


def test_intact_auto_removes_second_applicant_when_attendant_care_declined_hallucination():
    """Accident Benefits 'Attendant Care Declined' must not become second_applicant."""
    generator = _make_generator("Intact_Auto", fields_config={"fields": {}})
    data = {
        "application_info": {},
        "applicant_information": {
            "last_name": "DALE",
            "first_name": "AJEH MARY",
            "postal_code": "P3N1B6",
            "full_address": "24-1845 Main St, Val Caron, ON",
            "phone": "6479177795",
            "email": "ajehm86@gmail.com",
        },
        "second_applicant_information": {
            "last_name": "Attendant Care Declined",
            "first_name": "Attendant Care Declined",
            "postal_code": "P3N1B6",
            "full_address": "24-1845 Main St, Val Caron, ON",
            "phone": "6479177795",
            "email": "ajehm86@gmail.com",
        },
        "driver": [{"licence_class": "G"}],
        "drivers_information": {},
        "vehicles_information": {},
    }
    documents = {
        "Application_Form": """
CSIO Ontario Application for Automobile Insurance Owner's Form (OAF 1)
1. Applicant's Name & Primary Address
Name and Address
Dale, Ajeh Mary
24-1845 Main St
Val Caron
Postal Code P3N 1B6
Phone No. Home (647) 917-7795
Email ajehm86@gmail.com
2. Policy Period
Effective Date 2026/06/22
3. Described Automobile
2021 TOYOTA RAV4
4. Accident Benefits
Medical, Rehabilitation & Attendant Care, Declined
Attendant Care Declined
""",
    }
    cleaned = generator._validate_and_clean_json(copy.deepcopy(data), documents=documents)
    assert "second_applicant_information" not in cleaned
    assert cleaned["applicant_information"]["last_name"] == "DALE"


def test_intact_auto_prompt_includes_universal_applicant_count_rule():
    cfg = _load_json_config("intact_auto_fields_config.json")
    generator = _make_generator("Intact_Auto", fields_config=cfg)
    prompt = generator._build_prompt({"Application_Form": "NAME\nSINGH, NAVDEEP"})
    assert "APPLICANT COUNT (EVERY POLICY)" in prompt
    assert "Global extraction rules (all policies)" in prompt
    assert "second_applicant_information" in prompt
    assert "ONLY on Application_Form Section 1" in prompt or "Application Section 1" in prompt
    assert "2+ MVR" in prompt or "2+ entries in `driver[]`" in prompt


def test_intact_auto_fields_prompt_expands_risk_interest_object():
    """Nested config objects (e.g. risk.interest) must not be emitted as `interest: string` in the model prompt."""
    cfg = _load_json_config("intact_auto_fields_config.json")
    generator = _make_generator("Intact_Auto", fields_config=cfg)
    section = generator._build_fields_prompt_section(cfg)
    assert "phone" in section
    assert "email" in section
    assert "interest: object" in section
    assert "NEVER output `interest` as a single string" in section
    assert "has_loan" in section
    assert "type_of_interest" in section
    assert "company_name" in section
    assert "address" in section
    assert "postal_code" in section


def test_get_applicant_filename_property_company_uses_property_prefix():
    generator = _make_generator("Intact_property", fields_config={"fields": {}})
    data = {
        "applicant_information": {
            "first_name": "Ken",
            "last_name": "Zhang",
        }
    }
    assert generator.get_applicant_filename(data) == "property+Ken Zhang"


def test_get_applicant_filename_auto_company_keeps_original_name():
    generator = _make_generator("Intact_Auto", fields_config={"fields": {}})
    data = {
        "applicant_information": {
            "first_name": "Ken",
            "last_name": "Zhang",
        }
    }
    assert generator.get_applicant_filename(data) == "Ken Zhang"


def test_get_required_top_level_fields_from_config():
    fallback = ["applicant_information", "drivers_information"]
    fields_config = {
        "fields": {
            "a": {"required": True},
            "b": {"required": False},
            "c": {},
        }
    }
    assert get_required_top_level_fields("Intact_Auto", fields_config, fallback) == ["a", "c"]


def test_get_required_top_level_fields_fallback_when_missing_fields():
    fallback = ["applicant_information", "drivers_information"]
    assert get_required_top_level_fields("Intact_Auto", {}, fallback) == fallback


def test_intact_property_backfills_missing_coverages_from_quote_rows():
    generator = _make_generator("Intact_property", fields_config={"fields": {}})
    data = {
        "coverages": {
            "Contents": {"amount": "$50,000", "deductible": "$1,000"},
            "Sewer Backup": {"amount": "$75,000", "deductible": "$2,000"},
        }
    }
    documents = {
        "Quote": """
Coverage                    Deductible      Amount      Premium
Contents                                    $50,000     $661
Additional Living Expenses                  $25,000     Inc.
Water                       $2,000
my Home and Auto
Annual Premium                                      $765
Coverage                    Deductible      Amount      Premium
Non-smoker
Mature Market
Sewer Backup                $2,000          $75,000
Annual Premium                                      $765
""",
    }
    out = generator._merge_missing_property_coverages_from_quote(copy.deepcopy(data), documents)
    cov = out["coverages"]
    assert "Additional Living Expenses" in cov
    assert cov["Additional Living Expenses"]["amount"] is None
    assert cov["Additional Living Expenses"]["deductible"] is None
    assert "Water" in cov
    assert cov["Water"]["amount"] is None
    assert cov["Water"]["deductible"] is None
    assert "my Home and Auto" in cov
    assert "Non-smoker" in cov
    assert "Mature Market" in cov


def test_intact_property_normalizes_noisy_coverage_keys_with_trailing_values():
    generator = _make_generator("Intact_property", fields_config={"fields": {}})
    data = {
        "coverages": {
            "Contents": {"amount": "$50,000", "deductible": "$1,000"},
            "Contents $50,000 $661": {"amount": None, "deductible": None},
            "Ground Water N/A N/A": {"amount": None, "deductible": None},
            "my Home and Auto": {"amount": None, "deductible": None},
        }
    }
    out = generator._merge_missing_property_coverages_from_quote(copy.deepcopy(data), documents={})
    cov = out["coverages"]
    assert "Contents $50,000 $661" not in cov
    assert "Ground Water N/A N/A" not in cov
    assert "Contents" in cov
    assert "Ground Water" in cov
    assert "my Home and Auto" in cov


def test_intact_property_insureds_use_application_date_when_prior_insurer_exists():
    generator = _make_generator("Intact_property", fields_config={"fields": {}})
    data = {
        "term": {"policy_effective_date": "2026-05-30"},
        "insureds": {
            "previous_insurer": "Intact Insurance",
            "insured_with_broker_since": "2026-05-30",
        },
    }
    documents = {
        "Application": "Property - Insured Since 05/21/2019",
    }
    from utils.company_postprocess import intact_property as intact_property_post

    out = intact_property_post.apply(generator, copy.deepcopy(data), documents=documents)
    insureds = out["insureds"]
    assert "automobile_insurance_cancelled_or_refused_in_last_3_years" not in insureds
    assert "ubi_consent" not in insureds
    assert insureds["insured_with_broker_since"] == "2019-05-21"
    assert insureds["insured_without_interruption_since"] == "2019-05-21"


def test_intact_property_previous_insurer_keeps_llm_output_without_programmatic_mapping():
    generator = _make_generator("Intact_property", fields_config={"fields": {}})
    data = {
        "term": {"policy_effective_date": "2026-05-30"},
        "insureds": {
            "previous_insurer": "Intact",
            "insured_with_broker_since": "05/21/2026",
        },
    }
    documents = {
        "Application": "Property - Insured Since 05/21/2019",
    }
    from utils.company_postprocess import intact_property as intact_property_post

    out = intact_property_post.apply(generator, copy.deepcopy(data), documents=documents)
    insureds = out["insureds"]
    assert insureds["previous_insurer"] == "Intact"


def test_intact_property_no_prior_insurer_uses_effective_date_and_omits_dependent_fields():
    generator = _make_generator("Intact_property", fields_config={"fields": {}})
    data = {
        "term": {"policy_effective_date": "2026-05-30"},
        "insureds": {
            "previous_insurer": "No Prior Insurer",
            "number_of_years_with_previous_insurer": 7,
            "previous_insurer_policy_number": "ABC-123",
            "previous_insurer_expiry_date": "2027-05-31",
            "insured_with_broker_since": None,
            "insured_without_interruption_since": None,
        },
    }
    documents = {
        "Application": "No prior property insurance",
    }
    from utils.company_postprocess import intact_property as intact_property_post

    out = intact_property_post.apply(generator, copy.deepcopy(data), documents=documents)
    insureds = out["insureds"]
    assert "number_of_years_with_previous_insurer" not in insureds
    assert "previous_insurer_policy_number" not in insureds
    assert "previous_insurer_expiry_date" not in insureds
    assert insureds["insured_with_broker_since"] == "2026-05-30"
    assert insureds["insured_without_interruption_since"] == "2026-05-30"
