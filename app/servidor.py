"""
App infobarBank: o emulador do aplicativo do banco, alimentado pelas consultas
CQL que o aluno escreve para Q1 a Q7.

Uso, no terminal do code-server:

    python3 app/servidor.py               # modo aluno
    python3 app/servidor.py --professor   # libera o botão "Solução"

Depois, abra no navegador:  http://<IP-PUBLICO>:8080/proxy/8000/
(em execução local:          http://localhost:8080/proxy/8000/)

Só usa a biblioteca padrão do Python e o driver do Cassandra que já vem na
imagem do laboratório. Aceita apenas SELECT na keyspace infobarbank.
"""

import argparse
import datetime
import json
import re
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from cassandra import ConsistencyLevel
from cassandra.cluster import EXEC_PROFILE_DEFAULT, Cluster, ExecutionProfile
from cassandra.policies import DCAwareRoundRobinPolicy, TokenAwarePolicy
from cassandra.query import SimpleStatement

PASTA = Path(__file__).resolve().parent
MAX_LINHAS = 500

# As sete clientes que têm conta, cartões e lançamentos no infobarbank.
PERSONAS = ["2b162060", "2b16242a", "2b16256a", "2b16353c", "2b1636ae", "2b16396a", "2b163bcc"]

# Cada consulta do fluxo aplicacional: o que a tela tem em mãos (parâmetros),
# o que ela precisa exibir (colunas), como conferir o resultado, dicas e a
# solução de referência — usada para conferir, e só mostrada em modo professor.
CONSULTAS = {
    "Q1": {
        "titulo": "Dados da conta",
        "tela": "início",
        "descricao": "Ao entrar no app, a tela mostra o apelido da cliente, o número da conta e o saldo disponível.",
        "parametros": ["id_cliente"],
        "colunas": ["apelido_cliente", "id_conta", "saldo_disponivel"],
        "dicas": ["A tabela é a conta_corrente.",
                  "A partition key da conta_corrente é id_cliente — exatamente o que o login entregou."],
        "solucao": "SELECT id_conta, apelido_cliente, saldo_disponivel\nFROM infobarbank.conta_corrente\nWHERE id_cliente = :id_cliente;",
    },
    "Q2": {
        "titulo": "Cartões de crédito e limites",
        "tela": "início",
        "descricao": "A tela lista os cartões da cliente, os ativos primeiro, com o limite disponível de cada um.",
        "parametros": ["id_cliente"],
        "colunas": ["id_cartao", "num_cartao", "status", "limite_disponivel"],
        "dicas": ["A tabela é a cartao_credito.",
                  "Basta a partition key. A ordem (ativos primeiro) já vem da clustering key status."],
        "solucao": "SELECT status, id_cartao, num_cartao, limite_disponivel\nFROM infobarbank.cartao_credito\nWHERE id_cliente = :id_cliente;",
    },
    "Q3": {
        "titulo": "Últimos lançamentos aprovados",
        "tela": "início",
        "descricao": "A tela mostra os três lançamentos aprovados mais recentes do mês. Se o mês não tiver nenhum, o app procura no mês anterior — essa regra é da aplicação, não do banco.",
        "parametros": ["id_cliente", "competencia"],
        "colunas": ["data_hora", "estabelecimento", "valor"],
        "dicas": ["A tabela é a lancamentos_por_status.",
                  "Partition key completa (id_cliente e competencia), status = 'APROVADA' e LIMIT 3. A ordem por data já está no disco."],
        "solucao": "SELECT data_hora, id_produto, estabelecimento, valor\nFROM infobarbank.lancamentos_por_status\nWHERE id_cliente = :id_cliente AND competencia = :competencia\n  AND status = 'APROVADA'\nLIMIT 3;",
    },
    "Q4": {
        "titulo": "Extrato do mês",
        "tela": "extrato",
        "descricao": "O extrato mostra todos os lançamentos do mês escolhido no seletor, do mais recente para o mais antigo. Cada linha precisa do id_lancamento, para a tela de detalhe.",
        "parametros": ["id_cliente", "competencia"],
        "colunas": ["id_lancamento", "data_hora", "estabelecimento", "valor", "tipo_operacao"],
        "dicas": ["A tabela é a lancamentos_por_periodo.",
                  "Só a partition key completa. A clustering key data_hora DESC entrega a ordem do extrato."],
        "solucao": "SELECT id_lancamento, data_hora, estabelecimento, valor, tipo_operacao\nFROM infobarbank.lancamentos_por_periodo\nWHERE id_cliente = :id_cliente AND competencia = :competencia;",
    },
    "Q5": {
        "titulo": "Extrato de um cartão ou da conta",
        "tela": "extrato",
        "descricao": "Com um cartão (ou a conta) selecionado no filtro, o extrato mostra só os lançamentos daquele produto no mês.",
        "parametros": ["id_cliente", "competencia", "id_produto"],
        "colunas": ["id_lancamento", "data_hora", "estabelecimento", "valor", "tipo_operacao"],
        "dicas": ["A tabela é a lancamentos_por_produto.",
                  "Partition key completa e id_produto, a primeira clustering key."],
        "solucao": "SELECT id_lancamento, data_hora, estabelecimento, valor, tipo_operacao\nFROM infobarbank.lancamentos_por_produto\nWHERE id_cliente = :id_cliente AND competencia = :competencia\n  AND id_produto = :id_produto;",
    },
    "Q6": {
        "titulo": "Extrato por tipo (débito ou crédito)",
        "tela": "extrato",
        "descricao": "Com o filtro débito ou crédito ligado, o extrato mostra só os lançamentos daquele tipo no mês.",
        "parametros": ["id_cliente", "competencia", "tipo_operacao"],
        "colunas": ["id_lancamento", "data_hora", "estabelecimento", "valor", "tipo_operacao"],
        "dicas": ["A tabela é a lancamentos_por_tipo.",
                  "Partition key completa e tipo_operacao, a primeira clustering key."],
        "solucao": "SELECT id_lancamento, data_hora, estabelecimento, valor, tipo_operacao\nFROM infobarbank.lancamentos_por_tipo\nWHERE id_cliente = :id_cliente AND competencia = :competencia\n  AND tipo_operacao = :tipo_operacao;",
    },
    "Q7": {
        "titulo": "Detalhe do lançamento",
        "tela": "detalhe",
        "descricao": "Ao tocar numa linha do extrato, a tela de detalhe mostra o lançamento completo, inclusive o código de autenticação.",
        "parametros": ["id_cliente", "id_lancamento"],
        "colunas": ["data_hora", "estabelecimento", "valor", "tipo_operacao", "status", "codigo_autenticacao"],
        "dicas": ["A tabela é a lancamentos_detalhe.",
                  "A chave é só id_lancamento — o id que a linha tocada no extrato entregou."],
        "solucao": "SELECT data_hora, estabelecimento, valor, tipo_operacao, status, codigo_autenticacao\nFROM infobarbank.lancamentos_detalhe\nWHERE id_lancamento = :id_lancamento;",
    },
}

NOMES_PARAMETROS = {
    "id_cliente": "o id da cliente que fez login",
    "competencia": "o mês escolhido no seletor (AAAA-MM)",
    "id_produto": "o cartão ou a conta escolhido no filtro",
    "tipo_operacao": "o filtro DEBITO ou CREDITO",
    "id_lancamento": "o id da linha tocada no extrato",
}


class Erro(Exception):
    """Erro com mensagem para o aluno."""


# ---------------------------------------------------------------------------
# Cassandra

def conectar():
    perfil = ExecutionProfile(
        load_balancing_policy=TokenAwarePolicy(DCAwareRoundRobinPolicy(local_dc="datacenter1")),
        consistency_level=ConsistencyLevel.LOCAL_ONE,
        request_timeout=15,
    )
    cluster = Cluster(["127.0.0.1"], execution_profiles={EXEC_PROFILE_DEFAULT: perfil})
    return cluster.connect("infobarbank")


def texto(valor):
    if valor is None:
        return None
    if isinstance(valor, datetime.datetime):
        return valor.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(valor, float):
        return round(valor, 2)
    if isinstance(valor, (int, str, bool)):
        return valor
    return str(valor)


def validar(cql):
    """Aceita um único SELECT sobre a keyspace infobarbank."""
    limpo = re.sub(r"--[^\n]*|//[^\n]*|/\*.*?\*/", " ", cql, flags=re.S).strip()
    limpo = limpo.rstrip(";").strip()
    if not limpo:
        raise Erro("Escreva uma consulta.")
    if ";" in limpo:
        raise Erro("Uma consulta por vez: tire o que vem depois do ';'.")
    if not re.match(r"(?i)select\b", limpo):
        raise Erro("Aqui só vale SELECT: o app apenas lê os dados.")
    for ks in re.findall(r'(?i)\bfrom\s+"?(\w+)"?\s*\.', limpo):
        if ks.lower() != "infobarbank":
            raise Erro(f"A consulta precisa ser na keyspace infobarbank, não em {ks}.")
    return limpo


def custo(rs, ms):
    """Resume o rastro (TRACING) da consulta em termos que importam para a modelagem."""
    resumo = {"ms": ms, "particoes": 0, "faixas": 0, "lidas": 0, "indice": False}
    try:
        trace = rs.get_query_trace(max_wait_sec=3)
        for ev in trace.events:
            a = ev.description
            if "Executing single-partition query" in a:
                resumo["particoes"] += 1
            m = re.search(r"Submitting range requests on (\d+) ranges", a)
            if m:
                resumo["faixas"] = max(resumo["faixas"], int(m.group(1)))
            m = re.search(r"Read (\d+) live rows", a)
            if m:
                resumo["lidas"] += int(m.group(1))
            if "using index" in a:
                resumo["indice"] = True
    except Exception:  # o rastro é um extra: sem ele, a consulta continua valendo
        resumo["indisponivel"] = True
    return resumo


def executar(sessao, cql, parametros, rastrear=True):
    sem_textos = re.sub(r"'(?:[^']|'')*'", "''", cql)  # ':' dentro de '10:10' não é parâmetro
    nomes = list(dict.fromkeys(re.findall(r":([A-Za-z_]\w*)", sem_textos)))
    valores = {}
    for n in nomes:
        if n not in parametros or parametros[n] in (None, ""):
            raise Erro(f"Nesta tela a aplicação não tem :{n} em mãos.")
        valores[n] = parametros[n]
    t0 = time.perf_counter()
    try:
        if nomes:
            stmt = sessao.prepare(cql)
            stmt.fetch_size = MAX_LINHAS
            rs = sessao.execute(stmt, valores, trace=rastrear)
        else:
            rs = sessao.execute(SimpleStatement(cql, fetch_size=MAX_LINHAS), trace=rastrear)
    except Erro:
        raise
    except Exception as e:  # a mensagem do Cassandra é parte da lição: devolve na íntegra
        raise Erro(getattr(e, "message", None) or str(e))
    ms = round((time.perf_counter() - t0) * 1000, 1)
    colunas = list(rs.column_names or [])
    linhas = [[texto(v) for v in linha] for linha in rs.current_rows][:MAX_LINHAS]
    return colunas, linhas, (custo(rs, ms) if rastrear else None)


def conferir(q, colunas, linhas, ref_colunas, ref_linhas):
    """Compara o resultado do aluno com o da solução, nas colunas que a tela usa."""
    esperadas = CONSULTAS[q]["colunas"]
    faltando = [c for c in esperadas if c not in colunas]
    if faltando:
        return {"ok": False, "faltando": faltando,
                "msg": "A tela precisa de " + ", ".join(faltando) + "."}

    def projeta(cols, rows):
        idx = [cols.index(c) for c in esperadas]
        return [[r[i] for i in idx] for r in rows]

    meu, ref = projeta(colunas, linhas), projeta(ref_colunas, ref_linhas)
    if meu == ref:
        return {"ok": True, "msg": "Confere com o que a tela espera."}
    if len(meu) != len(ref):
        return {"ok": False, "msg": f"A tela esperava {len(ref)} linha(s) e recebeu {len(meu)}."}
    if sorted(map(str, meu)) == sorted(map(str, ref)):
        return {"ok": False, "msg": "As linhas certas, mas fora da ordem que a tela mostra."}
    return {"ok": False, "msg": "O resultado não é o que a tela espera."}


# ---------------------------------------------------------------------------
# HTTP

class App(SimpleHTTPRequestHandler):
    sessao = None
    professor = False

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(PASTA / "web"), **kwargs)

    def log_message(self, fmt, *args):  # silencia o log de cada requisição estática
        if "/api/" in (args[0] if args else ""):
            super().log_message(fmt, *args)

    def json(self, dados, status=200):
        corpo = json.dumps(dados, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(corpo)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(corpo)

    def do_GET(self):
        if self.path.startswith("/api/inicio"):
            return self.json(self.inicio())
        if self.path.startswith("/api/competencias"):
            id_cliente = self.path.split("id_cliente=")[-1][:20]
            return self.json(self.competencias(id_cliente))
        return super().do_GET()

    def do_POST(self):
        tamanho = int(self.headers.get("Content-Length", 0))
        try:
            dados = json.loads(self.rfile.read(tamanho) or b"{}")
        except json.JSONDecodeError:
            return self.json({"erro": "Requisição inválida."}, 400)
        if self.path.startswith("/api/executar"):
            return self.json(self.executar(dados))
        return self.json({"erro": "Rota desconhecida."}, 404)

    # --- rotas ---------------------------------------------------------------

    def inicio(self):
        personas = []
        for id_cliente in PERSONAS:
            linha = self.sessao.execute(
                "SELECT nome_completo FROM cliente WHERE id_cliente = %s", [id_cliente]).one()
            personas.append({"id": id_cliente, "nome": linha.nome_completo if linha else id_cliente})
        consultas = {q: {k: v for k, v in c.items() if k != "solucao"} for q, c in CONSULTAS.items()}
        if self.professor:
            for q in consultas:
                consultas[q]["solucao"] = CONSULTAS[q]["solucao"]
        return {"personas": personas, "consultas": consultas,
                "nomes_parametros": NOMES_PARAMETROS, "professor": self.professor}

    def competencias(self, id_cliente):
        # Conveniência do app (o seletor de mês), não uma consulta do aluno.
        rs = self.sessao.execute("SELECT DISTINCT id_cliente, competencia FROM lancamentos_por_periodo")
        meses = sorted({r.competencia for r in rs if r.id_cliente == id_cliente})
        return {"competencias": meses}

    def executar(self, dados):
        q = dados.get("q")
        if q not in CONSULTAS:
            return {"erro": "Consulta desconhecida."}
        disponiveis = {k: v for k, v in (dados.get("parametros") or {}).items()
                       if k in CONSULTAS[q]["parametros"]}
        try:
            cql = validar(dados.get("cql", ""))
            colunas, linhas, resumo = executar(self.sessao, cql, disponiveis)
        except Erro as e:
            return {"erro": str(e)}
        if resumo is not None:
            resumo["filtragem"] = bool(re.search(r"(?i)\ballow\s+filtering\b", cql))
        resposta = {"colunas": colunas, "linhas": linhas, "custo": resumo}
        try:
            ref_c, ref_l, _ = executar(self.sessao, CONSULTAS[q]["solucao"].rstrip(";"), disponiveis,
                                       rastrear=False)
            resposta["confere"] = conferir(q, colunas, linhas, ref_c, ref_l)
        except Erro:
            resposta["confere"] = None
        return resposta


def main():
    ap = argparse.ArgumentParser(description="App infobarBank para o laboratório de Cassandra.")
    ap.add_argument("--porta", type=int, default=8000)
    ap.add_argument("--professor", action="store_true", help="libera o botão Solução")
    args = ap.parse_args()

    App.sessao = conectar()
    App.professor = args.professor
    servidor = ThreadingHTTPServer(("127.0.0.1", args.porta), App)
    print(f"App infobarBank no ar, porta {args.porta}{' (modo professor)' if args.professor else ''}.")
    print(f"Abra no navegador:  http://<IP-PUBLICO>:8080/proxy/{args.porta}/")
    print("Para encerrar: Control+C")
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        print("\nApp encerrado.")


if __name__ == "__main__":
    main()
