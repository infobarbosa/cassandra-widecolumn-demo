# App infobarBank

Emulador do aplicativo do infobarBank para a seção 9.j do laboratório. As três telas do app (início, extrato e detalhe) só funcionam com as consultas CQL que o aluno escreve para Q1 a Q7.

## Como subir

No terminal do code-server:

```sh
python3 app/servidor.py
```

Depois abra `http://<IP-PUBLICO>:8080/proxy/8000/`. O app escuta só em `127.0.0.1:8000`; o acesso passa pelo proxy do próprio code-server, então nenhuma porta nova precisa ser aberta na AWS. Em execução local, `http://localhost:8080/proxy/8000/`.

Opções:

| Opção | Efeito |
|---|---|
| `--professor` | mostra o botão **Solução**, que preenche a consulta de referência |
| `--porta N` | usa outra porta (o endereço passa a ser `/proxy/N/`) |

## O que o app faz

- **Só leitura.** Aceita apenas um `SELECT` por vez, na keyspace `infobarbank`.
- **Parâmetros por tela.** Cada consulta só enxerga o que a tela tem em mãos naquele momento (`:id_cliente`, `:competencia`, `:id_produto`, `:tipo_operacao`, `:id_lancamento`), e executa como prepared statement.
- **Confere o resultado.** O servidor roda também a consulta de referência e compara, nas colunas que a tela usa: linhas, quantidade e ordem.
- **Mede o custo.** Cada execução usa `TRACING` e resume em partições lidas, faixas de token percorridas e linhas lidas. Varredura e `ALLOW FILTERING` aparecem em âmbar.
- **Regras da aplicação.** A Q3 sem lançamentos aprovados no mês repete a consulta no mês anterior (regra Q3.1) e avisa que fez isso.
- O progresso e as consultas de cada aluno ficam no navegador dele (`localStorage`).

## Arquivos

| Arquivo | Conteúdo |
|---|---|
| `servidor.py` | servidor HTTP (biblioteca padrão do Python) e acesso ao Cassandra (driver já instalado na imagem); definição das consultas Q1 a Q7, dicas e soluções de referência |
| `web/index.html` | a interface: o celular à esquerda, o painel de CQL à direita (HTML, CSS e JavaScript, sem dependências) |
