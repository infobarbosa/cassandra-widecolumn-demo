"""
O fluxo aplicacional Q1 a Q7 do infobarbank, executado por uma aplicação.

Uso:

    python3 driver_demo.py                 # cliente e competência padrão
    python3 driver_demo.py 2b16242a        # outra cliente
    python3 driver_demo.py 2b162060 2026-05

A competência é descoberta no banco quando não informada, porque os lançamentos
são gerados em relação à data de execução. O script escolhe a mais recente, o
mês atual, como a tela inicial do app.
"""

import sys
from datetime import datetime

from cassandra import ConsistencyLevel
from cassandra.cluster import EXEC_PROFILE_DEFAULT, Cluster, ExecutionProfile
from cassandra.policies import DCAwareRoundRobinPolicy, TokenAwarePolicy

CONTACT_POINTS = ["127.0.0.1"]
KEYSPACE = "infobarbank"
DATACENTER = "datacenter1"

# Marivalda Kanamary, a mesma cliente das seções anteriores.
ID_CLIENTE_PADRAO = "2b162060"

# Uma consulta por tela do fluxo aplicacional. Cada uma lê de uma tabela
# diferente, e é a chave primária de cada tabela que determina qual.
CONSULTAS = {
    "Q1": """
        SELECT status, apelido_cliente, saldo_disponivel
        FROM conta_corrente
        WHERE id_cliente = ?
    """,
    "Q2": """
        SELECT status, id_cartao, num_cartao, limite_total, limite_disponivel
        FROM cartao_credito
        WHERE id_cliente = ?
    """,
    "Q3": """
        SELECT data_hora, id_produto, estabelecimento, valor
        FROM lancamentos_por_status
        WHERE id_cliente = ? AND competencia = ? AND status = 'APROVADA'
        LIMIT 3
    """,
    "Q4": """
        SELECT data_hora, id_produto, tipo_operacao, estabelecimento, valor
        FROM lancamentos_por_periodo
        WHERE id_cliente = ? AND competencia = ?
          AND data_hora >= ? AND data_hora < ?
    """,
    "Q5": """
        SELECT data_hora, estabelecimento, valor
        FROM lancamentos_por_produto
        WHERE id_cliente = ? AND competencia = ? AND id_produto = ?
    """,
    "Q6": """
        SELECT data_hora, estabelecimento, valor
        FROM lancamentos_por_tipo
        WHERE id_cliente = ? AND competencia = ? AND tipo_operacao = ?
    """,
    "Q7": """
        SELECT id_lancamento, data_hora, estabelecimento, valor, status,
               codigo_autenticacao
        FROM lancamentos_detalhe
        WHERE id_lancamento = ?
    """,
}


def abre_sessao():
    """Conecta ao cluster com a política de balanceamento declarada.

    `TokenAwarePolicy` é o motivo pelo qual prepared statements importam para o
    desempenho: sabendo a partition key, o driver calcula o token no cliente e
    envia a consulta direto para um nó que tem a réplica, em vez de sortear um
    nó qualquer e deixá-lo intermediar. Com um nó só isso não muda nada — mas é
    a configuração que se leva para produção.
    """
    perfil = ExecutionProfile(
        load_balancing_policy=TokenAwarePolicy(DCAwareRoundRobinPolicy(local_dc=DATACENTER)),
        consistency_level=ConsistencyLevel.LOCAL_ONE,
        request_timeout=15,
    )
    cluster = Cluster(CONTACT_POINTS, execution_profiles={EXEC_PROFILE_DEFAULT: perfil})
    return cluster, cluster.connect(KEYSPACE)


def descobre_competencia(session, id_cliente):
    """A competência mais recente com lançamentos desta cliente (o mês atual).

    Note o `SELECT DISTINCT`. A tentativa óbvia —

        SELECT competencia FROM lancamentos_por_periodo WHERE id_cliente = ?

    — é recusada, porque a partition key da tabela é o par
    `(id_cliente, competencia)` e metade dela não identifica partição alguma.
    `SELECT DISTINCT` sobre as colunas da partition key é o caminho válido: ele
    percorre o índice de partições, não os dados.

    Ainda assim, isso é conveniência de laboratório, não algo que uma aplicação
    faria: percorrer todas as partições não escala. Um aplicativo de banco não
    descobre a competência, ele a recebe do seletor de mês da tela.
    """
    linhas = session.execute(
        "SELECT DISTINCT id_cliente, competencia FROM lancamentos_por_periodo"
    )
    competencias = sorted({l.competencia for l in linhas if l.id_cliente == id_cliente})
    if not competencias:
        raise SystemExit(f"Cliente {id_cliente} não tem lançamentos.")
    return competencias[-1]


def titulo(texto):
    print(f"\n\033[1m{texto}\033[0m")


def moeda(valor):
    return f"R$ {valor:>10,.2f}".replace(",", "@").replace(".", ",").replace("@", ".")


def main():
    id_cliente = sys.argv[1] if len(sys.argv) > 1 else ID_CLIENTE_PADRAO
    cluster, session = abre_sessao()

    try:
        # Preparar uma vez, executar muitas. O servidor guarda o plano da
        # consulta e o cliente passa a enviar só o id dela mais os parâmetros.
        stmt = {nome: session.prepare(cql) for nome, cql in CONSULTAS.items()}

        cliente = session.execute(
            session.prepare("SELECT nome_completo, cpf, email FROM cliente WHERE id_cliente = ?"),
            [id_cliente],
        ).one()
        if cliente is None:
            raise SystemExit(f"Cliente {id_cliente} não encontrado.")

        competencia = sys.argv[2] if len(sys.argv) > 2 else descobre_competencia(session, id_cliente)
        print(f"Cliente {id_cliente} — {cliente.nome_completo} — competência {competencia}")

        titulo("Q1 · Dados da conta")
        for conta in session.execute(stmt["Q1"], [id_cliente]):
            # O id da conta é o próprio id_cliente: uma conta por cliente.
            print(f"  conta {id_cliente}  {conta.status:<8} "
                  f"apelido {conta.apelido_cliente:<12} saldo {moeda(conta.saldo_disponivel)}")

        titulo("Q2 · Cartões de crédito")
        cartoes = list(session.execute(stmt["Q2"], [id_cliente]))
        for cartao in cartoes:
            print(f"  {cartao.id_cartao}  {cartao.status:<8} {cartao.num_cartao}  "
                  f"limite {moeda(cartao.limite_total)}  disponível {moeda(cartao.limite_disponivel)}")

        titulo("Q3 · Últimos lançamentos aprovados")
        for lanc in session.execute(stmt["Q3"], [id_cliente, competencia]):
            print(f"  {lanc.data_hora:%d/%m %H:%M}  {lanc.id_produto}  "
                  f"{lanc.estabelecimento:<20} {moeda(lanc.valor)}")

        titulo("Q4 · Extrato por período (dias 1 a 14)")
        # O cqlsh aceita '2026-10-01' como literal de timestamp; o driver não.
        # Parâmetro de prepared statement é tipado, e o tipo é verificado no
        # cliente antes de a consulta sair da máquina.
        ano, mes = (int(parte) for parte in competencia.split("-"))
        inicio = datetime(ano, mes, 1)
        fim = datetime(ano, mes, 15)
        for lanc in session.execute(stmt["Q4"], [id_cliente, competencia, inicio, fim]):
            print(f"  {lanc.data_hora:%d/%m %H:%M}  {lanc.tipo_operacao:<8} "
                  f"{lanc.estabelecimento:<20} {moeda(lanc.valor)}")

        if cartoes:
            id_cartao = cartoes[0].id_cartao
            titulo(f"Q5 · Lançamentos do cartão {id_cartao}")
            for lanc in session.execute(stmt["Q5"], [id_cliente, competencia, id_cartao]):
                print(f"  {lanc.data_hora:%d/%m %H:%M}  "
                      f"{lanc.estabelecimento:<20} {moeda(lanc.valor)}")

        titulo("Q6 · Lançamentos de saída (débito)")
        debitos = list(session.execute(stmt["Q6"], [id_cliente, competencia, "DEBITO"]))
        for lanc in debitos[:5]:
            print(f"  {lanc.data_hora:%d/%m %H:%M}  "
                  f"{lanc.estabelecimento:<20} {moeda(lanc.valor)}")
        print(f"  ({len(debitos)} no total)")

        if debitos:
            # A tela de detalhe recebe o id do lançamento que o usuário tocou.
            # Aqui simulamos isso pegando o primeiro da lista anterior.
            id_lancamento = session.execute(
                session.prepare(
                    "SELECT id_lancamento FROM lancamentos_por_periodo "
                    "WHERE id_cliente = ? AND competencia = ? LIMIT 1"
                ),
                [id_cliente, competencia],
            ).one().id_lancamento

            titulo(f"Q7 · Detalhe do lançamento {id_lancamento}")
            detalhe = session.execute(stmt["Q7"], [id_lancamento]).one()
            print(f"  {detalhe.data_hora:%d/%m/%Y %H:%M}  {detalhe.estabelecimento}")
            print(f"  {moeda(detalhe.valor)}  {detalhe.status}")
            print(f"  autenticação {detalhe.codigo_autenticacao}")

    finally:
        cluster.shutdown()


if __name__ == "__main__":
    main()
