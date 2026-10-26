#!/bin/sh
set -eu

config_path=${1:-/etc/rpi-cabinet-controller/controller.conf}

if [ ! -r "$config_path" ]; then
    echo "RFComm setup: cannot read $config_path" >&2
    exit 1
fi
if ! command -v rfcomm >/dev/null 2>&1; then
    echo "RFComm setup: rfcomm command is not installed" >&2
    exit 1
fi

# Emit number, device, address, and channel for cabinets that have an address.
awk -F= '
function trim(value) {
    sub(/^[[:space:]]+/, "", value)
    sub(/[[:space:]]+$/, "", value)
    return value
}
{
    sub(/#.*/, "", $0)
    separator = index($0, "=")
    if (separator == 0) next
    key = trim(substr($0, 1, separator - 1))
    value = trim(substr($0, separator + 1))
    if (key ~ /^cabinet\.[0-9]+$/) {
        id = key
        sub(/^cabinet\./, "", id)
        device[id] = value
    } else if (key ~ /^cabinet\.[0-9]+\.address$/) {
        id = key
        sub(/^cabinet\./, "", id)
        sub(/\.address$/, "", id)
        address[id] = value
    } else if (key ~ /^cabinet\.[0-9]+\.channel$/) {
        id = key
        sub(/^cabinet\./, "", id)
        sub(/\.channel$/, "", id)
        channel[id] = value
    }
}
END {
    for (id in address) {
        selected_channel = channel[id]
        if (selected_channel == "") selected_channel = 1
        printf "%s\t%s\t%s\t%s\n", id, device[id], address[id], selected_channel
    }
}
' "$config_path" |
while IFS="$(printf '\t')" read -r cabinet_number device address channel; do
    if [ -z "$device" ]; then
        echo "RFComm setup: cabinet.$cabinet_number.address has no device mapping" >&2
        exit 1
    fi
    case "$device" in
        /dev/rfcomm[0-9]*) unit=${device#/dev/rfcomm} ;;
        *)
            echo "RFComm setup: $device is not a /dev/rfcommN path" >&2
            exit 1
            ;;
    esac
    case "$unit" in
        ''|*[!0-9]*)
            echo "RFComm setup: invalid RFCOMM unit in $device" >&2
            exit 1
            ;;
    esac
    case "$channel" in
        ''|*[!0-9]*)
            echo "RFComm setup: invalid channel for cabinet $cabinet_number" >&2
            exit 1
            ;;
    esac

    rfcomm release "$unit" >/dev/null 2>&1 || true
    echo "Binding cabinet $cabinet_number: $device -> $address channel $channel"
    rfcomm bind "$unit" "$address" "$channel"
done
