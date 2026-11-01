"""ISO 4217 active currency codes and their minor-unit exponents (K1, K2).

Hardcoded to avoid a dependency. Codes with no minor unit defined by ISO
(precious metals, SDR, test codes) are excluded.
"""

_EXPONENT_0 = "BIF CLP DJF GNF ISK JPY KMF KRW PYG RWF UGX UYI VND VUV XAF XOF XPF"
_EXPONENT_3 = "BHD IQD JOD KWD LYD OMR TND"
_EXPONENT_4 = "CLF UYW"
_EXPONENT_2 = (
    "AED AFN ALL AMD AOA ARS AUD AWG AZN BAM BBD BDT BMD BND BOB BOV BRL BSD BTN BWP BYN "
    "BZD CAD CDF CHE CHF CHW CNY COP COU CRC CUP CVE CZK DKK DOP DZD EGP ERN ETB EUR FJD "
    "FKP GBP GEL GHS GIP GMD GTQ GYD HKD HNL HTG HUF IDR ILS INR IRR JMD KES KGS KHR KPW "
    "KYD KZT LAK LBP LKR LRD LSL MAD MDL MGA MKD MMK MNT MOP MRU MUR MVR MWK MXN MXV MYR "
    "MZN NAD NGN NIO NOK NPR NZD PAB PEN PGK PHP PKR PLN QAR RON RSD RUB SAR SBD SCR SDG "
    "SEK SGD SHP SLE SOS SRD SSP STN SVC SYP SZL THB TJS TMT TOP TRY TTD TWD TZS UAH USD "
    "USN UYU UZS VED VES WST XCD XCG YER ZAR ZMW ZWG"
)

EXPONENTS: dict[str, int] = {
    code: exponent
    for exponent, codes in ((0, _EXPONENT_0), (2, _EXPONENT_2), (3, _EXPONENT_3), (4, _EXPONENT_4))
    for code in codes.split()
}

DEFAULT_CURRENCY = "EUR"


def exponent(code: str) -> int | None:
    return EXPONENTS.get(code)
