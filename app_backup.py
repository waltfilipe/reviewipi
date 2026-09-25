# app.py (v14) - corrige IntegrityError ao deletar jogador (remoção manual de dependências)
import os
import time
import streamlit as st
import plotly.graph_objects as go
import pandas as pd
import sqlite3
import base64
from pathlib import Path
from datetime import date, datetime

st.set_page_config(page_title="SGA - IDP", page_icon="⚽", layout="wide")

DB_PATH = "sga_evaluations.db"

# Admin password read from environment (fallback default)
ADMIN_PASSWORD = os.getenv("SGA_ADMIN_PASSWORD", "changeme")

# Padrão de tamanho das fotos dos jogadores (px)
PLAYER_IMG_W = 180
PLAYER_IMG_H = 240

# Logo sources (local base64 fallback to URL)
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

# Fonts
FONT_DISPLAY = "'Orbitron', sans-serif"
FONT_GRAPHIC = "'Source Sans 3', sans-serif"
FONT_DOCUMENT = "'Trebuchet MS', 'Source Sans 3', sans-serif"

# Domain definitions
TECHNICAL_SKILLS = [
    "General Passing", "1st Touch", "Head. Direction", "1v1 Defending",
    "Crossing", "1v1 Attacking", "Aerials Duels", "Off Ball Def.",
]
MENTAL_SKILLS = ["Awareness", "Effort", "Team Work"]
MOG_CATEGORIES = [
    "Off. Possession", "Off. Transition", "Def. Organization",
    "Def. Transition", "Set Pieces",
]
LEVELS = ["Above Level", "Good", "Average", "Below Level"]

# ---------------------------
# Helper: trigger safe rerun (avoid st.experimental_rerun() in nested contexts)
# ---------------------------
def trigger_rerun():
    # Try to force a rerun by changing the query params. If that fails (race),
    # fall back to setting a session_state token so no exception bubbles up.
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
# Database helpers
# ---------------------------
def get_db():
    # Ensure foreign keys are enabled on every new connection
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA foreign_keys = ON;")
    except Exception:
        pass
    return conn

def init_db():
    conn = get_db()
    conn.executescript("""
        PRAGMA foreign_keys = ON;
        CREATE TABLE IF NOT EXISTS players (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE, position TEXT, club TEXT, photo_url TEXT
        );
        CREATE TABLE IF NOT EXISTS evaluations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            player_id INTEGER NOT NULL, analyst TEXT NOT NULL,
            eval_date TEXT NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (player_id) REFERENCES players(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS eval_skills (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            evaluation_id INTEGER NOT NULL, category TEXT NOT NULL,
            skill_name TEXT NOT NULL, level TEXT NOT NULL,
            FOREIGN KEY (evaluation_id) REFERENCES evaluations(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS eval_mog (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            evaluation_id INTEGER NOT NULL, category TEXT NOT NULL,
            value INTEGER NOT NULL,
            FOREIGN KEY (evaluation_id) REFERENCES evaluations(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS eval_notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            evaluation_id INTEGER NOT NULL, note_type TEXT NOT NULL,
            position INTEGER NOT NULL, text TEXT NOT NULL,
            FOREIGN KEY (evaluation_id) REFERENCES evaluations(id) ON DELETE CASCADE
        );
    """)
    conn.commit()
    conn.close()

init_db()

def get_players():
    conn = get_db()
    df = pd.read_sql("SELECT * FROM players ORDER BY name", conn)
    conn.close()
    return df

def add_player(name, position, club, photo_url):
    conn = get_db()
    conn.execute("INSERT OR IGNORE INTO players (name,position,club,photo_url) VALUES (?,?,?,?)",
                 (name, position, club, photo_url))
    conn.commit()
    conn.close()

def delete_player(player_id: int):
    """
    Safe deletion of a player and all related records.
    Some deployed DBs may not have been created with ON DELETE CASCADE,
    so delete dependent rows manually in the correct order.
    """
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("PRAGMA foreign_keys = ON;")
        # Find evaluations to delete related records
        cur.execute("SELECT id FROM evaluations WHERE player_id = ?", (player_id,))
        eval_ids = [row[0] for row in cur.fetchall()]

        for eid in eval_ids:
            cur.execute("DELETE FROM eval_skills WHERE evaluation_id = ?", (eid,))
            cur.execute("DELETE FROM eval_mog WHERE evaluation_id = ?", (eid,))
            cur.execute("DELETE FROM eval_notes WHERE evaluation_id = ?", (eid,))

        # Delete evaluations
        cur.execute("DELETE FROM evaluations WHERE player_id = ?", (player_id,))
        # Finally delete player
        cur.execute("DELETE FROM players WHERE id = ?", (player_id,))
        conn.commit()
    except sqlite3.IntegrityError as e:
        conn.rollback()
        # re-raise so upper-level UI can show an error message / Streamlit will capture it
        raise
    finally:
        conn.close()

def update_player(player_id: int, name: str, position: str, club: str, photo_url: str):
    conn = get_db()
    try:
        conn.execute(
            "UPDATE players SET name = ?, position = ?, club = ?, photo_url = ? WHERE id = ?",
            (name.strip(), position.strip(), club.strip(), photo_url.strip(), player_id),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        raise
    conn.close()

def save_evaluation(player_id, analyst, eval_date, skills, mog, strengths, improvements):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("INSERT INTO evaluations (player_id,analyst,eval_date) VALUES (?,?,?)",
                (player_id, analyst, eval_date))
    eid = cur.lastrowid
    for cat, sd in skills.items():
        for sn, lv in sd.items():
            if sn.strip() and lv.strip():
                cur.execute("INSERT INTO eval_skills (evaluation_id,category,skill_name,level) VALUES (?,?,?,?)",
                            (eid, cat, sn, lv))
    for c, v in mog.items():
        cur.execute("INSERT INTO eval_mog (evaluation_id,category,value) VALUES (?,?,?)", (eid, c, v))
    for i, t in enumerate(strengths):
        if t.strip():
            cur.execute("INSERT INTO eval_notes (evaluation_id,note_type,position,text) VALUES (?,'strength',?,?)",
                        (eid, i + 1, t))
    for i, t in enumerate(improvements):
        if t.strip():
            cur.execute("INSERT INTO eval_notes (evaluation_id,note_type,position,text) VALUES (?,'improve',?,?)",
                        (eid, i + 1, t))
    conn.commit()
    conn.close()
    return eid

def update_evaluation_meta(evaluation_id: int, analyst: str, eval_date: str):
    conn = get_db()
    conn.execute("UPDATE evaluations SET analyst = ?, eval_date = ? WHERE id = ?", (analyst, eval_date, evaluation_id))
    conn.commit()
    conn.close()

def replace_evaluation_content(evaluation_id: int, skills: dict, mog: dict, strengths: list, improvements: list):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM eval_skills WHERE evaluation_id = ?", (evaluation_id,))
    cur.execute("DELETE FROM eval_mog WHERE evaluation_id = ?", (evaluation_id,))
    cur.execute("DELETE FROM eval_notes WHERE evaluation_id = ?", (evaluation_id,))
    # Insert new
    for cat, sd in skills.items():
        for sn, lv in sd.items():
            if sn.strip() and lv.strip():
                cur.execute(
                    "INSERT INTO eval_skills (evaluation_id,category,skill_name,level) VALUES (?,?,?,?)",
                    (evaluation_id, cat, sn, lv)
                )
    for c, v in mog.items():
        cur.execute("INSERT INTO eval_mog (evaluation_id,category,value) VALUES (?,?,?)", (evaluation_id, c, v))
    for i, t in enumerate(strengths):
        if t.strip():
            cur.execute("INSERT INTO eval_notes (evaluation_id,note_type,position,text) VALUES (?,'strength',?,?)",
                        (evaluation_id, i + 1, t))
    for i, t in enumerate(improvements):
        if t.strip():
            cur.execute("INSERT INTO eval_notes (evaluation_id,note_type,position,text) VALUES (?,'improve',?,?)",
                        (evaluation_id, i + 1, t))
    conn.commit()
    conn.close()

def get_latest_evaluation(player_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM evaluations WHERE player_id=? ORDER BY eval_date DESC, id DESC LIMIT 1",
                (player_id,))
    ev = cur.fetchone()
    if not ev:
        conn.close()
        return None
    eid = ev["id"]
    skills = {}
    for r in cur.execute("SELECT category,skill_name,level FROM eval_skills WHERE evaluation_id=?", (eid,)):
        skills.setdefault(r["category"], {})[r["skill_name"]] = r["level"]
    mog = {}
    for r in cur.execute("SELECT category,value FROM eval_mog WHERE evaluation_id=?", (eid,)):
        mog[r["category"]] = r["value"]
    strengths, improvements = [], []
    for r in cur.execute("SELECT note_type,position,text FROM eval_notes WHERE evaluation_id=? ORDER BY position",
                         (eid,)):
        (strengths if r["note_type"] == "strength" else improvements).append(r["text"])
    conn.close()
    return {"id": eid, "analyst": ev["analyst"], "eval_date": ev["eval_date"], "skills": skills, "mog": mog,
            "strengths": strengths, "improvements": improvements}


# ---------------------------
# UI: Sidebar Admin area
# ---------------------------
with st.sidebar.expander("Admin"):
    if is_admin():
        st.success("🔐 Autenticado como admin")
        if st.button("Logout", use_container_width=True):
            logout_admin()
            # use safe rerun (try/except inside helper)
            trigger_rerun()
    else:
        pwd = st.text_input("Senha de administrador", type="password")
        if st.button("Entrar", use_container_width=True):
            # IMPORTANT: do not call trigger_rerun() here — the button click
            # already causes a rerun; calling the helper can race on some systems.
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
            position = st.text_input("Posição", placeholder="Ex: Left Winger")
        with c2:
            club = st.text_input("Clube", placeholder="Ex: Houston Dynamo")
            photo_url = st.text_input("URL da foto")
        if st.form_submit_button("💾 Cadastrar", use_container_width=True):
            if not name.strip():
                st.error("Nome é obrigatório.")
            else:
                add_player(name.strip(), position.strip(), club.strip(), photo_url.strip())
                st.success(f"✅ Jogador **{name}** cadastrado!")
                trigger_rerun()


# ---------------------------
# Page: Nova Avaliação
# ---------------------------
elif page == "📝 Nova Avaliação":
    st.header("Nova Avaliação")
    players_df = get_players()
    if players_df.empty:
        st.warning("Nenhum jogador cadastrado. Vá em **➕ Cadastrar Jogador**.")
        st.stop()
    with st.form("form_evaluation"):
        ca, cb, cc = st.columns(3)
        with ca:
            player_name = st.selectbox("Jogador", players_df["name"].tolist())
        with cb:
            analyst = st.text_input("Nome do Analista *")
        with cc:
            eval_date = st.date_input("Data", value=date.today())
        st.divider()

        # Technical
        st.subheader("🎯 Technical")
        tc = st.columns(4)
        tv = {}
        for i, s in enumerate(TECHNICAL_SKILLS):
            with tc[i % 4]:
                tv[s] = st.selectbox(s, LEVELS, key=f"t_{s}")

        st.divider()

        # Player-specific (customizable)
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

        # Mental
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

        # Strengths / Improve
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


# ---------------------------
# Page: Jogadores (lista / ações) - Edit card aligned left and protected
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

        # LEFT: Edit card + actions (aligned with "Ações")
        left_col, right_col = st.columns([1, 2], gap="large")

        with left_col:
            # If not admin, show a small notice and quick password input to allow login in place
            if not is_admin():
                st.warning("Para editar/excluir jogadores você precisa estar autenticado como admin.")
                quick_pwd = st.text_input("Senha de admin (rápido)", type="password", key="quick_admin_pwd")
                if st.button("Entrar (rápido)", use_container_width=True):
                    if try_login(quick_pwd):
                        st.success("Autenticado como admin.")
                    else:
                        st.error("Senha incorreta.")
                # show basic info but hide edit card
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
                # admin: show full edit card (edita TODOS os atributos, inclusive avaliação)
                st.markdown('<div class="block-container card" style="padding:12px">', unsafe_allow_html=True)
                st.markdown('### ✏️ Editar jogador')

                with st.form(f"form_edit_{sel_row['id']}"):
                    # Player basic info
                    new_name = st.text_input("Nome completo *", value=sel_row["name"])
                    new_position = st.text_input("Posição", value=sel_row["position"] or "")
                    new_club = st.text_input("Clube", value=sel_row["club"] or "")
                    new_photo = st.text_input("URL da foto", value=sel_row["photo_url"] or "")

                    # Preview da foto (fixa, ajustada com contain)
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

                    # Analyst and date (prefill if evaluation exists)
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

                    st.subheader("🎯 Technical")
                    tech_vals = {}
                    for i, s in enumerate(TECHNICAL_SKILLS):
                        cur_val = ""
                        if evaluation and evaluation.get("skills", {}).get("technical", {}):
                            cur_val = evaluation["skills"]["technical"].get(s, "")
                        tech_vals[s] = st.selectbox(f"{s}", [""] + LEVELS,
                                                    index=([""] + LEVELS).index(cur_val) if cur_val in LEVELS else 0,
                                                    key=f"edit_t_{sel_row['id']}_{s}")

                    st.subheader("⚡ Player-Specific Indicators (até 4)")
                    existing_ps = {}
                    if evaluation and evaluation.get("skills", {}).get("player_specific", {}):
                        existing_ps = evaluation["skills"]["player_specific"].copy()
                    ps_items = list(existing_ps.items())
                    while len(ps_items) < 4:
                        ps_items.append(("", ""))
                    ps_names = []
                    ps_levels = []
                    for i in range(4):
                        default_name = ps_items[i][0]
                        default_level = ps_items[i][1] if ps_items[i][1] in LEVELS else ""
                        name_key = f"edit_ps_name_{sel_row['id']}_{i}"
                        level_key = f"edit_ps_level_{sel_row['id']}_{i}"
                        n = st.text_input(f"Atributo {i+1}", value=default_name or "", key=name_key)
                        l = st.selectbox(f"Nível {i+1}", [""] + LEVELS,
                                         index=([""] + LEVELS).index(default_level) if default_level in LEVELS else 0,
                                         key=level_key)
                        ps_names.append(n)
                        ps_levels.append(l)

                    st.subheader("🧠 Mental")
                    mental_vals = {}
                    for i, s in enumerate(MENTAL_SKILLS):
                        cur_val = ""
                        if evaluation and evaluation.get("skills", {}).get("mental", {}):
                            cur_val = evaluation["skills"]["mental"].get(s, "")
                        mental_vals[s] = st.selectbox(f"{s}", [""] + LEVELS,
                                                      index=([""] + LEVELS).index(cur_val) if cur_val in LEVELS else 0,
                                                      key=f"edit_m_{sel_row['id']}_{s}")

                    st.subheader("📐 Moments of the Game (MoG)")
                    mog_vals = {}
                    for i, c in enumerate(MOG_CATEGORIES):
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

                    st.markdown("")  # spacer
                    save_clicked = st.form_submit_button("💾 Salvar alterações", use_container_width=True)

                    if save_clicked:
                        # Validation
                        if not new_name.strip():
                            st.error("Nome é obrigatório.")
                        else:
                            try:
                                # Update player data
                                update_player(int(sel_row["id"]), new_name, new_position, new_club, new_photo)

                                # Build payloads
                                technical_payload = {s: (tech_vals[s] or "").strip() for s in TECHNICAL_SKILLS}
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

                                # If evaluation exists -> update meta + replace content
                                if evaluation:
                                    eval_id = evaluation["id"]
                                    # update meta
                                    update_evaluation_meta(eval_id, analyst_input.strip() or evaluation.get("analyst", ""), eval_date_input.isoformat())
                                    # replace content
                                    replace_evaluation_content(eval_id, skills_payload, mog_payload, strengths_payload, improvements_payload)
                                    st.success(f"✅ Jogador e avaliação atualizados com sucesso!")
                                else:
                                    # Create new evaluation (analyst required)
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
                                # safe rerun after successful save/delete
                                trigger_rerun()
                            except sqlite3.IntegrityError:
                                st.error("Já existe um jogador com esse nome. Escolha outro nome.")
                st.markdown("</div>", unsafe_allow_html=True)

                # Delete action (protected)
                st.markdown("")  # spacer
                confirm = st.checkbox("Confirmo exclusão deste atleta e todas as avaliações associadas", key=f"confirm_del_{sel_row['id']}")
                if confirm:
                    if st.button("Confirmar exclusão"):
                        try:
                            delete_player(int(sel_row["id"]))
                            st.success(f"Atleta {sel_row['name']} apagado com sucesso.")
                            trigger_rerun()
                        except sqlite3.IntegrityError:
                            st.error("Erro ao apagar jogador: existem registros dependentes. Entre em contato com o administrador.")

        # RIGHT: Details / Radar / Meta (visual)
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
                # reduced spacer (was larger); less gap between title and chart
                st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)

                def build_radar(mog_data):
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
                        margin=dict(l=40, r=40, t=48, b=40),  # increased top margin to avoid label clipping
                        height=420,  # slightly taller to give room for labels
                    )
                    return fig

                # title + chart with tighter spacing and safer margins to avoid label clipping
                st.markdown('<div class="block-container radar-outer"><div class="radar-title">MoG – Moments of the Game</div><div class="radar-body">', unsafe_allow_html=True)
                fig = build_radar(evaluation["mog"])
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
        "Above Level": {"bg": "rgba(27,94,32,0.85)", "fg": "#FFFFFF"},
        "Good": {"bg": "rgba(102,187,106,0.72)", "fg": "#FFFFFF"},
        "Average": {"bg": "rgba(230,168,23,0.75)", "fg": "#FFFFFF"},
        "Below Level": {"bg": "rgba(198,40,40,0.75)", "fg": "#FFFFFF"},
    }

    # Load Google fonts
    st.markdown(
        '<link href="https://fonts.googleapis.com/css2?family=Orbitron:wght@400;500;600;700;800;900&family=Source+Sans+3:wght@400;600;700;800&display=swap" rel="stylesheet">',
        unsafe_allow_html=True,
    )

    # CSS template scoped to .block-container to avoid affecting sidebar elements
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
        height: 96px;
        width: auto;
        object-fit: contain;
        flex-shrink: 0;
        position: relative;
        z-index: 1;
    }
    .block-container .header-bar .header-sep {
        width: 2px;
        height: 72px;
        background: rgba(10,42,74,0.2);
        border-radius: 1px;
        flex-shrink: 0;
        position: relative;
        z-index: 1;
    }
    .block-container .header-bar h1 {
        font-family: __FD__ !important;
        color: #0a2a4a;
        margin: 0;
        font-size: 2rem;
        font-weight: 900;
        letter-spacing: 2.5px;
        text-transform: uppercase;
        position: relative;
        z-index: 1;
        line-height: 1.2;
    }

    .block-container .card {
        background: white;
        border-radius: 12px;
        padding: 20px;
        box-shadow: 0 2px 12px rgba(13,71,161,0.12);
    }
    .block-container .player-card { text-align: center; }
    .block-container .player-card .divider {
        width: 50px; height: 3px;
        background: #67b6fb;
        border-radius: 2px;
        margin: 10px auto;
    }
    .block-container .player-card .label {
        font-family: __FG__ !important;
        font-size: 0.72rem;
        color: #78909C;
        text-transform: uppercase;
        letter-spacing: 1.5px;
        font-weight: 700;
    }
    .block-container .player-card .value {
        font-family: __FG__ !important;
        font-size: 1.05rem;
        color: #0D47A1;
        font-weight: 700;
        margin-bottom: 10px;
    }

    .block-container .section {
        border-radius: 12px;
        overflow: hidden;
        box-shadow: 0 2px 10px rgba(13,71,161,0.12);
        margin-bottom: 16px;
    }
    .block-container .section-header {
        background: #0D47A1;
        color: white;
        padding: 10px 20px;
        font-family: __FD__ !important;
        font-size: 0.9rem;
        font-weight: 700;
        letter-spacing: 1px;
        text-transform: uppercase;
    }
    .block-container .section-body {
        background: #1E88E5;
        padding: 14px 20px;
    }

    .block-container .radar-outer {
        background: #0C1F3A;
        border-radius: 12px;
        box-shadow: 0 2px 10px rgba(13,71,161,0.12);
        overflow: hidden;
        margin-bottom: 8px; /* reduced bottom spacing */
    }
    /* reduced padding to bring chart closer to title */
    .block-container .radar-title {
        background: #0C1F3A;
        color: white;
        text-align: center;
        font-family: __FD__ !important;
        font-size: 0.85rem;
        font-weight: 700;
        letter-spacing: 1.5px;
        text-transform: uppercase;
        padding: 8px 12px 6px 12px; /* smaller top & bottom padding */
        margin-bottom: 0;
    }
    .block-container .radar-body { background: #0C1F3A; padding: 0 8px 12px 8px; } /* small bottom padding */
    .block-container .radar-body > div { margin: 0 !important; padding: 0 !important; }

    .block-container .badge-table {
        width: 100%;
        border-collapse: collapse;
        table-layout: fixed;
    }
    .block-container .badge-table td {
        padding: 8px 8px;
        vertical-align: middle;
    }
    .block-container .badge-table .cell-label {
        color: white;
        font-family: __FG__ !important;
        font-size: 0.92rem;
        font-weight: 600;
        text-align: right;
        padding-right: 14px;
        white-space: normal;
        word-break: break-word;
    }
    .block-container .badge-table .cell-tag {
        text-align: left;
        white-space: nowrap;
    }
    .block-container .badge-tag {
        display: inline-block;
        padding: 6px 12px;
        border-radius: 6px;
        font-family: __FG__ !important;
        font-size: 0.82rem;
        font-weight: 700;
        white-space: nowrap;
        min-width: 90px;
        text-align: center;
        box-shadow: inset 0 -2px 0 rgba(0,0,0,0.06);
    }

    .block-container .text-list {
        list-style: none;
        padding: 0;
        margin: 0;
    }
    .block-container .text-list li {
        color: white;
        font-family: __FDO__ !important;
        font-size: 0.95rem;
        font-weight: 600;
        padding: 5px 0;
        border-bottom: 1px solid rgba(255,255,255,0.15);
    }
    .block-container .text-list li:last-child { border-bottom: none; }
    .block-container .text-list .num {
        display: inline-block;
        width: 24px; height: 24px;
        line-height: 24px;
        text-align: center;
        background: rgba(255,255,255,0.2);
        border-radius: 50%;
        font-size: 0.8rem;
        margin-right: 8px;
    }

    .block-container .no-data-msg {
        text-align: center;
        padding: 40px 20px;
        color: #78909C;
        font-size: 1.1rem;
    }
    .block-container .eval-meta {
        background: rgba(13,71,161,0.06);
        border-radius: 8px;
        padding: 8px 16px;
        margin-top: 8px;
        font-family: __FDO__ !important;
        font-size: 0.85rem;
        color: #546E7A;
    }
    .block-container div[data-testid="stSelectbox"] label {
        font-weight: 600;
        color: #0D47A1;
        font-family: __FG__ !important;
    }
    </style>
    """

    _css = _css_template.replace("__FD__", FONT_DISPLAY).replace("__FG__", FONT_GRAPHIC).replace("__FDO__", FONT_DOCUMENT)
    st.markdown(_css, unsafe_allow_html=True)

    # Helpers reused in dashboard
    def badge_tag(level):
        if not level:
            return ""
        s = BADGE_STYLES.get(level, {"bg": "#616161", "fg": "#FFF"})
        return f'<span class="badge-tag" style="background:{s["bg"]};color:{s["fg"]};">{level}</span>'

    def render_section(title, body):
        return f'<div class="section"><div class="section-header">{title}</div><div class="section-body">{body}</div></div>'

    def render_badges_table(items: list, cols: int = 4, tag_px: int = 110) -> str:
        # pad to multiple of cols
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

        table_html = f'<table class="badge-table">{colgroup_html}{rows_html}</table>'
        return table_html

    def render_list(items):
        if not items:
            return '<span style="color:rgba(255,255,255,0.5);">—</span>'
        li = ""
        for i, t in enumerate(items):
            li += f'<li><span class="num">{i + 1}</span>{t}</li>'
        return '<ul class="text-list">' + li + "</ul>"

    def build_radar(mog_data):
        cats = list(mog_data.keys())
        vals = list(mog_data.values()) if mog_data else [50]*len(cats)
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

    # Header (use f-string to avoid messy concatenation)
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

    left_col, right_col = st.columns([1, 3], gap="large")

    with left_col:
        photo = pr["photo_url"] or ""
        if photo:
            st.markdown(
                f'''
                <div class="block-container card player-card">
                    <div style="width:{PLAYER_IMG_W}px;height:{PLAYER_IMG_H}px;margin:0 auto 8px auto;display:flex;align-items:center;justify-content:center;background:#ffffff;border-radius:10px;border:3px solid #67b6fb;overflow:hidden;">
                        <img src="{photo}" alt="{player_name}" style="max-width:100%;max-height:100%;object-fit:contain;display:block;">
                    </div>
                    <div class="divider"></div>
                    <div class="label">Position</div><div class="value">{pr["position"] or "—"}</div>
                    <div class="label">Club</div><div class="value">{pr["club"] or "—"}</div>
                </div>
                ''',
                unsafe_allow_html=True,
            )
        else:
            st.markdown(f'''
                <div class="block-container card player-card">
                    <div class="divider"></div>
                    <div class="label">Position</div><div class="value">{pr["position"] or "—"}</div>
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

        # Technical
        tech_items = [(s, sk.get("technical", {}).get(s, "")) for s in TECHNICAL_SKILLS]
        st.markdown(render_section("Technical", render_badges_table(tech_items, 4)), unsafe_allow_html=True)

        # Player-specific (preserve input order, padded to 4)
        ps_data = sk.get("player_specific", {})
        ps_items = [(n, l) for n, l in ps_data.items()]
        while len(ps_items) < 4:
            ps_items.append(("", ""))
        st.markdown(render_section("Player-Specific Indicators", render_badges_table(ps_items, 4)), unsafe_allow_html=True)

        # Mental (fixed order, padded)
        m_items = [(s, sk.get("mental", {}).get(s, "")) for s in MENTAL_SKILLS]
        while len(m_items) < 4:
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
