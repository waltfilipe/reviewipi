# app.py (v3) - position-based attributes + elegant PDF export
import os
import time
import streamlit as st
import plotly.graph_objects as go
import pandas as pd
import base64
from pathlib import Path
from datetime import date, datetime

# Supabase client
from supabase import create_client, Client

st.set_page_config(page_title="SGA - IDP", page_icon="⚽", layout="wide")

ADMIN_PASSWORD = os.getenv("SGA_ADMIN_PASSWORD", "changeme")

PLAYER_IMG_W = 180
PLAYER_IMG_H = 240

LOGO_URL = "https://github.com/Dev-SGA/IPI_test/blob/main/Logo_SGA_Completa_Horizontal_AzulEscuro%20(1).png?raw=true"
LOGO_PATH = "assets/sga_logo.png"


def get_logo_base64(path: str) -> str:
    file = Path(path)
    if file.exists():
        b64 = base64.b64encode(file.read_bytes()).decode()
        suffix = file.suffix.replace(".", "")
        mime = f"image/{suffix}" if suffix != "svg" else "image/svg+xml"
        return f"data:{mime};base64,{b64}"
    return ""


LOGO_SRC = get_logo_base64(LOGO_PATH) or LOGO_URL

FONT_DISPLAY = "'Orbitron', sans-serif"
FONT_GRAPHIC = "'Source Sans 3', sans-serif"
FONT_DOCUMENT = "'Trebuchet MS', 'Source Sans 3', sans-serif"

# ---------------------------
# Position definitions
# ---------------------------
POSITIONS = ["CB", "FB", "CDM", "AM", "WG", "ST"]

POSITION_LABELS = {
    "CB":  "Center-Back",
    "FB":  "Full-Back",
    "CDM": "Central Def. Midfielder",
    "AM":  "Attacking Midfielder",
    "WG":  "Winger",
    "ST":  "Striker",
}

POSITION_SKILLS = {
    "CB": [
        "General Passing", "Long Ball", "1st Touch", "Carrying",
        "Heading Direction", "Aerial Duels", "1v1 Defending", "Off Ball Defending",
    ],
    "FB": [
        "General Passing", "Crossing", "1st Touch", "1v1 Attacking",
        "Heading Direction", "Aerial Duels", "1v1 Defending", "Off Ball Defending",
    ],
    "CDM": [
        "General Passing", "Progressive Passing", "1st Touch", "Pressure Evasion",
        "Aerial Duels", "Second Ball Reaction", "Cover & Balance", "Interceptions",
    ],
    "AM": [
        "Final Third Passing", "Through Balls", "1st Touch", "1v1 Attacking",
        "Finishing", "Box Positioning", "Pressing Actions", "Counter-Pressing React",
    ],
    "WG": [
        "Final Ball", "Combination Play", "1v1 Attacking", "Ball Carrying in Space",
        "Finishing", "Aerial Timing", "Pressing Actions", "Tracking Back",
    ],
    "ST": [
        "Link-Up Play", "Final Pass", "Ball Protection", "Finishing Touches",
        "Finishing", "Heading", "Pressing Triggers", "Defensive Positioning",
    ],
}

MENTAL_SKILLS = ["Awareness", "Effort", "Team Work"]
MOG_CATEGORIES = [
    "Off. Possession", "Off. Transition", "Def. Organization",
    "Def. Transition", "Set Pieces",
]
LEVELS = ["Above Level", "Good", "Average", "Below Level"]


def _pos_skills(position: str) -> list:
    return POSITION_SKILLS.get(position, POSITION_SKILLS["CB"])


def _pos_label(position: str) -> str:
    return POSITION_LABELS.get(position, position)


def _section_title(position: str) -> str:
    return f"{position} – {_pos_label(position)}"


# ---------------------------
# Helper: trigger safe rerun
# ---------------------------
def trigger_rerun():
    try:
        st.experimental_set_query_params(_refresh=int(time.time()))
    except Exception:
        st.session_state["_refresh_token"] = int(time.time())


# ---------------------------
# Session helpers (auth)
# ---------------------------
if "admin_authenticated" not in st.session_state:
    st.session_state["admin_authenticated"] = False

def is_admin() -> bool:
    return bool(st.session_state.get("admin_authenticated", False))

def try_login(password: str) -> bool:
    if password == ADMIN_PASSWORD:
        st.session_state["admin_authenticated"] = True
        return True
    return False

def logout_admin():
    st.session_state["admin_authenticated"] = False


# ---------------------------
# Database helpers (Supabase)
# ---------------------------
SUPABASE_URL = os.getenv("SUPABASE_URL") or (st.secrets.get("SUPABASE_URL") if hasattr(st, "secrets") else None)
SUPABASE_KEY = os.getenv("SUPABASE_KEY") or (st.secrets.get("SUPABASE_KEY") if hasattr(st, "secrets") else None)

if not SUPABASE_URL or not SUPABASE_KEY:
    st.warning("Supabase não está configurado. Defina SUPABASE_URL e SUPABASE_KEY nas variáveis de ambiente / secrets.")
    supabase = None
else:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


def _resp_error(resp):
    if resp is None:
        return "No response from Supabase"
    try:
        err_attr = getattr(resp, "error", None)
        if err_attr:
            return err_attr
    except Exception:
        pass
    try:
        if isinstance(resp, dict) and resp.get("error"):
            return resp.get("error")
        get_err = getattr(resp, "get", None)
        if callable(get_err):
            err = resp.get("error", None)
            if err:
                return err
    except Exception:
        pass
    try:
        code = getattr(resp, "status_code", None)
        if code is not None and not (200 <= int(code) < 300):
            data = getattr(resp, "data", None)
            return f"status={code}, data={data}"
    except Exception:
        pass
    return None


def _resp_data(resp):
    if resp is None:
        return None
    try:
        return getattr(resp, "data", None)
    except Exception:
        try:
            return resp.get("data")
        except Exception:
            return None


def init_db():
    return


init_db()


def get_players():
    if not supabase:
        return pd.DataFrame(columns=["id", "name", "position", "club", "photo_url"])
    resp = supabase.table("players").select("*").execute()
    err = _resp_error(resp)
    if err:
        st.warning(f"Warning fetching players: {err}")
        return pd.DataFrame(columns=["id", "name", "position", "club", "photo_url"])
    data = _resp_data(resp) or []
    df = pd.DataFrame(data)
    if not df.empty and "name" in df.columns:
        df = df.sort_values("name").reset_index(drop=True)
    return df


def add_player(name, position, club, photo_url):
    if not supabase:
        raise Exception("Supabase não configurado.")
    payload = {"name": name, "position": position, "club": club, "photo_url": photo_url}
    resp = supabase.table("players").insert(payload).execute()
    err = _resp_error(resp)
    if err:
        raise Exception(err if isinstance(err, str) else str(err))
    return _resp_data(resp)


def delete_player(player_id: int):
    if not supabase:
        raise Exception("Supabase não configurado.")
    resp = supabase.table("players").delete().eq("id", player_id).execute()
    err = _resp_error(resp)
    if err:
        raise Exception(err if isinstance(err, str) else str(err))
    return _resp_data(resp)


def update_player(player_id: int, name: str, position: str, club: str, photo_url: str):
    if not supabase:
        raise Exception("Supabase não configurado.")
    payload = {"name": name.strip(), "position": position.strip(), "club": club.strip(), "photo_url": photo_url.strip()}
    resp = supabase.table("players").update(payload).eq("id", player_id).execute()
    err = _resp_error(resp)
    if err:
        raise Exception(err if isinstance(err, str) else str(err))
    return _resp_data(resp)


def save_evaluation(player_id, analyst, eval_date, skills, mog, strengths, improvements):
    if not supabase:
        raise Exception("Supabase não configurado.")
    ev = {"player_id": player_id, "analyst": analyst, "eval_date": eval_date}
    resp = supabase.table("evaluations").insert(ev).execute()
    err = _resp_error(resp)
    if err:
        raise Exception(err if isinstance(err, str) else str(err))
    edata = _resp_data(resp) or []
    if not edata:
        raise Exception("Falha ao criar avaliação (resposta vazia)")
    eid = edata[0]["id"]

    rows = []
    for cat, sd in (skills or {}).items():
        for sn, lv in sd.items():
            if str(sn).strip() and str(lv).strip():
                rows.append({"evaluation_id": eid, "category": cat, "skill_name": sn.strip(), "level": lv.strip()})
    if rows:
        r = supabase.table("eval_skills").insert(rows).execute()
        e = _resp_error(r)
        if e:
            raise Exception(e)

    rows = [{"evaluation_id": eid, "category": c, "value": int(v)} for c, v in (mog or {}).items()]
    if rows:
        r = supabase.table("eval_mog").insert(rows).execute()
        e = _resp_error(r)
        if e:
            raise Exception(e)

    rows = []
    for i, t in enumerate(strengths or []):
        if str(t).strip():
            rows.append({"evaluation_id": eid, "note_type": "strength", "position": i + 1, "text": t.strip()})
    for i, t in enumerate(improvements or []):
        if str(t).strip():
            rows.append({"evaluation_id": eid, "note_type": "improve", "position": i + 1, "text": t.strip()})
    if rows:
        r = supabase.table("eval_notes").insert(rows).execute()
        e = _resp_error(r)
        if e:
            raise Exception(e)

    return eid


def update_evaluation_meta(evaluation_id: int, analyst: str, eval_date: str):
    if not supabase:
        raise Exception("Supabase não configurado.")
    resp = supabase.table("evaluations").update({"analyst": analyst, "eval_date": eval_date}).eq("id", evaluation_id).execute()
    err = _resp_error(resp)
    if err:
        raise Exception(err if isinstance(err, str) else str(err))
    return _resp_data(resp)


def replace_evaluation_content(evaluation_id: int, skills: dict, mog: dict, strengths: list, improvements: list):
    if not supabase:
        raise Exception("Supabase não configurado.")
    r = supabase.table("eval_skills").delete().eq("evaluation_id", evaluation_id).execute()
    e = _resp_error(r)
    if e:
        raise Exception(e)
    r = supabase.table("eval_mog").delete().eq("evaluation_id", evaluation_id).execute()
    e = _resp_error(r)
    if e:
        raise Exception(e)
    r = supabase.table("eval_notes").delete().eq("evaluation_id", evaluation_id).execute()
    e = _resp_error(r)
    if e:
        raise Exception(e)

    rows = []
    for cat, sd in (skills or {}).items():
        for sn, lv in sd.items():
            if str(sn).strip() and str(lv).strip():
                rows.append({"evaluation_id": evaluation_id, "category": cat, "skill_name": sn.strip(), "level": lv.strip()})
    if rows:
        r = supabase.table("eval_skills").insert(rows).execute()
        e = _resp_error(r)
        if e:
            raise Exception(e)

    rows = [{"evaluation_id": evaluation_id, "category": c, "value": int(v)} for c, v in (mog or {}).items()]
    if rows:
        r = supabase.table("eval_mog").insert(rows).execute()
        e = _resp_error(r)
        if e:
            raise Exception(e)

    rows = []
    for i, t in enumerate(strengths or []):
        if str(t).strip():
            rows.append({"evaluation_id": evaluation_id, "note_type": "strength", "position": i + 1, "text": t.strip()})
    for i, t in enumerate(improvements or []):
        if str(t).strip():
            rows.append({"evaluation_id": evaluation_id, "note_type": "improve", "position": i + 1, "text": t.strip()})
    if rows:
        r = supabase.table("eval_notes").insert(rows).execute()
        e = _resp_error(r)
        if e:
            raise Exception(e)


def get_latest_evaluation(player_id):
    if not supabase:
        return None
    resp = supabase.table("evaluations").select("*").eq("player_id", player_id).execute()
    err = _resp_error(resp)
    if err:
        st.warning(f"Warning fetching evaluations: {err}")
        return None
    evs = _resp_data(resp) or []
    if not evs:
        return None
    evs_sorted = sorted(evs, key=lambda x: (x.get("eval_date") or "", x.get("id") or 0), reverse=True)
    ev = evs_sorted[0]
    eid = ev["id"]

    skills = {}
    resp = supabase.table("eval_skills").select("category,skill_name,level").eq("evaluation_id", eid).execute()
    for r in (_resp_data(resp) or []):
        skills.setdefault(r["category"], {})[r["skill_name"]] = r["level"]

    mog = {}
    resp = supabase.table("eval_mog").select("category,value").eq("evaluation_id", eid).execute()
    for r in (_resp_data(resp) or []):
        mog[r["category"]] = r["value"]

    strengths = []
    improvements = []
    resp = supabase.table("eval_notes").select("note_type,position,text").eq("evaluation_id", eid).execute()
    notes = _resp_data(resp) or []
    try:
        notes_sorted = sorted(notes, key=lambda r: int(r.get("position") or 0))
    except Exception:
        notes_sorted = sorted(notes, key=lambda r: (r.get("position") or 0))
    for r in notes_sorted:
        if r.get("note_type") == "strength":
            strengths.append(r.get("text"))
        else:
            improvements.append(r.get("text"))

    return {
        "id": eid,
        "analyst": ev.get("analyst"),
        "eval_date": str(ev.get("eval_date")),
        "skills": skills,
        "mog": mog,
        "strengths": strengths,
        "improvements": improvements,
    }


# Module-level font registry — populated lazily on first PDF call
_PDF_FONTS: dict = {}

# ---------------------------
# PDF Report Generator (v3 — elegant, fixed MoG bars, logo header)
# ---------------------------
def generate_player_pdf(
    player_name: str,
    position: str,
    club: str,
    photo_url: str,
    evaluation: dict,
    pos_skills_list: list,
) -> bytes:
    """Generate an elegant IPI report as PDF bytes using reportlab."""
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib import colors as rl_colors
        from reportlab.lib.units import mm
        from reportlab.platypus import (
            SimpleDocTemplate, Table, TableStyle,
            Paragraph, Spacer, Image as RLImage,
        )
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
    except ImportError:
        raise ImportError("reportlab não instalado. Execute: pip install reportlab")

    import io as _io
    import urllib.request as _urlreq
    import re as _re

    # ── Lazy Google Fonts registration (once per process) ────────────────
    global _PDF_FONTS
    if not _PDF_FONTS:
        _fmap = {"display": "Helvetica-Bold", "body": "Helvetica", "body_b": "Helvetica-Bold"}
        try:
            from reportlab.pdfbase.ttfonts import TTFont as _TTF
            from reportlab.pdfbase import pdfmetrics as _pdm
            _ua = "Mozilla/4.0 (compatible; MSIE 5.5; Windows NT 5.0)"

            def _dlfont(fam, wt, nm):
                try:
                    req = _urlreq.Request(
                        f"https://fonts.googleapis.com/css?family={fam}:{wt}",
                        headers={"User-Agent": _ua})
                    css = _urlreq.urlopen(req, timeout=6).read().decode("utf-8")
                    urls = _re.findall(r'src:\s*url\((https://fonts\.gstatic\.com/[^)]+)\)', css)
                    if not urls:
                        return False
                    freq = _urlreq.Request(urls[0], headers={"User-Agent": _ua})
                    _pdm.registerFont(_TTF(nm, _io.BytesIO(_urlreq.urlopen(freq, timeout=6).read())))
                    return True
                except Exception:
                    return False

            if _dlfont("Orbitron", "900", "Orbitron-Black"):
                _fmap["display"] = "Orbitron-Black"
            if _dlfont("Source+Sans+3", "400", "SourceSans3"):
                _fmap["body"] = "SourceSans3"
            if _dlfont("Source+Sans+3", "700", "SourceSans3-Bold"):
                _fmap["body_b"] = "SourceSans3-Bold"
        except Exception:
            pass
        _PDF_FONTS.update(_fmap)

    F_DISP = _PDF_FONTS.get("display", "Helvetica-Bold")
    F_BODY = _PDF_FONTS.get("body",    "Helvetica")
    F_BOLD = _PDF_FONTS.get("body_b",  "Helvetica-Bold")

    buf = _io.BytesIO()
    PAGE_W, _ = A4
    MAR = 14 * mm
    CW = PAGE_W - 2 * MAR  # usable content width (points)

    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=MAR, rightMargin=MAR,
        topMargin=MAR, bottomMargin=MAR,
    )

    # ── Colour palette ────────────────────────────────────────────────────
    NAVY     = rl_colors.HexColor("#5aaaf5")   # top header bar — matches dashboard gradient
    HDR_TEXT = rl_colors.HexColor("#0A2A4A")   # header text — matches dashboard h1
    HDR_SEP  = rl_colors.HexColor("#1A4870")   # divider on light-blue header bg
    INDIGO  = rl_colors.HexColor("#1A237E")   # section headers
    BLUE    = rl_colors.HexColor("#1565C0")   # mog bar filled / accent
    BG      = rl_colors.HexColor("#EEF2FA")   # section body background
    CARD    = rl_colors.HexColor("#F7F9FC")   # player card background
    CWHT    = rl_colors.white
    CDARK   = rl_colors.HexColor("#1C2B3A")   # primary body text
    CMED    = rl_colors.HexColor("#546E7A")   # secondary / meta text
    CSEP    = rl_colors.HexColor("#BCC8E0")   # dividers / borders
    CBAR_E  = rl_colors.HexColor("#D0DCEF")   # mog bar empty portion

    # Badge colours — slightly pastel (muted / ~20 % lighter than v2)
    LVL_BG = {
        "Above Level": rl_colors.HexColor("#3D8B50"),
        "Good":        rl_colors.HexColor("#4A9E5E"),
        "Average":     rl_colors.HexColor("#D07A28"),
        "Below Level": rl_colors.HexColor("#C04040"),
    }

    # ── Paragraph style factory ───────────────────────────────────────────
    def _ps(name, font="Helvetica", size=9, lead=12, color=None, align=TA_LEFT):
        return ParagraphStyle(
            name, fontName=font, fontSize=size, leading=lead,
            textColor=color or CWHT, alignment=align,
        )

    S_HDR_TITLE = _ps("hdr_t",  F_DISP, 13, 17, HDR_TEXT, TA_RIGHT)
    S_HDR_LOGO  = _ps("hdr_l",  F_DISP, 16, 20, HDR_TEXT, TA_LEFT)
    S_SEC       = _ps("sec",    F_DISP,  8, 11, CWHT,     TA_LEFT)
    S_PLYR_NAME = _ps("pn",     F_BOLD, 17, 21, CDARK,    TA_LEFT)
    S_PLYR_POS  = _ps("pp",     F_BOLD, 10, 13, BLUE,     TA_LEFT)
    S_PLYR_CLB  = _ps("pc",     F_BODY,  9, 12, CMED,     TA_LEFT)
    S_META      = _ps("meta",   F_BODY,  8, 11, CMED,     TA_LEFT)
    S_SK_LBL    = _ps("sklbl",  F_BODY,  8, 11, CDARK,    TA_RIGHT)
    S_BADGE     = _ps("badge",  F_BOLD,  7,  9, CWHT,     TA_CENTER)
    S_BADGE_NA  = _ps("badgna", F_BODY,  7,  9, rl_colors.HexColor("#9E9E9E"), TA_CENTER)
    S_MOG_CAT   = _ps("mccat",  F_BOLD,  8, 11, CDARK,    TA_LEFT)
    S_MOG_VAL   = _ps("mcval",  F_BOLD,  9, 12, BLUE,     TA_RIGHT)
    S_NOTE_H    = _ps("noteh",  F_DISP,  8, 11, CWHT,     TA_LEFT)
    S_NOTE_B    = _ps("noteb",  F_BODY,  8, 12, CDARK,    TA_LEFT)

    # ── Fetch remote assets ───────────────────────────────────────────────
    logo_img = None
    try:
        req = _urlreq.Request(LOGO_URL, headers={"User-Agent": "Mozilla/5.0"})
        raw = _urlreq.urlopen(req, timeout=5).read()
        _logo_rl = RLImage(_io.BytesIO(raw))
        _logo_target_w = 42 * mm
        _logo_rl.drawWidth  = _logo_target_w
        _logo_rl.drawHeight = _logo_target_w * _logo_rl.imageHeight / _logo_rl.imageWidth
        logo_img = _logo_rl
    except Exception:
        pass

    photo_img = None
    if photo_url:
        try:
            req = _urlreq.Request(photo_url, headers={"User-Agent": "Mozilla/5.0"})
            raw = _urlreq.urlopen(req, timeout=4).read()
            photo_img = RLImage(_io.BytesIO(raw), width=28 * mm, height=37 * mm)
        except Exception:
            pass

    # ── Helper: section header ────────────────────────────────────────────
    def sec_hdr(title: str):
        t = Table([[Paragraph(title.upper(), S_SEC)]], colWidths=[CW])
        t.setStyle(TableStyle([
            ("BACKGROUND",    (0, 0), (-1, -1), INDIGO),
            ("TOPPADDING",    (0, 0), (-1, -1),  6),
            ("BOTTOMPADDING", (0, 0), (-1, -1),  6),
            ("LEFTPADDING",   (0, 0), (-1, -1), 10),
            ("RIGHTPADDING",  (0, 0), (-1, -1), 10),
        ]))
        return t

    # ── Helper: 2-column skill badge grid ────────────────────────────────
    def skill_grid(items: list):
        NCOLS = 2
        items = list(items)
        while len(items) % NCOLS:
            items.append(("", ""))

        SLOT_W = CW / NCOLS
        LBL_W  = SLOT_W * 0.60
        BDG_W  = SLOT_W * 0.40
        col_ws = [LBL_W, BDG_W] * NCOLS

        rows = []
        cmds = [
            ("BACKGROUND",    (0, 0), (-1, -1), BG),
            ("TOPPADDING",    (0, 0), (-1, -1),  5),
            ("BOTTOMPADDING", (0, 0), (-1, -1),  5),
            ("LEFTPADDING",   (0, 0), (-1, -1),  8),
            ("RIGHTPADDING",  (0, 0), (-1, -1),  8),
            ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ]

        for ri, row_start in enumerate(range(0, len(items), NCOLS)):
            chunk = items[row_start: row_start + NCOLS]
            row = []
            for ci, (skill, level) in enumerate(chunk):
                bcol = ci * 2 + 1
                if skill:
                    row.append(Paragraph(skill, S_SK_LBL))
                    if level in LVL_BG:
                        row.append(Paragraph(level, S_BADGE))
                        cmds.append(("BACKGROUND", (bcol, ri), (bcol, ri), LVL_BG[level]))
                    elif level:
                        row.append(Paragraph(level, S_BADGE))
                    else:
                        row.append(Paragraph("—", S_BADGE_NA))
                else:
                    row.append(Paragraph("", S_SK_LBL))
                    row.append(Paragraph("", S_BADGE_NA))
            rows.append(row)

        # Subtle row dividers
        for ri in range(len(rows) - 1):
            cmds.append(("LINEBELOW", (0, ri), (-1, ri), 0.5, CSEP))

        t = Table(rows, colWidths=col_ws)
        t.setStyle(TableStyle(cmds))
        return t

    # ── Helper: notes table ───────────────────────────────────────────────
    def notes_tbl(title: str, items: list, w: float):
        rows = [[Paragraph(title.upper(), S_NOTE_H)]]
        for i, txt in enumerate(items or []):
            if txt and str(txt).strip():
                rows.append([Paragraph(f"{i + 1}.  {str(txt).strip()}", S_NOTE_B)])
        if len(rows) == 1:
            rows.append([Paragraph("—", S_NOTE_B)])
        t = Table(rows, colWidths=[w])
        t.setStyle(TableStyle([
            ("BACKGROUND",    (0, 0), (0,  0), INDIGO),
            ("BACKGROUND",    (0, 1), (0, -1), BG),
            ("TOPPADDING",    (0, 0), (-1, -1),  6),
            ("BOTTOMPADDING", (0, 0), (-1, -1),  6),
            ("LEFTPADDING",   (0, 0), (-1, -1), 10),
            ("RIGHTPADDING",  (0, 0), (-1, -1), 10),
            ("VALIGN",        (0, 0), (-1, -1), "TOP"),
        ]))
        return t

    # ── Build story ───────────────────────────────────────────────────────
    story = []
    sk            = (evaluation or {}).get("skills", {})
    analyst_val   = str((evaluation or {}).get("analyst",  "—") or "—")
    eval_date_val = str((evaluation or {}).get("eval_date","—") or "—")

    # 1 ── Header bar (logo + title, mirroring the dashboard header)
    LOGO_COL_W = 44 * mm if logo_img else 28 * mm
    hdr_left   = logo_img if logo_img else Paragraph("SGA", S_HDR_LOGO)
    hdr_right  = Paragraph("INDIVIDUAL PLAYER INDICATORS", S_HDR_TITLE)

    hdr = Table([[hdr_left, hdr_right]], colWidths=[LOGO_COL_W, CW - LOGO_COL_W])
    hdr.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), NAVY),
        ("TOPPADDING",    (0, 0), (-1, -1), 11),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 11),
        ("LEFTPADDING",   (0, 0), (0,  -1), 13),
        ("RIGHTPADDING",  (1, 0), (1,  -1), 13),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("LINEAFTER",     (0, 0), (0,  -1),  1, HDR_SEP),
    ]))
    story.append(hdr)
    story.append(Spacer(1, 4 * mm))

    # 2 ── Player profile card
    PHOTO_W = 30 * mm
    INFO_W  = CW - PHOTO_W if photo_img else CW

    pos_label_str = (
        f"{position} – {POSITION_LABELS.get(position, position)}"
        if position in POSITIONS else (position or "—")
    )
    meta_str = f"Analyst: {analyst_val}   •   Date: {eval_date_val}"

    info_rows = [
        [Paragraph(player_name, S_PLYR_NAME)],
        [Paragraph(pos_label_str, S_PLYR_POS)],
        [Paragraph(club or "—", S_PLYR_CLB)],
        [Paragraph(meta_str, S_META)],
    ]
    info_t = Table(info_rows, colWidths=[INFO_W])
    info_t.setStyle(TableStyle([
        ("TOPPADDING",    (0, 0), (0, 0),   5),
        ("BOTTOMPADDING", (0, 0), (0, 0),   2),
        ("TOPPADDING",    (0, 1), (0, 1),   1),
        ("BOTTOMPADDING", (0, 1), (0, 1),   1),
        ("TOPPADDING",    (0, 2), (0, 2),   1),
        ("BOTTOMPADDING", (0, 2), (0, 2),   5),
        ("TOPPADDING",    (0, 3), (0, 3),   4),
        ("BOTTOMPADDING", (0, 3), (0, 3),   5),
        ("LEFTPADDING",   (0, 0), (-1, -1), 10),
        ("RIGHTPADDING",  (0, 0), (-1, -1),  8),
    ]))

    if photo_img:
        profile_t = Table([[photo_img, info_t]], colWidths=[PHOTO_W, INFO_W])
        profile_t.setStyle(TableStyle([
            ("BACKGROUND",    (0, 0), (-1, -1), CARD),
            ("TOPPADDING",    (0, 0), (0,  -1),  8),
            ("BOTTOMPADDING", (0, 0), (0,  -1),  8),
            ("LEFTPADDING",   (0, 0), (0,  -1),  8),
            ("RIGHTPADDING",  (0, 0), (0,  -1),  4),
            ("LEFTPADDING",   (1, 0), (1,  -1),  0),
            ("RIGHTPADDING",  (1, 0), (1,  -1),  0),
            ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
            ("BOX",           (0, 0), (-1, -1), 0.5, CSEP),
        ]))
    else:
        profile_t = Table([[info_t]], colWidths=[CW])
        profile_t.setStyle(TableStyle([
            ("BACKGROUND",    (0, 0), (-1, -1), CARD),
            ("TOPPADDING",    (0, 0), (-1, -1),  0),
            ("BOTTOMPADDING", (0, 0), (-1, -1),  0),
            ("LEFTPADDING",   (0, 0), (-1, -1),  0),
            ("RIGHTPADDING",  (0, 0), (-1, -1),  0),
            ("BOX",           (0, 0), (-1, -1), 0.5, CSEP),
        ]))

    story.append(profile_t)
    story.append(Spacer(1, 4 * mm))

    # 3 ── Technical Indicators
    pos_code   = position if position in POSITIONS else None
    tskills    = pos_skills_list if pos_code else list(sk.get("technical", {}).keys())
    tech_items = [(s, sk.get("technical", {}).get(s, "")) for s in tskills]
    story.append(sec_hdr("Technical Indicators"))
    if tech_items:
        story.append(skill_grid(tech_items))
    story.append(Spacer(1, 4 * mm))

    # 4 ── Player-Specific Indicators (only if present)
    ps_dict = sk.get("player_specific", {})
    if ps_dict:
        story.append(sec_hdr("Player-Specific Indicators"))
        story.append(skill_grid(list(ps_dict.items())))
        story.append(Spacer(1, 4 * mm))

    # 5 ── Mental
    mental_items = [(s, sk.get("mental", {}).get(s, "")) for s in MENTAL_SKILLS]
    story.append(sec_hdr("Mental"))
    if mental_items:
        story.append(skill_grid(mental_items))
    story.append(Spacer(1, 4 * mm))

    # 6 ── Moments of the Game — bars constrained to cell width
    mog_data = (evaluation or {}).get("mog", {})
    if mog_data:
        story.append(sec_hdr("Moments of the Game (MoG)"))

        LBL_W  = 52 * mm
        VAL_W  = 13 * mm
        BAR_CW = CW - LBL_W - VAL_W   # total bar column width (points)
        BAR_LP = 6                     # bar cell left padding (points)
        BAR_RP = 6                     # bar cell right padding (points)
        BAR_IW = BAR_CW - BAR_LP - BAR_RP  # drawable bar width

        mog_rows = []
        mog_cmds = [
            ("BACKGROUND",    (0, 0), (-1, -1), BG),
            ("TOPPADDING",    (0, 0), (-1, -1),  6),
            ("BOTTOMPADDING", (0, 0), (-1, -1),  6),
            ("LEFTPADDING",   (0, 0), (0,  -1), 10),   # label
            ("RIGHTPADDING",  (0, 0), (0,  -1),  4),
            ("LEFTPADDING",   (1, 0), (1,  -1),  4),   # value
            ("RIGHTPADDING",  (1, 0), (1,  -1),  8),
            ("LEFTPADDING",   (2, 0), (2,  -1), BAR_LP),  # bar cell
            ("RIGHTPADDING",  (2, 0), (2,  -1), BAR_RP),
            ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ]

        mog_list = list(mog_data.items())
        for ri, (cat, raw) in enumerate(mog_list):
            try:
                v = max(0, min(100, int(raw)))
            except Exception:
                v = 0

            fw = BAR_IW * v / 100
            ew = BAR_IW - fw
            # Prevent zero-width columns
            if fw < 1:
                fw, ew = 1.0, BAR_IW - 1.0
            elif ew < 1:
                ew, fw = 1.0, BAR_IW - 1.0

            bar = Table([["", ""]], colWidths=[fw, ew])
            bar.setStyle(TableStyle([
                ("BACKGROUND",    (0, 0), (0, 0), BLUE),
                ("BACKGROUND",    (1, 0), (1, 0), CBAR_E),
                ("TOPPADDING",    (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LEFTPADDING",   (0, 0), (-1, -1), 0),
                ("RIGHTPADDING",  (0, 0), (-1, -1), 0),
            ]))

            mog_rows.append([
                Paragraph(cat, S_MOG_CAT),
                Paragraph(str(v), S_MOG_VAL),
                bar,
            ])
            if ri < len(mog_list) - 1:
                mog_cmds.append(("LINEBELOW", (0, ri), (-1, ri), 0.5, CSEP))

        mog_t = Table(mog_rows, colWidths=[LBL_W, VAL_W, BAR_CW])
        mog_t.setStyle(TableStyle(mog_cmds))
        story.append(mog_t)
        story.append(Spacer(1, 4 * mm))

    # 7 ── Strengths / Need to Improve
    strengths    = (evaluation or {}).get("strengths", [])
    improvements = (evaluation or {}).get("improvements", [])
    half = (CW - 3 * mm) / 2
    si = Table(
        [[notes_tbl("My Strengths",    strengths,    half),
          notes_tbl("Need to Improve", improvements, half)]],
        colWidths=[half + 1.5 * mm, half + 1.5 * mm],
    )
    si.setStyle(TableStyle([
        ("LEFTPADDING",   (0, 0), (-1, -1), 0),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 0),
        ("TOPPADDING",    (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ("VALIGN",        (0, 0), (-1, -1), "TOP"),
    ]))
    story.append(si)

    doc.build(story)
    buf.seek(0)
    return buf.read()


# ---------------------------
# UI: Sidebar Admin area
# ---------------------------
with st.sidebar.expander("Admin"):
    if is_admin():
        st.success("🔐 Autenticado como admin")
        if st.button("Logout", use_container_width=True):
            logout_admin()
            trigger_rerun()
    else:
        pwd = st.text_input("Senha de administrador", type="password")
        if st.button("Entrar", use_container_width=True):
            if try_login(pwd):
                st.success("Autenticado com sucesso.")
            else:
                st.error("Senha incorreta.")


# ---------------------------
# UI: Sidebar navigation
# ---------------------------
page = st.sidebar.radio("Navegação", ["📊 Dashboard", "📝 Nova Avaliação", "➕ Cadastrar Jogador", "📚 Jogadores"])


# ---------------------------
# Page: Cadastrar Jogador (protected)
# ---------------------------
if page == "➕ Cadastrar Jogador":
    st.header("Cadastrar Novo Jogador")

    if not is_admin():
        st.warning("Atenção: criar jogadores exige autenticação de administrador.")
        st.info("Use o painel 'Admin' na barra lateral para entrar.")
        st.stop()

    with st.form("form_player"):
        c1, c2 = st.columns(2)
        with c1:
            name = st.text_input("Nome completo *")
            position = st.selectbox(
                "Posição",
                POSITIONS,
                format_func=lambda p: f"{p} – {_pos_label(p)}",
            )
        with c2:
            club = st.text_input("Clube", placeholder="Ex: Houston Dynamo")
            photo_url = st.text_input("URL da foto")
        if st.form_submit_button("💾 Cadastrar", use_container_width=True):
            if not name.strip():
                st.error("Nome é obrigatório.")
            else:
                try:
                    add_player(name.strip(), position.strip(), club.strip(), photo_url.strip())
                    st.success(f"✅ Jogador **{name}** cadastrado!")
                    trigger_rerun()
                except Exception as e:
                    msg = str(e).lower()
                    if "unique" in msg or "duplicate" in msg or "already exists" in msg:
                        st.error("Já existe um jogador com esse nome. Escolha outro nome.")
                    else:
                        st.error(f"Erro ao cadastrar jogador: {e}")


# ---------------------------
# Page: Nova Avaliação
# ---------------------------
elif page == "📝 Nova Avaliação":
    st.header("Nova Avaliação")
    players_df = get_players()
    if players_df.empty:
        st.warning("Nenhum jogador cadastrado. Vá em **➕ Cadastrar Jogador**.")
        st.stop()

    sel_col, pos_col = st.columns(2)
    with sel_col:
        player_name = st.selectbox("Jogador", players_df["name"].tolist(), key="eval_player_sel")
    player_row = players_df[players_df["name"] == player_name].iloc[0]
    stored_pos = player_row["position"] if player_row["position"] in POSITIONS else POSITIONS[0]
    with pos_col:
        eval_position = st.selectbox(
            "Posição",
            POSITIONS,
            index=POSITIONS.index(stored_pos),
            key="eval_position_sel",
            format_func=lambda p: f"{p} – {_pos_label(p)}",
        )

    pos_skills = _pos_skills(eval_position)

    st.divider()

    with st.form("form_evaluation"):
        fa, fb = st.columns(2)
        with fa:
            analyst = st.text_input("Nome do Analista *")
        with fb:
            eval_date = st.date_input("Data", value=date.today())
        st.divider()

        # Technical — position-specific
        st.subheader(f"🎯 {_section_title(eval_position)}")
        tc = st.columns(4)
        tv = {}
        for i, s in enumerate(pos_skills):
            with tc[i % 4]:
                tv[s] = st.selectbox(s, LEVELS, key=f"t_{s}")

        st.divider()

        # Player-Specific Indicators (customizable)
        st.subheader("⚡ Player-Specific Indicators")
        st.caption("Digite o nome do atributo e escolha a classificação. Deixe em branco para ignorar.")
        ps = {}
        pn = st.columns(4)
        pl = st.columns(4)
        for i in range(4):
            with pn[i]:
                an = st.text_input(f"Atributo {i+1}", key=f"psn_{i}", placeholder="Ex: Speed")
            with pl[i]:
                al = st.selectbox(f"Nível {i+1}", [""] + LEVELS, key=f"psl_{i}")
            if an.strip() and al:
                ps[an.strip()] = al

        st.divider()

        # Mental — same for all
        st.subheader("🧠 Mental")
        mc = st.columns(4)
        mv = {}
        for i, s in enumerate(MENTAL_SKILLS):
            with mc[i % 4]:
                mv[s] = st.selectbox(s, LEVELS, key=f"m_{s}")

        st.divider()

        # MoG
        st.subheader("📐 Moments of the Game (MoG)")
        mgc = st.columns(5)
        mgv = {}
        for i, c in enumerate(MOG_CATEGORIES):
            with mgc[i]:
                mgv[c] = st.slider(c, 0, 100, 50, key=f"mog_{c}")

        st.divider()

        col_s, col_i = st.columns(2)
        with col_s:
            st.subheader("💪 My Strengths")
            s1 = st.text_input("Strength 1")
            s2 = st.text_input("Strength 2")
            s3 = st.text_input("Strength 3")
        with col_i:
            st.subheader("📈 Need to Improve")
            i1 = st.text_input("Improvement 1")
            i2 = st.text_input("Improvement 2")
            i3 = st.text_input("Improvement 3")

        st.divider()

        if st.form_submit_button("💾 Salvar Avaliação", use_container_width=True):
            if not analyst.strip():
                st.error("Nome do analista é obrigatório.")
            else:
                player_id = int(players_df.loc[players_df["name"] == player_name, "id"].iloc[0])
                try:
                    save_evaluation(
                        player_id=player_id,
                        analyst=analyst.strip(),
                        eval_date=eval_date.isoformat(),
                        skills={"technical": tv, "player_specific": ps, "mental": mv},
                        mog=mgv,
                        strengths=[s1, s2, s3],
                        improvements=[i1, i2, i3],
                    )
                    st.success(f"✅ Avaliação de **{player_name}** salva!")
                    st.balloons()
                except Exception as e:
                    st.error(f"Erro ao salvar avaliação: {e}")


# ---------------------------
# Page: Jogadores (lista / ações)
# ---------------------------
elif page == "📚 Jogadores":
    st.header("Lista de Atletas Cadastrados")

    players_df = get_players()
    if players_df.empty:
        st.info("Nenhum jogador cadastrado. Vá em 'Cadastrar Jogador' para adicionar.")
    else:
        display_df = players_df[["id", "name", "position", "club", "photo_url"]].rename(
            columns={"id": "ID", "name": "Nome", "position": "Posição", "club": "Clube", "photo_url": "Foto URL"}
        )

        st.subheader("Tabela de Atletas")
        st.dataframe(display_df, use_container_width=True)

        st.markdown("---")
        st.subheader("Ações")

        sel_name = st.selectbox("Selecione um atleta", players_df["name"].tolist())
        sel_row = players_df[players_df["name"] == sel_name].iloc[0]
        evaluation = get_latest_evaluation(int(sel_row["id"]))

        stored_edit_pos = sel_row["position"] if sel_row["position"] in POSITIONS else POSITIONS[0]

        left_col, right_col = st.columns([1, 2], gap="large")

        with left_col:
            if not is_admin():
                st.warning("Para editar/excluir jogadores você precisa estar autenticado como admin.")
                quick_pwd = st.text_input("Senha de admin (rápido)", type="password", key="quick_admin_pwd")
                if st.button("Entrar (rápido)", use_container_width=True):
                    if try_login(quick_pwd):
                        st.success("Autenticado como admin.")
                    else:
                        st.error("Senha incorreta.")
                st.markdown(f"**Nome:** {sel_row['name']}")
                st.markdown(f"**Posição:** {sel_row['position'] or '—'}  •  **Clube:** {sel_row['club'] or '—'}")
                if sel_row["photo_url"]:
                    st.markdown(
                        f'''
                        <div style="width:{PLAYER_IMG_W}px;height:{PLAYER_IMG_H}px;margin:0 auto 8px auto;display:flex;align-items:center;justify-content:center;background:#ffffff;border-radius:10px;border:3px solid #67b6fb;overflow:hidden;">
                            <img src="{sel_row["photo_url"]}" alt="player" style="max-width:100%;max-height:100%;object-fit:contain;display:block;">
                        </div>
                        ''',
                        unsafe_allow_html=True,
                    )
            else:
                st.markdown('<div class="block-container card" style="padding:12px">', unsafe_allow_html=True)
                st.markdown('### ✏️ Editar jogador')

                edit_pos_key = f"edit_eval_pos_{sel_row['id']}"
                if edit_pos_key not in st.session_state:
                    st.session_state[edit_pos_key] = stored_edit_pos
                edit_position = st.selectbox(
                    "Posição (perfil + avaliação)",
                    POSITIONS,
                    index=POSITIONS.index(st.session_state[edit_pos_key]),
                    key=edit_pos_key,
                    format_func=lambda p: f"{p} – {_pos_label(p)}",
                )
                edit_pos_skills = _pos_skills(edit_position)

                with st.form(f"form_edit_{sel_row['id']}"):
                    new_name = st.text_input("Nome completo *", value=sel_row["name"])
                    new_club = st.text_input("Clube", value=sel_row["club"] or "")
                    new_photo = st.text_input("URL da foto", value=sel_row["photo_url"] or "")

                    if new_photo.strip():
                        st.markdown(
                            f'''
                            <div style="width:{PLAYER_IMG_W}px;height:{PLAYER_IMG_H}px;margin:0 auto 8px auto;display:flex;align-items:center;justify-content:center;background:#ffffff;border-radius:8px;border:2px solid rgba(0,0,0,0.08);overflow:hidden;">
                                <img src="{new_photo.strip()}" alt="preview" style="max-width:100%;max-height:100%;object-fit:contain;display:block;">
                            </div>
                            ''',
                            unsafe_allow_html=True,
                        )

                    st.divider()
                    st.markdown("**Avaliação (editar última ou criar nova)**")

                    if evaluation:
                        analyst_val = evaluation.get("analyst", "")
                        try:
                            eval_date_prefill = datetime.fromisoformat(evaluation.get("eval_date")).date()
                        except Exception:
                            eval_date_prefill = date.today()
                    else:
                        analyst_val = ""
                        eval_date_prefill = date.today()

                    analyst_input = st.text_input("Analista", value=analyst_val)
                    eval_date_input = st.date_input("Data da avaliação", value=eval_date_prefill)

                    st.subheader(f"🎯 {_section_title(edit_position)}")
                    tech_vals = {}
                    for s in edit_pos_skills:
                        cur_val = ""
                        if evaluation and evaluation.get("skills", {}).get("technical", {}):
                            cur_val = evaluation["skills"]["technical"].get(s, "")
                        tech_vals[s] = st.selectbox(
                            f"{s}", [""] + LEVELS,
                            index=([""] + LEVELS).index(cur_val) if cur_val in LEVELS else 0,
                            key=f"edit_t_{sel_row['id']}_{s}",
                        )

                    st.subheader("⚡ Player-Specific Indicators (até 4)")
                    existing_ps = {}
                    if evaluation and evaluation.get("skills", {}).get("player_specific", {}):
                        existing_ps = evaluation["skills"]["player_specific"].copy()
                    ps_items_edit = list(existing_ps.items())
                    while len(ps_items_edit) < 4:
                        ps_items_edit.append(("", ""))
                    ps_names = []
                    ps_levels = []
                    for i in range(4):
                        default_name = ps_items_edit[i][0]
                        default_level = ps_items_edit[i][1] if ps_items_edit[i][1] in LEVELS else ""
                        n = st.text_input(f"Atributo {i+1}", value=default_name or "", key=f"edit_ps_name_{sel_row['id']}_{i}")
                        l = st.selectbox(f"Nível {i+1}", [""] + LEVELS,
                                         index=([""] + LEVELS).index(default_level) if default_level in LEVELS else 0,
                                         key=f"edit_ps_level_{sel_row['id']}_{i}")
                        ps_names.append(n)
                        ps_levels.append(l)

                    st.subheader("🧠 Mental")
                    mental_vals = {}
                    for s in MENTAL_SKILLS:
                        cur_val = ""
                        if evaluation and evaluation.get("skills", {}).get("mental", {}):
                            cur_val = evaluation["skills"]["mental"].get(s, "")
                        mental_vals[s] = st.selectbox(
                            f"{s}", [""] + LEVELS,
                            index=([""] + LEVELS).index(cur_val) if cur_val in LEVELS else 0,
                            key=f"edit_m_{sel_row['id']}_{s}",
                        )

                    st.subheader("📐 Moments of the Game (MoG)")
                    mog_vals = {}
                    for c in MOG_CATEGORIES:
                        cur_v = 50
                        if evaluation and evaluation.get("mog", {}):
                            try:
                                cur_v = int(evaluation["mog"].get(c, 50))
                            except Exception:
                                cur_v = 50
                        mog_vals[c] = st.slider(c, 0, 100, cur_v, key=f"edit_mog_{sel_row['id']}_{c}")

                    st.subheader("💪 Strengths / 📈 Need to Improve")
                    s_pref = ["", "", ""]
                    i_pref = ["", "", ""]
                    if evaluation:
                        s_pref = (evaluation.get("strengths") or []) + ["", "", ""]
                        i_pref = (evaluation.get("improvements") or []) + ["", "", ""]
                    s1 = st.text_input("Strength 1", value=s_pref[0] or "", key=f"edit_s1_{sel_row['id']}")
                    s2 = st.text_input("Strength 2", value=s_pref[1] or "", key=f"edit_s2_{sel_row['id']}")
                    s3 = st.text_input("Strength 3", value=s_pref[2] or "", key=f"edit_s3_{sel_row['id']}")
                    i1 = st.text_input("Improvement 1", value=i_pref[0] or "", key=f"edit_i1_{sel_row['id']}")
                    i2 = st.text_input("Improvement 2", value=i_pref[1] or "", key=f"edit_i2_{sel_row['id']}")
                    i3 = st.text_input("Improvement 3", value=i_pref[2] or "", key=f"edit_i3_{sel_row['id']}")

                    st.markdown("")
                    save_clicked = st.form_submit_button("💾 Salvar alterações", use_container_width=True)

                    if save_clicked:
                        if not new_name.strip():
                            st.error("Nome é obrigatório.")
                        else:
                            try:
                                update_player(int(sel_row["id"]), new_name, edit_position, new_club, new_photo)

                                technical_payload = {s: (tech_vals[s] or "").strip() for s in edit_pos_skills}
                                mental_payload = {s: (mental_vals[s] or "").strip() for s in MENTAL_SKILLS}
                                ps_payload = {}
                                for n, l in zip(ps_names, ps_levels):
                                    if n.strip() and l:
                                        ps_payload[n.strip()] = l
                                skills_payload = {
                                    "technical": technical_payload,
                                    "player_specific": ps_payload,
                                    "mental": mental_payload,
                                }
                                mog_payload = {c: int(mog_vals[c]) for c in MOG_CATEGORIES}
                                strengths_payload = [s1, s2, s3]
                                improvements_payload = [i1, i2, i3]

                                if evaluation:
                                    eval_id = evaluation["id"]
                                    update_evaluation_meta(eval_id, analyst_input.strip() or evaluation.get("analyst", ""), eval_date_input.isoformat())
                                    replace_evaluation_content(eval_id, skills_payload, mog_payload, strengths_payload, improvements_payload)
                                    st.success("✅ Jogador e avaliação atualizados com sucesso!")
                                else:
                                    if not analyst_input.strip():
                                        st.error("Analista é necessário ao criar nova avaliação.")
                                    else:
                                        player_id = int(sel_row["id"])
                                        save_evaluation(
                                            player_id=player_id,
                                            analyst=analyst_input.strip(),
                                            eval_date=eval_date_input.isoformat(),
                                            skills=skills_payload,
                                            mog=mog_payload,
                                            strengths=strengths_payload,
                                            improvements=improvements_payload,
                                        )
                                        st.success("✅ Jogador atualizado e nova avaliação criada!")
                                trigger_rerun()
                            except Exception as e:
                                msg = str(e).lower()
                                if "unique" in msg or "duplicate" in msg or "already exists" in msg:
                                    st.error("Já existe um jogador com esse nome. Escolha outro nome.")
                                else:
                                    st.error(f"Erro ao salvar jogador/avaliação: {e}")
                st.markdown("</div>", unsafe_allow_html=True)

                st.markdown("")
                confirm = st.checkbox("Confirmo exclusão deste atleta e todas as avaliações associadas", key=f"confirm_del_{sel_row['id']}")
                if confirm:
                    if st.button("Confirmar exclusão"):
                        try:
                            delete_player(int(sel_row["id"]))
                            st.success(f"Atleta {sel_row['name']} apagado com sucesso.")
                            trigger_rerun()
                        except Exception as e:
                            st.error(f"Erro ao apagar jogador: {e}")

        with right_col:
            st.markdown(f"**Nome:** {sel_row['name']}")
            st.markdown(f"**Posição:** {sel_row['position'] or '—'}  •  **Clube:** {sel_row['club'] or '—'}")
            if sel_row["photo_url"]:
                st.markdown(
                    f'''
                    <div style="width:{PLAYER_IMG_W}px;height:{PLAYER_IMG_H}px;margin:0 auto 8px auto;display:flex;align-items:center;justify-content:center;background:#ffffff;border-radius:10px;border:3px solid #67b6fb;overflow:hidden;">
                        <img src="{sel_row["photo_url"]}" alt="player" style="max-width:100%;max-height:100%;object-fit:contain;display:block;">
                    </div>
                    ''',
                    unsafe_allow_html=True,
                )

            if evaluation and evaluation.get("mog"):
                st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)

                def build_radar_side(mog_data):
                    cats = list(mog_data.keys())
                    vals = list(mog_data.values())
                    if not cats:
                        return go.Figure()
                    cats_c = cats + [cats[0]]
                    vals_c = vals + [vals[0]]
                    fig = go.Figure()
                    fig.add_trace(go.Scatterpolar(
                        r=vals_c, theta=cats_c, fill="toself",
                        fillcolor="rgba(100,181,246,0.30)",
                        line=dict(color="#64B5F6", width=2.5),
                        marker=dict(size=6, color="#64B5F6"),
                    ))
                    fig.update_layout(
                        polar=dict(
                            bgcolor="rgba(255,255,255,0.03)",
                            domain=dict(x=[0.0, 1.0], y=[0.0, 1.0]),
                            radialaxis=dict(visible=True, range=[0, 100], showticklabels=False,
                                            gridcolor="rgba(255,255,255,0.10)"),
                            angularaxis=dict(
                                gridcolor="rgba(255,255,255,0.10)",
                                tickfont=dict(size=12, color="#CFD8DC",
                                              family="Source Sans 3, Trebuchet MS, sans-serif"),
                                rotation=90,
                            ),
                        ),
                        paper_bgcolor="rgba(0,0,0,0)",
                        plot_bgcolor="rgba(0,0,0,0)",
                        showlegend=False,
                        margin=dict(l=40, r=40, t=48, b=40),
                        height=420,
                    )
                    return fig

                st.markdown('<div class="block-container radar-outer"><div class="radar-title">MoG – Moments of the Game</div><div class="radar-body">', unsafe_allow_html=True)
                fig = build_radar_side(evaluation["mog"])
                st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
                st.markdown("</div></div>", unsafe_allow_html=True)

        st.markdown("---")
        csv = display_df.to_csv(index=False).encode("utf-8")
        st.download_button(label="Exportar lista como CSV", data=csv, file_name="players.csv", mime="text/csv")


# ---------------------------
# Page: Dashboard (full)
# ---------------------------
else:
    BADGE_STYLES = {
        "Above Level": {"bg": "rgba(27,94,32,0.85)",  "fg": "#FFFFFF"},
        "Good":        {"bg": "rgba(102,187,106,0.72)","fg": "#FFFFFF"},
        "Average":     {"bg": "rgba(230,168,23,0.75)", "fg": "#FFFFFF"},
        "Below Level": {"bg": "rgba(198,40,40,0.75)",  "fg": "#FFFFFF"},
    }

    st.markdown(
        '<link href="https://fonts.googleapis.com/css2?family=Orbitron:wght@400;500;600;700;800;900&family=Source+Sans+3:wght@400;600;700;800&display=swap" rel="stylesheet">',
        unsafe_allow_html=True,
    )

    _css_template = """
    <style>
    .block-container, .block-container * {
        font-family: __FG__ !important;
    }
    .block-container .header-bar {
        background: linear-gradient(135deg, #67b6fb 0%, #5aaaf5 50%, #4d9eef 100%);
        padding: 28px 40px;
        border-radius: 12px;
        display: flex;
        align-items: center;
        gap: 28px;
        margin-bottom: 24px;
        box-shadow: 0 4px 20px rgba(103,182,251,0.30);
        position: relative;
        overflow: hidden;
    }
    .block-container .header-bar::before {
        content: '';
        position: absolute;
        top: 0; left: 0; right: 0; bottom: 0;
        background: url("data:image/svg+xml,%3Csvg width='60' height='60' viewBox='0 0 60 60' xmlns='http://www.w3.org/2000/svg'%3E%3Cg fill='none' fill-rule='evenodd'%3E%3Cg fill='%23ffffff' fill-opacity='0.06'%3E%3Cpath d='M36 34v-4h-2v4h-4v2h4v4h2v-4h4v-2h-4zm0-30V0h-2v4h-4v2h4v4h2V6h4V4h-4zM6 34v-4H4v4H0v2h4v4h2v-4h4v-2H6zM6 4V0H4v4H0v2h4v4h2V6h4V4H6z'/%3E%3C/g%3E%3C/g%3E%3C/svg%3E");
        pointer-events: none;
    }
    .block-container .header-bar .header-logo {
        height: 96px; width: auto; object-fit: contain;
        flex-shrink: 0; position: relative; z-index: 1;
    }
    .block-container .header-bar .header-sep {
        width: 2px; height: 72px;
        background: rgba(10,42,74,0.2);
        border-radius: 1px; flex-shrink: 0;
        position: relative; z-index: 1;
    }
    .block-container .header-bar h1 {
        font-family: __FD__ !important;
        color: #0a2a4a; margin: 0;
        font-size: 2rem; font-weight: 900;
        letter-spacing: 2.5px; text-transform: uppercase;
        position: relative; z-index: 1; line-height: 1.2;
    }
    .block-container .card {
        background: white; border-radius: 12px; padding: 20px;
        box-shadow: 0 2px 12px rgba(13,71,161,0.12);
    }
    .block-container .player-card { text-align: center; }
    .block-container .player-card .divider {
        width: 50px; height: 3px; background: #67b6fb;
        border-radius: 2px; margin: 10px auto;
    }
    .block-container .player-card .label {
        font-family: __FG__ !important; font-size: 0.72rem;
        color: #78909C; text-transform: uppercase;
        letter-spacing: 1.5px; font-weight: 700;
    }
    .block-container .player-card .value {
        font-family: __FG__ !important; font-size: 1.05rem;
        color: #0D47A1; font-weight: 700; margin-bottom: 10px;
    }
    .block-container .section {
        border-radius: 12px; overflow: hidden;
        box-shadow: 0 2px 10px rgba(13,71,161,0.12); margin-bottom: 16px;
    }
    .block-container .section-header {
        background: #0D47A1; color: white;
        padding: 10px 20px; font-family: __FD__ !important;
        font-size: 0.9rem; font-weight: 700;
        letter-spacing: 1px; text-transform: uppercase;
    }
    .block-container .section-body { background: #1E88E5; padding: 14px 20px; }
    .block-container .radar-outer {
        background: #0C1F3A; border-radius: 12px;
        box-shadow: 0 2px 10px rgba(13,71,161,0.12);
        overflow: hidden; margin-bottom: 8px;
    }
    .block-container .radar-title {
        background: #0C1F3A; color: white; text-align: center;
        font-family: __FD__ !important; font-size: 0.85rem;
        font-weight: 700; letter-spacing: 1.5px; text-transform: uppercase;
        padding: 8px 12px 6px 12px; margin-bottom: 0;
    }
    .block-container .radar-body { background: #0C1F3A; padding: 0 8px 12px 8px; }
    .block-container .radar-body > div { margin: 0 !important; padding: 0 !important; }
    .block-container .badge-table {
        width: 100%; border-collapse: collapse; table-layout: fixed;
    }
    .block-container .badge-table td { padding: 8px 8px; vertical-align: middle; }
    .block-container .badge-table .cell-label {
        color: white; font-family: __FG__ !important;
        font-size: 0.92rem; font-weight: 600;
        text-align: right; padding-right: 14px;
        white-space: normal; word-break: break-word;
    }
    .block-container .badge-table .cell-tag { text-align: left; white-space: nowrap; }
    .block-container .badge-tag {
        display: inline-block; padding: 6px 12px; border-radius: 6px;
        font-family: __FG__ !important; font-size: 0.82rem; font-weight: 700;
        white-space: nowrap; min-width: 90px; text-align: center;
        box-shadow: inset 0 -2px 0 rgba(0,0,0,0.06);
    }
    .block-container .text-list { list-style: none; padding: 0; margin: 0; }
    .block-container .text-list li {
        color: white; font-family: __FDO__ !important;
        font-size: 0.95rem; font-weight: 600;
        padding: 5px 0; border-bottom: 1px solid rgba(255,255,255,0.15);
    }
    .block-container .text-list li:last-child { border-bottom: none; }
    .block-container .text-list .num {
        display: inline-block; width: 24px; height: 24px;
        line-height: 24px; text-align: center;
        background: rgba(255,255,255,0.2); border-radius: 50%;
        font-size: 0.8rem; margin-right: 8px;
    }
    .block-container .no-data-msg {
        text-align: center; padding: 40px 20px;
        color: #78909C; font-size: 1.1rem;
    }
    .block-container .eval-meta {
        background: rgba(13,71,161,0.06); border-radius: 8px;
        padding: 8px 16px; margin-top: 8px;
        font-family: __FDO__ !important; font-size: 0.85rem; color: #546E7A;
    }
    .block-container div[data-testid="stSelectbox"] label {
        font-weight: 600; color: #0D47A1; font-family: __FG__ !important;
    }
    </style>
    """

    _css = _css_template.replace("__FD__", FONT_DISPLAY).replace("__FG__", FONT_GRAPHIC).replace("__FDO__", FONT_DOCUMENT)
    st.markdown(_css, unsafe_allow_html=True)

    def badge_tag(level):
        if not level:
            return ""
        s = BADGE_STYLES.get(level, {"bg": "#616161", "fg": "#FFF"})
        return f'<span class="badge-tag" style="background:{s["bg"]};color:{s["fg"]};">{level}</span>'

    def render_section(title, body):
        return f'<div class="section"><div class="section-header">{title}</div><div class="section-body">{body}</div></div>'

    def render_badges_table(items: list, cols: int = 4, tag_px: int = 110) -> str:
        if len(items) % cols != 0:
            remaining = cols - (len(items) % cols)
            items = items + [("", "")] * remaining

        total_tag_px = tag_px * cols
        label_col_calc = f"calc((100% - {total_tag_px}px) / {cols})"

        colgroup_html = "<colgroup>"
        for _ in range(cols):
            colgroup_html += f'<col class="label-col" style="width:{label_col_calc}">'
            colgroup_html += f'<col class="tag-col" style="width:{tag_px}px">'
        colgroup_html += "</colgroup>"

        rows_html = ""
        for row_start in range(0, len(items), cols):
            row_items = items[row_start: row_start + cols]
            cells = ""
            for label, level in row_items:
                if label:
                    cells += f'<td class="cell-label">{label}</td>'
                    if level:
                        cells += f'<td class="cell-tag">{badge_tag(level)}</td>'
                    else:
                        cells += '<td class="cell-tag"></td>'
                else:
                    cells += "<td></td><td></td>"
            rows_html += f"<tr>{cells}</tr>"

        return f'<table class="badge-table">{colgroup_html}{rows_html}</table>'

    def render_list(items):
        if not items:
            return '<span style="color:rgba(255,255,255,0.5);">—</span>'
        li = ""
        for i, t in enumerate(items):
            li += f'<li><span class="num">{i + 1}</span>{t}</li>'
        return '<ul class="text-list">' + li + "</ul>"

    def build_radar(mog_data):
        cats = list(mog_data.keys())
        vals = list(mog_data.values()) if mog_data else [50] * len(cats)
        if not cats:
            return go.Figure()
        cats_c = cats + [cats[0]]
        vals_c = vals + [vals[0]]
        fig = go.Figure()
        fig.add_trace(go.Scatterpolar(
            r=vals_c, theta=cats_c, fill="toself",
            fillcolor="rgba(100,181,246,0.30)",
            line=dict(color="#64B5F6", width=2.5),
            marker=dict(size=6, color="#64B5F6"),
        ))
        fig.update_layout(
            polar=dict(
                bgcolor="rgba(255,255,255,0.03)",
                domain=dict(x=[0.0, 1.0], y=[0.0, 1.0]),
                radialaxis=dict(visible=True, range=[0, 100], showticklabels=False,
                                gridcolor="rgba(255,255,255,0.10)"),
                angularaxis=dict(
                    gridcolor="rgba(255,255,255,0.10)",
                    tickfont=dict(size=12, color="#CFD8DC",
                                  family="Source Sans 3, Trebuchet MS, sans-serif"),
                    rotation=90,
                ),
            ),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            showlegend=False,
            margin=dict(l=40, r=40, t=48, b=40),
            height=420,
        )
        return fig

    # Header
    st.markdown(f'''
        <div class="block-container header-bar">
            <img src="{LOGO_SRC}" alt="SGA Logo" class="header-logo">
            <div class="header-sep"></div>
            <h1>Individual Player Indicators</h1>
        </div>
        ''', unsafe_allow_html=True)

    players_df = get_players()
    if players_df.empty:
        st.info("Nenhum jogador cadastrado. Vá em **➕ Cadastrar Jogador**.")
        st.stop()

    player_name = st.selectbox("Select Player", players_df["name"].tolist())
    pr = players_df[players_df["name"] == player_name].iloc[0]
    evaluation = get_latest_evaluation(int(pr["id"]))

    dash_pos    = pr["position"] if pr["position"] in POSITIONS else None
    dash_skills = _pos_skills(dash_pos) if dash_pos else []

    left_col, right_col = st.columns([1, 3], gap="large")

    with left_col:
        photo = pr["photo_url"] or ""
        pos_display = pr["position"] or "—"
        if photo:
            st.markdown(
                f'''
                <div class="block-container card player-card">
                    <div style="width:{PLAYER_IMG_W}px;height:{PLAYER_IMG_H}px;margin:0 auto 8px auto;display:flex;align-items:center;justify-content:center;background:#ffffff;border-radius:10px;border:3px solid #67b6fb;overflow:hidden;">
                        <img src="{photo}" alt="{player_name}" style="max-width:100%;max-height:100%;object-fit:contain;display:block;">
                    </div>
                    <div class="divider"></div>
                    <div class="label">Position</div><div class="value">{pos_display}</div>
                    <div class="label">Club</div><div class="value">{pr["club"] or "—"}</div>
                </div>
                ''',
                unsafe_allow_html=True,
            )
        else:
            st.markdown(f'''
                <div class="block-container card player-card">
                    <div class="divider"></div>
                    <div class="label">Position</div><div class="value">{pos_display}</div>
                    <div class="label">Club</div><div class="value">{pr["club"] or "—"}</div>
                </div>
                ''', unsafe_allow_html=True)

        if evaluation and evaluation["mog"]:
            st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
            st.markdown('<div class="block-container radar-outer"><div class="radar-title">MoG – Moments of the Game</div><div class="radar-body">', unsafe_allow_html=True)
            fig = build_radar(evaluation["mog"])
            st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
            st.markdown("</div></div>", unsafe_allow_html=True)

    with right_col:
        if not evaluation:
            st.markdown(
                '<div class="block-container card no-data-msg">📋 Nenhuma avaliação encontrada.<br>'
                'Vá em <b>📝 Nova Avaliação</b> para criar.</div>',
                unsafe_allow_html=True,
            )
            st.stop()

        sk = evaluation["skills"]

        # Technical — always labelled "Technical Indicators" in the dashboard
        tech_title = "Technical Indicators"
        if dash_pos:
            tech_items = [(s, sk.get("technical", {}).get(s, "")) for s in dash_skills]
        else:
            stored_tech = sk.get("technical", {})
            tech_items = [(n, l) for n, l in stored_tech.items()]

        while len(tech_items) % 4 != 0:
            tech_items.append(("", ""))
        st.markdown(render_section(tech_title, render_badges_table(tech_items, 4)), unsafe_allow_html=True)

        # Player-Specific
        ps_data  = sk.get("player_specific", {})
        ps_items = [(n, l) for n, l in ps_data.items()]
        while len(ps_items) % 4 != 0:
            ps_items.append(("", ""))
        st.markdown(render_section("Player-Specific Indicators", render_badges_table(ps_items, 4)), unsafe_allow_html=True)

        # Mental
        m_items = [(s, sk.get("mental", {}).get(s, "")) for s in MENTAL_SKILLS]
        while len(m_items) % 4 != 0:
            m_items.append(("", ""))
        st.markdown(render_section("Mental", render_badges_table(m_items, 4)), unsafe_allow_html=True)

        sc, ic = st.columns(2, gap="medium")
        with sc:
            st.markdown(render_section("My Strengths", render_list(evaluation["strengths"])), unsafe_allow_html=True)
        with ic:
            st.markdown(render_section("Need to Improve", render_list(evaluation["improvements"])), unsafe_allow_html=True)

        st.markdown(
            f'<div class="block-container eval-meta">📅 <b>Avaliação:</b> {evaluation["eval_date"]} &nbsp;•&nbsp; 👤 <b>Analista:</b> {evaluation["analyst"]}</div>',
            unsafe_allow_html=True,
        )

        # PDF export button
        st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)
        pdf_key = f"pdf_bytes_{player_name}"
        if st.button("📄 Gerar Relatório PDF", use_container_width=True, key="btn_gen_pdf"):
            with st.spinner("Gerando PDF..."):
                try:
                    pdf_bytes = generate_player_pdf(
                        player_name=player_name,
                        position=pr["position"] or "",
                        club=pr["club"] or "",
                        photo_url=pr["photo_url"] or "",
                        evaluation=evaluation,
                        pos_skills_list=dash_skills,
                    )
                    st.session_state[pdf_key] = pdf_bytes
                except ImportError as exc:
                    st.warning(f"⚠️ {exc}")
                    st.session_state.pop(pdf_key, None)
                except Exception as exc:
                    st.error(f"Erro ao gerar PDF: {exc}")
                    st.session_state.pop(pdf_key, None)
        if pdf_key in st.session_state:
            fname = f"IPI_{player_name.replace(' ', '_')}.pdf"
            st.download_button(
                label="⬇️ Baixar PDF",
                data=st.session_state[pdf_key],
                file_name=fname,
                mime="application/pdf",
                use_container_width=True,
                key="btn_dl_pdf",
            )
