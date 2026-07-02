from pathlib import Path

from coruscant.exposure.domain_config import load_companies


def test_load_companies() -> None:
    companies = load_companies(Path("config"))
    assert [company.slug for company in companies] == [
        "apple",
        "microsoft",
        "tesla",
        "exxonmobil",
        "cargill",
        "spacex",
    ]
