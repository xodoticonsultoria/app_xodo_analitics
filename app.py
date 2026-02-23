from flask import Flask, render_template, request, redirect
import psycopg2
from datetime import datetime, timedelta
import os

app = Flask(__name__)

DATABASE_URL = os.getenv("DATABASE_URL")

def get_connection():
    return psycopg2.connect(DATABASE_URL)

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

    return redirect("/")