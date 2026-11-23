# B.R.A.I.N. — Bioplataforma de Reabilitação Assistida por Interface Neural
Repositório destinado ao armazenamento e à disponibilização dos códigos-fonte desenvolvidos durante o Trabalho de Conclusão de Curso (TCC) do projeto B.R.A.I.N., realizado no Instituto Federal do Paraná (IFPR), Campus Campo Largo.

## 1. Sobre o projeto
O B.R.A.I.N. (Bioplataforma de Reabilitação Assistida por Interface Neural) consiste no desenvolvimento de uma plataforma experimental de controle de uma cadeira de rodas em escala reduzida por meio de sinais de eletroencefalografia (EEG).

A proposta utiliza sinais cerebrais associados aos estados de concentração e relaxamento para gerar comandos de movimentação, buscando explorar a aplicação de interfaces cérebro-computador em tecnologias assistivas.

O sistema integra aquisição de sinais EEG, processamento computacional, classificação de estados mentais e acionamento de motores, utilizando comunicação sem fio entre os módulos de processamento e controle.

## 2. Arquitetura do sistema
O funcionamento da plataforma envolve diferentes etapas: 

• Aquisição dos sinais EEG: utilização do dispositivo NeuroSky MindWave Mobile 2 para captação dos sinais cerebrais.

• Processamento dos sinais: análise dos dados EEG, com utilização de parâmetros relacionados à atividade das ondas cerebrais e aplicação de técnicas de suavização.

• Classificação: identificação dos estados de concentração e relaxamento por meio de limiares e mecanismos de histerese.

• Geração e transmissão dos comandos: conversão dos resultados do processamento em comandos de controle, transmitidos via Bluetooth.

• Acionamento dos motores: interpretação dos comandos pelo microcontrolador ESP32 e controle dos motores por meio de modulação por largura de pulso (PWM).

• Na implementação experimental adotada, os sinais EEG previamente gravados são utilizados como entrada para o processamento computacional e geração dos comandos de controle.

## 3. Tecnologias e ferramentas utilizadas

• Python: processamento dos sinais EEG, análise de dados, geração de gráficos, classificação e comunicação.

• ESP32: microcontrolador responsável pelo recebimento dos comandos e controle dos motores.

• Arduino IDE / C++: desenvolvimento e programação do firmware do microcontrolador.

• OpenViBE: ambiente utilizado durante as etapas de aquisição e experimentação com sinais EEG.

• NeuroSky MindWave Mobile 2: dispositivo utilizado para aquisição dos sinais de eletroencefalografia.

• Bluetooth: comunicação sem fio entre os módulos do sistema.

## 4. Organização do repositório
Os arquivos estão organizados de acordo com suas respectivas funções no desenvolvimento do projeto.

**python/**

Reúne os códigos desenvolvidos em Python, divididos em três categorias:

- tentativas_comunicacao/: implementações experimentais destinadas a estabelecer a comunicação direta com o headset NeuroSky MindWave Mobile 2, incluindo captura e visualização dos sinais, transmissão via TCP e utilização do protocolo Lab Streaming Layer (LSL).

- analise_experimental/: scripts utilizados na análise dos sinais EEG, geração de gráficos e estimativa inicial dos limiares de classificação.

- implementacao_final/: código correspondente à implementação adotada, envolvendo o processamento dos sinais previamente gravados e a transmissão dos comandos ao ESP32.

**esp32/**

Contém o firmware desenvolvido para o microcontrolador ESP32, responsável pela comunicação Bluetooth e pelo controle dos motores da cadeira de rodas por meio de PWM.

## 5. Finalidade do repositório
Este repositório possui finalidade acadêmica e documental, reunindo os códigos-fonte desenvolvidos durante as diferentes etapas do projeto.

Sua disponibilização busca facilitar a consulta, análise e compreensão das soluções implementadas, além de contribuir para a documentação e continuidade de pesquisas relacionadas à aplicação de interfaces cérebro-computador em tecnologias assistivas.

Os códigos experimentais são mantidos para documentar as abordagens investigadas durante o desenvolvimento, enquanto os diretórios de implementação final identificam as soluções efetivamente adotadas no sistema.

## 6. Instituição e equipe

Instituição: Instituto Federal do Paraná (IFPR)<br>
Campus: Campo Largo<br>
Curso: Técnico em Automação Industrial Integrado ao Ensino Médio<br>

Projeto: B.R.A.I.N. — Bioplataforma de Reabilitação Assistida por Interface Neural.

**Integrantes:**
Henrique dos Anjos Frasson, Roberto Massensini, Victor Bonacin Ambrosio

**Orientadores:**
Beatriz dos Santos Pês, Diego Tefili, Marcos Santos Hara

Repositório desenvolvido como parte das atividades do Trabalho de Conclusão de Curso do projeto B.R.A.I.N.
