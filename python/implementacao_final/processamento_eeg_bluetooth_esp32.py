import collections
import csv
import threading
import time
import numpy as np
from scipy.signal import butter, sosfilt, sosfilt_zi

SAMPLE_RATE_HZ = 512.0     

ALPHA_BAND = (8.0, 12.0)
RAW_BAND = (1.0, 40.0)          
BANDA_TOTAL_ALFA = (4.0, 40.0)  
ALPHA_WINDOW_S = 8.0       
ALPHA_HOP_S = 0.5          
EMA_ALFA = 0.2

LIMIAR_RELAX_ALTO = 0.2390
LIMIAR_RELAX_BAIXO = 0.2190
LIMIAR_CONC_ALTO = -0.2190
LIMIAR_CONC_BAIXO = -0.2390

ARQUIVO_REPLAY_AO_VIVO = "Teste 0607 CSV.txt"
VELOCIDADE_REPLAY = 1.0    

LIMIAR_PISCADA = 450.0
REFRATARIO_PISCADA_S = 0.5
LIMIAR_ARTEFATO_JANELA = 450.0
LIMITE_FRACAO_CONTAMINADA = 0.30

INTERVALO_PRINT_S = 0.2

ENVIAR_PARA_ARDUINO = True
PORTA_SERIAL = "COM16"         
BAUD_SERIAL = 115200          
ESPERA_RESET_ARDUINO_S = 2.0  

MODO_CONTROLE = "concentracao"

ALFA_VELOCIDADE_MAX = 0.35    
ALFA_VELOCIDADE_MIN = 0.10    

PWM_MIN = 40
PWM_MAX = 255

RAMPA_MAX_POR_ATUALIZACAO = 15

GERAR_GRAFICO_AO_FINAL = False
MIN_PCT_PARA_ROTULO = 3.0   

MOSTRAR_INTERFACE = True
JANELA_ONDA_S = 5.0            
TAXA_ATUALIZACAO_ONDA_S = 0.02  

JANELA_ALFA_S = 30.0            

TAXA_ATUALIZACAO_TELA_MS = 100  
DURACAO_ESPERA_PAUSA_S = 0.6    
DURACAO_FADE_PAUSA_S = 0.4      
INTERVALO_FADE_MS = 40           

def carregar_csv_openvibe(caminho):
    """Le um CSV no formato 'Time:<fs>Hz,Epoch,Electrode,...' e retorna
    (tempos, valores_eletrodo) como arrays numpy."""
    tempos = []
    valores = []
    with open(caminho, "r", encoding="utf-8", newline="") as f:
        leitor = csv.reader(f)
        cabecalho = next(leitor, None)
        if cabecalho is None:
            raise ValueError(
                f"'{caminho}' esta vazio (0 linhas) - o upload/download deve "
                f"ter falhado. Confiram o arquivo e reenviem."
            )
        for linha in leitor:
            if not linha:
                continue
            tempos.append(float(linha[0]))
            valores.append(float(linha[2]))

    if len(tempos) < int(ALPHA_WINDOW_S * SAMPLE_RATE_HZ):
        raise ValueError(
            f"'{caminho}' tem só {len(tempos)} amostras "
            f"({len(tempos) / SAMPLE_RATE_HZ:.1f}s) - precisa de pelo menos "
            f"{ALPHA_WINDOW_S:.0f}s (ALPHA_WINDOW_S) pra formar 1 janela de alfa."
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
    """A partir do eletrodo bruto, calcula:
      - bruto_filtrado: sinal bruto filtrado em RAW_BAND (equivalente ao que
        o OpenViBE mandava na porta 'bruto', usado na deteccao de piscada)
      - serie_alfa: potencia RELATIVA de alfa numa janela deslizante de
        ALPHA_WINDOW_S segundos (potencia_alfa / potencia_total(BANDA_TOTAL_ALFA)
        na MESMA janela), publicada a cada ALPHA_HOP_S segundos.
      - tempos_alfa: instante (mesma base de tempo do arquivo) de cada valor
        de serie_alfa
      - serie_valida: array booleano, mesma forma de serie_alfa - False
        so quando a FRACAO de amostras contaminadas dentro da janela passa
        de LIMITE_FRACAO_CONTAMINADA. Ate esse ponto, amostras contaminadas
        isoladas sao simplesmente EXCLUIDAS do calculo de potencia daquela
        janela (nao descartam a janela inteira) - antes, 1 pico de <1s
        bastava pra jogar fora ~17 janelas seguidas (quase 9s de dado bom
        descartado por causa de um instante ruim). Agora so descartamos a
        janela inteira quando a contaminacao realmente domina ela.
    """
    filtro_bruto = FiltroPassaBandaOnline(RAW_BAND, fs)
    filtro_total = FiltroPassaBandaOnline(BANDA_TOTAL_ALFA, fs)
    filtro_alfa = FiltroPassaBandaOnline(ALPHA_BAND, fs)
    filtro_bruto.resetar(brutos[0])
    filtro_total.resetar(brutos[0])
    filtro_alfa.resetar(brutos[0])

    bruto_filtrado = filtro_bruto.processar(brutos)
    total_filtrado = filtro_total.processar(brutos)
    alfa_filtrado = filtro_alfa.processar(brutos)

    amostra_limpa = np.abs(bruto_filtrado) <= LIMIAR_ARTEFATO_JANELA

    tam_janela = int(ALPHA_WINDOW_S * fs)
    hop = max(1, int(ALPHA_HOP_S * fs))

    serie_alfa = []
    tempos_alfa = []
    serie_valida = []
    for fim in range(tam_janela, len(alfa_filtrado) + 1, hop):
        mascara = amostra_limpa[fim - tam_janela:fim]
        fracao_contaminada = 1.0 - float(np.mean(mascara))

        jan_alfa = alfa_filtrado[fim - tam_janela:fim]
        jan_total = total_filtrado[fim - tam_janela:fim]

        if fracao_contaminada > LIMITE_FRACAO_CONTAMINADA:

            potencia_alfa = float(np.mean(np.square(jan_alfa)))
            potencia_total = float(np.mean(np.square(jan_total)))
            valida = False
        else:

            potencia_alfa = float(np.mean(np.square(jan_alfa[mascara])))
            potencia_total = float(np.mean(np.square(jan_total[mascara])))
            valida = True

        relativa = potencia_alfa / potencia_total if potencia_total > 0 else 0.0
        serie_alfa.append(relativa)
        tempos_alfa.append(tempos[fim - 1])
        serie_valida.append(valida)

    return (bruto_filtrado, np.array(serie_alfa), np.array(tempos_alfa),
            np.array(serie_valida))

class EMA:
    def __init__(self, alfa):
        self.alfa = alfa
        self.valor = None

    def atualizar(self, novo_valor):
        if self.valor is None:
            self.valor = novo_valor
        else:
            self.valor = self.alfa * novo_valor + (1 - self.alfa) * self.valor
        return self.valor

class ClassificadorFixo:
    def __init__(self, limiar_alto, limiar_baixo):
        self.limiar_alto = limiar_alto
        self.limiar_baixo = limiar_baixo
        self.estado = "neutro"

    def atualizar(self, valor):
        if valor > self.limiar_alto:
            self.estado = "ALTO"
        elif valor < self.limiar_baixo:
            self.estado = "BAIXO"
        return self.estado

def thread_deteccao_piscada(reader_bruto, parar_evento):
    ultima_piscada_t = 0.0
    ultimo_timestamp_processado = None

    while not parar_evento.is_set():
        time.sleep(0.01)

        valor = reader_bruto.last_value
        timestamp = reader_bruto.last_update_time
        if valor is None or timestamp is None:
            continue
        if timestamp == ultimo_timestamp_processado:
            continue
        ultimo_timestamp_processado = timestamp

        agora = time.time()
        if abs(valor) > LIMIAR_PISCADA and agora - ultima_piscada_t > REFRATARIO_PISCADA_S:
            ultima_piscada_t = agora
            print(f">>> PISCADA detectada (bruto={valor:.1f})")

class LeitorReplay:
    def __init__(self, nome):
        self.nome = nome
        self.last_value = None
        self.last_update_time = None
        self.connected = False

class CSVPlayer:
    def __init__(self, caminho, velocidade=1.0, fs=SAMPLE_RATE_HZ):
        self.caminho = caminho
        self.velocidade = velocidade
        self.terminou = False
        self._running = False
        self._thread = None

        tempos, brutos = carregar_csv_openvibe(caminho)
        self._tempos = tempos
        self._bruto_filtrado, self._serie_alfa, self._tempos_alfa, self._serie_valida = \
            computar_series_processadas(tempos, brutos, fs)

        n_invalidas = int(np.sum(~self._serie_valida))
        n_total = len(self._serie_valida)
        print(f"'{caminho}': {tempos[-1]:.1f}s de sinal, bruto filtrado "
              f"min/max = {self._bruto_filtrado.min():.1f}/{self._bruto_filtrado.max():.1f} "
              f"(referencia p/ ajustar LIMIAR_PISCADA)")
        if n_total:
            print(f"  janelas de alfa descartadas por excesso de artefato "
                  f"(>{100*LIMITE_FRACAO_CONTAMINADA:.0f}% da janela contaminada): "
                  f"{n_invalidas}/{n_total} ({100*n_invalidas/n_total:.1f}%)")
            if n_invalidas / n_total > 0.30:
                print(f"  AVISO: mais de 30% das janelas descartadas - essa "
                      f"gravacao provavelmente tem um problema de contato/"
                      f"movimento (ver conversa sobre o '19_08_R').")

        self.bruto = LeitorReplay("bruto")
        self.alfa = LeitorReplay("alfa")

    def readers(self):
        return {"alfa": self.alfa, "bruto": self.bruto}

    def series_para_grafico(self):
        """Devolve as series ja calculadas (serie_alfa, tempos_alfa,
        serie_valida, duracao_total) - usadas por gerar_grafico_percentual."""
        return (self._serie_alfa, self._tempos_alfa, self._serie_valida,
                float(self._tempos[-1]))

    def start(self):
        self._running = True
        self.bruto.connected = True
        self.alfa.connected = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)

    def _run(self):
        print(f"[replay] reproduzindo '{self.caminho}' "
              f"({len(self._tempos)} amostras a {SAMPLE_RATE_HZ:.0f}Hz, "
              f"velocidade={self.velocidade}x)")

        t0_real = time.time()
        t0_virtual = self._tempos[0] if len(self._tempos) else 0.0
        idx_alfa = 0
        n_alfa = len(self._serie_alfa)

        for i, t_virtual in enumerate(self._tempos):
            if not self._running:
                return

            alvo = t0_real + (t_virtual - t0_virtual) / self.velocidade
            atraso = alvo - time.time()
            if atraso > 0:
                time.sleep(atraso)

            agora = time.time()
            self.bruto.last_value = float(self._bruto_filtrado[i])
            self.bruto.last_update_time = agora

            while idx_alfa < n_alfa and self._tempos_alfa[idx_alfa] <= t_virtual:
                if self._serie_valida[idx_alfa]:
                    self.alfa.last_value = float(self._serie_alfa[idx_alfa])
                    self.alfa.last_update_time = agora
                idx_alfa += 1

        self.terminou = True
        print(f"[replay] '{self.caminho}' terminou.")

def calcular_pwm_alvo(valor_alfa):
    """Converte a alfa relativa suavizada em PWM: 0 = parado,
    PWM_MIN..PWM_MAX = girando. A DISTANCIA ate o limiar vira velocidade -
    encostado no limiar = quase parado; longe dele = rapido.

    Dentro da zona de histerese (entre BAIXO e ALTO) o motor fica PARADO nos
    dois modos: e a faixa 'nao decidido', entao nao faz sentido acionar nela.
    """
    if MODO_CONTROLE == "relaxamento":

        if valor_alfa <= LIMIAR_RELAX_ALTO:
            return 0
        span = ALFA_VELOCIDADE_MAX - LIMIAR_RELAX_ALTO
        fracao = (valor_alfa - LIMIAR_RELAX_ALTO) / span if span > 0 else 0.0
    else:  

        if valor_alfa >= LIMIAR_RELAX_BAIXO:
            return 0
        span = LIMIAR_RELAX_BAIXO - ALFA_VELOCIDADE_MIN
        fracao = (LIMIAR_RELAX_BAIXO - valor_alfa) / span if span > 0 else 0.0

    fracao = max(0.0, min(1.0, fracao))
    return int(round(PWM_MIN + fracao * (PWM_MAX - PWM_MIN)))

class ControleMotorSerial:
    """Mantem a conexao serial com o Arduino e aplica a rampa de velocidade.

    Se o pyserial nao estiver instalado, ou a porta nao abrir (Arduino
    desconectado, porta errada, Monitor Serial da IDE segurando a porta), o
    script AVISA e continua rodando sem motor - o replay e a classificacao
    nao dependem disso.
    """

    def __init__(self, porta, baud):
        self.conectado = False
        self._serial = None
        self._pwm_atual = 0

        try:
            import serial  
        except ImportError:
            print("[motor] pyserial nao instalado - seguindo sem motor. "
                  "Para habilitar: pip install pyserial")
            return

        try:
            self._serial = serial.Serial(porta, baud, timeout=1)
        except Exception as e:
            print(f"[motor] nao consegui abrir '{porta}' ({e}) - seguindo sem "
                  f"motor. Confiram a porta no Gerenciador de Dispositivos e "
                  f"se o Monitor Serial da IDE do Arduino nao esta aberto "
                  f"(ele segura a porta).")
            return

        print(f"[motor] conectado em {porta} - esperando o Arduino reiniciar...")
        time.sleep(ESPERA_RESET_ARDUINO_S)
        self.conectado = True
        print(f"[motor] pronto. modo = '{MODO_CONTROLE}'  "
              f"(PWM {PWM_MIN}-{PWM_MAX})")

    def atualizar(self, valor_alfa):
        """Calcula o PWM alvo, aplica a rampa e envia. Devolve o PWM enviado."""
        alvo = calcular_pwm_alvo(valor_alfa)

        delta = alvo - self._pwm_atual
        if abs(delta) > RAMPA_MAX_POR_ATUALIZACAO:
            self._pwm_atual += (RAMPA_MAX_POR_ATUALIZACAO if delta > 0
                                else -RAMPA_MAX_POR_ATUALIZACAO)
        else:
            self._pwm_atual = alvo
        self._pwm_atual = max(0, min(PWM_MAX, self._pwm_atual))

        if self.conectado:
            try:
                self._serial.write(f"V{self._pwm_atual}\n".encode("ascii"))
            except Exception as e:
                print(f"[motor] falha ao enviar ({e}) - desligando o controle.")
                self.conectado = False

        return self._pwm_atual

    def parar(self):
        """Manda o motor parar e fecha a porta. SEMPRE chamado no final -
        sem isso o motor continuaria girando depois do script terminar."""
        if self.conectado:
            try:
                self._serial.write(b"V0\n")
                time.sleep(0.1)
            except Exception:
                pass
        if self._serial is not None:
            try:
                self._serial.close()
            except Exception:
                pass
        self.conectado = False

def gerar_grafico_percentual(caminho, serie_alfa, tempos_alfa, serie_valida,
                             duracao_total):
    """Gera um PNG com 2 paineis:
      - em cima : a alfa relativa suavizada (o numero que o classificador ve),
                  com as linhas dos limiares e a zona de histerese sombreada
      - embaixo : a faixa de estados, segmento por segmento, com a % de cada um

    O eixo X e a PORCENTAGEM da gravacao (0 a 100%), nao o tempo absoluto -
    entao gravacoes de 2min e de 9min viram barras do mesmo tamanho, faceis
    de comparar.

    Obs: o grafico e montado a partir das series ja calculadas pelo
    CSVPlayer (mesma matematica do loop ao vivo), entao ele mostra a
    gravacao INTEIRA mesmo que voces tenham interrompido o replay no meio
    com Ctrl+C - nesse caso o RESUMO impresso cobre so o trecho que rodou,
    mas o grafico cobre tudo.
    """
    try:
        import matplotlib
        matplotlib.use("Agg")   
        import matplotlib.pyplot as plt
        from matplotlib.patches import Patch
    except ImportError:
        print("\n[grafico] matplotlib nao esta instalado - pulei a geracao "
              "do grafico. Para habilitar: pip install matplotlib")
        return

    import os

    CORES = {
        "RELAXAMENTO": "#4E93D9",
        "CONCENTRACAO": "#E0873C",
        "indefinido": "#C9C7BF",
    }

    valor = None
    estado = "indefinido"
    pcts, estados, suavizados = [], [], []
    for t, v, ok in zip(tempos_alfa, serie_alfa, serie_valida):
        if ok:
            valor = v if valor is None else EMA_ALFA * v + (1 - EMA_ALFA) * valor
            if valor > LIMIAR_RELAX_ALTO:
                estado = "RELAXAMENTO"
            elif valor < LIMIAR_RELAX_BAIXO:
                estado = "CONCENTRACAO"

        pcts.append(100.0 * t / duracao_total)
        estados.append(estado)
        suavizados.append(valor if valor is not None else float("nan"))

    pcts = np.array(pcts)
    suavizados = np.array(suavizados)

    segmentos = []
    ini = 0.0
    estado_atual = estados[0]
    for i in range(1, len(estados)):
        if estados[i] != estado_atual:
            segmentos.append((ini, pcts[i], estado_atual))
            ini = pcts[i]
            estado_atual = estados[i]
    segmentos.append((ini, 100.0, estado_atual))

    nome_base = os.path.splitext(os.path.basename(caminho))[0]
    n_descartadas = int(np.sum(~serie_valida))
    n_total = len(serie_valida)

    fig, (ax_sinal, ax_faixa) = plt.subplots(
        2, 1, figsize=(13, 6), sharex=True,
        gridspec_kw={"height_ratios": [3, 1], "hspace": 0.18},
    )

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
    ax_sinal.set_title(
        f"{nome_base}\n"
        f"duracao real = {duracao_total:.0f}s (normalizada para 100%)  ·  "
        f"janelas descartadas por artefato: {n_descartadas}/{n_total} "
        f"({100*n_descartadas/n_total:.1f}%)",
        fontsize=10, loc="left",
    )

    for ini, fim, est in segmentos:
        largura = fim - ini
        ax_faixa.barh(0, largura, left=ini, height=0.6,
                      color=CORES[est], edgecolor="white", linewidth=1.0)
        if largura >= MIN_PCT_PARA_ROTULO:
            ax_faixa.text(ini + largura / 2, 0, f"{largura:.1f}%",
                          ha="center", va="center", fontsize=8.5,
                          color="white", fontweight="bold")

    ax_faixa.set_xlim(0, 100)
    ax_faixa.set_ylim(-0.5, 0.5)
    ax_faixa.set_yticks([])
    ax_faixa.set_xlabel("porcentagem da gravacao (%)")
    ax_faixa.set_xticks(range(0, 101, 10))

    totais = {}
    for ini, fim, est in segmentos:
        totais[est] = totais.get(est, 0.0) + (fim - ini)
    handles = [Patch(facecolor=CORES[e], label=f"{e}: {p:.1f}%")
               for e, p in sorted(totais.items(), key=lambda kv: -kv[1])]
    ax_faixa.legend(handles=handles, loc="upper center",
                    bbox_to_anchor=(0.5, -0.45), ncol=3, fontsize=9, frameon=False)

    saida = f"grafico_{nome_base}.png"
    fig.savefig(saida, dpi=160, bbox_inches="tight", facecolor="white")
    plt.close(fig)

    resumo = "  ".join(f"{e}={p:.1f}%" for e, p in
                       sorted(totais.items(), key=lambda kv: -kv[1]))
    print(f"\n=== GRAFICO (% da gravacao) ===")
    print(f"trocas de estado: {len(segmentos) - 1}  ·  {resumo}")
    print(f"salvo em: {saida}")

class EstadoAoVivo:
    """Guarda os ultimos valores calculados pelo loop de controle, pra
    interface grafica ler e desenhar. Um lock simples evita que a tela leia
    os dados no meio de uma atualizacao (nao e sobre performance, e so pra
    nao pegar um estado "pela metade")."""

    def __init__(self, tam_janela_onda, tam_janela_alfa):
        self._lock = threading.Lock()
        self.onda = collections.deque(maxlen=tam_janela_onda)
        self.tempos_onda = collections.deque(maxlen=tam_janela_onda)
        self.serie_alfa = collections.deque(maxlen=tam_janela_alfa)
        self.tempos_alfa_tela = collections.deque(maxlen=tam_janela_alfa)
        self.tempos_pwm = collections.deque(maxlen=tam_janela_alfa)
        self.serie_pwm = collections.deque(maxlen=tam_janela_alfa)
        self.pwm = 0
        self.estado_relax = "neutro"
        self.estado_conc = "neutro"
        self.alfa_suave_relax = None
        self.alfa_suave_conc = None
        self.motor_conectado = False
        self.segundos_ativo = 0.0
        self.segundos_total = 0.0
        self.t0 = time.time()

    def atualizar(self, **kwargs):
        with self._lock:
            for chave, valor in kwargs.items():
                setattr(self, chave, valor)

    def adicionar_ponto_onda(self, t, valor):
        with self._lock:
            self.tempos_onda.append(t)
            self.onda.append(valor)

    def adicionar_ponto_alfa(self, t, valor):
        if valor is None:
            return
        with self._lock:
            self.tempos_alfa_tela.append(t)
            self.serie_alfa.append(valor)

    def adicionar_ponto_pwm(self, t, valor):
        with self._lock:
            self.tempos_pwm.append(t)
            self.serie_pwm.append(valor)

    def copia(self):
        """Devolve uma copia 'congelada' dos valores atuais - a tela desenha
        a partir dela, nunca lendo os atributos direto (evita corrida)."""
        with self._lock:
            return {
                "onda": list(self.onda),
                "tempos_onda": list(self.tempos_onda),
                "serie_alfa": list(self.serie_alfa),
                "tempos_alfa_tela": list(self.tempos_alfa_tela),
                "tempos_pwm": list(self.tempos_pwm),
                "serie_pwm": list(self.serie_pwm),
                "pwm": self.pwm,
                "estado_relax": self.estado_relax,
                "estado_conc": self.estado_conc,
                "alfa_suave_relax": self.alfa_suave_relax,
                "alfa_suave_conc": self.alfa_suave_conc,
                "motor_conectado": self.motor_conectado,
                "segundos_ativo": self.segundos_ativo,
                "segundos_total": self.segundos_total,
            }

def thread_coletor_onda(reader_bruto, estado_ao_vivo, parar_evento, taxa_s):
    """So existe pra alimentar o GRAFICO da onda. Amostra o sinal bruto
    filtrado num ritmo mais lento que os 512Hz reais (ver
    TAXA_ATUALIZACAO_ONDA_S) - rapido o bastante pra parecer uma onda se
    mexendo, devagar o bastante pra nao pesar a tela. Nao participa em nada
    do calculo de alfa/classificacao/PWM, que continuam vindo do loop de
    controle de sempre."""
    t0 = estado_ao_vivo.t0
    while not parar_evento.is_set():
        time.sleep(taxa_s)
        valor = reader_bruto.last_value
        if valor is None:
            continue
        estado_ao_vivo.adicionar_ponto_onda(time.time() - t0, valor)

def rodar_interface_ao_vivo(estado_ao_vivo, parar_evento, player):
    """Abre a interface clara com dois graficos EEG e barra PWM horizontal.
    A interface apenas exibe valores; nao altera a logica de controle.

    Roda na thread principal (exigencia do matplotlib pra janela
    interativa) e so devolve o controle quando a janela e fechada ou o
    replay termina.

    Devolve True se conseguiu abrir a interface, False se o matplotlib (ou
    o backend com janela, tkinter) nao estava disponivel - nesse caso quem
    chamou deve continuar so pelo console, sem quebrar o programa.
    """
    try:
        import matplotlib
        matplotlib.use("TkAgg")   
        import matplotlib.pyplot as plt
        import matplotlib.animation as animation
    except ImportError:
        print("\n[interface] matplotlib (ou o backend com janela / tkinter) "
              "nao esta disponivel - seguindo so com o console. Para "
              "habilitar: pip install matplotlib   "
              "(no Linux pode precisar tambem 'sudo apt install python3-tk')")
        return False

    plt.rcParams["toolbar"] = "None"   

    COR_FUNDO = "#FFFFFF"
    COR_PAINEL = "#FFFFFF"
    COR_TEXTO = "#111111"
    COR_TEXTO_SUAVE = "#282828"
    COR_GRADE = "#C5C5C5"
    COR_ONDA = "#00B52A"
    COR_ALFA = "#FF00D4"
    COR_PWM = "#095BFA"
    COR_PWM_FUNDO = "#D1D1D1"
    COR_LIMIAR_RELAX = "#0048FF"
    COR_LIMIAR_CONC = "#F32626"

    def estilizar_eixo(ax):
        ax.set_facecolor(COR_PAINEL)
        for borda in ax.spines.values():
            borda.set_color("#AAAAAA")
            borda.set_linewidth(0.85)
        ax.tick_params(colors=COR_TEXTO, labelsize=10)
        ax.title.set_color(COR_TEXTO)
        ax.xaxis.label.set_color(COR_TEXTO)
        ax.yaxis.label.set_color(COR_TEXTO)

    fig = plt.figure(figsize=(16, 9), facecolor=COR_FUNDO)
    try:
        fig.canvas.manager.set_window_title("EEG ao vivo - TCC")
    except Exception:
        pass

    fig.suptitle("Monitoramento da Cadeira de Rodas em Tempo Real",
                 color=COR_TEXTO, fontsize=22, fontweight="bold", y=0.987)
    texto_tempo = fig.text(0.975, 0.988, "00:00", color=COR_TEXTO,
                           fontsize=16, fontweight="bold", ha="right", va="top")
    texto_motor_status = fig.text(0.975, 0.950, "● sem motor", color="#777777",
                                  fontsize=14, ha="right", va="top")

    grade = fig.add_gridspec(3, 1, height_ratios=[2.0, 1.65, 1.45],
                             hspace=0.72, top=0.875, bottom=0.095,
                             left=0.08, right=0.975)

    ax_onda = fig.add_subplot(grade[0, 0])
    estilizar_eixo(ax_onda)
    glow_onda, = ax_onda.plot([], [], color=COR_ONDA, linewidth=7.5,
                              alpha=0.10, solid_capstyle="round")
    linha_onda, = ax_onda.plot([], [], color=COR_ONDA, linewidth=3.5,
                               solid_capstyle="round")
    ponto_glow, = ax_onda.plot([], [], marker="o", markersize=15,
                               color=COR_ONDA, alpha=0.18, linestyle="none")
    ponto_atual, = ax_onda.plot([], [], marker="o", markersize=7,
                                color=COR_ONDA, markeredgecolor=COR_FUNDO,
                                markeredgewidth=1.2, linestyle="none")
    ax_onda.set_ylabel("sinal bruto filtrado", fontsize=11, fontweight="bold")
    ax_onda.grid(color=COR_GRADE, alpha=0.85, linewidth=0.8)
    ax_onda.set_title("Onda ao vivo", loc="left", fontsize=13,
                      fontweight="bold", pad=10)
    ax_onda.tick_params(labelbottom=False)

    ax_alfa = fig.add_subplot(grade[1, 0])
    estilizar_eixo(ax_alfa)
    ax_alfa.axhspan(LIMIAR_RELAX_BAIXO, LIMIAR_RELAX_ALTO,
                    color="#E9E9E9", alpha=0.40, zorder=1)
    ax_alfa.axhline(LIMIAR_RELAX_ALTO, color=COR_LIMIAR_RELAX,
                    linestyle="--", linewidth=1.7, zorder=2,
                    label=f"limiar relax = {LIMIAR_RELAX_ALTO:.3f}")
    ax_alfa.axhline(LIMIAR_RELAX_BAIXO, color=COR_LIMIAR_CONC,
                    linestyle="--", linewidth=1.7, zorder=2,
                    label=f"limiar conc = {LIMIAR_RELAX_BAIXO:.3f}")
    linha_alfa, = ax_alfa.plot([], [], color=COR_ALFA, linewidth=3.7,
                                solid_capstyle="round", zorder=3)
    ponto_alfa, = ax_alfa.plot([], [], marker="o", markersize=8,
                               color=COR_ALFA, markeredgecolor=COR_FUNDO,
                               markeredgewidth=1.0, linestyle="none", zorder=4)
    ax_alfa.set_ylabel("alfa relativa\n(suavizada)", fontsize=11,
                       fontweight="bold")
    ax_alfa.set_xlabel("tempo (s)", fontsize=11, fontweight="bold")
    ax_alfa.grid(color=COR_GRADE, alpha=0.85, linewidth=0.8, zorder=0)
    ax_alfa.set_title("Sinal de decisão (o que controla os motores)", loc="left",
                      fontsize=13, fontweight="bold", pad=10)

    texto_estado = ax_alfa.text(
        1.0, 1.09, "AGUARDANDO...", transform=ax_alfa.transAxes,
        ha="right", va="bottom", fontsize=12, fontweight="bold",
        color="#555555", clip_on=False,
        bbox=dict(boxstyle="round,pad=0.35", facecolor="#F1F1F1",
                  edgecolor="#999999", linewidth=1.5),
    )
    ax_alfa.legend(loc="upper right", fontsize=9, frameon=True,
                   facecolor=COR_FUNDO, edgecolor="none", labelcolor=COR_TEXTO)

    ax_pwm = fig.add_subplot(grade[2, 0])
    estilizar_eixo(ax_pwm)
    ax_pwm.set_ylim(0, PWM_MAX)
    ax_pwm.set_yticks([0, 51, 102, 153, 204, 255])
    ax_pwm.set_ylabel("PWM", fontsize=11, fontweight="bold")
    ax_pwm.set_xlabel("tempo (s)", fontsize=11, fontweight="bold")
    ax_pwm.grid(color=COR_GRADE, alpha=0.85, linewidth=0.8, zorder=0)
    ax_pwm.set_title("PWM enviado aos motores", loc="left", fontsize=13,
                     fontweight="bold", pad=10)

    texto_pwm = ax_pwm.text(
        1.0, 1.09, "0/255 (0%)", transform=ax_pwm.transAxes,
        ha="right", va="bottom", fontsize=12, fontweight="bold",
        color="#103DB4", clip_on=False,
        bbox=dict(boxstyle="round,pad=0.35", facecolor="#F0F5FF",
                  edgecolor="#536D9A", linewidth=1.5),
    )
    qtd_barras = max(1, int(JANELA_ALFA_S / INTERVALO_PRINT_S))
    largura_barra = INTERVALO_PRINT_S * 0.84
    colunas_pwm = ax_pwm.bar([0.0] * qtd_barras, [0] * qtd_barras,
                             width=largura_barra, color=COR_PWM,
                             edgecolor="none", align="center", zorder=3)
    for coluna in colunas_pwm:
        coluna.set_visible(False)

    def desenhar(_frame):
        dados = estado_ao_vivo.copia()

        if dados["tempos_onda"]:
            linha_onda.set_data(dados["tempos_onda"], dados["onda"])
            glow_onda.set_data(dados["tempos_onda"], dados["onda"])
            minimo, maximo = min(dados["onda"]), max(dados["onda"])
            margem = max(1.0, 0.1 * (maximo - minimo))
            ax_onda.set_ylim(minimo - margem, maximo + margem)
            ultimo_t, ultimo_v = dados["tempos_onda"][-1], dados["onda"][-1]
            ax_onda.set_xlim(dados["tempos_onda"][0], ultimo_t + 0.12)
            ponto_glow.set_data([ultimo_t], [ultimo_v])
            ponto_atual.set_data([ultimo_t], [ultimo_v])

        if dados["tempos_alfa_tela"]:
            linha_alfa.set_data(dados["tempos_alfa_tela"], dados["serie_alfa"])
            ax_alfa.set_xlim(dados["tempos_alfa_tela"][0], dados["tempos_alfa_tela"][-1] + 0.3)
            minimo_a = min(min(dados["serie_alfa"]), LIMIAR_RELAX_BAIXO)
            maximo_a = max(max(dados["serie_alfa"]), LIMIAR_RELAX_ALTO)
            margem_a = max(0.02, 0.15 * (maximo_a - minimo_a))
            ax_alfa.set_ylim(minimo_a - margem_a, maximo_a + margem_a)
            ultimo_ta = dados["tempos_alfa_tela"][-1]
            ultimo_va = dados["serie_alfa"][-1]
            ponto_alfa.set_data([ultimo_ta], [ultimo_va])

        pwm = dados["pwm"]
        percentual_pwm = 100 * pwm / PWM_MAX
        texto_pwm.set_text(f"{pwm}/{PWM_MAX} ({percentual_pwm:.0f}%)")
        if dados["tempos_alfa_tela"]:
            ax_pwm.set_xlim(ax_alfa.get_xlim())
        elif dados["tempos_pwm"]:
            ax_pwm.set_xlim(max(0, dados["tempos_pwm"][-1] - JANELA_ALFA_S),
                            dados["tempos_pwm"][-1] + 0.3)
        for i, coluna in enumerate(colunas_pwm):
            if i < len(dados["serie_pwm"]):
                coluna.set_x(dados["tempos_pwm"][i] - largura_barra / 2)
                coluna.set_height(dados["serie_pwm"][i])
                coluna.set_visible(True)
            else:
                coluna.set_visible(False)

        if dados["estado_relax"] == "ALTO":
            rotulo_estado, cor_estado, fundo_estado = (
                "RELAXAMENTO", "#0048B5", "#EAF1FF")
        elif dados["estado_relax"] == "BAIXO":
            rotulo_estado, cor_estado, fundo_estado = (
                "CONCENTRACAO", COR_LIMIAR_CONC, "#FFF0F0")
        else:
            rotulo_estado, cor_estado, fundo_estado = (
                "AGUARDANDO...", "#555555", "#F1F1F1")
        texto_estado.set_text(rotulo_estado)
        texto_estado.set_color(cor_estado)
        texto_estado.get_bbox_patch().set_edgecolor(cor_estado)
        texto_estado.get_bbox_patch().set_facecolor(fundo_estado)

        decorridos = int(time.time() - estado_ao_vivo.t0)
        mm, ss = divmod(decorridos, 60)
        texto_tempo.set_text(f"{mm:02d}:{ss:02d}")

        if dados["motor_conectado"]:
            texto_motor_status.set_text("●  motor conectado")
            texto_motor_status.set_color("#078A24")
        else:
            texto_motor_status.set_text("●  sem motor")
            texto_motor_status.set_color("#777777")

        if player.terminou or parar_evento.is_set():
            anim.event_source.stop()
            plt.close(fig)

        return (linha_onda, glow_onda, ponto_glow, ponto_atual, linha_alfa,
                ponto_alfa, texto_pwm, *colunas_pwm, texto_tempo,
                texto_motor_status, texto_estado)

    def ao_fechar(_evento):

        parar_evento.set()

    fig.canvas.mpl_connect("close_event", ao_fechar)

    banner_pausa = fig.text(
        0.5, 0.5, "PAUSADO — espaço para continuar", fontsize=16,
        fontweight="bold", color=COR_TEXTO, ha="center", va="center",
        bbox=dict(boxstyle="round,pad=0.6", facecolor=COR_PAINEL,
                 edgecolor=COR_TEXTO_SUAVE, alpha=0.95),
        visible=False, zorder=10,
    )
    fig.text(0.02, 0.012, "espaço = pausar/retomar a tela", fontsize=12,
             color=COR_TEXTO_SUAVE, ha="left", va="bottom")

    pausado = False
    timer_fade = None
    fade_inicio = 0.0

    def atualizar_fade_pausa():
        nonlocal timer_fade
        decorrido = time.time() - fade_inicio

        if decorrido < DURACAO_ESPERA_PAUSA_S:
            return  

        progresso = (decorrido - DURACAO_ESPERA_PAUSA_S) / DURACAO_FADE_PAUSA_S
        if progresso >= 1.0:
            banner_pausa.set_visible(False)
            banner_pausa.set_alpha(1.0)  
            if timer_fade is not None:
                timer_fade.stop()
                timer_fade = None
        else:
            banner_pausa.set_alpha(1.0 - progresso)

        fig.canvas.draw_idle()

    def tecla_pressionada(evento):
        nonlocal pausado, timer_fade, fade_inicio
        if evento.key != " ":
            return
        if anim.event_source is None:
            return

        if not pausado:

            pausado = True
            anim.pause()
            banner_pausa.set_alpha(1.0)
            banner_pausa.set_visible(True)
            fade_inicio = time.time()
            if timer_fade is not None:
                timer_fade.stop()
            timer_fade = fig.canvas.new_timer(interval=INTERVALO_FADE_MS)
            timer_fade.add_callback(atualizar_fade_pausa)
            timer_fade.start()
        else:

            pausado = False
            if timer_fade is not None:
                timer_fade.stop()
                timer_fade = None
            banner_pausa.set_visible(False)
            banner_pausa.set_alpha(1.0)
            anim.resume()

        fig.canvas.draw_idle()

    fig.canvas.mpl_connect("key_press_event", tecla_pressionada)

    anim = animation.FuncAnimation(
        fig, desenhar, interval=TAXA_ATUALIZACAO_TELA_MS, cache_frame_data=False,
    )
    plt.show()   
    return True

def loop_controle(motor, readers, parar_evento, tempo_por_estado_conc,
                  tempo_por_estado_relax, player, estado_ao_vivo=None):
    """E o MESMO loop que antes ficava direto dentro do main() - a unica
    diferenca de comportamento e que agora tambem para se parar_evento for
    sinalizado (antes so olhava pro player.terminou; isso permite a janela
    grafica ser fechada e o programa encerrar de forma limpa). Quando
    estado_ao_vivo e passado (MOSTRAR_INTERFACE=True), publica os valores
    calculados pra tela ler - isso e so um "espelho" do que ja e impresso
    no console, nao influencia o calculo de nada."""
    classif_concentracao = ClassificadorFixo(LIMIAR_CONC_ALTO, LIMIAR_CONC_BAIXO)
    classif_relaxamento = ClassificadorFixo(LIMIAR_RELAX_ALTO, LIMIAR_RELAX_BAIXO)
    ema_alfa_conc = EMA(EMA_ALFA)
    ema_alfa_relax = EMA(EMA_ALFA)

    ultimo_timestamp_alfa = None
    alfa_suave_conc = alfa_suave_relax = None
    estado_conc = estado_relax = "neutro"

    LINHAS_ENTRE_CABECALHOS = 20
    contador_linhas = 0

    def imprimir_cabecalho():
        print(f"{'CONCENTRACAO':>13} | {'estado':>10}   ||   "
              f"{'RELAXAMENTO':>13} | {'estado':>10}")
        print("-" * 62)

    imprimir_cabecalho()

    while not player.terminou and not parar_evento.is_set():
        time.sleep(INTERVALO_PRINT_S)

        alfa = readers["alfa"].last_value
        timestamp = readers["alfa"].last_update_time
        if alfa is None:
            continue

        if timestamp != ultimo_timestamp_alfa:
            ultimo_timestamp_alfa = timestamp
            alfa_suave_conc = ema_alfa_conc.atualizar(-alfa)
            alfa_suave_relax = ema_alfa_relax.atualizar(alfa)
            estado_conc = classif_concentracao.atualizar(alfa_suave_conc)
            estado_relax = classif_relaxamento.atualizar(alfa_suave_relax)

        tempo_por_estado_conc[estado_conc] += INTERVALO_PRINT_S
        tempo_por_estado_relax[estado_relax] += INTERVALO_PRINT_S

        texto_pwm = ""
        pwm = None
        if motor is not None:
            pwm = motor.atualizar(alfa_suave_relax)
            texto_pwm = f"   ||   PWM {pwm:3d}"

        print(f"CONC {alfa_suave_conc:13.4f} | {estado_conc:>10}   ||   "
              f"RELAX {alfa_suave_relax:13.4f} | {estado_relax:>10}{texto_pwm}")

        if estado_ao_vivo is not None:
            if MODO_CONTROLE == "relaxamento":
                segundos_ativo = tempo_por_estado_relax["ALTO"]
            else:
                segundos_ativo = tempo_por_estado_conc["BAIXO"]
            segundos_total = sum(tempo_por_estado_relax.values())

            estado_ao_vivo.atualizar(
                pwm=pwm if pwm is not None else 0,
                estado_relax=estado_relax,
                estado_conc=estado_conc,
                alfa_suave_relax=alfa_suave_relax,
                alfa_suave_conc=alfa_suave_conc,
                motor_conectado=(motor.conectado if motor is not None else False),
                segundos_ativo=segundos_ativo,
                segundos_total=segundos_total,
            )
            instante_tela = time.time() - estado_ao_vivo.t0
            estado_ao_vivo.adicionar_ponto_alfa(
                instante_tela, alfa_suave_relax
            )
            estado_ao_vivo.adicionar_ponto_pwm(
                instante_tela, pwm if pwm is not None else 0
            )

        contador_linhas += 1
        if contador_linhas % LINHAS_ENTRE_CABECALHOS == 0:
            imprimir_cabecalho()

    parar_evento.set()

def main():
    print(f"\n=== MODO AO VIVO (replay de '{ARQUIVO_REPLAY_AO_VIVO}') ===\n")

    motor = None
    if ENVIAR_PARA_ARDUINO:
        if VELOCIDADE_REPLAY != 1.0:
            print(f"[motor] AVISO: VELOCIDADE_REPLAY={VELOCIDADE_REPLAY}x - com "
                  f"motor ligado use 1.0, senao os comandos saem muito mais "
                  f"rapido que o tempo real e o motor nao acompanha.")
        motor = ControleMotorSerial(PORTA_SERIAL, BAUD_SERIAL)

    player = CSVPlayer(ARQUIVO_REPLAY_AO_VIVO, velocidade=VELOCIDADE_REPLAY)
    readers = player.readers()
    player.start()

    parar_evento = threading.Event()
    t_piscada = threading.Thread(
        target=thread_deteccao_piscada,
        args=(readers["bruto"], parar_evento),
        daemon=True,
    )
    t_piscada.start()

    tempo_por_estado_conc = {"ALTO": 0.0, "BAIXO": 0.0, "neutro": 0.0}
    tempo_por_estado_relax = {"ALTO": 0.0, "BAIXO": 0.0, "neutro": 0.0}

    estado_ao_vivo = None
    if MOSTRAR_INTERFACE:
        tam_janela_onda = max(1, int(JANELA_ONDA_S / TAXA_ATUALIZACAO_ONDA_S))
        tam_janela_alfa = max(1, int(JANELA_ALFA_S / INTERVALO_PRINT_S))
        estado_ao_vivo = EstadoAoVivo(tam_janela_onda, tam_janela_alfa)
        t_coletor_onda = threading.Thread(
            target=thread_coletor_onda,
            args=(readers["bruto"], estado_ao_vivo, parar_evento, TAXA_ATUALIZACAO_ONDA_S),
            daemon=True,
        )
        t_coletor_onda.start()

    t_controle = threading.Thread(
        target=loop_controle,
        args=(motor, readers, parar_evento, tempo_por_estado_conc,
              tempo_por_estado_relax, player, estado_ao_vivo),
        daemon=True,
    )
    t_controle.start()

    try:
        if estado_ao_vivo is not None:
            interface_abriu = rodar_interface_ao_vivo(estado_ao_vivo, parar_evento, player)
            if not interface_abriu:
                t_controle.join()   
        else:
            t_controle.join()
    except KeyboardInterrupt:
        print("\nEncerrando...")
    finally:
        parar_evento.set()
        player.stop()
        t_controle.join(timeout=2.0)
        if motor is not None:
            motor.parar()   

        print("\n=== RESUMO ===")
        print(f"Concentracao -> ALTO: {tempo_por_estado_conc['ALTO']:.1f}s   "
              f"BAIXO: {tempo_por_estado_conc['BAIXO']:.1f}s   "
              f"neutro: {tempo_por_estado_conc['neutro']:.1f}s")
        print(f"Relaxamento  -> ALTO: {tempo_por_estado_relax['ALTO']:.1f}s   "
              f"BAIXO: {tempo_por_estado_relax['BAIXO']:.1f}s   "
              f"neutro: {tempo_por_estado_relax['neutro']:.1f}s")

        if GERAR_GRAFICO_AO_FINAL:
            serie_alfa, tempos_alfa, serie_valida, duracao = player.series_para_grafico()
            gerar_grafico_percentual(ARQUIVO_REPLAY_AO_VIVO, serie_alfa,
                                     tempos_alfa, serie_valida, duracao)

if __name__ == "__main__":
    main()

