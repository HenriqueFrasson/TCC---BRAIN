import serial
import time
import matplotlib.pyplot as plt
from collections import deque
import re

# Porta serial
# time.sleep(1)

tentativa = 1
while True:
    try:
        ser = serial.Serial("COM12", baudrate=57600, timeout=2)
        ser.reset_input_buffer()  # Descarta tudo que já chegou
        ser.reset_output_buffer()  # Descarta dados pendentes de envio (normalmente vazio)
        print("Conectado!")
        break
    except serial.SerialException as e:
        print(f"Tentativa {tentativa} falhou: {e}")
        tentativa += 1
print(ser)
time.sleep(1)
# Buffer de 200 amostras
N = 200
buffer = deque([0] * N, maxlen=N)


# Configuração do gráfico
plt.ion()
fig, ax = plt.subplots()
linha, = ax.plot(buffer)


ax.set_title("Bytes recebidos")
ax.set_xlabel("Amostra")
ax.set_ylabel("Valor")
ax.set_xlim(0, N - 1)
ax.set_ylim(-1200, 1200)


print("Fim da inicialização")
print("Dados recebidos:")
try:


    while True:
        print(" ")
        ser.write(bytes.fromhex("7200000000000000"))
        time.sleep(0.01)


        b = ser.read_all()


        # print(b)
        dados = b.hex()
        # print(dados)
        # eeg = dados[10:14]
        # print(eeg)
        eeg = re.findall(r'aaaa048002([0-9a-fA-F]{4})', dados)
        # print("eeg")
        # print(eeg)
        try:
            if len(b)>0:
                # valor = b[0]          # converte b'\xaa' -> 170
                # valor = int(eeg, 16)
                valor = [int(x, 16) for x in eeg]
                valor = [v - 65536 if v >= 32768 else v for v in valor]
                print(valor)
                for v in valor:
                    buffer.append(v)


                linha.set_ydata(buffer)


                fig.canvas.draw_idle()
                fig.canvas.flush_events()
                plt.pause(0.001)
        except serial.SerialException as e:
            print("{e}")
            break
except KeyboardInterrupt:
    print("\nEncerrando...")


finally:
    ser.close()
    print("Porta serial fechada.")

