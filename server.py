"""
ConcursoAlert — Backend API
Lê o banco SQLite do blogwatcher e serve dados processados
"""

import sqlite3
import json
import re
import os
from datetime import datetime, timedelta
from flask import Flask, jsonify, request
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

DB_PATH = os.path.expanduser("~/.blogwatcher-cli/blogwatcher-cli.db")

# Check if local DB exists (dev only)
HAS_LOCAL_DB = os.path.exists(DB_PATH) if DB_PATH.startswith('/') else False

# ==========================================
# HEURÍSTICAS DE CLASSIFICAÇÃO
# ==========================================

# Palavras-chave por status
STATUS_PATTERNS = {
    "aberto": [
        r"inscri[çc][õo]es abertas?", r"edital publicado", r"edital saiu",
        r"publicad[oa]", r"abert[oa]s?", r"concurso.*aberto"
    ],
    "em-breve": [
        r"edital em breve", r"previsto", r"autorizado", r"banca definida",
        r"banca contratada", r"edital.*previsto", r"iminente"
    ],
    "encerrando": [
        r"[uú]ltimos dias", r"encerram?", r"termina", r"prazo final",
        r"n[aã]o perca", r"[uú]ltima semana"
    ]
}

# Órgãos comuns (padrões de extração)
ORGAO_PATTERNS = [
    r"(?:Concurso|Edital)\s+(.+?)(?:\s+\d{4}|\s*:|\s*-|\s+inscri)",
    r"^(?:Concurso|Edital)\s+(.+?)(?:\s+\d{4})",
]

# Tags de região
REGIAO_TAGS = {
    "acre": ["acre", "ac", "rio branco"],
    "rondonia": ["rondônia", "rondonia", "ro", "porto velho"],
    "amazonas": ["amazonas", "am", "manaus"],
    "nacional": ["nacional", "federal", "brasil"]
}


def get_db():
    if not HAS_LOCAL_DB:
        return None
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    return db


def extract_orgao(title):
    """Tenta extrair o nome do órgão do título"""
    # Remove prefixo "Concurso " ou "Edital "
    cleaned = re.sub(r'^(?:Concurso|Edital|Processo Seletivo)\s+', '', title, flags=re.IGNORECASE)

    # Padrões comuns: "Órgão 2026:", "Órgão: cargo", "Órgão -"
    for pattern in [
        r'^(.+?)\s+\d{4}\s*[:—–-]',
        r'^(.+?)\s*:\s',
        r'^(.+?)\s+inscri[çc]',
        r'^(.+?)(?:\s+\d{4})',
    ]:
        m = re.match(pattern, cleaned, re.IGNORECASE)
        if m:
            return m.group(1).strip()

    # Fallback: primeiras 3 palavras
    words = cleaned.split()
    if len(words) >= 3:
        return ' '.join(words[:3])

    return cleaned[:60]


def extract_status(title, categories_str):
    """Determina o status do concurso pelo título e categorias"""
    title_lower = title.lower()
    cats = []
    try:
        cats = [c.lower() for c in json.loads(categories_str or '[]')]
    except:
        pass

    text = title_lower + ' ' + ' '.join(cats)

    # Verifica encerrando primeiro
    for pattern in STATUS_PATTERNS["encerrando"]:
        if re.search(pattern, text):
            return "encerrando"

    for pattern in STATUS_PATTERNS["aberto"]:
        if re.search(pattern, text):
            return "aberto"

    for pattern in STATUS_PATTERNS["em-breve"]:
        if re.search(pattern, text):
            return "em-breve"

    # Se tem "edital publicado" nas categorias
    if "edital publicado" in cats:
        return "aberto"
    if "autorizado" in cats:
        return "em-breve"
    if "banca contratada" in cats:
        return "em-breve"

    return "desconhecido"


def extract_regiao(title, categories_str):
    """Extrai região do título e categorias"""
    text = (title + ' ' + (categories_str or '')).lower()

    for regiao, tags in REGIAO_TAGS.items():
        for tag in tags:
            if tag in text:
                return regiao

    return "nacional"


def extract_vagas(title):
    """Tenta extrair número de vagas do título"""
    patterns = [
        r'(\d+)\s*vagas?',
        r'(\d+)\s*cargos?',
    ]
    for p in patterns:
        m = re.search(p, title, re.IGNORECASE)
        if m:
            return int(m.group(1))
    return None


def extract_area(categories):
    """Mapeia categorias para áreas"""
    try:
        cats = [c.lower() for c in json.loads(categories or '[]')]
    except:
        cats = []

    area_map = {
        "policial": ["policial", "pm", "polícia", "bombeiro", "militar", "agente", "delegado"],
        "fiscal": ["fiscal", "auditor", "receita", "sefaz", "tribut"],
        "juridica": ["jurídic", "judici", "tribunal", "trf", "trt", "tst", "tcu", "tj ", "tre", "juiz", "promotor", "defensor"],
        "bancaria": ["banco", "bancári", "caixa", "bb", "cef"],
        "educacao": ["educa", "professor", "escolar", "pedagog", "ensino"],
        "administrativa": ["administrativo", "técnico", "analista", "prefeitura"],
    }

    for area, keywords in area_map.items():
        for kw in keywords:
            for cat in cats:
                if kw in cat:
                    return area
            if kw in ' '.join(cats):
                return area

    return "administrativa"


def extract_escolaridade(title, categories_str):
    """Determina escolaridade pelo texto"""
    text = (title + ' ' + (categories_str or '')).lower()
    if any(w in text for w in ['superior', 'graduação', 'bacharel', 'direito', 'advogado', 'médico', 'enfermeir', 'engenheir']):
        return "superior"
    return "medio"


def process_article(row):
    """Processa um artigo bruto e retorna JSON estruturado"""
    title = row["title"]
    categories_str = row["categories"] or '[]'
    status = extract_status(title, categories_str)
    regiao = extract_regiao(title, categories_str)
    vagas = extract_vagas(title)
    area = extract_area(categories_str)
    escolaridade = extract_escolaridade(title, categories_str)
    orgao = extract_orgao(title)

    published = row["published_date"]
    if published:
        try:
            dt = datetime.fromisoformat(published.replace('Z', '+00:00'))
            published = dt.strftime('%Y-%m-%d')
        except:
            pass

    return {
        "id": row["id"],
        "titulo": title,
        "orgao": orgao,
        "url": row["url"],
        "fonte": row["blog_name"],
        "data": published or '',
        "status": status,
        "regiao": regiao,
        "vagas": vagas,
        "area": area,
        "escolaridade": escolaridade,
        "categorias": json.loads(categories_str) if categories_str else [],
    }


# ==========================================
# API ENDPOINTS
# ==========================================

@app.route('/')
def health():
    return jsonify({"status": "ok", "service": "Radar Concursos API", "local_db": HAS_LOCAL_DB})


@app.route('/api/concursos')
def list_concursos():
    db = get_db()
    if not db:
        return jsonify({"concursos": [], "total": 0, "limit": 0, "offset": 0})
    cur = db.cursor()

    # Filtros
    status = request.args.get('status', '')
    area = request.args.get('area', '')
    regiao = request.args.get('regiao', '')
    escolaridade = request.args.get('escolaridade', '')
    search = request.args.get('search', '').lower()
    limit = min(int(request.args.get('limit', 50)), 200)
    offset = int(request.args.get('offset', 0))

    cur.execute("""
        SELECT a.*, b.name as blog_name
        FROM articles a
        JOIN blogs b ON a.blog_id = b.id
        ORDER BY a.published_date DESC
        LIMIT 200
    """)

    rows = cur.fetchall()
    resultados = []

    for row in rows:
        item = process_article(row)

        # Aplicar filtros
        if status and item["status"] != status:
            continue
        if area and item["area"] != area:
            continue
        if regiao and item["regiao"] != regiao:
            continue
        if escolaridade and item["escolaridade"] != escolaridade:
            continue
        if search and search not in item["titulo"].lower() and search not in item["orgao"].lower():
            continue

        resultados.append(item)

    total = len(resultados)
    resultados = resultados[offset:offset + limit]

    db.close()
    return jsonify({
        "concursos": resultados,
        "total": total,
        "limit": limit,
        "offset": offset
    })


@app.route('/api/stats')
def stats():
    db = get_db()
    if not db:
        return jsonify({"total_artigos":0,"nao_lidos":0,"hoje":0,"por_fonte":{},"por_status":{}})
    cur = db.cursor()

    cur.execute("SELECT COUNT(*) FROM articles")
    total = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM articles WHERE is_read = 0")
    nao_lidos = cur.fetchone()[0]

    cur.execute("""
        SELECT b.name, COUNT(*) as cnt
        FROM articles a JOIN blogs b ON a.blog_id = b.id
        GROUP BY b.name
    """)
    by_blog = {row["name"]: row["cnt"] for row in cur.fetchall()}

    # Artigos de hoje
    hoje = datetime.utcnow().strftime('%Y-%m-%d')
    cur.execute("SELECT COUNT(*) FROM articles WHERE published_date LIKE ?", (f'{hoje}%',))
    hoje_count = cur.fetchone()[0]

    # Processa últimos 200 pra estatísticas de status
    cur.execute("""
        SELECT a.*, b.name as blog_name
        FROM articles a JOIN blogs b ON a.blog_id = b.id
        ORDER BY a.published_date DESC LIMIT 200
    """)

    status_counts = {"aberto": 0, "em-breve": 0, "encerrando": 0, "desconhecido": 0}
    for row in cur.fetchall():
        s = extract_status(row["title"], row["categories"] or '[]')
        status_counts[s] = status_counts.get(s, 0) + 1

    db.close()
    return jsonify({
        "total_artigos": total,
        "nao_lidos": nao_lidos,
        "hoje": hoje_count,
        "por_fonte": by_blog,
        "por_status": status_counts
    })


@app.route('/api/alertas')
def alertas():
    """Últimos artigos como alertas"""
    db = get_db()
    if not db:
        return jsonify({"alertas":[]})
    cur = db.cursor()
    cur.execute("""
        SELECT a.*, b.name as blog_name
        FROM articles a
        JOIN blogs b ON a.blog_id = b.id
        ORDER BY a.published_date DESC
        LIMIT 20
    """)

    rows = cur.fetchall()
    hoje = datetime.utcnow()
    alertas_list = []

    for row in rows:
        item = process_article(row)
        published = row["published_date"]
        urgente = False

        if published:
            try:
                dt = datetime.fromisoformat(published.replace('Z', '+00:00'))
                if (hoje - dt.replace(tzinfo=None)) < timedelta(hours=6):
                    urgente = True
            except:
                pass

        status_emoji = {
            "aberto": "📋", "em-breve": "🔜",
            "encerrando": "⏰", "desconhecido": "📌"
        }

        alertas_list.append({
            "id": item["id"],
            "texto": f"{status_emoji.get(item['status'], '📌')} {item['titulo']}",
            "url": item["url"],
            "data": item["data"],
            "fonte": item["fonte"],
            "urgente": urgente and item["status"] == "encerrando",
            "status": item["status"],
            "regiao": item["regiao"]
        })

    db.close()
    return jsonify({"alertas": alertas_list})


@app.route('/api/feed')
def feed_raw():
    """Dados brutos dos feeds — útil pra debug"""
    db = get_db()
    cur = db.cursor()
    cur.execute("""
        SELECT a.*, b.name as blog_name, b.feed_url
        FROM articles a
        JOIN blogs b ON a.blog_id = b.id
        ORDER BY a.published_date DESC
        LIMIT 20
    """)
    rows = [dict(r) for r in cur.fetchall()]
    db.close()
    return jsonify({"articles": rows})


@app.route('/api/scan', methods=['POST'])
def trigger_scan():
    """Dispara scan nos feeds"""
    import subprocess
    try:
        result = subprocess.run(
            ['blogwatcher-cli', 'scan'],
            capture_output=True, text=True, timeout=30
        )
        return jsonify({"ok": True, "output": result.stdout[:500]})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route('/api/ping')
def ping():
    return jsonify({"ping": "pong", "routes": [r.rule for r in app.url_map.iter_rules()]})


@app.route('/api/buscar')
def buscar_web():
    """Busca concursos na web + mescla com dados locais"""
    esfera = request.args.get('esfera', '')
    regiao = request.args.get('regiao', '')
    area = request.args.get('area', '')
    query = request.args.get('q', '')

    # Monta query de busca
    termos = ['concurso público', 'edital', '2026']
    if esfera and esfera != 'todas':
        termos.append(esfera)
    if regiao and regiao != 'todas':
        if regiao == 'acre': termos.append('Acre')
        elif regiao == 'rondonia': termos.append('Rondônia')
        elif regiao == 'amazonas': termos.append('Amazonas')
        elif regiao == 'nacional': termos.append('nacional')
    if area and area != 'todas':
        termos.append(area)
    if query:
        termos.insert(0, query)

    q = ' '.join(termos)

    resultados = []
    try:
        from duckduckgo_search import DDGS
        ddgs = DDGS()
        for r in ddgs.text(q, max_results=5, region='br-pt'):
            resultados.append({
                'titulo': r.get('title', ''),
                'url': r.get('href', ''),
                'fonte': 'Web Search',
                'data': r.get('date', ''),
                'descricao': r.get('body', '')[:200],
                'origem': 'web'
            })
    except Exception as e:
        app.logger.warning(f"DuckDuckGo search failed: {e}")

    # Mescla com dados locais do blogwatcher
    db = get_db()
    if db:
        cur = db.cursor()
        search_term = f"%{query or esfera or regiao or area}%"
        cur.execute("""
            SELECT a.*, b.name as blog_name FROM articles a
            JOIN blogs b ON a.blog_id = b.id
            WHERE a.title LIKE ? OR a.categories LIKE ?
            ORDER BY a.published_date DESC LIMIT 10
        """, [search_term, search_term])

        for row in cur.fetchall():
            item = process_article(row)
            item['origem'] = 'rss'
            if not any(r.get('url') == item['url'] for r in resultados):
                resultados.append(item)
        db.close()

    return jsonify({
        'query': q,
        'resultados': resultados,
        'total': len(resultados),
        'web': sum(1 for r in resultados if r.get('origem') == 'web'),
        'rss': sum(1 for r in resultados if r.get('origem') == 'rss')
    })


import urllib.request
import urllib.parse

@app.route('/api/google-news')
def google_news():
    """Proxy para Google News RSS - evita CORS"""
    q = request.args.get('q', 'concurso')
    url = f"https://news.google.com/rss/search?q={urllib.parse.quote(q)}&hl=pt-BR&gl=BR&ceid=BR:pt-419"
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = resp.read()
        return data, 200, {'Content-Type': 'application/xml', 'Access-Control-Allow-Origin': '*'}
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print(f"🔔 Radar Concursos API rodando na porta {port}")
    app.run(host='0.0.0.0', port=port, debug=False)
