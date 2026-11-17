# Etiquetas MPT-II

Aplicativo desktop para configurar e imprimir etiquetas na impressora térmica **MPT-II / TECH CLA58** pelo USB no Kubuntu. Desenvolvido em Python com Tkinter e Pillow, envia a impressão ao CUPS em formato ESC/POS.

## Recursos

- Configuração de largura, altura, espaço entre etiquetas e ajuste vertical da impressão.
- Perfis com nome para salvar medidas e restaurar o último perfil usado.
- Editor de texto com fonte, alinhamento e negrito.
- Prévia da etiqueta e exportação em PNG.
- Importação de TXT: cada linha não vazia gera uma etiqueta.
- Navegação pela prévia do lote e quantidade de cópias por etiqueta.
- Indicador de presença USB e disponibilidade da fila CUPS.
- Avanço manual do papel com distância aproximada.
- Instalador que prepara o CUPS, configura a fila `MPTII` e cria o atalho no KDE com ícone.

## Compatibilidade

A versão portátil foi gerada para **Kubuntu 26.04 x86_64**. Inclui Python, Tkinter, Pillow e fontes. A compatibilidade com versões anteriores do Linux e outras arquiteturas não é garantida.

A impressão depende do CUPS local com suporte a **filas raw**, como o CUPS 2.x. O computador deve ter conexão USB com a impressora. O identificador observado na unidade usada no desenvolvimento é `6868:0200`, com nome `TECH CLA58`.

Para a instalação automática, são necessários um sistema com `systemd`, o comando `sudo` e um usuário com permissão administrativa. Se os pacotes do CUPS não estiverem instalados, será necessária conexão com a internet.

## Instalação da versão portátil

1. Extraia `Etiquetas-MPTII-Kubuntu-26.04-x86_64.tar.gz`.
2. Mova a pasta `Etiquetas-MPTII` inteira para o local definitivo. Preserve a subpasta `_internal`.
3. Ligue a impressora e conecte-a com um cabo USB de dados.
4. Abra o terminal na pasta extraída e execute:

```bash
bash instalar.sh
```

Execute com seu usuário normal, **sem colocar `sudo` antes do script**. O instalador solicitará a senha quando necessário.

O instalador:

- Instala `cups` e `cups-client`, quando ausentes.
- Ativa o serviço de impressão.
- Procura dispositivos USB identificados como MPT-II, TECH CLA58 ou YAEN, usando o endereço descoberto pelo CUPS.
- Cria ou atualiza a fila local `MPTII` em modo raw, habilitada e sem compartilhamento de rede.
- Cria a entrada **Etiquetas MPT-II** no menu de aplicativos do KDE.

Se houver mais de uma impressora compatível, será necessário escolher o dispositivo. Se uma fila `MPTII` existente apontar para outra impressora, o instalador pedirá confirmação antes de alterar o destino. Ele não muda a impressora padrão do sistema nem envia impressão de teste.

Após instalar, abra **Etiquetas MPT-II** pelo menu do KDE. Se mover a pasta, execute `bash instalar.sh` novamente no novo local para atualizar o atalho.

## Como usar

### Configurar a etiqueta

Informe as medidas em milímetros:

| Campo | Descrição |
| --- | --- |
| Largura | Largura do papel, de 15 a 58 mm. A impressão fica limitada a 48 mm. |
| Altura | Altura da parte adesiva da etiqueta, de 10 a 300 mm. |
| Espaço | Intervalo entre duas etiquetas, de 0 a 20 mm. Use zero para papel contínuo. |
| Ajuste vertical | Deslocamento do texto: positivo desce e negativo sobe. Aceita até ±20 mm, limitado ao espaço disponível na etiqueta. |

O avanço calculado de cada etiqueta é **altura + espaço**. O ajuste vertical move o texto dentro da etiqueta sem alterar esse avanço. Se o texto não couber, o aplicativo solicita a correção antes de imprimir.

A linha verde da prévia indica o início do intervalo; ela não é impressa. A imagem exportada inclui o intervalo em branco.

### Salvar tamanhos

1. Configure as medidas e o ajuste vertical.
2. Digite um nome no campo de perfis.
3. Clique em **Salvar perfil**.

Os tamanhos salvos ficam na lista. Selecionar um perfil aplica as medidas e o torna o perfil restaurado na próxima abertura. Salvar com o mesmo nome atualiza os valores. Após editar as medidas, clique novamente em **Salvar perfil** para guardar as alterações.

Os perfis incluem largura, altura, espaço e ajuste vertical. Conteúdo, fonte e quantidade de cópias não fazem parte do perfil.

Na versão portátil, os dados ficam em `perfis.json`, ao lado do executável. Preserve esse arquivo ao atualizar e copie-o junto com a pasta para levar seus tamanhos a outro computador. A pasta precisa permitir gravação para salvar perfis.

### Imprimir texto ou um lote TXT

Digite o conteúdo no editor ou clique em **Importar TXT**.

- Cada linha não vazia do TXT vira uma etiqueta.
- Linhas vazias e espaços nas bordas são ignorados.
- São aceitos UTF-8, UTF-8 com BOM e, como alternativa, Windows-1252.
- Use **Anterior** e **Próxima** para conferir as etiquetas importadas.
- A quantidade de cópias se aplica a cada linha.
- O limite é de 1.000 etiquetas por lote, incluindo as cópias.
- Todo o lote é validado antes do envio à fila.

Exemplo de TXT:

```text
Café especial · 250 g
Açúcar cristal · 1 kg
Produto artesanal
```

Confira a prévia e comece com uma cópia para ajustar o alinhamento físico. Clique em **Texto manual** para voltar à edição de uma etiqueta.

### Avançar papel

Use **Avançar papel** para expor a etiqueta e facilitar o destaque. O avanço usa quebras de linha e tem distância aproximada, em passos nominais de 4,23 mm. O valor inicial de 12 mm envia três quebras de linha.

### Atalhos

| Atalho | Ação |
| --- | --- |
| `Ctrl+O` | Importar TXT |
| `Ctrl+S` | Salvar perfil |
| `Ctrl+Enter` | Imprimir |

## Limitações conhecidas

- **Sem leitura automática dos intervalos:** o posicionamento é calculado pelas medidas informadas. Alinhe a primeira etiqueta; pode haver desalinhamento acumulado em lotes longos.
- **Sem recuo ou corte automático:** o controle manual disponível é o avanço.
- **Área imprimível de até 384 pontos:** o perfil usa 8 pontos/mm, equivalente a aproximadamente 203 dpi, com 48 mm de impressão em papel de 58 mm.
- **Status limitado:** a presença USB não confirma bateria carregada, tampa fechada ou papel disponível. O envio aceito pelo CUPS não comprova impressão física.
- **Compatibilidade ESC/POS:** o texto é convertido em imagem monocromática usando `GS v 0`. Unidades com firmware diferente precisam de teste físico.
- **Filas raw estão obsoletas no CUPS:** o instalador informa e interrompe a configuração se a versão instalada não aceitar esse modo.

## Estrutura do projeto

```text
.
├── README.md
├── LEIA-ME.txt
├── Etiquetas-MPTII-Kubuntu-26.04-x86_64.tar.gz
└── fonte/
    ├── etiquetas.py
    ├── instalar.sh
    ├── gerar-portatil.sh
    ├── requirements.txt
    ├── icone.png
    ├── fonts/
    │   ├── DejaVuSans.ttf
    │   ├── DejaVuSans-Bold.ttf
    │   └── LICENCA.txt
    ├── test_geometria.py
    ├── test_perfis.py
    └── test_instalador.py
```

## Executar pelo código-fonte

No Kubuntu, instale as dependências e execute a partir da raiz do repositório:

```bash
sudo apt install python3-tk python3-pil python3-pil.imagetk
cd fonte
python3 etiquetas.py
```

Para imprimir, também é necessário ter o CUPS ativo e a fila `MPTII` configurada. O instalador deve ser usado na pasta da distribuição portátil, que contém o executável.

## Gerar a versão portátil

Use Kubuntu 26.04 x86_64 para reproduzir a base de compilação deste pacote:

```bash
sudo apt install python3-venv python3-tk
cd fonte
bash gerar-portatil.sh
```

O script cria um ambiente virtual, instala as versões de Pillow e PyInstaller de `requirements.txt` e gera a pasta:

```text
fonte/dist/Etiquetas-MPTII/
```

O resultado inclui o runtime, as fontes, o ícone e o instalador. O script não cria compactado nem inclui perfis pessoais. O CUPS é preparado no computador de destino pelo instalador.

## Testes

A partir da raiz do repositório:

```bash
python3 -m unittest discover -s fonte -p 'test_*.py'
bash -n fonte/instalar.sh
bash -n fonte/gerar-portatil.sh
```

Os testes cobrem geometria de impressão, persistência de perfis e cenários do instalador com comandos simulados, incluindo dependências ausentes, múltiplas impressoras e preservação de uma fila com outro destino. Não enviam impressões reais nem alteram a configuração do CUPS.

A interface e o executável também foram verificados em uma tela virtual, com envio simulado. A instalação em outro computador e o alinhamento físico precisam ser conferidos no equipamento de destino.

## Solução de problemas

**A impressora não foi encontrada:** confirme que ela está ligada, use um cabo USB de dados e execute o instalador novamente. Para consultar os dispositivos:

```bash
lsusb
sudo lpinfo -h localhost --include-schemes usb -v
```

**O trabalho foi enviado, mas não imprimiu:** consulte a fila e o serviço:

```bash
lpstat -h localhost -p MPTII -l
lpstat -h localhost -v MPTII
systemctl status cups
```

**O atalho abre um caminho antigo:** execute `bash instalar.sh` na pasta portátil que deseja usar.

**Não foi possível salvar um perfil:** verifique a permissão de escrita da pasta e a integridade de `perfis.json`. Faça uma cópia desse arquivo antes de corrigi-lo ou substituí-lo.

## Remover o aplicativo

Remova o atalho do seu usuário:

```bash
rm ~/.local/share/applications/etiquetas-mptii.desktop
```

Se usa `XDG_DATA_HOME` personalizado, remova o arquivo equivalente em `$XDG_DATA_HOME/applications/`.

Se quiser remover também a fila criada pelo instalador:

```bash
sudo lpadmin -h localhost -x MPTII
```

Depois, apague a pasta portátil. Faça uma cópia de `perfis.json` antes se quiser preservar os tamanhos.

## Fontes e referências

As fontes DejaVu distribuídas têm seus termos em [`fonte/fonts/LICENCA.txt`](fonte/fonts/LICENCA.txt).

- [CUPS — configuração de impressoras com lpadmin](https://www.cups.org/doc/man-lpadmin.html)
- [CUPS — descoberta de dispositivos com lpinfo](https://www.cups.org/doc/man-lpinfo.html)
- [Epson — referência ESC/POS para impressão raster](https://download4.epson.biz/sec_pubs/pos/reference_en/escpos/gs_v_0.html)
