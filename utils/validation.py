import re


# Standalone validation utilities extracted from PlanillaFinalApp
# The class methods call these same implementations.

def parse_float(value):
    if not value: return 0.0
    if isinstance(value, (int, float)): return float(value)
    val_str = str(value).strip()
    if not val_str: return 0.0
    if ',' in val_str and '.' in val_str:
        if val_str.rfind(',') > val_str.rfind('.'): val_str = val_str.replace('.', '').replace(',', '.')
        else: val_str = val_str.replace(',', '')
    elif ',' in val_str: val_str = val_str.replace(',', '.')
    val_str = re.sub(r'[^\d.-]', '', val_str)
    try: return float(val_str)
    except: return 0.0


def clean_filename(text):
    return re.sub(r'[\\/*?:"<>|]', "", str(text)).strip()


def contrast_text(hex_color):
    """Devuelve '#FFFFFF' o '#000000' segun la luminancia del color de fondo."""
    try:
        r = int(hex_color[1:3], 16)
        g = int(hex_color[3:5], 16)
        b = int(hex_color[5:7], 16)
        lum = 0.2126 * r + 0.7152 * g + 0.0722 * b
        return "#FFFFFF" if lum < 140 else "#000000"
    except:
        return "#FFFFFF"
