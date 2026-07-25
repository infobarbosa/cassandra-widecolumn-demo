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

### Convenções

Nem todo bloco de código é para ser executado. Há três tipos:

| | |
|---|---|
| ```sh``` com prompt limpo | **Execute.** É o caminho do laboratório. |
| **Não execute** | Exemplo para leitura: descreve um ambiente que não é este — um cluster com vários datacenters, por exemplo. Rodar aqui só devolve erro de configuração. |
| **Provoque este erro** | Comando que falha de propósito, e a mensagem de erro é a lição. Estes você deve executar. |

A diferença entre os dois últimos importa: o Cassandra recusa consultas mal modeladas com mensagens muito informativas, e aprender a lê-las é metade do trabalho. O que não vale a pena é executar comandos que só falham porque o ambiente de estudo tem um nó.

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

Baixe o arquivo do Docker Compose:

```sh
wget https://raw.githubusercontent.com/infobarbosa/cassandra5-demo/revisao-julho2026/compose.yaml

```

Veja o que ele descreve — um nó Cassandra e dois containers de carga, um por keyspace:

```sh
cat compose.yaml

```

Suba o ambiente:

```sh
docker compose up -d

```

```
 Network cassandra5-demo_default Created
 Container cassandra-database Creating
 Container cassandra-database Started
 Container cassandra-database Waiting
 Container cassandra-database Healthy
 Container cassandra-init-ecommerce Starting
 Container cassandra-init-infobarbank Starting
 Container cassandra-init-ecommerce Started
 Container cassandra-init-infobarbank Started
```

Repare na linha `Waiting`: o comando só retorna depois que o Cassandra passa no healthcheck, porque os containers de carga declaram `depends_on: service_healthy`. Isso leva cerca de **um minuto**. Depois disso, a carga das duas keyspaces leva outros **30 segundos** — e essa parte roda em segundo plano, então o prompt volta antes de terminar.

Para acompanhar a carga:

```sh
docker compose logs -f cassandra-init-ecommerce

```

```
cassandra-init-ecommerce  | Carregadas 11959 linhas em pedidos_por_produto (3.3s).
cassandra-init-ecommerce  | Keyspace ecommerce pronta em 25.8s. Cliente-âncora: CLI-000001.
```

> Para sair do `logs -f`, digite `Control+C` uma única vez.

### O que foi criado

```sh
docker ps -a

```

```
NAMES                        IMAGE                                        STATUS
cassandra-init-ecommerce     ...cassandra-gerador-esquema-ecommerce:2.0   Exited (0) 4 minutes ago
cassandra-init-infobarbank   ...cassandra-gerador-esquema-infobarbank:1.0 Exited (0) 4 minutes ago
cassandra-database           cassandra:5.0.8                              Up 6 minutes (healthy)
```

Os dois containers de carga aparecem como `Exited (0)`, e **é isso que se espera deles**: cada um cria a sua keyspace, insere os dados e termina. `Exited (0)` significa que terminaram sem erro. Só o `cassandra-database` fica no ar.

### Verificando o ambiente

```sh
curl -sS https://raw.githubusercontent.com/infobarbosa/cassandra5-demo/revisao-julho2026/scripts/check.sh | bash

```

```
Keyspaces
  ✓ infobarbank: 12 tabelas (modelagem de dados)
  ✓ ecommerce: 11 tabelas (trabalho final)
  ! lab: ainda não criada — você a cria na Parte I

Dados
  ✓ infobarbank.cliente: 50 clientes
  ✓ ecommerce.pedido_detalhe: 11959 pedidos

Resultado
  Ambiente pronto.
```

Guarde este comando. Sempre que uma seção não se comportar como o texto descreve, rode-o: ele diz o que está faltando em vez de deixar você adivinhar.

### Dois atalhos

O `cqlsh` e o `nodetool` estão dentro do container, mas você **não vai entrar nele em momento algum** neste laboratório. Em vez disso, defina dois atalhos:

```sh
alias cql='docker exec -it cassandra-database cqlsh -e'
alias nt='docker exec -it cassandra-database nodetool'

```

Teste:

```sh
cql "SELECT release_version FROM system.local;"

```

```
 release_version
-----------------
           5.0.8

(1 rows)
```

> Os `alias` valem apenas para **este terminal**. Se abrir outro, ou fechar e reabrir, defina-os de novo. Se algum comando adiante devolver `cql: command not found`, é isso que aconteceu.

**→ Próxima seção.** O ambiente está no ar e duas keyspaces já foram carregadas por outra pessoa. Antes de criar as suas, vale saber o que exatamente está rodando aí.

---

## 2. Primeiro contato

### O que existe no nó

```sh
cql "DESCRIBE KEYSPACES;"

```

```
ecommerce    system_auth         system_traces
infobarbank  system_distributed  system_views
system       system_schema       system_virtual_schema
```

Duas keyspaces são do curso — `infobarbank` e `ecommerce`. As outras seis são do próprio Cassandra: `system_schema` guarda a definição das suas tabelas, `system_auth` os usuários, `system_views` e `system_virtual_schema` expõem métricas internas como se fossem tabelas. Você vai consultar algumas delas ao longo do laboratório.

### Quem é este nó

```sh
cql "SELECT cluster_name, release_version, cql_version, data_center, rack FROM system.local;"

```

```
 cluster_name   | release_version | cql_version | data_center | rack
----------------+-----------------+-------------+-------------+------
 infobarbosainc |           5.0.8 |       3.4.7 | datacenter1 | RAC1

(1 rows)
```

`system.local` é a tabela em que o nó guarda o que sabe sobre si mesmo. Note que ele se declara em um **datacenter** (`datacenter1`) e em um **rack** (`RAC1`) — nomes que vieram do `compose.yaml`. Um nó só, mas já se apresentando com endereço na topologia. Isso vai importar na próxima seção.

### O ponto de vista do operador

```sh
nt status

```

```
Datacenter: datacenter1
=======================
Status=Up/Down
|/ State=Normal/Leaving/Joining/Moving
--  Address     Load        Tokens  Owns (effective)  Host ID                               Rack
UN  172.21.0.2  111.45 KiB  16      100.0%            15ae1f2b-82f9-4753-afaa-b21bc7813e4a  RAC1
```

O `Host ID`, o `Address` e o `Load` do seu ambiente serão diferentes dos que aparecem aqui — são gerados na criação do container. O que deve coincidir é o resto.

`UN` é a leitura mais frequente do dia a dia de quem opera Cassandra: **U**p e **N**ormal. A legenda logo acima do resultado explica as combinações possíveis — um nó entrando no cluster, por exemplo, aparece como `UJ` (Up, Joining).

Duas colunas para guardar: `Owns` diz que este nó responde por 100% dos dados, o que é esperado quando há um nó só; e `Tokens 16` diz que ele ocupa dezesseis posições no anel de tokens. O que são esses tokens é assunto da seção 5.

> Se o `nt status` devolver `Server is not initialized yet, cannot run nodetool`, o serviço ainda está subindo. Espere alguns segundos e repita.

### Sobre o `cqlsh`

O `cqlsh` é a linha de comando do Cassandra, e fala **CQL** (Cassandra Query Language). Ele tem dois modos:

- **Não interativo**, com `-e` ou `--execute`: executa um comando e sai. É o que o nosso `alias cql` faz, e é a forma usada em scripts de manutenção.
- **Interativo**, sem parâmetro: abre um prompt `cqlsh>` que fica aguardando comandos.

Este laboratório usa o modo não interativo do começo ao fim — assim nenhum comando depende de você estar "dentro" de algum lugar. Se quiser conhecer o modo interativo:

```sh
docker exec -it cassandra-database cqlsh

```

```
ATTENTION: All commands will be saved to history file: /root/.cassandra/cqlsh_history
This may include sensitive information such as passwords.
[...]

Connected to infobarbosainc at 127.0.0.1:9042
[cqlsh 6.2.0 | Cassandra 5.0.8 | CQL spec 3.4.7 | Native protocol v5]
Use HELP for help.
cqlsh>
```

O aviso do topo é normal: o `cqlsh` grava histórico de comandos, e o Cassandra 5 passou a alertar sobre isso porque o histórico pode conter senhas. Não é erro.

Para sair, digite `exit` ou `Control+D`.

**→ Próxima seção.** Você viu duas keyspaces prontas. Agora vai criar a sua — e a primeira decisão que o Cassandra pede não é sobre tabelas, é sobre quantas cópias do dado você quer.

---

## 3. Keyspace: onde a replicação é decidida

Uma `keyspace` é o repositório lógico das tabelas. Em outros bancos equivale a um *schema* ou *database*.

O papel importante dela, porém, é **físico**: é na keyspace que se define como o dado será replicado. Essa é a decisão que determina o que acontece com a sua aplicação quando um nó cai.

Crie a sua:

```sh
cql "
CREATE KEYSPACE lab
    WITH REPLICATION = {
        'class': 'NetworkTopologyStrategy',
        'datacenter1': 1
    };"

```

Conferindo:

```sh
cql "DESCRIBE KEYSPACE lab;"

```

```
CREATE KEYSPACE lab WITH replication = {'class': 'NetworkTopologyStrategy', 'datacenter1': '1'}  AND durable_writes = true;
```

### As duas estratégias

```
CREATE KEYSPACE [IF NOT EXISTS] nome_da_keyspace
   WITH REPLICATION = {
      'class' : 'SimpleStrategy', 'replication_factor' : N
    | 'class' : 'NetworkTopologyStrategy', 'nome_do_dc' : N [, ...]
   }
   [AND DURABLE_WRITES = true|false] ;
```

A `SimpleStrategy` distribui as réplicas ignorando a topologia: para ela não existem datacenters nem racks. Funciona, inclusive nesta versão, mas só faz sentido em ambiente de estudo com um nó.

Usamos `NetworkTopologyStrategy` porque é ela que permite dizer **quantas cópias em cada datacenter** — e porque é coerente com o `compose.yaml`, que configurou o nó com `GossipingPropertyFileSnitch`, `CASSANDRA_DC=datacenter1` e `CASSANDRA_RACK=RAC1`. É também a estratégia usada pelas duas keyspaces do curso.

Os nomes dos datacenters não são etiquetas livres: precisam existir na topologia declarada pelo administrador. Nomear um datacenter inexistente é recusado:

> **Não execute.** Exemplo para leitura.

```
CREATE KEYSPACE lab_erro
  WITH REPLICATION = { 'class':'NetworkTopologyStrategy', 'dc-brasil':1 };

ConfigurationException: Unrecognized strategy option {dc-brasil}
passed to NetworkTopologyStrategy for keyspace lab_erro
```

Guarde esse comportamento ao ler os exemplos a seguir: é por isso que nenhum deles roda aqui.

### Exemplos de produção

Os casos abaixo são para debate em sala.

> **Não execute.** Os três descrevem topologias com vários datacenters. Neste ambiente de um nó, todos devolveriam o `ConfigurationException` acima.

Distribuição geográfica em três países — três cópias no Brasil, três nos Estados Unidos, duas na Alemanha:

```
CREATE KEYSPACE ks001
  WITH REPLICATION = {
   'class'  : 'NetworkTopologyStrategy',
   'bra-sp' : 3 , // São Paulo/Brasil
   'usa-ny' : 3 , // Nova Iorque/Estados Unidos
   'deu-fr' : 2   // Frankfurt/Alemanha
  };
```

Uma região só, mas com quatro instalações em duas zonas de disponibilidade, segmentadas por propósito. Três cópias transacionais em cada zona (seis no total) e uma cópia analítica em cada (duas no total) — o mesmo cluster servindo OLTP e OLAP sem que a carga analítica pese nos nós transacionais:

```
CREATE KEYSPACE ks001
  WITH REPLICATION = {
   'class'  : 'NetworkTopologyStrategy',
   'bra-sp-az1-oltp' : 3 , // Transacional AZ1 em São Paulo/Brasil
   'bra-sp-az2-oltp' : 3 , // Transacional AZ2 em São Paulo/Brasil
   'bra-sp-az1-olap' : 1 , // Analítico AZ1 em São Paulo/Brasil
   'bra-sp-az2-olap' : 1   // Analítico AZ2 em São Paulo/Brasil
  };
```

O comando a seguir entrega a mesma quantidade de cópias do anterior, mas a distribuição física depende de como o administrador declarou a topologia. É um tópico mais avançado, para discutirmos em sala:

```
CREATE KEYSPACE ks001
  WITH REPLICATION = {
   'class'  : 'NetworkTopologyStrategy',
   'bra-sp-oltp' : 6,
   'bra-sp-olap' : 2
  };
```

Vale também segmentar keyspaces por assunto — pedidos, faturamento, contábil — ou uma por microsserviço. A segmentação facilita a administração e permite política de replicação diferente para cada conjunto de dados.

**→ Próxima seção.** Você escolheu uma cópia do dado. Essa escolha tem consequência direta sobre disponibilidade, e dá para senti-la mesmo com um nó só — mas para isso precisamos de dados. Vamos criar a primeira tabela.

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

Fases: **A0** estrutura · **A1** seções 1–3 (feitas) · A2 seções 4–5 · A3 seção 6 · A4 seções 7–9 · A5 seção 10 · A6 seção 11 e apêndices · A7 execução completa em ambiente limpo, com todos os outputs regerados.

### Pendências da revisão

- As URLs de `wget` e `curl` apontam para a branch `revisao-julho2026`, para que ela seja executável antes do merge. **No merge, trocar por `main`.**
- As imagens `ghcr.io/infobarbosa/cassandra-gerador-esquema-{infobarbank,ecommerce}` precisam ser publicadas e tornadas públicas. Enquanto isso, o `compose.yaml` só funciona em máquina que as tenha construído localmente.
- O teste prático de fator de replicação contra consistency level ficou no fim da seção 4, e não na 3: ele precisa de dados na tabela. A seção 3 anuncia, a 4 executa.

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
