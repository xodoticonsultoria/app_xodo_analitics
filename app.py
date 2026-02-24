from flask import Flask, render_template, request, redirect, Response, flash
import psycopg2
from datetime import datetime, timedelta
import os

from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, Image
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import TableStyle
from io import BytesIO

app = Flask(__name__)

app.secret_key = "xodo_super_secret"

DATABASE_URL = os.getenv("DATABASE_URL")

def get_connection():
    return psycopg2.connect(DATABASE_URL)

# ======================================
# FUNÇÃO GERAR PDF
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

    # =========================
    # LOGO (CAMINHO CORRETO)
    # =========================
    logo_path = os.path.join(app.root_path, "static", "logo.png")

    if os.path.exists(logo_path):
        logo = Image(logo_path, width=2*inch, height=1.2*inch)
        elements.append(logo)

    elements.append(Spacer(1, 0.3 * inch))

    # =========================
    # DATA + HORA
    # =========================
    agora = datetime.now()
    data_formatada = agora.strftime("%d/%m/%Y")
    hora_formatada = agora.strftime("%H:%M")

    elements.append(Paragraph(
        f"<b>Relatório {tipo.capitalize()}</b>",
        styles['Title']
    ))

    elements.append(Paragraph(
        f"Data: {data_formatada}",
        styles['Normal']
    ))

    elements.append(Paragraph(
        f"Hora: {hora_formatada}",
        styles['Normal']
    ))

    elements.append(Spacer(1, 0.4 * inch))

    # =========================
    # TABELA
    # =========================
    tabela_dados = [["Produto", "Quantidade"]]

    for item in dados:
        tabela_dados.append([item[0], str(item[1])])

    tabela = Table(tabela_dados, colWidths=[4*inch, 1.5*inch])

    tabela.setStyle(TableStyle([
        # Cabeçalho vermelho Xodó
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#b71c1c")),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),

        # Bordas
        ('GRID', (0, 0), (-1, -1), 1, colors.black),

        # Centralizar coluna quantidade
        ('ALIGN', (1, 1), (-1, -1), 'CENTER'),
    ]))

    elements.append(tabela)

    doc.build(elements)
    buffer.seek(0)

    return buffer
# ======================================
# ROTAS
# ======================================

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/producao")
def producao():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, nome FROM produtos WHERE ativo = TRUE ORDER BY nome;")
    produtos = cur.fetchall()
    conn.close()
    return render_template("producao.html", produtos=produtos)

@app.route("/fechamento")
def fechamento():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, nome FROM produtos WHERE ativo = TRUE ORDER BY nome;")
    produtos = cur.fetchall()
    conn.close()
    return render_template("fechamento.html", produtos=produtos)

@app.route("/salvar", methods=["POST"])
def salvar():

    tipo = request.form.get("tipo")

    if tipo == "producao":
        data = datetime.now().date() + timedelta(days=1)
    else:
        data = datetime.now().date()

    conn = get_connection()
    cur = conn.cursor()

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

    pdf_buffer = gerar_pdf_relatorio(data, tipo)

    return Response(
        pdf_buffer,
        mimetype="application/pdf",
        headers={
            "Content-Disposition":
            f"inline; filename=relatorio_{tipo}_{data}.pdf"
        }
    )

@app.route("/produto", methods=["GET", "POST"])
def produto():

    conn = get_connection()
    cur = conn.cursor()

    if request.method == "POST":

        produto_id = request.form.get("id")
        nome = request.form.get("nome")

        if produto_id:  # 👉 SE EXISTE ID = EDITAR
            cur.execute(
                "UPDATE produtos SET nome = %s WHERE id = %s;",
                (nome, produto_id)
            )
            flash("✏️ Produto atualizado com sucesso!")

        elif nome:  # 👉 SE NÃO TEM ID = NOVO PRODUTO
            cur.execute(
                "INSERT INTO produtos (nome, ativo) VALUES (%s, TRUE);",
                (nome,)
            )
            flash("🎉 Parabéns! Produto salvo com sucesso.")

        conn.commit()
        cur.close()
        conn.close()

        return redirect("/produto")

    # 👉 LISTAR PRODUTOS
    cur.execute("SELECT id, nome, ativo FROM produtos ORDER BY nome;")
    produtos = cur.fetchall()

    cur.close()
    conn.close()

    return render_template("cadastrar_produto.html", produtos=produtos)
if __name__ == "__main__":
    app.run(debug=True)