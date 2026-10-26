# CR-100EMUR protocol notes

## Confirmed hardware

The CR-100EMUR sold as `CR100-EM(232)` is a read-only 125 kHz EM/EM4100
reader. Its USB cable contains a Silicon Labs CP2102 bridge:

- USB VID:PID: `10c4:ea60`
- USB product: `CP2102 USB to UART Bridge Controller`
- observed serial: `0001`
- Linux kernel driver: `cp210x`
- Linux interface: a `ttyUSB` device

The vendor's current product material distinguishes this serial model from
the `CR100-EM(KEY)` keyboard-emulation model. The vendor download for board
entry 20 is named `20_CR100-EM-232.zip` and contains the Windows CP210x VCP
driver plus generic C++, VB, and C# serial examples.

## Receive format

Live capture from the connected reader confirmed this 14-byte frame:

```text
02 36 38 30 30 36 39 44 44 32 42 0D 0A 03
```

The structure is:

```text
STX (02)
10 uppercase ASCII hexadecimal UID characters
CR LF (0D 0A)
ETX (03)
```

For the captured card, the ASCII payload was `680069DD2B`, representing the
five-byte EM UID in display order:

```text
68 00 69 DD 2B
```

The vendor's own terminal screenshot shows the same ten-character payload
shape with another card (`3F00238493`). The parser treats control characters
and non-hexadecimal bytes as frame delimiters. It therefore accepts the
confirmed framing while remaining safe when USB serial delivery splits one
frame across many reads—the live capture delivered every byte separately.

The SDK exposes all three lossless forms:

- uppercase hexadecimal string: `3F00238493`
- bytes: `3f 00 23 84 93`
- unsigned 40-bit value: `0x3f00238493`

Do not assume that a third-party access-control application's "decimal card
number" is the full 40-bit value. Such applications often select, reverse,
or pad only part of an EM UID. Use the hexadecimal or byte representation as
the canonical identity and apply an application's conversion convention
explicitly.

## Serial settings

The connected CR-100EMUR was live-validated at `9600 8-N-1`, raw mode, and no
flow control. This is the SDK default. The baud remains an SDK/CLI option for
possible hardware revisions. If a different revision does not produce a
valid UID at 9600, try the other common fixed rates:

```sh
cr100-read --baud 19200 --count 1
cr100-read --baud 38400 --count 1
```

No bytes are sent to the device. It is a read-only streaming reader.

To capture the exact unparsed bytes from one scan:

```sh
cr100-dump --baud 9600
```

The tool prints offsets, hexadecimal bytes, and printable ASCII. It keeps
reading for 100 ms after the last received byte, so a frame split across
multiple USB/serial reads is shown in full. The connected reader was observed
delivering all 14 bytes as individual reads, which also validates the SDK's
incremental parser.

## Sources

- Vendor product listing:
  <https://nowwin.co.kr/product/rf-rfid%EB%A6%AC%EB%8D%94%EA%B8%B0-usb-mini-em-125khz-cr-100/213/>
- Vendor support entry 20:
  <http://www.s-rfid.com/?doc=list_read.php&id=board11&number=29>
- Silicon Labs CP210x VCP documentation:
  <https://www.silabs.com/developer-tools/usb-to-uart-bridge-vcp-drivers>
