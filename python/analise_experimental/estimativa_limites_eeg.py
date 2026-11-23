import csv
import numpy as np
from scipy.signal import butter, sosfilt, sosfilt_zi




# ============================ PARAMETROS ============================
# (copia dos mesmos valores do eeg_offline.py - ver aviso no topo do arquivo)


SAMPLE_RATE_HZ = 512.0
ALPHA_BAND = (8.0, 12.0)
RAW_BAND = (1.0, 40.0)
BANDA_TOTAL_ALFA = (4.0, 40.0)
ALPHA_WINDOW_S = 8.0
ALPHA_HOP_S = 0.5
LIMIAR_ARTEFATO_JANELA = 450.0


# ============================ EDITE AQUI =============================


ARQUIVOS_ROTULADOS = [ #coloque aqui seus arquivos, entre parenteses e aspas, e separados por vírgula, cmomo no exemplo a seguir: 
    ("19.08.C_CSV.txt", "conc"),
    ("19.08.R_CSV.txt", "relax"),
]


MARGEM_RELATIVA = 0.15  # fracao da diferenca entre as medias que vira a
                         # "zona neutra" (histerese) em volta do corte otimo


# ======================================================================




def carregar_csv_openvibe(caminho):
    """Le um CSV no formato 'Time:<fs>Hz,Epoch,Electrode,...' e retorna
    (tempos, valores_eletrodo) como arrays numpy."""
    tempos, valores = [], []
    with open(caminho, "r", encoding="utf-8", newline="") as f:
        leitor = csv.reader(f)
        cabecalho = next(leitor, None)
        if cabecalho is None:
            raise ValueError(f"'{caminho}' esta vazio (0 linhas).")
        for linha in leitor:
            if not linha:
                continue
            tempos.append(float(linha[0]))
            valores.append(float(linha[2]))


    if len(tempos) < int(ALPHA_WINDOW_S * SAMPLE_RATE_HZ):
        raise ValueError(
            f"'{caminho}' tem só {len(tempos)} amostras "
            f"({len(tempos) / SAMPLE_RATE_HZ:.1f}s) - precisa de pelo menos "
            f"{ALPHA_WINDOW_S:.0f}s pra formar 1 janela de alfa."
        )
    return np.array(tempos, dtype=float), np.array(valores, dtype=float)




class FiltroPassaBandaOnline:
    def __init__(self, banda, fs, ordem=4):
        nyq = fs / 2.0
        low, high = banda[0] / nyq, banda[1] / nyq
        self.sos = butter(ordem, [low, high], btype="bandpass", output="sos")
        self.zi = sosfilt_zi(self.sos)


    def resetar(self, valor_inicial=0.0):
        self.zi = sosfilt_zi(self.sos) * valor_inicial


    def processar(self, amostras):
        saida, self.zi = sosfilt(self.sos, amostras, zi=self.zi)
        return saida




def computar_series_processadas(tempos, brutos, fs=SAMPLE_RATE_HZ):
    """Mesma logica do eeg_offline.py: filtra em paralelo (RAW_BAND,
    BANDA_TOTAL_ALFA, ALPHA_BAND), janela deslizante de ALPHA_WINDOW_S com
    passo ALPHA_HOP_S, calcula a razao potencia_alfa/potencia_total, e
    marca como invalida qualquer janela cujo pico do sinal bruto passe de
    LIMIAR_ARTEFATO_JANELA."""
    filtro_bruto = FiltroPassaBandaOnline(RAW_BAND, fs)
    filtro_total = FiltroPassaBandaOnline(BANDA_TOTAL_ALFA, fs)
    filtro_alfa = FiltroPassaBandaOnline(ALPHA_BAND, fs)
    filtro_bruto.resetar(brutos[0])
    filtro_total.resetar(brutos[0])
    filtro_alfa.resetar(brutos[0])


    bruto_filtrado = filtro_bruto.processar(brutos)
    total_filtrado = filtro_total.processar(brutos)
    alfa_filtrado = filtro_alfa.processar(brutos)


    tam_janela = int(ALPHA_WINDOW_S * fs)
    hop = max(1, int(ALPHA_HOP_S * fs))


    serie_alfa, serie_valida = [], []
    for fim in range(tam_janela, len(alfa_filtrado) + 1, hop):
        jan_alfa = alfa_filtrado[fim - tam_janela:fim]
        jan_total = total_filtrado[fim - tam_janela:fim]
        potencia_alfa = float(np.mean(np.square(jan_alfa)))
        potencia_total = float(np.mean(np.square(jan_total)))
        relativa = potencia_alfa / potencia_total if potencia_total > 0 else 0.0
        serie_alfa.append(relativa)


        pico_bruto = float(np.max(np.abs(bruto_filtrado[fim - tam_janela:fim])))
        serie_valida.append(pico_bruto <= LIMIAR_ARTEFATO_JANELA)


    return np.array(serie_alfa), np.array(serie_valida)




def computar_serie(caminho):
    tempos, brutos = carregar_csv_openvibe(caminho)
    serie_alfa, serie_valida = computar_series_processadas(tempos, brutos)
    n_invalidas = int(np.sum(~serie_valida))
    if n_invalidas:
        print(f"  aviso: '{caminho}' teve {n_invalidas}/{len(serie_valida)} "
              f"janelas descartadas por artefato - considerem excluir esse "
              f"arquivo da calibracao se essa fracao for alta.")
    return tempos[-1], serie_alfa[serie_valida]




def main():
    if len(ARQUIVOS_ROTULADOS) < 2:
        raise RuntimeError("Precisa de pelo menos 1 arquivo 'relax' e 1 'conc'.")


    print("Processando arquivos...")
    dados = {}
    for caminho, label in ARQUIVOS_ROTULADOS:
        dur, serie = computar_serie(caminho)
        dados[caminho] = (label, dur, serie)
        print(f"  {caminho:<50} [{label:<6}] media={serie.mean():.4f}  "
              f"mediana={np.median(serie):.4f}  n_janelas={len(serie)}")


    relax_vals = np.concatenate([d[2] for d in dados.values() if d[0] == "relax"])
    conc_vals = np.concatenate([d[2] for d in dados.values() if d[0] == "conc"])
    if len(relax_vals) == 0 or len(conc_vals) == 0:
        raise RuntimeError("Precisa de pelo menos 1 arquivo de cada rotulo (relax e conc).")


    todos = np.concatenate([d[2] for d in dados.values()])
    candidatos = np.linspace(todos.min(), todos.max(), 3000)
    tempo_total = sum(d[1] for d in dados.values())


    melhor = None
    for T in candidatos:
        correto = sum(
            (np.sum(d[2] >= T) if d[0] == "relax" else np.sum(d[2] < T)) * (d[1] / len(d[2]))
            for d in dados.values()
        )
        if melhor is None or correto > melhor[1]:
            melhor = (T, correto)
    T_otimo, correto = melhor


    margem = MARGEM_RELATIVA * abs(relax_vals.mean() - conc_vals.mean())


    print(f"\n=== RESULTADO ===")
    print(f"Ponto de corte otimo (T) = {T_otimo:.4f}")
    print(f"Acerto combinado (nos proprios arquivos calibrados) = "
          f"{100*correto/tempo_total:.1f}%")
    print(f"(lembrem: acerto medido nos MESMOS arquivos usados pra calibrar "
          f"tende a ser otimista - validem sempre num arquivo separado, nao "
          f"incluido aqui, antes de confiar no numero acima)")


    print(f"\nCole isto no topo do eeg_offline.py:\n")
    print(f"LIMIAR_RELAX_ALTO = {T_otimo + margem:.4f}")
    print(f"LIMIAR_RELAX_BAIXO = {T_otimo - margem:.4f}")
    print(f"LIMIAR_CONC_ALTO = {-(T_otimo - margem):.4f}")
    print(f"LIMIAR_CONC_BAIXO = {-(T_otimo + margem):.4f}")


    print(f"\n=== acerto por arquivo, com os novos limiares (+ histerese) ===")
    for caminho, (label, dur, serie) in dados.items():
        dt = dur / len(serie)
        certo = (np.sum(serie >= T_otimo) if label == "relax" else np.sum(serie < T_otimo)) * dt
        print(f"  {caminho:<50} {100*certo/dur:.1f}%")




if __name__ == "__main__":
    main()



