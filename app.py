from flask import Flask, render_template, request, redirect, Response, flash, session
import psycopg2
from datetime import datetime, timedelta
import os
from functools import wraps
import pytz

from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, Image
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import TableStyle
from io import BytesIO

from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv
load_dotenv()

# ======================================
# CONFIGURAÇÃO
# ======================================

app = Flask(__name__)
app.secret_key = "xodo_super_secret"

DATABASE_URL = os.getenv("DATABASE_URL")

def get_connection():
    return psycopg2.connect(DATABASE_URL)

# ======================================
# LOGIN REQUIRED
# ======================================

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session:
            return redirect("/login")
        return f(*args, **kwargs)
    return decorated_function

# ======================================
# GERAR PDF
# ======================================

def gerar_pdf_relatorio(data, tipo):

    conn = get_connection()
    cur = conn.cursor()

    if tipo == "producao":
        cur.execute("""
            SELECT p.nome, o.produzido
            FROM operacao_diaria o
            JOIN produtos p ON p.id = o.produto_id
            WHERE o.data = %s AND o.produzido > 0
        """, (data,))
    else:
        cur.execute("""
            SELECT p.nome, o.sobra_real
            FROM operacao_diaria o
            JOIN produtos p ON p.id = o.produto_id
            WHERE o.data = %s AND o.sobra_real > 0
        """, (data,))

    dados = cur.fetchall()
    conn.close()

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer)
    elements = []
    styles = getSampleStyleSheet()

    # Logo
    logo_path = os.path.join(app.root_path, "static", "logo-pdf.png")
    if os.path.exists(logo_path):
        logo = Image(logo_path, width=2*inch, height=1*inch)
        elements.append(logo)

    elements.append(Spacer(1, 0.3 * inch))

    # FUSO BRASIL
    fuso = pytz.timezone("America/Sao_Paulo")
    agora = datetime.now(fuso)

    elements.append(Paragraph(f"<b>Lista {tipo.capitalize()}</b>", styles['Title']))
    elements.append(Paragraph(f"Data: {agora.strftime('%d/%m/%Y')}", styles['Normal']))
    elements.append(Paragraph(f"Hora: {agora.strftime('%H:%M')}", styles['Normal']))
    elements.append(Paragraph(
        f"Operador: {session.get('username')} | Filial: {session.get('filial_nome')}",
        styles['Normal']
    ))

    elements.append(Spacer(1, 0.4 * inch))

    tabela_dados = [["Produto", "Quantidade"]]

    for item in dados:
        tabela_dados.append([item[0], str(item[1])])

    tabela = Table(tabela_dados, colWidths=[4*inch, 1.5*inch])
    tabela.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#b71c1c")),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ('ALIGN', (1, 1), (-1, -1), 'CENTER'),
    ]))

    elements.append(tabela)
    doc.build(elements)
    buffer.seek(0)

    return buffer

# ======================================
# HOME
# ======================================

@app.route("/")
@login_required
def index():
    return render_template("index.html")

# ======================================
# PRODUÇÃO / FECHAMENTO
# ======================================

@app.route("/producao")
@login_required
def producao():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, nome FROM produtos WHERE ativo = TRUE ORDER BY nome;")
    produtos = cur.fetchall()
    conn.close()
    return render_template("producao.html", produtos=produtos)

@app.route("/fechamento")
@login_required
def fechamento():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, nome FROM produtos WHERE ativo = TRUE ORDER BY nome;")
    produtos = cur.fetchall()
    conn.close()
    return render_template("fechamento.html", produtos=produtos)

# ======================================
# SALVAR
# ======================================

@app.route("/salvar", methods=["POST"])
@login_required
def salvar():

    tipo = request.form.get("tipo")

    if tipo == "producao":
        data = datetime.now().date() + timedelta(days=1)
    else:
        data = datetime.now().date()

    conn = get_connection()
    cur = conn.cursor()

    # 🔥 LIMPA O DIA ANTES (evita duplicação)
    cur.execute("""
        DELETE FROM operacao_diaria
        WHERE data = %s
    """, (data,))

    for key in request.form:
        if key.startswith("produto_"):
            produto_id = key.split("_")[1]
            quantidade = int(request.form[key])

            if quantidade > 0:
                if tipo == "producao":
                    cur.execute("""
                        INSERT INTO operacao_diaria 
                        (data, produto_id, produzido, vendido, enviado_filial, sobra_real)
                        VALUES (%s, %s, %s, 0, 0, 0)
                    """, (data, produto_id, quantidade))
                else:
                    cur.execute("""
                        INSERT INTO operacao_diaria 
                        (data, produto_id, produzido, vendido, enviado_filial, sobra_real)
                        VALUES (%s, %s, 0, 0, 0, %s)
                    """, (data, produto_id, quantidade))

    conn.commit()
    conn.close()

    return redirect(f"/pdf/{tipo}/{data}")

# ======================================
# ROTA PDF
# ======================================

@app.route("/pdf/<tipo>/<data>")
@login_required
def gerar_pdf(tipo, data):

    pdf_buffer = gerar_pdf_relatorio(data, tipo)

    return Response(
        pdf_buffer,
        mimetype="application/pdf",
        headers={
            "Content-Disposition":
            f"inline; filename=relatorio_{tipo}_{data}.pdf"
        }
    )

# ======================================
# PRODUTOS
# ======================================

@app.route("/produto", methods=["GET", "POST"])
@login_required
def produto():

    conn = get_connection()
    cur = conn.cursor()

    if request.method == "POST":
        produto_id = request.form.get("id")
        nome = request.form.get("nome")

        if produto_id:
            cur.execute("UPDATE produtos SET nome = %s WHERE id = %s;", (nome, produto_id))
            flash("Produto atualizado com sucesso!")

        elif nome:
            cur.execute("INSERT INTO produtos (nome, ativo) VALUES (%s, TRUE);", (nome,))
            flash("Produto salvo com sucesso!")

        conn.commit()
        conn.close()
        return redirect("/produto")

    cur.execute("SELECT id, nome, ativo FROM produtos ORDER BY nome;")
    produtos = cur.fetchall()
    conn.close()

    return render_template("cadastrar_produto.html", produtos=produtos)

# ======================================
# REGISTER
# ======================================

@app.route("/register", methods=["GET", "POST"])
def register():

    conn = get_connection()
    cur = conn.cursor()

    if request.method == "POST":
        username = request.form.get("username")
        senha = request.form.get("senha")
        filial_id = request.form.get("filial")

        senha_hash = generate_password_hash(senha)

        cur.execute("""
            INSERT INTO usuarios (username, senha, filial_id)
            VALUES (%s, %s, %s)
        """, (username, senha_hash, filial_id))

        conn.commit()
        conn.close()

        flash("Usuário cadastrado com sucesso! 🎉")
        return redirect("/register")

    cur.execute("SELECT id, nome FROM filiais ORDER BY nome;")
    filiais = cur.fetchall()
    conn.close()

    return render_template("register.html", filiais=filiais)

# ======================================
# LOGIN
# ======================================

@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":
        username = request.form.get("username")
        senha = request.form.get("senha")

        conn = get_connection()
        cur = conn.cursor()

        cur.execute("""
            SELECT u.id, u.username, u.senha, f.nome
            FROM usuarios u
            JOIN filiais f ON f.id = u.filial_id
            WHERE u.username = %s
        """, (username,))

        user = cur.fetchone()
        conn.close()

        if user and check_password_hash(user[2], senha):
            session["user_id"] = user[0]
            session["username"] = user[1]
            session["filial_nome"] = user[3]
            return redirect("/")

        flash("Usuário ou senha inválidos")

    return render_template("login.html")

# ======================================
# LOGOUT
# ======================================

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")

if __name__ == "__main__":
    app.run(debug=True)