"""
dashboard.py — Interface visual do bot em Streamlit.

Para rodar:
    streamlit run dashboard.py

CONCEITO: Como o Streamlit funciona
─────────────────────────────────────
O Streamlit re-executa o arquivo inteiro do topo ao fundo a cada
interação do usuário (clique de botão, refresh automático, etc).

Isso é diferente de frameworks como Flask onde você define "rotas".
Pense assim: cada atualização é como rodar `python dashboard.py` de
novo — mas o Streamlit é inteligente e só re-renderiza o que mudou.

A ORDEM das chamadas importa: o que você escreve primeiro aparece
primeiro na página. Pense nisso como "escrever um script de cima
para baixo, e o Streamlit monta a tela nessa ordem".
"""

import json
import re
import time
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

# ─────────────────────────────────────────────────────────────
# CONFIGURAÇÃO DA PÁGINA
#
# CONCEITO: set_page_config()
# Deve ser a PRIMEIRA chamada Streamlit do arquivo — sem exceções.
# Define o título da aba do browser, ícone, e se o layout usa
# a largura total da tela ("wide") ou fica centralizado ("centered").
# ─────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Base Yield Lab",
    page_icon="⚡",
    layout="wide",
)

# ─────────────────────────────────────────────────────────────
# CAMINHOS DOS ARQUIVOS
#
# CONCEITO: Path(__file__).parent
# __file__ é o caminho absoluto do script atual (dashboard.py).
# .parent sobe um nível para a pasta que contém o script.
# Assim, os arquivos são sempre encontrados relativo ao projeto,
# independente de onde você rode o comando "streamlit run".
# ─────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).parent
BOT_LOG = PROJECT_ROOT / "bot.log"
HISTORY_FILE = PROJECT_ROOT / "bot_history.json"


# ─────────────────────────────────────────────────────────────
# FUNÇÕES DE LEITURA DE DADOS
#
# CONCEITO: Separar dados da apresentação
# Funções que leem arquivos ficam separadas do código de UI.
# Isso é o mesmo princípio do "Model vs View" em MVC.
# Benefício: se amanhã você quiser ler de um banco de dados em
# vez de arquivos, só muda aqui, sem tocar no código visual.
# ─────────────────────────────────────────────────────────────


def load_history() -> dict:
    """Lê bot_history.json. Retorna dict vazio se não existir."""
    if not HISTORY_FILE.exists():
        return {}
    try:
        return json.loads(HISTORY_FILE.read_text())
    except json.JSONDecodeError:
        return {}


def parse_log(n_lines: int = 500) -> list[dict]:
    """
    Lê as últimas n_lines do bot.log e retorna eventos parseados.

    CONCEITO: Regex (Expressões Regulares)
    ───────────────────────────────────────
    Regex é uma mini-linguagem para encontrar padrões em texto.
    O bot.log tem linhas assim:
        2026-02-24 15:30:00 [INFO] bot: INICIO DO CICLO

    O padrão que usamos:
        r"^(\\d{4}-\\d{2}-\\d{2} \\d{2}:\\d{2}:\\d{2}) \\[(\\w+)\\] [\\w.]+: (.+)$"

    Decodificando:
        ^               → início da linha
        (\\d{4}-...)    → grupo 1: timestamp (4 dígitos, traço, 2 dígitos...)
        \\[(\\w+)\\]    → grupo 2: nível de log entre colchetes [INFO]
        [\\w.]+         → nome do módulo (bot, listener, etc) — não capturado
        (.+)$           → grupo 3: o restante é a mensagem

    re.compile() "compila" o padrão para usar várias vezes com eficiência.
    m.groups() retorna os grupos capturados em ordem.
    """
    if not BOT_LOG.exists():
        return []

    lines = BOT_LOG.read_text(encoding="utf-8", errors="ignore").splitlines()
    lines = lines[-n_lines:]

    pattern = re.compile(
        r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) \[(\w+)\] [\w.]+: (.+)$"
    )

    events = []
    for line in lines:
        m = pattern.match(line)
        if m:
            timestamp_str, level, message = m.groups()
            events.append({"timestamp": timestamp_str, "level": level, "message": message})

    return events


def extract_apy_history(events: list[dict]) -> pd.DataFrame:
    """
    Constrói série temporal de APY a partir dos eventos do log.

    CONCEITO: Série temporal sem banco de dados
    ────────────────────────────────────────────
    A cada ciclo, o bot loga uma linha com os APYs atuais.
    Ao parsear TODAS essas linhas, reconstituímos o histórico
    sem precisar de banco de dados. O arquivo bot.log É o banco.

    Formato da linha que buscamos:
        "Aave: 3.2000% APY, 49.50 USDC | Compound: 5.8000% APY, 0.00 USDC"

    CONCEITO: pd.DataFrame
    Um DataFrame do pandas é como uma planilha em memória.
    Cada dict na lista vira uma linha; as chaves viram colunas.
    O Streamlit sabe renderizar DataFrames nativamente como
    tabelas e gráficos.
    """
    apy_pattern = re.compile(
        r"Aave: ([\d.]+)% APY.*?Compound: ([\d.]+)% APY"
    )

    rows = []
    for event in events:
        m = apy_pattern.search(event["message"])
        if m:
            rows.append({
                "Timestamp": event["timestamp"],
                "Aave (%)": float(m.group(1)),
                "Compound (%)": float(m.group(2)),
            })

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    df = df.set_index("Timestamp")
    return df


def get_last_state(events: list[dict]) -> dict:
    """
    Extrai o estado mais recente do bot varrendo o log de trás para frente.

    CONCEITO: "Leitura regressiva" do log
    ──────────────────────────────────────
    O log cresce para baixo (mais recente no final). Iteramos
    reversed(events) para pegar o estado mais recente primeiro.
    Paramos assim que tivermos todos os campos que precisamos.
    """
    state = {
        "aave_apy": None,
        "compound_apy": None,
        "aave_usdc": None,
        "compound_usdc": None,
        "wallet_usdc": None,
        "wallet_eth": None,
        "gas_gwei": None,
        "gas_usd": None,
        "last_decision": None,
        "last_cycle": None,
        "mode": None,
    }

    # Padrões para cada tipo de linha do log
    apy_pattern = re.compile(
        r"Aave: ([\d.]+)% APY, ([\d.]+) USDC \| Compound: ([\d.]+)% APY, ([\d.]+) USDC"
    )
    wallet_pattern = re.compile(
        r"Wallet: ([\d.]+) USDC, ([\d.]+) ETH \| Gas: ([\d.]+) gwei \(\$([\d.]+)\)"
    )
    mode_pattern = re.compile(r"Bot iniciando em modo: (.+)")
    decision_pattern = re.compile(r"^(DECISAO|ALERTA|FIREWALL|EXECUCAO): (.+)$")

    for event in reversed(events):
        msg = event["message"]

        if state["aave_apy"] is None:
            m = apy_pattern.search(msg)
            if m:
                state["aave_apy"] = float(m.group(1))
                state["aave_usdc"] = float(m.group(2))
                state["compound_apy"] = float(m.group(3))
                state["compound_usdc"] = float(m.group(4))
                state["last_cycle"] = event["timestamp"]

        if state["wallet_usdc"] is None:
            m = wallet_pattern.search(msg)
            if m:
                state["wallet_usdc"] = float(m.group(1))
                state["wallet_eth"] = float(m.group(2))
                state["gas_gwei"] = float(m.group(3))
                state["gas_usd"] = float(m.group(4))

        if state["mode"] is None:
            m = mode_pattern.search(msg)
            if m:
                state["mode"] = m.group(1).strip()

        if state["last_decision"] is None:
            m = decision_pattern.search(msg)
            if m:
                state["last_decision"] = f"{m.group(1)}: {m.group(2)}"

        # Parar cedo se já temos tudo
        if all(v is not None for v in state.values()):
            break

    return state


# ─────────────────────────────────────────────────────────────
# CARREGAR DADOS
#
# CONCEITO: Por que carregar antes de renderizar?
# Se você carregar os dados no meio da página, parte da UI aparece
# antes de ter os dados prontos, causando "flash". Carregando tudo
# aqui no topo, a página sempre renderiza com dados completos.
# ─────────────────────────────────────────────────────────────
events = parse_log(500)
history = load_history()
state = get_last_state(events)
apy_df = extract_apy_history(events)


# ─────────────────────────────────────────────────────────────
# CABEÇALHO
#
# CONCEITO: st.columns()
# Divide a linha horizontal em colunas. A lista define as proporções:
#   st.columns([4, 1]) → primeira coluna ocupa 80%, segunda 20%
# Você acessa cada coluna com "with col:" e tudo dentro do bloco
# aparece naquela coluna.
# ─────────────────────────────────────────────────────────────
col_title, col_controls = st.columns([4, 1])

with col_title:
    mode = state["mode"] or "Aguardando primeiro ciclo..."
    st.title(f"Base Yield Lab — {mode}")
    if state["last_cycle"]:
        st.caption(f"Ultimo ciclo registrado: {state['last_cycle']}")
    else:
        st.caption("Nenhum dado ainda. Rode `python main.py` para iniciar o bot.")

with col_controls:
    # CONCEITO: st.toggle()
    # Um botão liga/desliga. Retorna True ou False.
    # st.button() retorna True apenas no ciclo em que é clicado.
    # st.rerun() re-executa o script inteiro imediatamente.
    auto_refresh = st.toggle("Auto-refresh (10s)", value=False)
    if st.button("Atualizar agora", use_container_width=True):
        st.rerun()

st.divider()

# ─────────────────────────────────────────────────────────────
# LINHA 1: MÉTRICAS DE APY E CAPITAL
#
# CONCEITO: st.metric()
# Exibe um card com:
#   label  → título do card
#   value  → valor principal (grande)
#   delta  → variação (pequeno, verde se positivo, vermelho se negativo)
#   help   → tooltip ao passar o mouse no "?"
#
# O delta é usado aqui para mostrar a diferença de APY entre os
# protocolos — te diz na hora qual está pagando mais.
# ─────────────────────────────────────────────────────────────
col1, col2, col3, col4 = st.columns(4)

with col1:
    value = f"{state['aave_apy']:.2f}%" if state["aave_apy"] is not None else "N/A"
    st.metric(
        label="Aave V3 APY",
        value=value,
        help="Taxa de rendimento anual atual do USDC depositado no Aave V3 na Base",
    )

with col2:
    value = f"{state['compound_apy']:.2f}%" if state["compound_apy"] is not None else "N/A"

    # Delta: quanto Compound paga a MAIS ou a MENOS que Aave
    # Se Compound > Aave → delta positivo → aparece verde (bom!)
    # Se Compound < Aave → delta negativo → aparece vermelho
    delta = None
    if state["aave_apy"] is not None and state["compound_apy"] is not None:
        diff = state["compound_apy"] - state["aave_apy"]
        delta = f"{diff:+.2f}% vs Aave"

    st.metric(
        label="Compound III APY",
        value=value,
        delta=delta,
        help="Taxa de rendimento anual atual do USDC depositado no Compound III na Base",
    )

with col3:
    if state["aave_apy"] is not None and state["compound_apy"] is not None:
        if state["aave_apy"] >= state["compound_apy"]:
            best_name = "Aave V3"
            best_apy = state["aave_apy"]
        else:
            best_name = "Compound III"
            best_apy = state["compound_apy"]
        st.metric(
            label="Melhor Protocolo Agora",
            value=best_name,
            delta=f"{best_apy:.2f}% APY",
        )
    else:
        st.metric(label="Melhor Protocolo Agora", value="N/A")

with col4:
    total = 0.0
    for key in ("aave_usdc", "compound_usdc", "wallet_usdc"):
        if state[key] is not None:
            total += state[key]

    value = f"$ {total:.2f} USDC" if total > 0 else "N/A"
    st.metric(
        label="Capital Total",
        value=value,
        help="Soma de: USDC na wallet + depositado no Aave + depositado no Compound",
    )

# ─────────────────────────────────────────────────────────────
# LINHA 2: WALLET E GAS
# ─────────────────────────────────────────────────────────────
col5, col6, col7, col8 = st.columns(4)

with col5:
    value = f"$ {state['wallet_usdc']:.2f}" if state["wallet_usdc"] is not None else "N/A"
    st.metric(
        label="USDC na Wallet",
        value=value,
        help="USDC livre na wallet do bot, ainda nao depositado em nenhum protocolo",
    )

with col6:
    value = f"{state['wallet_eth']:.6f} ETH" if state["wallet_eth"] is not None else "N/A"

    # CONCEITO: delta_color="inverse"
    # Por padrão, delta verde = bom, vermelho = ruim.
    # "inverse" inverte: vermelho = bom, verde = ruim.
    # Aqui: ETH baixo É ruim (bot não consegue pagar gas), então
    # se ETH está baixo (delta negativo), queremos vermelho — inverse faz isso.
    eth_warn = None
    eth_color = "normal"
    if state["wallet_eth"] is not None and state["wallet_eth"] < 0.0001:
        eth_warn = "CRITICO: recarregar ETH!"
        eth_color = "inverse"

    st.metric(
        label="ETH para Gas",
        value=value,
        delta=eth_warn,
        delta_color=eth_color,
        help="ETH disponivel para pagar gas. Abaixo de 0.0001 ETH o bot para de operar",
    )

with col7:
    value = f"{state['gas_gwei']:.4f} gwei" if state["gas_gwei"] is not None else "N/A"
    sub = f"(~$ {state['gas_usd']:.4f} por operação)" if state["gas_usd"] is not None else ""
    st.metric(
        label="Gas Price Atual",
        value=value,
        help=f"Gas price na rede Base agora. Custo estimado de uma operacao completa: {sub}",
    )

with col8:
    moves = history.get("total_moves_24h", "N/A")
    gas_spent = history.get("total_gas_spent_24h_usd")
    delta_gas = f"$ {gas_spent:.4f} em gas" if gas_spent else None
    st.metric(
        label="Movimentacoes (24h)",
        value=str(moves),
        delta=delta_gas,
        help="Quantas vezes o bot moveu fundos nas ultimas 24 horas e quanto gastou em gas",
    )

st.divider()

# ─────────────────────────────────────────────────────────────
# POSIÇÕES ATUAIS (lado a lado)
#
# CONCEITO: st.container(border=True)
# Cria uma "caixa" visual com borda ao redor do conteúdo.
# Agrupa métricas relacionadas visualmente.
# ─────────────────────────────────────────────────────────────
st.subheader("Posicoes Atuais")
col_aave, col_compound, col_wallet = st.columns(3)

with col_aave:
    with st.container(border=True):
        aave_dep = state["aave_usdc"] or 0.0
        aave_apy = state["aave_apy"] or 0.0
        st.markdown("**Aave V3**")
        st.metric("Depositado", f"$ {aave_dep:.2f} USDC")
        rendimento = aave_dep * aave_apy / 100
        st.caption(f"Rendimento anual estimado: $ {rendimento:.2f}")
        st.caption(f"APY: {aave_apy:.4f}%")

with col_compound:
    with st.container(border=True):
        comp_dep = state["compound_usdc"] or 0.0
        comp_apy = state["compound_apy"] or 0.0
        st.markdown("**Compound III**")
        st.metric("Depositado", f"$ {comp_dep:.2f} USDC")
        rendimento = comp_dep * comp_apy / 100
        st.caption(f"Rendimento anual estimado: $ {rendimento:.2f}")
        st.caption(f"APY: {comp_apy:.4f}%")

with col_wallet:
    with st.container(border=True):
        wallet_usdc = state["wallet_usdc"] or 0.0
        st.markdown("**Wallet (livre)**")
        st.metric("Disponivel", f"$ {wallet_usdc:.2f} USDC")
        st.caption("Nao rende. Capital aqui deveria ser depositado.")
        last_move = history.get("last_move_action", "Nenhum")
        st.caption(f"Ultimo move: {last_move}")

st.divider()

# ─────────────────────────────────────────────────────────────
# GRÁFICO DE APY AO LONGO DO TEMPO
#
# CONCEITO: st.line_chart()
# Recebe um DataFrame do pandas onde:
#   - o índice vira o eixo X
#   - cada coluna vira uma linha no gráfico
#   - o parâmetro color define as cores (lista hex, uma por coluna)
#
# CONCEITO: Por que pandas aqui?
# st.line_chart() aceita listas e dicts simples, mas o pandas
# dá controle fino sobre índices, colunas nomeadas, e tipos.
# O Streamlit e pandas foram feitos para trabalhar juntos.
# ─────────────────────────────────────────────────────────────
st.subheader("Historico de APY")

if not apy_df.empty:
    st.line_chart(
        apy_df,
        color=["#FF6B6B", "#4ECDC4"],  # vermelho para Aave, verde-água para Compound
    )
    n_ciclos = len(apy_df)
    st.caption(
        f"{n_ciclos} ciclos registrados. "
        f"Cada ponto = 1 ciclo de {300 // 60} minutos do bot."
    )
else:
    # CONCEITO: st.info() / st.warning() / st.error() / st.success()
    # Caixas coloridas com ícone para comunicar status:
    #   info    → azul (neutro)
    #   warning → amarelo (atenção)
    #   error   → vermelho (problema)
    #   success → verde (ok)
    st.info(
        "Nenhum dado de historico ainda. "
        "O grafico aparece automaticamente apos o bot completar alguns ciclos."
    )

st.divider()

# ─────────────────────────────────────────────────────────────
# LOG DE DECISÕES
#
# CONCEITO: Colorir logs por tipo
# Usamos st.error/warning/success/text para dar cor diferente
# dependendo do tipo de evento, facilitando a leitura visual.
# ─────────────────────────────────────────────────────────────
st.subheader("Log de Eventos Recentes")

if events:
    # Últimos 30, mais recente no topo
    recent = list(reversed(events[-30:]))

    for event in recent:
        level = event["level"]
        msg = event["message"]
        ts = event["timestamp"]
        line = f"`{ts}` — {msg}"

        if level == "ERROR" or "FIREWALL BLOQUEOU" in msg:
            st.error(line)
        elif level == "WARNING" or "ALERTA" in msg:
            st.warning(line)
        elif "DECISAO: MOVE" in msg or "EXECUCAO: SUCCESS" in msg:
            st.success(line)
        elif "DECISAO: HOLD" in msg:
            # CONCEITO: st.text() vs st.markdown()
            # st.text() renderiza texto simples sem processamento.
            # st.markdown() interpreta # para títulos, ** para negrito, etc.
            st.text(f"{ts}  {msg}")
        elif "INICIO DO CICLO" in msg:
            st.markdown(f"---\n`{ts}` — **{msg}**")
        else:
            st.text(f"{ts}  {msg}")
else:
    st.info("bot.log nao encontrado. Rode o bot para ver eventos aqui.")

st.divider()

# ─────────────────────────────────────────────────────────────
# SEÇÃO COLAPSÁVEL: DADOS BRUTOS
#
# CONCEITO: st.expander()
# Seção que começa fechada. O usuário clica para expandir.
# Útil para informações avançadas que não precisam estar sempre
# visíveis e que polulariam a tela se sempre abertas.
# ─────────────────────────────────────────────────────────────
with st.expander("Dados brutos (bot_history.json)"):
    if history:
        display = dict(history)
        # Converter timestamp Unix → formato legível para humanos
        ts_raw = display.get("last_move_timestamp")
        if ts_raw:
            display["last_move_timestamp_legivel"] = datetime.fromtimestamp(ts_raw).strftime(
                "%Y-%m-%d %H:%M:%S"
            )
        # CONCEITO: st.json()
        # Renderiza um dict Python como JSON formatado e interativo
        # (com abas para colapsar objetos aninhados).
        st.json(display)
    else:
        st.info("bot_history.json nao encontrado ainda.")

with st.expander("Tabela de APY historico (DataFrame bruto)"):
    if not apy_df.empty:
        # CONCEITO: st.dataframe()
        # Renderiza um DataFrame como tabela interativa:
        # clique nas colunas para ordenar, scroll horizontal e vertical.
        # use_container_width=True expande para a largura disponível.
        st.dataframe(apy_df, use_container_width=True)
    else:
        st.info("Sem dados ainda.")

# ─────────────────────────────────────────────────────────────
# AUTO-REFRESH
#
# CONCEITO: Loop de refresh com time.sleep() + st.rerun()
# ────────────────────────────────────────────────────────────
# st.rerun() re-executa o script do zero, "atualizando" a página.
# time.sleep(10) pausa a execução por 10 segundos ANTES de rerun.
#
# Isso cria um loop: script roda → dorme 10s → roda de novo.
#
# IMPORTANTE: enquanto o sleep está ativo, a aba do browser fica
# "ocupada" (spinner no título). Por isso o toggle permite desligar.
# Use auto-refresh apenas quando estiver monitorando ativamente.
# ─────────────────────────────────────────────────────────────
if auto_refresh:
    # CONCEITO: st.empty()
    # Cria um placeholder que pode ser atualizado depois.
    # Aqui usamos para mostrar uma contagem regressiva.
    placeholder = st.empty()
    for i in range(10, 0, -1):
        placeholder.caption(f"Atualizando em {i}s...")
        time.sleep(1)
    placeholder.empty()
    st.rerun()
