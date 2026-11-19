"""Public Sodir (Norwegian Offshore Directorate) FactPages tables.

No account is needed. Useful for production history per field, and licensee and
ownership history, which ground the licence -> company shares in ``licence_shares.csv``
(shares in FactPages are percent; the study uses fractions).
"""

from __future__ import annotations

import io

import httpx
import pandas as pd

_URL = (
    "https://factpages.sodir.no/public?/Factpages/external/tableview/{table}"
    "&rs:Command=Render&rc:Toolbar=false&rc:Parameters=f&IpAddress=not_used"
    "&CultureCode=en&rs:Format=CSV&Top100=false"
)
TABLES = {
    "field_production_monthly": "Saleable production per field and month (net, mill/bill Sm3)",
    "field_licensee_hst": "Licensees per field over time, with company shares (percent)",
    "field_owner_hst": "Owning licence/unit per field over time",
    "licence_licensee_hst": "Licensees per production licence over time (percent)",
    "discovery": "Discoveries with owning licence and status",
}
ALVHEIM_AREA_FIELDS = ("ALVHEIM", "VILJE", "VOLUND", "BØYLA", "SKOGUL", "TYRVING")
_DATE_COLUMNS = (
    "fldOwnerFrom",
    "fldOwnerTo",
    "fldLicenseeFrom",
    "fldLicenseeTo",
    "fldOwnershipFromDate",
    "fldOwnershipToDate",
    "prlLicenseeDateValidFrom",
    "prlLicenseeDateValidTo",
)


def parse_table(text: str) -> pd.DataFrame:
    df = pd.read_csv(io.StringIO(text.lstrip("\ufeff")))
    for col in _DATE_COLUMNS:
        if col in df:
            df[col] = pd.to_datetime(df[col], format="%d.%m.%Y", errors="coerce")
    return df


def fetch_text(table: str, *, client: httpx.Client | None = None, timeout: float = 120.0) -> str:
    """The table as Sodir's CSV text (cache this; :func:`parse_table` reads it)."""
    if table not in TABLES:
        raise KeyError(f"unknown table {table!r}; known: {', '.join(TABLES)}")
    url = _URL.format(table=table)
    response = client.get(url) if client else httpx.get(url, timeout=timeout)
    response.raise_for_status()
    return response.text


def fetch_table(
    table: str, *, client: httpx.Client | None = None, timeout: float = 120.0
) -> pd.DataFrame:
    return parse_table(fetch_text(table, client=client, timeout=timeout))


def current_field_licensees(
    licensees: pd.DataFrame, fields: tuple[str, ...] = ALVHEIM_AREA_FIELDS
) -> pd.DataFrame:
    df = licensees[licensees["fldName"].isin(fields) & licensees["fldLicenseeTo"].isna()]
    return (
        df[
            [
                "fldName",
                "fldOwnerKind",
                "fldOwnerName",
                "cmpLongName",
                "fldCompanyShare",
                "fldSdfiShare",
            ]
        ]
        .sort_values(["fldName", "fldCompanyShare"], ascending=[True, False])
        .reset_index(drop=True)
    )


def field_monthly(
    production: pd.DataFrame, fields: tuple[str, ...] = ALVHEIM_AREA_FIELDS
) -> pd.DataFrame:
    df = production[production["prfInformationCarrier"].isin(fields)].copy()
    df["period"] = pd.to_datetime(dict(year=df["prfYear"], month=df["prfMonth"], day=1))
    return df.sort_values(["prfInformationCarrier", "period"]).reset_index(drop=True)


def to_licence_shares(licensees: pd.DataFrame, license_from: str = "fldOwnerName") -> pd.DataFrame:
    """Field licensee history in the study's ``licence_shares.csv`` layout."""
    return pd.DataFrame(
        {
            "license": licensees[license_from].astype(str),
            "company": licensees["cmpLongName"],
            "share": licensees["fldCompanyShare"] / 100.0,
            "valid_from": licensees["fldLicenseeFrom"],
            "valid_to": licensees["fldLicenseeTo"],
        }
    )
