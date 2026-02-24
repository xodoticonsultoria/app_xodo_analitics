from flask import Flask, render_template, request, redirect, Response
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
            JOIN produtos p ON p.id = o.produzido
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

    # LOGO
    logo_path = os.path.join("static", "logo.png")
    if os.path.exists(logo_path):
        logo = Image(logo_path, width=2*inch, height=0.8*inch)
        elements.append(logo)

    elements.append(Spacer(1, 0.3 * inch))

    # TITULO
    elements.append(Paragraph(f"<b>Relatório {tipo.capitalize()}</b>", styles['Title']))
    elements.append(Paragraph(f"Data: {data}", styles['Normal']))
    elements.append(Spacer(1, 0.3 * inch))

    tabela_dados = [["Produto", "Quantidade"]]
    total_geral = 0

    for item in dados:
        tabela_dados.append([item[0], str(item[1])])
        total_geral += item[1]

    tabela_dados.append(["TOTAL GERAL", str(total_geral)])

    tabela = Table(tabela_dados, colWidths=[4*inch, 1.5*inch])
    tabela.setStyle(TableStyle([
        # Cabeçalho vermelho
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#b71c1c")),
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),

        # Total destacado
        ('BACKGROUND', (0,-1), (-1,-1), colors.HexColor("#ffe6e6")),
        ('TEXTCOLOR', (0,-1), (-1,-1), colors.red),

        ('GRID', (0,0), (-1,-1), 1, colors.black),
        ('ALIGN',(1,1),(-1,-1),'CENTER'),
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
        nome = request.form.get("nome")

        if nome:
            cur.execute(
                "INSERT INTO produtos (nome, ativo) VALUES (%s, TRUE);",
                (nome,)
            )
            conn.commit()

        cur.close()
        conn.close()
        return redirect("/produto")

    cur.close()
    conn.close()
    return render_template("cadastrar_produto.html")

if __name__ == "__main__":
    app.run(debug=True)