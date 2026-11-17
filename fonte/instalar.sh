#!/usr/bin/env bash
# Instalação local para Kubuntu/Ubuntu com CUPS 2.x.
set -euo pipefail
export LC_ALL=C
APP_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
fail() { printf '\nErro: %s\n' "$*" >&2; exit 1; }
trap 'printf "\nInstalação interrompida. Corrija o erro acima e execute bash instalar.sh novamente.\n" >&2' ERR
if [[ "$(id -u)" == 0 ]]; then
    fail 'Execute bash instalar.sh com seu usuário do KDE, sem sudo. A senha será solicitada quando necessária.'
fi
[[ -f "$APP_DIR/Etiquetas-MPTII" ]] || fail 'Executável Etiquetas-MPTII não encontrado nesta pasta.'
[[ "$(uname -m)" == x86_64 ]] || fail 'Esta versão portátil requer Linux x86_64.'
command -v sudo >/dev/null || fail 'O comando sudo precisa estar instalado.'
command -v systemctl >/dev/null || fail 'Este instalador requer um sistema com systemd (Kubuntu/Ubuntu).'
# A fila é criada no CUPS local, mesmo que o usuário tenha um servidor remoto definido.
export CUPS_SERVER=localhost
printf 'Etiquetas MPT-II — preparação do computador\nLigue a impressora e conecte-a por USB com um cabo de dados.\n'
missing=()
for package in cups cups-client; do
    if ! command -v dpkg-query >/dev/null || [[ "$(dpkg-query -W -f='${Status}' "$package" 2>/dev/null || true)" != 'install ok installed' ]]; then
        missing+=("$package")
    fi
done
if (( ${#missing[@]} )); then
    command -v apt-get >/dev/null || fail 'Instale CUPS e cups-client com o gerenciador da sua distribuição.'
    printf '\nInstalando CUPS. Esta etapa precisa de internet e senha de administrador.\n'
    sudo apt-get update
    sudo apt-get install -y "${missing[@]}"
fi
for command in lpinfo lpadmin lpstat cupsenable cupsaccept; do
    command -v "$command" >/dev/null || fail "Comando $command ausente após preparar o CUPS."
done
printf '\nAtivando o serviço de impressão…\n'
sudo systemctl enable --now cups
sudo -v
uris=()
# Reconhece os nomes conhecidos desta família. Não escolhe outra impressora USB.
for attempt in 1 2 3; do
    discovery="$(sudo lpinfo -h localhost --include-schemes usb --timeout 10 -v)" || fail 'Não foi possível consultar as impressoras USB no CUPS.'
    mapfile -t uris < <(printf '%s\n' "$discovery" | awk '$1 == "direct" && $2 ~ /^usb:\/\// {uri=$2; lower=tolower(uri); if(lower ~ /cla58|mpt-?ii|mpt-?2|yaen/) print uri}' | sort -u)
    if (( ${#uris[@]} )); then break; fi
    printf '\nImpressora MPT-II/TECH CLA58 não encontrada por USB.\n'
    if (( attempt == 3 )) || [[ ! -t 0 ]]; then
        fail 'Confira a alimentação e o cabo USB de dados. Conecte a impressora e execute novamente o instalador.'
    fi
    read -r -p 'Conecte a impressora e pressione Enter para tentar novamente (Ctrl+C para sair). ' _
done
if (( ${#uris[@]} == 1 )); then
    uri="${uris[0]}"
else
    printf '\nMais de uma impressora compatível encontrada:\n'
    for index in "${!uris[@]}"; do printf '%s) %s\n' "$((index + 1))" "${uris[index]}"; done
    read -r -p 'Número da impressora que será usada na fila MPTII: ' choice
    [[ "$choice" =~ ^[1-9][0-9]?$ ]] || fail 'Seleção inválida.'
    (( choice <= ${#uris[@]} )) || fail 'Seleção fora da lista.'
    uri="${uris[choice - 1]}"
fi
existing="$(lpstat -h localhost -v MPTII 2>/dev/null || true)"
if [[ -n "$existing" ]]; then
    old_uri="${existing#*: }"
    if [[ "$old_uri" != "$uri" ]]; then
        printf '\nA fila MPTII existente aponta para: %s\nNova impressora: %s\n' "$old_uri" "$uri"
        read -r -p 'Atualizar a fila MPTII para esta impressora? [s/N] ' answer
        [[ "$answer" == s || "$answer" == S ]] || fail 'Fila existente preservada. Nenhuma alteração de destino foi feita.'
    fi
fi
printf '\nConfigurando MPTII: %s\n' "$uri"
if ! sudo lpadmin -h localhost -p MPTII -E -v "$uri" -m raw -D 'Etiquetas MPT-II' -o printer-is-shared=false -o job-sheets-default=none,none; then
    fail 'Falha ao criar a fila raw. Verifique a mensagem do CUPS. Este aplicativo requer CUPS com suporte a filas raw (CUPS 2.x).'
fi
sudo cupsenable -h localhost MPTII
sudo cupsaccept -h localhost MPTII
lpstat -h localhost -v MPTII
lpstat -h localhost -p MPTII
printf '\nCriando entrada do KDE para seu usuário…\n'
chmod +x "$APP_DIR/Etiquetas-MPTII"
"$APP_DIR/Etiquetas-MPTII" --install-kde
printf '\nInstalação concluída. Abra Etiquetas MPT-II no menu do KDE.\nFila: MPTII. Nenhuma impressão de teste foi enviada.\nMantenha esta pasta no local atual; se mover, execute o instalador novamente.\n'
