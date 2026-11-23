# TCC B.R.A.I.N. — Bioplataforma de Reabilitação Assistida por Interface Neural
Repositório oficial dos códigos-fonte desenvolvidos durante o Trabalho de Conclusão de Curso do projeto B.R.A.I.N., desenvolvido no Instituto Federal do Paraná (IFPR), Campus Campo Largo.

## Sobre o projeto
O B.R.A.I.N. consiste no desenvolvimento de uma plataforma experimental de reabilitação assistida por interface neural, utilizando sinais de eletroencefalografia (EEG) para controlar um protótipo de cadeira de rodas em escala reduzida.
O sistema utiliza sinais cerebrais captados pelo dispositivo NeuroSky MindWave Mobile 2, processados computacionalmente para identificar padrões associados aos estados de concentração e relaxamento. A partir dessa classificação, são gerados comandos enviados via Bluetooth a um microcontrolador ESP32, responsável pelo acionamento dos motores.
Atualmente utilizamos sinais previamente gravados, pois o dispositivo de captação apresentou falhas que impossibilitaram continuar com seu uso. Ainda assim, toda a arquitetura do projeto será relatada

## Arquitetura do sistema
O funcionamento do sistema envolve as seguintes etapas:
1. Aquisição dos sinais: captação dos sinais EEG por meio do NeuroSky MindWave Mobile 2. <br>
2. Processamento: utilização do OpenViBE e de algoritmos desenvolvidos em Python para processamento e análise dos sinais.<br>
3. Classificação: identificação dos estados de concentração e relaxamento a partir de parâmetros extraídos dos sinais.<br>
4. Comunicação: transmissão dos comandos de controle via Bluetooth.<br>
5. Acionamento: interpretação dos comandos pelo ESP32 e controle dos motores por modulação por largura de pulso.<br>

## Tecnologias utilizadas
• Python <br>
• ESP32<br>
• Arduino / C++<br>
• OpenViBE<br>
• NeuroSky MindWave Mobile 2<br>
• Comunicação Bluetooth<br>

## Organização do repositório
• python/: códigos de aquisição, processamento, comunicação e interface. <br>
• esp32/: firmware e códigos de controle do microcontrolador.<br>
• openvibe/: arquivos e configurações relacionados ao ambiente OpenViBE.<br>
• documentacao/: documentação técnica e informações complementares.<br>
• resultados/: resultados experimentais e materiais demonstrativos.<br>

## Finalidade

Este repositório tem finalidade acadêmica e documental, reunindo os códigos-fonte utilizados no desenvolvimento do projeto e permitindo sua consulta, análise e eventual reprodução por outros pesquisadores.

## Instituição
Instituto Federal do Paraná (IFPR)<br>
Campus Campo Largo
