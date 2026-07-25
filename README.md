# Wide-column com Apache Cassandra 5

Author: Prof. Barbosa<br>
Contact: infobarbosa@gmail.com<br>
Github: [infobarbosa](https://github.com/infobarbosa)

> **Esta branch está em revisão.** O laboratório em uso está na branch `main`.
> Ver o [plano de revisão](#plano-de-revisão) ao final para o que já está pronto.

[Cassandra](https://cassandra.apache.org/) é um banco de dados distribuído com modelo de armazenamento **wide-column**. Neste laboratório você vai construir uma tabela do zero, acompanhar o dado descer até o disco, descobrir o limite de consulta que o Cassandra impõe — e então ver como um sistema real resolve esse limite.

O laboratório inteiro cabe neste arquivo. Os comandos são copy-paste em terminal Linux, na ordem em que aparecem.

---

## O que você vai saber fazer ao final

- Criar keyspaces e escolher o fator de replicação, entendendo o que ele custa em disponibilidade.
- Escrever `CREATE TABLE` cujo `PRIMARY KEY` responde a uma consulta específica, e explicar a diferença entre **partition key** e **clustering key**.
- Prever em qual partição uma linha vai cair, e por que a ordem física dos dados no disco é uma decisão de modelagem.
- Acompanhar o caminho de escrita — commit log, memtable, SSTable, compactação, tombstone — observando os arquivos que o Cassandra cria.
- Ler um modelo físico de verdade e dizer **qual consulta motivou cada tabela**.
- Reconhecer os erros que o Cassandra devolve e saber, para cada um, se a resposta é corrigir a consulta ou modelar outra tabela.
- Consultar o Cassandra a partir de uma aplicação Python, com prepared statements e paginação.

---

## Pré-requisitos

- **Docker** com o plugin `compose` (v2). Nada mais precisa ser instalado: o `cqlsh` e o `nodetool` vêm dentro do container.
- **Python 3** com `venv`, apenas para a Parte III.
- Cerca de **2 GB de RAM** livres e **5 GB de disco**.

Recomendo Linux. Caso não tenha um à disposição, use o **AWS Cloud9** — as instruções estão em [data-engineering-cloud9](https://github.com/infobarbosa/data-engineering-cloud9).

---

## Como o laboratório está organizado

| Parte | Assunto | Keyspace | Tempo |
|---|---|---|---|
| **I** | Fundamentos: do ambiente ao dado no disco | `lab`, criada por você | ~100 min |
| **II** | Modelagem: de sete consultas a doze tabelas | `infobarbank` | ~60 min |
| **III** | A aplicação: o mesmo fluxo em Python | `infobarbank` | ~30 min |
| **IV** | Trabalho final | `ecommerce` | — |

São três keyspaces, com papéis distintos:

- **`lab`** — sua bancada de trabalho. Você a cria na Parte I, erra nela à vontade, e apaga no final.
- **`infobarbank`** — o sistema de um banco digital, já carregado. É o caso de uso da modelagem.
- **`ecommerce`** — uma loja, também já carregada. É o **espelho** do banco: as mesmas convenções de modelagem em outro domínio. É sobre ela que o trabalho final é feito.

Ao longo de todo o laboratório os comandos são executados a partir do host, nunca de dentro do container, usando dois atalhos definidos na primeira seção:

```sh
alias cql='docker exec -it cassandra-database cqlsh -e'
alias nt='docker exec -it cassandra-database nodetool'
```

---

## Índice

**Parte I — Fundamentos**

1. [O ambiente](#1-o-ambiente)
2. [Primeiro contato](#2-primeiro-contato)
3. [Keyspace: onde a replicação é decidida](#3-keyspace-onde-a-replicação-é-decidida)
4. [Sua primeira tabela](#4-sua-primeira-tabela)
5. [Onde o dado mora: partição e token](#5-onde-o-dado-mora-partição-e-token)
6. [Do memtable ao disco](#6-do-memtable-ao-disco)

**Parte II — Modelagem**

7. [Não existe JOIN — existe outra tabela](#7-não-existe-join--existe-outra-tabela)
8. [Chave primária na prática](#8-chave-primária-na-prática)
9. [Cassandra 5: SAI e UCS](#9-cassandra-5-sai-e-ucs)

**Parte III — A aplicação**

10. [O driver Python](#10-o-driver-python)

**Parte IV — Trabalho final**

11. [Enunciado](#11-enunciado)

**Apêndices**

- [A. Busca vetorial](#a-busca-vetorial)
- [B. Encerrando o ambiente](#b-encerrando-o-ambiente)
- [C. Troubleshooting](#c-troubleshooting)
- [D. Nota para o instrutor](#d-nota-para-o-instrutor)

---

## 1. O ambiente

> Em elaboração (fase A1).

## 2. Primeiro contato

> Em elaboração (fase A1).

## 3. Keyspace: onde a replicação é decidida

> Em elaboração (fase A1).

## 4. Sua primeira tabela

> Em elaboração (fase A2).

## 5. Onde o dado mora: partição e token

> Em elaboração (fase A2).

## 6. Do memtable ao disco

> Em elaboração (fase A3).

## 7. Não existe JOIN — existe outra tabela

> Em elaboração (fase A4).

## 8. Chave primária na prática

> Em elaboração (fase A4).

## 9. Cassandra 5: SAI e UCS

> Em elaboração (fase A4).

## 10. O driver Python

> Em elaboração (fase A5).

## 11. Enunciado

> Em elaboração (fase A6).

## A. Busca vetorial

> Em elaboração (fase A6).

## B. Encerrando o ambiente

```sh
docker compose down -v

```

O `-v` remove também o volume de dados. Como as duas keyspaces são recriadas em cerca de 30 segundos no próximo `up`, não há motivo para preservá-las.

## C. Troubleshooting

> Em elaboração (fase A6).

Enquanto isso, para verificar o ambiente:

```sh
bash scripts/check.sh

```

## D. Nota para o instrutor

> Em elaboração (fase A6).

---

## Plano de revisão

Esta branch reformula o laboratório, que antes estava dividido em sete subdiretórios, em um arquivo único e com um fio condutor só. O que mudou de fato:

| | |
|---|---|
| **Um único jeito de digitar** | Antes, o aluno entrava no container na seção 2, saía na 6 e voltava na 7. Agora tudo roda do host, via `alias`. |
| **Um único enredo** | Antes eram quatro keyspaces sem relação declarada (`ks001`, `infobarbank`, `ecommerce`, `infobarbank5`). Agora são três, com papéis explícitos. |
| **Cluster sai** | Tokens, réplicas e disponibilidade ganham repositório próprio. O que dava para manter em um nó — fator de replicação e consistency level — ficou. |
| **Cassandra 5 entra** | O laboratório se chamava `cassandra5` e não usava nenhum recurso da versão 5. Entram SAI, UCS e busca vetorial. |
| **Modelagem é o centro** | O modelo do `infobarbank` deixa de ser cenário e passa a ser o objeto: cada uma das doze tabelas é lida a partir da consulta que a motivou. |

Fases: **A0** estrutura (feita) · A1 seções 1–3 · A2 seções 4–5 · A3 seção 6 · A4 seções 7–9 · A5 seção 10 · A6 seção 11 e apêndices · A7 execução completa em ambiente limpo, com todos os outputs regerados.

### Mapa do que saiu

| Antes | Agora |
|---|---|
| `01-Cassandra-Start/` | seção 1 |
| `02-cqlsh/` | seção 2 |
| `03-Keyspaces/` | seção 3 |
| `04-Tables/` | seções 4 e 5 |
| `05-Datafiles/` | seção 6 |
| `06-Cluster/` | repositório próprio, a ser criado |
| `07-Cassandra-Driver/` | seção 10 |
| `ecommerce-samples.md` | seção 11 |
| `assets/scripts/standalone/compose.yaml` | `compose.yaml`, na raiz |
| `assets/scripts/cluster/*.yaml` | repositório de cluster |
