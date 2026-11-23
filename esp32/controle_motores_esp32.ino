/* =====================================================================
/*
 * B.R.A.I.N. - Bioplataforma de Reabilitação
 * Assistida por Interface Neural
 *
 * Arquivo: controle_motores_esp32.ino
 *
 * Descrição:
 * Firmware desenvolvido para o microcontrolador
 * ESP32, responsável por receber os comandos
 * transmitidos via Bluetooth e controlar o
 * acionamento dos motores por meio de PWM.
 *
 * Hardware:
 * - ESP32
 * - Driver de motores
 * - Micromotores N20
 *
 * Projeto: Trabalho de Conclusão de Curso
 * Instituição: IFPR - Campus Campo Largo
 * Em algumas linhas desse código está citado "Arduino" pois aproveitamos o código que já tínhamos para utilizar com o ESP32, então não há preocupação quanto a isso
 */
   arduino_motor.ino  -  receptor de velocidade via serial (projeto EEG)


   Recebe do Python comandos no formato  "V<0-255>\n"  (ex: "V180\n")
   e aplica esse valor como PWM no pino PINO_PWM.


   Comandos aceitos:
     V<n>   define o PWM (n de 0 a 255). Valores fora da faixa sao presos
            nos limites. Ex: "V0" = parado, "V255" = maximo.
     T      RAMPA DE TESTE: sobe o PWM de 0 a 255 devagar, imprimindo o
            valor atual. Use pra descobrir o PWM_MIN do SEU motor (veja
            "COMO DESCOBRIR O PWM_MIN" abaixo).
     S      parada imediata (mesma coisa que V0).
     ?      imprime o estado atual.


   Qualquer outra coisa que chegue e ignorada em silencio, entao lixo na
   linha nao trava o sketch.


   ---------------------------------------------------------------------
   LIGACAO
   ---------------------------------------------------------------------
   TESTE COM LED (o que voce vai fazer agora):
       PINO_PWM (9) --> resistor 220-330 ohm --> LED (perna longa)
       LED (perna curta) --> GND
       Nada mais e necessario. O LED acende proporcional ao PWM.


   MOTOR DC (depois):
       NAO ligue o motor direto no pino do ESP. O pino da ~20-40mA e
       um motor puxa muito mais - voce queima a porta. Use um driver:


       - Ponte H (L298N, L293D, DRV8871, TB6612...):
           PINO_PWM  -> entrada ENA / PWM do driver
           PINO_IN1  -> IN1     PINO_IN2 -> IN2   (definem o sentido)
           GND do ESP  -> GND do driver  (TERRA COMUM, obrigatorio)
           fonte externa (pilhas/fonte) -> alimentacao de motor do driver


       - Ou um MOSFET/transistor com diodo de roda-livre em paralelo com
         o motor, se o giro for sempre no mesmo sentido.


       Se voce usar ponte H, descomente USAR_PONTE_H abaixo.


   ---------------------------------------------------------------------
   COMO DESCOBRIR O PWM_MIN (aquele do Python)
   ---------------------------------------------------------------------
   Motor DC nao sai do lugar com PWM baixo (atrito estatico). Entao:
     1. Monte o motor ja preso como vai ficar no projeto (com a carga!
        o valor muda se ele estiver girando solto no ar).
     2. Abra o Monitor Serial da IDE em 115200, "Nova linha" ligado.
     3. Digite T e Enter. O PWM vai subir de 5 em 5 a cada 400ms.
     4. Anote o numero impresso no instante em que o eixo COMECA a girar
        de forma estavel (nao so tremer/zumbir).
     5. Coloque esse numero (com uma folga de +5) no PWM_MIN do Python.
     6. Feche o Monitor Serial antes de rodar o Python - so um programa
        por vez pode segurar a porta COM.


   ---------------------------------------------------------------------
   OBSERVACOES
   ---------------------------------------------------------------------
   - O Arduino REINICIA quando a serial abre. O Python ja espera 2s
     (ESPERA_RESET_ARDUINO_S) por causa disso.
   - A rampa de aceleracao (RAMPA_MAX_POR_ATUALIZACAO) ja e feita no
     Python. Aqui o valor recebido e aplicado direto.
   - WATCHDOG: se nao chegar nenhum comando por TIMEOUT_MS, o PWM vai a
     zero sozinho. Isso evita o motor ficar girando pra sempre se o
     Python fechar, travar ou o cabo cair. O Python manda a cada ~0.2s,
     entao 1000ms e uma margem confortavel.
   ===================================================================== */


// ----------------------------- CONFIG -----------------------------


const uint8_t PINO_PWM = 9;      // no UNO/Nano: 3,5,6,9,10,11 fazem PWM


// Descomente a linha abaixo se estiver usando uma ponte H com pinos de
// sentido (IN1/IN2). Com LED, deixe comentado.
// #define USAR_PONTE_H


#ifdef USAR_PONTE_H
const uint8_t PINO_IN1 = 7;
const uint8_t PINO_IN2 = 8;
#endif


const unsigned long BAUD       = 115200;  // igual ao BAUD_SERIAL do Python
const unsigned long TIMEOUT_MS = 1000;    // watchdog (0 desativa)


const bool ECO_SERIAL = true;    // imprime cada valor recebido. Util pra
                                 // depurar; se poluir demais, ponha false.


// rampa de teste (comando T)
const uint8_t  PASSO_TESTE    = 5;
const uint16_t INTERVALO_TESTE_MS = 400;


// ---------------------------- ESTADO ------------------------------


char    buffer[16];
uint8_t tamBuffer = 0;


uint8_t pwmAtual = 0;
unsigned long ultimoComandoMs = 0;


// ---------------------------- FUNCOES -----------------------------


void aplicarPWM(uint8_t valor) {
  pwmAtual = valor;
  analogWrite(PINO_PWM, pwmAtual);
}


void processarComando(const char *cmd) {
  if (cmd[0] == '\0') return;


  ultimoComandoMs = millis();


  switch (cmd[0]) {


    case 'V':
    case 'v': {
      // atoi ignora espacos e para no primeiro caractere invalido;
      // "V" sozinho vira 0, o que e uma parada segura.
      long v = atol(cmd + 1);
      if (v < 0)   v = 0;
      if (v > 255) v = 255;
      aplicarPWM((uint8_t)v);
      if (ECO_SERIAL) {
        Serial.print(F("PWM="));
        Serial.println(pwmAtual);
      }
      break;
    }


    case 'S':
    case 's':
      aplicarPWM(0);
      Serial.println(F("parado"));
      break;


    case 'T':
    case 't':
      rampaDeTeste();
      break;


    case '?':
      Serial.print(F("PWM atual = "));
      Serial.println(pwmAtual);
      break;


    default:
      // lixo na linha: ignora
      break;
  }
}


void rampaDeTeste() {
  Serial.println(F("--- rampa de teste: anote o PWM em que o motor comeca a girar"));
  Serial.println(F("--- (mande qualquer caractere para abortar)"));


  for (uint16_t v = 0; v <= 255; v += PASSO_TESTE) {
    aplicarPWM((uint8_t)v);
    Serial.print(F("PWM = "));
    Serial.println(v);


    unsigned long t0 = millis();
    while (millis() - t0 < INTERVALO_TESTE_MS) {
      if (Serial.available()) {
        while (Serial.available()) Serial.read();   // limpa a linha
        aplicarPWM(0);
        Serial.println(F("--- rampa abortada, PWM = 0"));
        ultimoComandoMs = millis();
        return;
      }
    }
  }


  aplicarPWM(0);
  Serial.println(F("--- fim da rampa, PWM = 0"));
  ultimoComandoMs = millis();
}


void lerSerial() {
  while (Serial.available()) {
    char c = Serial.read();


    if (c == '\n' || c == '\r') {
      buffer[tamBuffer] = '\0';
      processarComando(buffer);
      tamBuffer = 0;
    } else if (tamBuffer < sizeof(buffer) - 1) {
      buffer[tamBuffer++] = c;
    } else {
      // comando absurdamente longo = ruido. Descarta e recomeca.
      tamBuffer = 0;
    }
  }
}


// ------------------------- SETUP / LOOP ---------------------------


void setup() {
  pinMode(PINO_PWM, OUTPUT);
  aplicarPWM(0);


#ifdef USAR_PONTE_H
  pinMode(PINO_IN1, OUTPUT);
  pinMode(PINO_IN2, OUTPUT);
  digitalWrite(PINO_IN1, HIGH);   // sentido fixo (inverta os dois para
  digitalWrite(PINO_IN2, LOW);    // girar pro outro lado)
#endif


  Serial.begin(BAUD);
  ultimoComandoMs = millis();


  Serial.println(F("pronto - aguardando comandos V<0-255>"));
}


void loop() {
  lerSerial();


  if (TIMEOUT_MS > 0 && pwmAtual > 0 &&
      (millis() - ultimoComandoMs) > TIMEOUT_MS) {
    aplicarPWM(0);
    Serial.println(F("timeout: nenhum comando recebido, motor parado"));
  }
}



