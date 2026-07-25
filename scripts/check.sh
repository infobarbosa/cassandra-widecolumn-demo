#!/usr/bin/env bash
#
# Verifica se o ambiente do laboratório está íntegro.
#
#   bash scripts/check.sh
#
# Ou, sem clonar o repositório:
#
#   curl -sS https://raw.githubusercontent.com/infobarbosa/cassandra5-demo/revisao-julho2026/scripts/check.sh | bash
#
# Use este script sempre que uma seção do laboratório não se comportar como o
# texto descreve: ele diz o que está faltando em vez de deixar você adivinhar.
#
set -uo pipefail

CONTAINER="${CASSANDRA_CONTAINER:-cassandra-database}"
FALHAS=0

ok()    { printf '  \033[32m✓\033[0m %s\n' "$1"; }
falha() { printf '  \033[31m✗\033[0m %s\n' "$1"; FALHAS=$((FALHAS + 1)); }
aviso() { printf '  \033[33m!\033[0m %s\n' "$1"; }
titulo(){ printf '\n\033[1m%s\033[0m\n' "$1"; }

cql() { docker exec "$CONTAINER" cqlsh -e "$1" 2>/dev/null; }

# Extrai o valor de um SELECT de uma linha e uma coluna.
valor() { cql "$1" | sed -n '4p' | tr -d ' '; }

titulo "Docker"
if ! command -v docker >/dev/null 2>&1; then
    falha "docker não encontrado no PATH"
    echo; echo "Instale o Docker antes de seguir."; exit 1
fi
ok "docker $(docker --version | sed 's/Docker version //;s/,.*//')"

if ! docker compose version >/dev/null 2>&1; then
    falha "docker compose (v2) não disponível"
else
    ok "docker compose $(docker compose version --short)"
fi

titulo "Container"
ESTADO=$(docker inspect -f '{{.State.Status}}' "$CONTAINER" 2>/dev/null || echo ausente)
case "$ESTADO" in
    running) ok "$CONTAINER está em execução" ;;
    ausente)
        falha "$CONTAINER não existe"
        echo; echo "Suba o ambiente com:  docker compose up -d"; exit 1 ;;
    *)
        falha "$CONTAINER está '$ESTADO'"
        echo; echo "Suba o ambiente com:  docker compose up -d"; exit 1 ;;
esac

SAUDE=$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}sem healthcheck{{end}}' "$CONTAINER" 2>/dev/null)
[ "$SAUDE" = "healthy" ] && ok "healthcheck: healthy" || aviso "healthcheck: $SAUDE (a inicialização leva 1 a 2 minutos)"

titulo "Cassandra"
VERSAO=$(valor "SELECT release_version FROM system.local;")
if [ -z "$VERSAO" ]; then
    falha "o nó não respondeu ao cqlsh"
    echo; echo "Aguarde a inicialização e rode de novo. Para acompanhar:"
    echo "  docker logs -f $CONTAINER"; exit 1
fi
case "$VERSAO" in
    5.*) ok "versão $VERSAO" ;;
    *)   aviso "versão $VERSAO — o laboratório foi escrito para a série 5.0" ;;
esac

# system.peers lista os *outros* nós, por isso o total é ela mais este nó.
VIZINHOS=$(cql "SELECT count(*) FROM system.peers;" | sed -n '4p' | tr -d ' ')
TOTAL=$((${VIZINHOS:-0} + 1))
if [ "$TOTAL" -eq 1 ]; then
    ok "cluster de 1 nó (este laboratório não usa cluster)"
else
    aviso "cluster de $TOTAL nós — o laboratório pressupõe um só"
fi

titulo "Keyspaces"
verifica_keyspace() {
    local keyspace="$1" esperadas="$2" papel="$3"
    local tabelas
    tabelas=$(valor "SELECT count(*) FROM system_schema.tables WHERE keyspace_name='$keyspace';")
    if [ -z "$tabelas" ] || [ "$tabelas" = "0" ]; then
        falha "$keyspace ausente ($papel)"
        return
    fi
    if [ "$tabelas" -eq "$esperadas" ]; then
        ok "$keyspace: $tabelas tabelas ($papel)"
    else
        aviso "$keyspace: $tabelas tabelas, esperadas $esperadas ($papel)"
    fi
}

verifica_keyspace infobarbank 12 "modelagem de dados"
verifica_keyspace ecommerce   11 "trabalho final"

LAB=$(valor "SELECT count(*) FROM system_schema.tables WHERE keyspace_name='lab';")
if [ -n "$LAB" ] && [ "$LAB" != "0" ]; then
    ok "lab: $LAB tabelas (sua bancada de trabalho)"
else
    aviso "lab: ainda não criada — você a cria na Parte I"
fi

titulo "Dados"
CLIENTES=$(valor "SELECT count(*) FROM infobarbank.cliente;")
[ "${CLIENTES:-0}" -gt 0 ] && ok "infobarbank.cliente: $CLIENTES clientes" || falha "infobarbank.cliente vazia"

PEDIDOS=$(valor "SELECT count(*) FROM ecommerce.pedido_detalhe;")
[ "${PEDIDOS:-0}" -gt 0 ] && ok "ecommerce.pedido_detalhe: $PEDIDOS pedidos" || falha "ecommerce.pedido_detalhe vazia"

# As competências são relativas à data em que o ambiente foi criado, por isso
# são descobertas e não fixadas no texto do laboratório.
titulo "Competências disponíveis"
COMP_BANCO=$(cql "SELECT DISTINCT id_cliente, competencia FROM infobarbank.lancamentos_por_periodo;" \
    | grep '2b162060' | awk '{print $3}' | sort | tr '\n' ' ')
COMP_LOJA=$(cql "SELECT DISTINCT id_cliente, competencia FROM ecommerce.pedidos_por_periodo;" \
    | grep 'CLI-000001' | awk '{print $3}' | sort | tr '\n' ' ')
[ -n "$COMP_BANCO" ] && ok "infobarbank, Marivalda (2b162060): $COMP_BANCO" || aviso "nenhuma competência no infobarbank"
[ -n "$COMP_LOJA" ]  && ok "ecommerce, Marivalda (CLI-000001): $COMP_LOJA"  || aviso "nenhuma competência no ecommerce"

titulo "Resultado"
if [ "$FALHAS" -eq 0 ]; then
    printf '  \033[32mAmbiente pronto.\033[0m\n\n'
    exit 0
fi
printf '  \033[31m%d verificação(ões) falharam.\033[0m\n' "$FALHAS"
cat <<'FIM'

  Para recriar o ambiente do zero:

    docker compose down -v
    docker compose up -d

FIM
exit 1
