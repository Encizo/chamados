PALETTES: dict[str, dict] = {
    "azul-tech": {
        "name": "Azul Tech e Profissional",
        "description": "Classica, confiavel e corporativa.",
        "colors": ["#005eb8", "#00478d", "#e8f1ff"],
        "vars": {
            "bg": "#f6f8fb",
            "surface": "#ffffff",
            "surface-soft": "#f2f5f8",
            "line": "#d8e0e6",
            "ink": "#1a1f24",
            "muted": "#576772",
            "primary": "#005eb8",
            "primary-deep": "#00478d",
            "accent-ok": "#0f7c4a",
            "accent-warn": "#a96a0f",
            "accent-open": "#1f5f66",
        },
    },
    "verde-crescimento": {
        "name": "Verde Sustentabilidade",
        "description": "Fresco, natural e focado em crescimento.",
        "colors": ["#1f7a3f", "#3ea88a", "#f3eee2"],
        "vars": {
            "bg": "#f6f3ea",
            "surface": "#ffffff",
            "surface-soft": "#eef4ef",
            "line": "#d4dfd7",
            "ink": "#233028",
            "muted": "#586a60",
            "primary": "#2f8a51",
            "primary-deep": "#1f7a3f",
            "accent-ok": "#1b7b45",
            "accent-warn": "#97711a",
            "accent-open": "#2d7768",
        },
    },
    "mono-sofisticado": {
        "name": "Monocromatico Sofisticado",
        "description": "Minimalista com tons de cinza elegantes.",
        "colors": ["#2f353b", "#707983", "#c2c8cf"],
        "vars": {
            "bg": "#f4f5f6",
            "surface": "#ffffff",
            "surface-soft": "#eff1f3",
            "line": "#d8dde2",
            "ink": "#252b31",
            "muted": "#5e6872",
            "primary": "#5d6772",
            "primary-deep": "#3f4650",
            "accent-ok": "#3c6a55",
            "accent-warn": "#8a6a33",
            "accent-open": "#4f6270",
        },
    },
    "pastel-suave": {
        "name": "Pastel Suave e Acolhedor",
        "description": "Calmo, amigavel e moderno.",
        "colors": ["#d7a7ba", "#8ea8d8", "#9cd2bd"],
        "vars": {
            "bg": "#f8f3ed",
            "surface": "#ffffff",
            "surface-soft": "#f2ede8",
            "line": "#e0d6cf",
            "ink": "#3a3532",
            "muted": "#71655e",
            "primary": "#8b73b5",
            "primary-deep": "#6e5a97",
            "accent-ok": "#5c9f8b",
            "accent-warn": "#c28f57",
            "accent-open": "#7d95be",
        },
    },
    "laranja-roxo": {
        "name": "Laranja e Roxo Inovacao",
        "description": "Energetico, criativo e ousado.",
        "colors": ["#f26b1d", "#6a3fb1", "#f8f8fb"],
        "vars": {
            "bg": "#f7f6fb",
            "surface": "#ffffff",
            "surface-soft": "#f2f0f8",
            "line": "#ddd7ea",
            "ink": "#2c2734",
            "muted": "#625a71",
            "primary": "#f26b1d",
            "primary-deep": "#6a3fb1",
            "accent-ok": "#24835d",
            "accent-warn": "#c27416",
            "accent-open": "#5f4e9b",
        },
    },
    "amarelo-azul": {
        "name": "Amarelo e Azul Criatividade",
        "description": "Otimista, claro e dinamico.",
        "colors": ["#b88600", "#1e58b7", "#f2f4f8"],
        "vars": {
            "bg": "#f5f6f8",
            "surface": "#ffffff",
            "surface-soft": "#f0f3f9",
            "line": "#d8dfeb",
            "ink": "#1f2430",
            "muted": "#596476",
            "primary": "#b88600",
            "primary-deep": "#1e58b7",
            "accent-ok": "#1e7b49",
            "accent-warn": "#c99300",
            "accent-open": "#2d5fa3",
        },
    },
    "dourado-preto": {
        "name": "Dourado e Preto Prestigio",
        "description": "Luxuoso e de alto contraste.",
        "colors": ["#b28a3f", "#111111", "#f6efe1"],
        "vars": {
            "bg": "#f7f1e7",
            "surface": "#fffdf8",
            "surface-soft": "#f1eadb",
            "line": "#dfd4bf",
            "ink": "#1d1913",
            "muted": "#605846",
            "primary": "#b28a3f",
            "primary-deep": "#826321",
            "accent-ok": "#3d7a54",
            "accent-warn": "#9d6a0f",
            "accent-open": "#6d5f46",
        },
    },
    "vinho-cinza": {
        "name": "Vinho e Cinza Sofisticacao",
        "description": "Elegante e profissional.",
        "colors": ["#6f243f", "#3b434d", "#f5eee8"],
        "vars": {
            "bg": "#f5eee8",
            "surface": "#ffffff",
            "surface-soft": "#f0e7e2",
            "line": "#dfd3cf",
            "ink": "#2c2830",
            "muted": "#625864",
            "primary": "#7c304c",
            "primary-deep": "#6f243f",
            "accent-ok": "#2f7a56",
            "accent-warn": "#a1721d",
            "accent-open": "#4a5a6b",
        },
    },
    "terra-verde": {
        "name": "Terra e Verde Natureza",
        "description": "Organico, sustentavel e acolhedor.",
        "colors": ["#b35c3c", "#2f6f45", "#efe2c8"],
        "vars": {
            "bg": "#f3ead8",
            "surface": "#fffdf8",
            "surface-soft": "#eee3cd",
            "line": "#dfd1b7",
            "ink": "#3a2f24",
            "muted": "#6d5b49",
            "primary": "#2f6f45",
            "primary-deep": "#255b39",
            "accent-ok": "#2c7a4a",
            "accent-warn": "#a97326",
            "accent-open": "#92624c",
        },
    },
    "marinho-areia": {
        "name": "Azul Marinho e Areia Praia",
        "description": "Tranquilo, fresco e luminoso.",
        "colors": ["#123a63", "#22a8b6", "#f2dfb3"],
        "vars": {
            "bg": "#f6f2e7",
            "surface": "#ffffff",
            "surface-soft": "#eef3f2",
            "line": "#d6e0df",
            "ink": "#1e2f3d",
            "muted": "#546676",
            "primary": "#22a8b6",
            "primary-deep": "#123a63",
            "accent-ok": "#1f7a52",
            "accent-warn": "#b07f22",
            "accent-open": "#206e78",
        },
    },
}


DEFAULT_PALETTE_KEY = "azul-tech"


def _hex_to_rgb(value: str) -> tuple[int, int, int]:
    raw = value.strip().lstrip("#")
    if len(raw) != 6:
        return (0, 0, 0)
    return int(raw[0:2], 16), int(raw[2:4], 16), int(raw[4:6], 16)


def _rgb_to_hex(rgb: tuple[int, int, int]) -> str:
    r, g, b = rgb
    return f"#{r:02x}{g:02x}{b:02x}"


def _mix_with_white(hex_color: str, ratio: float) -> str:
    ratio = max(0.0, min(1.0, ratio))
    r, g, b = _hex_to_rgb(hex_color)
    mixed = (
        int(r + (255 - r) * ratio),
        int(g + (255 - g) * ratio),
        int(b + (255 - b) * ratio),
    )
    return _rgb_to_hex(mixed)


def _mix_with_black(hex_color: str, ratio: float) -> str:
    ratio = max(0.0, min(1.0, ratio))
    r, g, b = _hex_to_rgb(hex_color)
    mixed = (
        int(r * (1.0 - ratio)),
        int(g * (1.0 - ratio)),
        int(b * (1.0 - ratio)),
    )
    return _rgb_to_hex(mixed)


def resolve_palette(key: str | None) -> tuple[str, dict]:
    candidate = (key or "").strip().lower()
    if candidate not in PALETTES:
        candidate = DEFAULT_PALETTE_KEY

    base = PALETTES[candidate]
    vars_copy = dict(base["vars"])
    vars_copy.setdefault("primary-soft", _mix_with_white(vars_copy["primary"], 0.70))
    vars_copy.setdefault("ok-soft", _mix_with_white(vars_copy["accent-ok"], 0.72))
    vars_copy.setdefault("warn-soft", _mix_with_white(vars_copy["accent-warn"], 0.70))
    vars_copy.setdefault("open-soft", _mix_with_white(vars_copy["accent-open"], 0.72))
    vars_copy.setdefault("accent-ok-strong", _mix_with_black(vars_copy["accent-ok"], 0.12))
    vars_copy.setdefault("accent-warn-strong", _mix_with_black(vars_copy["accent-warn"], 0.10))
    vars_copy.setdefault("accent-open-strong", _mix_with_black(vars_copy["accent-open"], 0.10))
    vars_copy.setdefault("status-open", vars_copy["muted"])
    vars_copy.setdefault("status-open-soft", _mix_with_white(vars_copy["status-open"], 0.82))
    vars_copy.setdefault("status-open-strong", _mix_with_black(vars_copy["status-open"], 0.16))
    vars_copy.setdefault("danger", "#a63d2f")
    vars_copy.setdefault("danger-soft", _mix_with_white(vars_copy["danger"], 0.84))
    vars_copy.setdefault("info", vars_copy["primary-deep"])
    vars_copy.setdefault("info-soft", _mix_with_white(vars_copy["info"], 0.84))

    resolved = {
        "name": base["name"],
        "description": base["description"],
        "colors": base["colors"],
        "vars": vars_copy,
    }
    return candidate, resolved
