from typing import Dict, Optional

from . import caa_auto, intact_auto, caa_property, intact_property


def run(generator, data: Dict, documents: Optional[Dict[str, str]] = None) -> Dict:
    """Route post-processing by company while preserving current behavior."""
    company_upper = (getattr(generator, "company", "") or "").upper()

    if generator._should_apply_caa_dob_normalization(data):
        data = caa_auto.apply(generator, data, documents)

    if generator._is_intact_auto_company():
        doc_summary = "(none)"
        if isinstance(documents, dict):
            doc_summary = ",".join(
                f"{k}({len(v)}ch)" if isinstance(v, str) else f"{k}(?)"
                for k, v in documents.items()
            )
        print(
            f"[BEACON:interest] pipeline_route_intact_auto | "
            f"company={company_upper} | documents={doc_summary}"
        )
        data = intact_auto.apply(generator, data, documents)
    else:
        print(
            f"[BEACON:interest] pipeline_skip_intact_auto | "
            f"company={company_upper} | is_intact_auto=False"
        )

    if company_upper == "CAA_PROPERTY":
        data = caa_property.apply(generator, data)
    elif company_upper == "INTACT_PROPERTY":
        data = intact_property.apply(generator, data, documents)

    return data
