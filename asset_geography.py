"""Indication géographique uniquement : aucune certification PEA."""

EEA_COUNTRIES = set("""Austria|Belgium|Bulgaria|Croatia|Cyprus|Czech Republic|Czechia|
Denmark|Estonia|Finland|France|Germany|Greece|Hungary|Ireland|Italy|Latvia|
Lithuania|Luxembourg|Malta|Netherlands|Poland|Portugal|Romania|Slovakia|
Slovenia|Spain|Sweden|Iceland|Liechtenstein|Norway""".replace("\n", "").split("|"))
OTHER_EUROPE = {"United Kingdom", "Switzerland", "Albania", "Andorra", "Belarus",
                "Bosnia and Herzegovina", "Kosovo", "Moldova", "Monaco", "Montenegro",
                "North Macedonia", "San Marino", "Serbia", "Ukraine", "Vatican City"}
TRANSCONTINENTAL = {"Russia", "Turkey", "Türkiye", "Kazakhstan", "Georgia", "Azerbaijan"}
EUROPEAN_SUFFIXES = {"PA", "DE", "F", "BE", "DU", "HM", "HA", "MU", "SG",
                     "L", "SW", "VX", "AS", "BR", "MC", "MI", "LS", "VI",
                     "ST", "HE", "CO", "OL", "IC", "IR", "AT", "WA", "PR", "BD"}


def european_status(country=None, ticker=""):
    """Le suffixe indique seulement la cotation, jamais le domicile de l'émetteur."""
    country = country.strip() if isinstance(country, str) else ""
    if country in EEA_COUNTRIES:
        return "Europe (UE/EEE)"
    if country in OTHER_EUROPE:
        return "Europe hors UE/EEE"
    if country in TRANSCONTINENTAL:
        return "Pays transcontinental"
    if country and country.lower() not in {"n/a", "unknown", "nan", "none", "inconnu"}:
        return "Hors Europe"
    if isinstance(ticker, str) and "." in ticker and ticker.rsplit(".", 1)[-1].upper() in EUROPEAN_SUFFIXES:
        return "Cotation Europe (pays inconnu)"
    return "Inconnu"
