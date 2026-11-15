"""Listas de referencia. La racha en vivo sale de Yahoo; esto solo identifica el índice."""

# Aristócratas del S&P 500 a 2 de noviembre de 2026, según el recuento público
# de Sure Dividend (68 nombres, ya sin Kenvue tras su salida del S&P 500).
# No es una publicación de S&P Global. Sirve para marcar la pertenencia, no para
# inventar años de dividendo: los años los pone el dato de Yahoo.
# Reyes del dividendo a 1 de noviembre de 2026: 60 nombres con 50 años o más
# de subidas, según el censo público de Sure Dividend. Yahoo a menudo publica
# una racha más corta; la marca de Rey no depende de ese campo.
KINGS = {
    "MO", "ADM", "CL", "KO", "HRL", "KMB", "MZTI", "PEP", "PG", "SYY", "TGT", "TR", "UVV", "WMT",
    "ABM", "ADP", "CSL", "DOV", "EMR", "GRC", "ITW", "MSA", "NDSN", "PH", "PNR", "SWK", "TNC", "GWW",
    "ABT", "ABBV", "BDX", "JNJ",
    "GPC", "LOW", "MCD",
    "CBSH", "CINF", "FMCB", "RLI", "SPGI", "SOME", "UBSI",
    "FUL", "PPG", "NUE", "RPM", "SON", "SCL",
    "NFG",
    "FRT",
    "AWR", "BKH", "CWT", "CU.TO", "ED", "FTS", "MGEE", "MSEX", "NWN", "HTO",
}

SP500_ARISTOCRATS = {
    "ABBV", "ABT", "ADM", "ADP", "AFL", "ALB", "AMCR", "AOS", "APD", "ATO",
    "BDX", "BEN", "BRO", "CAH", "CAT", "CB", "CHD", "CHRW", "CINF", "CL",
    "CLX", "CTAS", "CVX", "DOV", "ECL", "ED", "EMR", "ERIE", "ES", "ESS",
    "EXPD", "FAST", "FDS", "FRT", "GD", "GPC", "GWW", "HRL", "IBM", "ITW",
    "JNJ", "KMB", "KO", "LIN", "LOW", "MCD", "MDT", "MKC", "NDSN", "NEE",
    "NUE", "O", "PEP", "PG", "PNR", "PPG", "ROP", "SHW", "SJM", "SPGI",
    "SWK", "SYY", "TGT", "TROW", "WMT", "WST", "XOM", "BF-B",
}

EU_REGIONS = ("de", "fr", "gb", "es", "it", "nl", "ch", "se", "dk", "be", "fi", "no", "pt", "at", "ie")

SECTORS = [
    ("", "Todos los sectores"),
    ("Technology", "Tecnología"),
    ("Healthcare", "Salud"),
    ("Financial Services", "Finanzas"),
    ("Consumer Defensive", "Consumo básico"),
    ("Consumer Cyclical", "Consumo cíclico"),
    ("Industrials", "Industria"),
    ("Energy", "Energía"),
    ("Utilities", "Servicios públicos"),
    ("Real Estate", "Inmobiliario"),
    ("Basic Materials", "Materiales"),
    ("Communication Services", "Comunicación"),
]

SECTOR_ES = {key: label for key, label in SECTORS if key}

REGION_ES = {
    "us": "EEUU",
    "ca": "Canadá",
    "de": "Alemania",
    "fr": "Francia",
    "gb": "Reino Unido",
    "es": "España",
    "it": "Italia",
    "nl": "Países Bajos",
    "ch": "Suiza",
    "se": "Suecia",
    "dk": "Dinamarca",
    "be": "Bélgica",
    "fi": "Finlandia",
    "no": "Noruega",
    "pt": "Portugal",
    "at": "Austria",
    "ie": "Irlanda",
    "eu": "Europa",
}
