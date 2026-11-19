from __future__ import annotations

import pandas as pd

from alvheim_tiein import sodir

LICENSEES = (
    "\ufefffldName,fldOwnerKind,fldOwnerName,fldOwnerFrom,fldOwnerTo,fldLicenseeFrom,fldLicenseeTo,"
    "cmpLongName,fldCompanyShare,fldSdfiShare,fldNpdidField,cmpNpdidCompany,fldLicenseeDateUpdated,DatesyncNPD\n"
    "ALVHEIM,PRODUCTION LICENCE,203,01.01.2020,,01.10.2022,,Aker BP ASA,80.000000,,1,2,01.01.2026,01.01.2026\n"
    "ALVHEIM,PRODUCTION LICENCE,203,01.01.2020,,01.10.2022,,ConocoPhillips Skandinavia AS,20.000000,,1,3,01.01.2026,01.01.2026\n"
    "ALVHEIM,PRODUCTION LICENCE,203,01.01.2020,,01.01.2016,30.09.2022,Old Partner AS,15.000000,,1,4,01.01.2026,01.01.2026\n"
    "TROLL,PRODUCTION LICENCE,054,01.01.2020,,01.01.2020,,Someone,100.000000,,9,5,01.01.2026,01.01.2026\n"
)


def test_parse_and_current_licensees() -> None:
    df = sodir.parse_table(LICENSEES)
    assert df["fldLicenseeFrom"].iloc[0] == pd.Timestamp("2022-10-01")
    current = sodir.current_field_licensees(df)
    assert current["cmpLongName"].tolist() == ["Aker BP ASA", "ConocoPhillips Skandinavia AS"]


def test_to_licence_shares_uses_fractions() -> None:
    df = sodir.parse_table(LICENSEES)
    shares = sodir.to_licence_shares(df[df["fldName"] == "ALVHEIM"])
    assert shares["share"].round(2).tolist() == [0.8, 0.2, 0.15]
    assert shares["license"].unique().tolist() == ["203"]
    assert shares["valid_to"].iloc[2] == pd.Timestamp("2022-09-30")
