ETIQUETAS MPT-II — CÓDIGO-FONTE

etiquetas.py: aplicativo Tkinter, renderização de etiquetas e impressão ESC/POS.
instalar.sh: dependências do CUPS, detecção USB, fila MPTII e atalho KDE.
fonts/ e icone.png: recursos locais do aplicativo.
test_*.py: testes de geometria, perfis e instalador com comandos simulados.

EXECUTAR O FONTE (Kubuntu):
sudo apt install python3-tk python3-pil python3-pil.imagetk
python3 etiquetas.py

TESTES (não enviam impressões reais):
python3 -m unittest discover -s . -p 'test_*.py'
bash -n instalar.sh

GERAR OUTRO EXECUTÁVEL PORTÁTIL:
Use Kubuntu 26.04 x86_64 (a compatibilidade depende da base Linux usada).
sudo apt install python3-venv python3-tk
bash gerar-portatil.sh
A compilação baixa Pillow e PyInstaller nas versões de requirements.txt.
Inclui Python, Tk, Pillow, fontes e ícone em dist/Etiquetas-MPTII.
O instalador usa o CUPS do computador de destino.
Perfis são guardados no arquivo perfis.json ao lado do executável;
preserve-o ao atualizar. A compilação não copia perfis pessoais.
