"""
Grafico de estados por PORCENTAGEM da gravacao
===============================================




Script INDEPENDENTE (nao importa o eeg_offline.py, pra evitar problema de
nome de arquivo/pasta). Os parametros abaixo sao uma COPIA dos mesmos
valores do eeg_offline.py.




>>> IMPORTANTE: se mudarem ALPHA_BAND, RAW_BAND, BANDA_TOTAL_ALFA,
>>> ALPHA_WINDOW_S, ALPHA_HOP_S, EMA_ALFA, os LIMIAR_* ou os parametros de
>>> artefato no eeg_offline.py, mudem a MESMA coisa aqui, senao os graficos
>>> deixam de refletir o que o script principal faz.




O QUE ELE FAZ:
Cada gravacao e tratada como 100%, independente da duracao real (uma de 2min
e outra de 9min viram as duas uma barra de 0 a 100%). O grafico mostra, ao
longo dessa escala, cada TROCA de estado como um segmento colorido, com a
porcentagem daquele trecho escrita dentro dele. Assim da pra comparar
gravacoes de duracoes diferentes lado a lado.




Cada arquivo gera um PNG com 2 paineis:
  - em cima : a alfa relativa suavizada (o numero que o classificador ve),
              com as linhas dos limiares ALTO/BAIXO desenhadas
  - embaixo : a faixa de estados, segmento por segmento, com os %




COMO USAR:
1. Edite ARQUIVOS abaixo com os CSVs que querem plotar.
2. python3 grafico_percentual.py
3. Os PNGs sao salvos na mesma pasta, um por arquivo.
"""




import csv
import os




import numpy as np
import matplotlib
matplotlib.use("Agg")   # backend sem janela - so salva arquivo
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
from scipy.signal import butter, sosfilt, sosfilt_zi








# ======================= PARAMETROS (copia do eeg_offline.py) =======================




SAMPLE_RATE_HZ = 512.0
ALPHA_BAND = (8.0, 12.0)
RAW_BAND = (1.0, 40.0)
BANDA_TOTAL_ALFA = (4.0, 40.0)
ALPHA_WINDOW_S = 8.0
ALPHA_HOP_S = 0.5
EMA_ALFA = 0.2




LIMIAR_RELAX_ALTO = 0.2390
LIMIAR_RELAX_BAIXO = 0.2190




LIMIAR_ARTEFATO_JANELA = 450.0
LIMITE_FRACAO_CONTAMINADA = 0.30




# ============================== EDITE AQUI ==============================




ARQUIVOS = [ #exemplos (os arquivos .csv devem estar na mesma pasta que o código)
    "19.08.C_CSV.txt",
    "19.08.R_CSV.txt",
    "Ondas Henrique Campo Minado CSV.txt",
    "Ondas Roberto 0807 C 2 CSV.txt",
    "Ondas Roberto 0807 R CSV.txt",
    "Ondas Roberto SMW CSV.txt",
    "Teste 0607 1minR 1minC 1minR CSV.txt",
    "Ondas Bonacin MegaBonk CSV.txt",
    "Ondas Henrique TVRUHH CSV.txt",
    "Ondas Roberto MegaBonk CSV.txt",
    "Ondas Roberto Musica e Relaxado CSV.txt",
   
]




# segmentos menores que isso (em % da gravacao) nao recebem rotulo escrito
# dentro da barra, pra nao virar um amontoado de numeros ilegivel
MIN_PCT_PARA_ROTULO = 3.0




# ========================================================================








CORES = {
    "RELAXAMENTO": "#4E93D9",
    "CONCENTRACAO": "#E0873C",
    "indefinido": "#C9C7BF",
}








def carregar_csv_openvibe(caminho):
    tempos, valores = [], []
    with open(caminho, "r", encoding="utf-8", newline="") as f:
        leitor = csv.reader(f)
        if next(leitor, None) is None:
            raise ValueError(f"'{caminho}' esta vazio (0 linhas).")
        for linha in leitor:
            if not linha:
                continue
            tempos.append(float(linha[0]))
            valores.append(float(linha[2]))
    if len(tempos) < int(ALPHA_WINDOW_S * SAMPLE_RATE_HZ):
        raise ValueError(
            f"'{caminho}' tem só {len(tempos) / SAMPLE_RATE_HZ:.1f}s - "
            f"precisa de pelo menos {ALPHA_WINDOW_S:.0f}s."
        )
    return np.array(tempos, dtype=float), np.array(valores, dtype=float)








class FiltroPassaBandaOnline:
    def __init__(self, banda, fs, ordem=4):
        nyq = fs / 2.0
        self.sos = butter(ordem, [banda[0] / nyq, banda[1] / nyq],
                          btype="bandpass", output="sos")
        self.zi = sosfilt_zi(self.sos)




    def resetar(self, valor_inicial=0.0):
        self.zi = sosfilt_zi(self.sos) * valor_inicial




    def processar(self, amostras):
        saida, self.zi = sosfilt(self.sos, amostras, zi=self.zi)
        return saida








def computar_series(tempos, brutos, fs=SAMPLE_RATE_HZ):
    """Mesma logica do eeg_offline.py: 3 filtros em paralelo, janela
    deslizante de ALPHA_WINDOW_S, alfa relativa, e rejeicao de artefato
    amostra a amostra (descartando a janela inteira so se a contaminacao
    passar de LIMITE_FRACAO_CONTAMINADA)."""
    fb = FiltroPassaBandaOnline(RAW_BAND, fs); fb.resetar(brutos[0])
    ft = FiltroPassaBandaOnline(BANDA_TOTAL_ALFA, fs); ft.resetar(brutos[0])
    fa = FiltroPassaBandaOnline(ALPHA_BAND, fs); fa.resetar(brutos[0])




    bruto_filtrado = fb.processar(brutos)
    total_filtrado = ft.processar(brutos)
    alfa_filtrado = fa.processar(brutos)




    amostra_limpa = np.abs(bruto_filtrado) <= LIMIAR_ARTEFATO_JANELA




    tam_janela = int(ALPHA_WINDOW_S * fs)
    hop = max(1, int(ALPHA_HOP_S * fs))




    serie, tempos_j, validas = [], [], []
    for fim in range(tam_janela, len(alfa_filtrado) + 1, hop):
        mascara = amostra_limpa[fim - tam_janela:fim]
        fracao_contaminada = 1.0 - float(np.mean(mascara))
        jan_alfa = alfa_filtrado[fim - tam_janela:fim]
        jan_total = total_filtrado[fim - tam_janela:fim]




        if fracao_contaminada > LIMITE_FRACAO_CONTAMINADA:
            pa = float(np.mean(np.square(jan_alfa)))
            pt = float(np.mean(np.square(jan_total)))
            valida = False
        else:
            pa = float(np.mean(np.square(jan_alfa[mascara])))
            pt = float(np.mean(np.square(jan_total[mascara])))
            valida = True




        serie.append(pa / pt if pt > 0 else 0.0)
        tempos_j.append(tempos[fim - 1])
        validas.append(valida)




    return np.array(serie), np.array(tempos_j), np.array(validas)








def classificar_ao_longo_do_tempo(serie, tempos_j, validas, duracao_total):
    """Reproduz a EMA + classificador com histerese do eeg_offline.py e
    devolve, pra cada janela, o percentual da gravacao e o estado vigente."""
    valor = None
    estado = "indefinido"
    pcts, estados, suavizados = [], [], []




    for t, v, ok in zip(tempos_j, serie, validas):
        if ok:
            valor = v if valor is None else EMA_ALFA * v + (1 - EMA_ALFA) * valor
            if valor > LIMIAR_RELAX_ALTO:
                estado = "RELAXAMENTO"
            elif valor < LIMIAR_RELAX_BAIXO:
                estado = "CONCENTRACAO"
            # entre os dois limiares: mantem o estado anterior (histerese)
        pcts.append(100.0 * t / duracao_total)
        estados.append(estado)
        suavizados.append(valor if valor is not None else np.nan)




    return np.array(pcts), estados, np.array(suavizados)








def agrupar_em_segmentos(pcts, estados):
    """Junta janelas consecutivas de mesmo estado num unico segmento
    (inicio_pct, fim_pct, estado) - e isso que vira cada bloco do grafico."""
    segmentos = []
    ini = 0.0
    estado_atual = estados[0]
    for i in range(1, len(estados)):
        if estados[i] != estado_atual:
            segmentos.append((ini, pcts[i], estado_atual))
            ini = pcts[i]
            estado_atual = estados[i]
    segmentos.append((ini, 100.0, estado_atual))
    return segmentos








def plotar(caminho, segmentos, pcts, suavizados, duracao_total, n_descartadas, n_total):
    nome_base = os.path.splitext(os.path.basename(caminho))[0]




    fig, (ax_sinal, ax_faixa) = plt.subplots(
        2, 1, figsize=(13, 6), sharex=True,
        gridspec_kw={"height_ratios": [3, 1], "hspace": 0.18},
    )




    # ---- painel de cima: a alfa relativa suavizada + limiares ----
    ax_sinal.plot(pcts, suavizados, color="#2A2A28", linewidth=1.3,
                  label="alfa relativa (suavizada pela EMA)")
    ax_sinal.axhline(LIMIAR_RELAX_ALTO, color=CORES["RELAXAMENTO"], linestyle="--",
                     linewidth=1.1, label=f"limiar ALTO = {LIMIAR_RELAX_ALTO:.4f}")
    ax_sinal.axhline(LIMIAR_RELAX_BAIXO, color=CORES["CONCENTRACAO"], linestyle="--",
                     linewidth=1.1, label=f"limiar BAIXO = {LIMIAR_RELAX_BAIXO:.4f}")
    ax_sinal.axhspan(LIMIAR_RELAX_BAIXO, LIMIAR_RELAX_ALTO, color="#D8D6CE", alpha=0.45)
    ax_sinal.set_ylabel("alfa relativa")
    ax_sinal.legend(loc="upper right", fontsize=8, framealpha=0.9)
    ax_sinal.grid(alpha=0.25, linewidth=0.5)




    titulo = (f"{nome_base}\n"
              f"duracao real = {duracao_total:.0f}s (normalizada para 100%)  ·  "
              f"janelas descartadas por artefato: {n_descartadas}/{n_total} "
              f"({100*n_descartadas/n_total:.1f}%)")
    ax_sinal.set_title(titulo, fontsize=10, loc="left")




    # ---- painel de baixo: a faixa de estados com os % ----
    for ini, fim, estado in segmentos:
        largura = fim - ini
        ax_faixa.barh(0, largura, left=ini, height=0.6,
                      color=CORES[estado], edgecolor="white", linewidth=1.0)
        if largura >= MIN_PCT_PARA_ROTULO:
            ax_faixa.text(ini + largura / 2, 0, f"{largura:.1f}%",
                          ha="center", va="center", fontsize=8.5,
                          color="white", fontweight="bold")




    ax_faixa.set_xlim(0, 100)
    ax_faixa.set_ylim(-0.5, 0.5)
    ax_faixa.set_yticks([])
    ax_faixa.set_xlabel("porcentagem da gravacao (%)")
    ax_faixa.set_xticks(range(0, 101, 10))




    # totais por estado, pra legenda
    totais = {}
    for ini, fim, estado in segmentos:
        totais[estado] = totais.get(estado, 0.0) + (fim - ini)
    handles = [Patch(facecolor=CORES[e], label=f"{e}: {p:.1f}%")
               for e, p in sorted(totais.items(), key=lambda kv: -kv[1])]
    ax_faixa.legend(handles=handles, loc="upper center",
                    bbox_to_anchor=(0.5, -0.45), ncol=3, fontsize=9, frameon=False)




    saida = f"grafico_{nome_base}.png"
    fig.savefig(saida, dpi=160, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return saida, totais, len(segmentos)








def main():
    for caminho in ARQUIVOS:
        if not os.path.exists(caminho):
            print(f"[pulado] '{caminho}' nao encontrado nesta pasta.")
            continue




        tempos, brutos = carregar_csv_openvibe(caminho)
        serie, tempos_j, validas = computar_series(tempos, brutos)
        duracao_total = float(tempos[-1])




        pcts, estados, suavizados = classificar_ao_longo_do_tempo(
            serie, tempos_j, validas, duracao_total
        )
        segmentos = agrupar_em_segmentos(pcts, estados)
        saida, totais, n_seg = plotar(
            caminho, segmentos, pcts, suavizados, duracao_total,
            int(np.sum(~validas)), len(validas)
        )




        resumo = "  ".join(f"{e}={p:.1f}%" for e, p in
                           sorted(totais.items(), key=lambda kv: -kv[1]))
        print(f"{os.path.basename(caminho)}")
        print(f"  duracao real: {duracao_total:.0f}s  ·  trocas de estado: {n_seg - 1}")
        print(f"  {resumo}")
        print(f"  -> {saida}\n")








if __name__ == "__main__":
    main()











