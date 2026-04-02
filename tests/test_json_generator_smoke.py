import copy
import hashlib

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
                    "insured_without_interruption_since": {"mode": "date", "description": "Insured Without Interruption Since in YYYY-MM format"},
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
    assert cleaned["driver"][0]["insured_without_interruption_since"] == "2017-06"
    assert cleaned["driver"][0]["expiry_date"] == "24-06-2026"
    assert "lapse_in_insurance_description" not in cleaned["driver"][0]
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
                        "description": "Insured Without Interruption Since in YYYY-MM format",
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
    }
    documents = {
        "Application": "Some header text... Broker Code :X40501 ... footer",
    }

    cleaned = generator._validate_and_clean_json(copy.deepcopy(data), documents=documents)

    assert cleaned["broker_information"]["broker_number"] == "40501"
    assert cleaned["driver"][0]["insured_without_interruption_since"] == "2026-03"


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
    assert digest == "4d785447a4f8ec336f2983a4ece0431bd0cbabad5eb7feb96cae71dc6af03bfc"


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


def test_get_required_top_level_fields_from_config():
    fallback = ["applicant_information", "drivers_information"]
    fields_config = {"fields": {"a": {}, "b": {}}}
    assert get_required_top_level_fields("Intact_Auto", fields_config, fallback) == ["a", "b"]


def test_get_required_top_level_fields_fallback_when_missing_fields():
    fallback = ["applicant_information", "drivers_information"]
    assert get_required_top_level_fields("Intact_Auto", {}, fallback) == fallback
